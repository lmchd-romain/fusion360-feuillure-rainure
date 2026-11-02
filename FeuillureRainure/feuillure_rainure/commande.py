"""Le bouton « Feuillure / rainure » et son dialogue, en création comme en réédition (double-clic dans
la timeline).

Tout l'état (définition, contrôle, handlers) vit dans des variables de module : Fusion libère les
handlers qu'aucun objet ne référence, et le bouton deviendrait muet sans message (constat MobPrez).

Ordre des gestes, comme une combinaison native : la cible, puis les armatures, puis le jeu et la
profondeur. Le résumé dit, pour chaque armature, ce qui sera fait ; l'aperçu montre l'usinage en
bleu et l'allongement des armatures en orange. L'aperçu se dessine dans `executePreview` seulement :
Fusion efface, avant chaque aperçu, ce qui a été dessiné ailleurs.
"""

from __future__ import annotations

import time
import traceback
from pathlib import Path

import adsk.core
import adsk.fusion

from . import fonction
from .calcul import Analyse, analyser
from .erreurs import ErreurFeuillure
from .fusion_api import (
    MM_PAR_CM,
    Marqueur,
    boite_monde,
    design_actif,
    design_parametrique,
    en_contexte,
    meme_piece,
    nom_piece,
    signaler_ouverture_ratee,
    ui,
)
from .journal import journal
from .langues import t
from .outils import Apercu
from .reglages import Reglages, ecrire_derniers, expression_mm, lire_derniers, resume

ID_COMMANDE = "feuillureRainureCmd"
ID_PANNEAU = "SolidModifyPanel"  # SOLIDE → Modifier, à côté de « Combiner »
DERNIERS = Path(__file__).resolve().parents[1] / "derniers_reglages.json"

_definition = None
_controle = None
_handlers: list = []  # vivent autant que l'add-in
_handlers_dialogue: list = []  # vivent autant que le dialogue ouvert
_dialogue: dict = {}  # dialogue ouvert : plan, aperçu, édition


# ------------------------------------------------------------------ dialogue


def _remplir(entrees, r: Reglages) -> None:
    cible = entrees.addSelectionInput("cible", t("commande.cible"), t("commande.cible_invite"))
    cible.addSelectionFilter("SolidBodies")
    cible.addSelectionFilter("Occurrences")
    cible.setSelectionLimits(0, 1)
    cible.tooltip = t("commande.cible_infobulle")
    armatures = entrees.addSelectionInput("armatures", t("commande.armatures"), t("commande.armatures_invite"))
    armatures.addSelectionFilter("SolidBodies")
    armatures.addSelectionFilter("Occurrences")
    armatures.setSelectionLimits(0, 0)
    armatures.tooltip = t("commande.armatures_infobulle")
    jeu = entrees.addValueInput(
        "jeu", t("commande.jeu"), "mm", adsk.core.ValueInput.createByString(expression_mm(r.expression_jeu, r.jeu))
    )
    jeu.tooltip = t("commande.jeu_infobulle")
    profondeur = entrees.addValueInput(
        "profondeur",
        t("commande.profondeur"),
        "mm",
        adsk.core.ValueInput.createByString(expression_mm(r.expression_profondeur, r.profondeur)),
    )
    profondeur.tooltip = t("commande.profondeur_infobulle")
    entrees.addTextBoxCommandInput("info", "", t("commande.invite"), 5, True)


def _entrees():
    return _dialogue["commande"].commandInputs


def _valeur(entrees, ident: str) -> tuple[float, str, bool]:
    """(valeur en mm, expression saisie, expression valide)."""
    champ = adsk.core.ValueCommandInput.cast(entrees.itemById(ident))
    return champ.value * MM_PAR_CM, champ.expression, champ.isValidExpression


def _lire(entrees) -> Reglages:
    jeu, expression_jeu, _ = _valeur(entrees, "jeu")
    profondeur, expression_profondeur, _ = _valeur(entrees, "profondeur")
    return Reglages(jeu, profondeur, expression_jeu, expression_profondeur)


def _valeurs_valides(entrees) -> bool:
    return all(_valeur(entrees, ident)[2] for ident in ("jeu", "profondeur"))


def _afficher(entrees, texte: str) -> None:
    boite = adsk.core.TextBoxCommandInput.cast(entrees.itemById("info"))
    if boite is not None:
        boite.formattedText = texte.replace("\n", "<br>")


def _pieces(entrees, ident: str) -> tuple[list[fonction.Piece], list[str]]:
    """Corps choisis (un composant donne son corps solide unique), sans doublon, et les messages de ce
    qui a été écarté."""
    selection = adsk.core.SelectionCommandInput.cast(entrees.itemById(ident))
    pieces: list[fonction.Piece] = []
    messages: list[str] = []
    for i in range(selection.selectionCount):
        entite = selection.selection(i).entity
        corps = adsk.fusion.BRepBody.cast(entite)
        if corps is None:
            occurrence = adsk.fusion.Occurrence.cast(entite)
            if occurrence is None:
                continue
            solides = [
                occurrence.bRepBodies.item(j)
                for j in range(occurrence.bRepBodies.count)
                if occurrence.bRepBodies.item(j).isSolid and occurrence.bRepBodies.item(j).isVisible
            ]
            if len(solides) != 1:
                if solides:
                    messages.append(t("erreur.plusieurs_corps", nom=occurrence.component.name))
                continue
            corps = solides[0]
        if not any(meme_piece(corps, p.corps) for p in pieces):
            pieces.append(fonction.Piece(corps, nom_piece(corps)))
    return pieces, messages


def _analyser(entrees) -> fonction.Plan | None:
    """Refait le plan après chaque changement, puis le résumé. Rend le plan s'il est bon pour OK."""
    _dialogue["plan"] = None
    _dialogue["apercu_analyses"] = []
    r = _lire(entrees)
    cibles, messages = _pieces(entrees, "cible")
    armatures, autres = _pieces(entrees, "armatures")
    messages += autres
    if not cibles:
        _afficher(entrees, "\n".join(messages + [t("commande.invite")]))
        return None
    cible = cibles[0]
    if not armatures:
        _afficher(entrees, "\n".join(messages + [t("commande.invite_armatures")]))
        return None
    boite_cible = boite_monde(cible.corps)
    analyses: list[Analyse] = []
    for p in armatures:
        if meme_piece(p.corps, cible.corps):
            analyses.append(Analyse(probleme="erreur.armature_est_la_cible"))
        else:
            analyses.append(analyser(boite_monde(p.corps), boite_cible, r.jeu, r.profondeur))
    plan = fonction.Plan(cible, armatures, analyses, r)
    _dialogue["apercu_analyses"] = analyses
    _dialogue["apercu_cible"] = boite_cible
    texte = resume([(p.nom, a) for p, a in zip(armatures, analyses)])
    bon = all(a.utilisable for a in analyses)
    if bon:
        try:
            fonction.verifier(plan)
        except ErreurFeuillure as e:
            messages.append(str(e))
            bon = False
    _afficher(entrees, "\n".join([texte] + messages))
    if bon and not messages:
        _dialogue["plan"] = plan
        return plan
    return None


def _focaliser_armatures(entrees) -> None:
    cible = adsk.core.SelectionCommandInput.cast(entrees.itemById("cible"))
    if cible.selectionCount:
        adsk.core.SelectionCommandInput.cast(entrees.itemById("armatures")).hasFocus = True


def _connecter(commande, execution, activation) -> None:
    paires = [
        (commande.inputChanged, _Changement()),
        (commande.validateInputs, _Validation()),
        (commande.executePreview, _Apercu()),
        (commande.execute, execution),
        (commande.preSelect, _Preselection()),
        (commande.destroy, _Fermeture()),
        (commande.activate, activation),
    ]
    for evenement, gestionnaire in paires:
        evenement.add(gestionnaire)
        _handlers_dialogue.append(gestionnaire)


def _nouveau_dialogue(commande) -> None:
    _dialogue.clear()
    _dialogue["commande"] = commande
    _dialogue["apercu"] = Apercu()


class _Creation(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            commande = adsk.core.CommandCreatedEventArgs.cast(args).command
            _nouveau_dialogue(commande)
            _remplir(commande.commandInputs, lire_derniers(DERNIERS))
            _connecter(commande, _Execution(), _CreationActivee())
        except Exception:
            signaler_ouverture_ratee("création du dialogue")


class _CreationActivee(adsk.core.CommandEventHandler):
    """Pièces choisies avant de lancer la commande : Fusion les met dans la première sélection sans
    toujours signaler de changement ; on analyse donc dès l'ouverture."""

    def notify(self, args):
        try:
            entrees = _entrees()
            _analyser(entrees)
            _focaliser_armatures(entrees)
        except Exception:
            journal().error("ouverture du dialogue :\n%s", traceback.format_exc())


class _EditionCreee(adsk.core.CommandCreatedEventHandler):
    """Double-clic sur une ligne Feuillure / rainure : même dialogue, prérempli."""

    def notify(self, args):
        try:
            commande = adsk.core.CommandCreatedEventArgs.cast(args).command
            selection = ui().activeSelections
            editee = fonction.fonction_editee(selection.item(0).entity) if selection.count else None
            if editee is None:
                raise ErreurFeuillure(t("commande.double_clic"))
            _nouveau_dialogue(commande)
            _dialogue["edition"] = {"fonction": editee}
            _remplir(commande.commandInputs, fonction.reglages(editee))
            _connecter(commande, _EditionValidee(), _EditionActivee())
        except ErreurFeuillure as e:
            ui().messageBox(str(e))
        except Exception:
            signaler_ouverture_ratee("ouverture de la réédition")


class _EditionActivee(adsk.core.CommandEventHandler):
    """Recule la timeline juste avant la fonction (méthode validée par Cabineo), puis remet les pièces
    lues sur ses dépendances."""

    def notify(self, args):
        commande = adsk.core.CommandEventArgs.cast(args).command
        entrees = commande.commandInputs
        try:
            edition = _dialogue["edition"]
            edition["marqueur"] = Marqueur(design_actif().timeline)
            fonction.reculer_avant(edition["fonction"])
            # Le recul reste hors de la transaction de l'aperçu, annulée à chaque changement.
            commande.beginStep()
            cible, armatures, _ = fonction.pieces_de(edition["fonction"])
            adsk.core.SelectionCommandInput.cast(entrees.itemById("cible")).addSelection(en_contexte(cible))
            selection = adsk.core.SelectionCommandInput.cast(entrees.itemById("armatures"))
            for corps in armatures:
                selection.addSelection(en_contexte(corps))
            edition["pret"] = True
            _analyser(entrees)
            _focaliser_armatures(entrees)
        except ErreurFeuillure as e:
            _afficher(entrees, str(e))
        except Exception:
            journal().error("réédition :\n%s", traceback.format_exc())
            _afficher(entrees, t("erreur.inattendue"))


class _Changement(adsk.core.InputChangedEventHandler):
    def notify(self, args):
        a = adsk.core.InputChangedEventArgs.cast(args)
        entrees = _entrees()
        try:
            edition = _dialogue.get("edition")
            if edition is not None and not edition.get("pret"):
                return  # activation pas encore faite : les pièces ne sont pas relues
            _analyser(entrees)
            if a.input.id == "cible":
                _focaliser_armatures(entrees)
        except ErreurFeuillure as e:
            _afficher(entrees, str(e))
        except Exception:
            journal().error("changement dans le dialogue :\n%s", traceback.format_exc())
            _afficher(entrees, t("erreur.inattendue"))


class _Preselection(adsk.core.SelectionEventHandler):
    """Dans « Armatures », la cible ne s'allume pas au survol."""

    def notify(self, args):
        a = adsk.core.SelectionEventArgs.cast(args)
        try:
            entree = a.activeInput
            if entree is None or entree.id != "armatures":
                return
            cibles, _ = _pieces(_entrees(), "cible")
            corps = adsk.fusion.BRepBody.cast(a.selection.entity)
            if cibles and corps is not None and meme_piece(corps, cibles[0].corps):
                a.isSelectable = False
        except Exception:
            journal().error("présélection :\n%s", traceback.format_exc())


class _Validation(adsk.core.ValidateInputsEventHandler):
    def notify(self, args):
        a = adsk.core.ValidateInputsEventArgs.cast(args)
        try:
            a.areInputsValid = _dialogue.get("plan") is not None and _valeurs_valides(_entrees())
        except Exception:
            a.areInputsValid = False


class _Apercu(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            apercu: Apercu = _dialogue["apercu"]
            apercu.effacer()
            analyses = _dialogue.get("apercu_analyses") or []
            if analyses:
                apercu.montrer(design_actif().rootComponent, _dialogue["apercu_cible"], analyses)
        except Exception:
            journal().error("aperçu :\n%s", traceback.format_exc())


def _plan_valide(entrees) -> fonction.Plan:
    plan = _analyser(entrees)
    if plan is None:
        raise ErreurFeuillure(t("erreur.rien_a_faire"))
    return plan


class _Execution(adsk.core.CommandEventHandler):
    def notify(self, args):
        a = adsk.core.CommandEventArgs.cast(args)
        try:
            _dialogue["apercu"].effacer()
            design_parametrique()
            plan = _plan_valide(a.command.commandInputs)
            debut = time.perf_counter()
            f = fonction.creer(plan)
            journal().info("%s créée en %.0f ms", f.name, (time.perf_counter() - debut) * 1000)
            _ecrire(plan.r)
        except ErreurFeuillure as e:
            a.executeFailed, a.executeFailedMessage = True, str(e)
        except Exception:
            journal().error("création :\n%s", traceback.format_exc())
            a.executeFailed = True
            a.executeFailedMessage = t("commande.echec")


class _EditionValidee(adsk.core.CommandEventHandler):
    def notify(self, args):
        a = adsk.core.CommandEventArgs.cast(args)
        try:
            _dialogue["apercu"].effacer()
            edition = _dialogue["edition"]
            plan = _plan_valide(a.command.commandInputs)
            debut = time.perf_counter()
            f = fonction.mettre_a_jour(edition["fonction"], plan)
            edition["marqueur"].rendre()
            edition["rendu"] = True
            journal().info("réédition de %s en %.0f ms", f.name, (time.perf_counter() - debut) * 1000)
            _ecrire(plan.r)
        except ErreurFeuillure as e:
            a.executeFailed, a.executeFailedMessage = True, str(e)
        except Exception:
            journal().error("réédition :\n%s", traceback.format_exc())
            a.executeFailed = True
            a.executeFailedMessage = t("commande.echec_reedition")


class _Fermeture(adsk.core.CommandEventHandler):
    """Annulation ou échec d'une réédition : Fusion abandonne la transaction de la commande, mais pas
    forcément le recul fait avant `beginStep` ; on rend donc le marqueur."""

    def notify(self, args):
        try:
            apercu = _dialogue.get("apercu")
            if apercu is not None:
                apercu.effacer()
            edition = _dialogue.get("edition")
            if edition and "marqueur" in edition and not edition.get("rendu"):
                edition["marqueur"].rendre()
        except Exception:
            journal().warning("fermeture du dialogue :\n%s", traceback.format_exc())
        finally:
            _dialogue.clear()
            _handlers_dialogue.clear()


# ------------------------------------------------------------------ démarrage


def demarrer() -> None:
    global _definition, _controle
    arreter()  # « Exécuter » deux fois sans « Arrêter » : pas de bouton ni de gestionnaire en double
    interface = ui()
    # Un Arrêter / Exécuter rapide peut laisser une définition orpheline : on la retire d'abord.
    ancienne = interface.commandDefinitions.itemById(ID_COMMANDE)
    if ancienne is not None:
        ancienne.deleteMe()
    fonction.enregistrer_definition(_EditionCreee())
    _definition = interface.commandDefinitions.addButtonDefinition(
        ID_COMMANDE, t("commande.nom"), t("commande.description"), fonction.ICONES
    )
    creation = _Creation()
    _definition.commandCreated.add(creation)
    _handlers.append(creation)
    panneau = interface.allToolbarPanels.itemById(ID_PANNEAU)
    if panneau is None:
        # Sans bouton, la définition de la fonction reste : les opérations existantes se recalculent.
        journal().warning("panneau %s introuvable : bouton non ajouté", ID_PANNEAU)
        return
    ancien_controle = panneau.controls.itemById(ID_COMMANDE)
    if ancien_controle is not None:
        ancien_controle.deleteMe()
    _controle = panneau.controls.addCommand(_definition)
    _controle.isPromoted = True


def arreter() -> None:
    """Retire bouton, définition et gestionnaires ; une étape qui échoue n'empêche pas les suivantes."""
    global _definition, _controle
    try:
        if _controle is not None and _controle.isValid:
            _controle.deleteMe()
        if _definition is not None and _definition.isValid:
            _definition.deleteMe()
    finally:
        try:
            fonction.oublier_definition()
        finally:
            _controle = _definition = None
            _handlers.clear()
            _handlers_dialogue.clear()


def _ecrire(r: Reglages) -> None:
    """Un fichier de réglages verrouillé ne doit jamais annuler une opération déjà posée."""
    try:
        ecrire_derniers(DERNIERS, r)
    except OSError:
        journal().warning("derniers réglages non écrits :\n%s", traceback.format_exc())
