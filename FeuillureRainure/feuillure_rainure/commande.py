"""Le bouton « Feuillure / rainure » et son dialogue, en création comme en réédition (double-clic dans
la timeline).

Tout l'état (définition, contrôle, handlers) vit dans des variables de module : Fusion libère les
handlers qu'aucun objet ne référence, et le bouton deviendrait muet sans message (constat MobPrez).

Ordre des gestes (décidé le 2026-11-02) : l'armature, puis les cibles, puis le jeu et la profondeur. Le
résumé dit, pour chaque cible, ce qui sera fait ; l'aperçu montre l'usinage en bleu et l'allongement de
l'armature en orange. L'aperçu se dessine dans `executePreview` seulement :
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
    armature = entrees.addSelectionInput("armature", t("commande.armature"), t("commande.armature_invite"))
    armature.addSelectionFilter("SolidBodies")
    armature.addSelectionFilter("Occurrences")
    armature.setSelectionLimits(0, 1)
    armature.tooltip = t("commande.armature_infobulle")
    cibles = entrees.addSelectionInput("cibles", t("commande.cibles"), t("commande.cibles_invite"))
    cibles.addSelectionFilter("SolidBodies")
    cibles.addSelectionFilter("Occurrences")
    cibles.setSelectionLimits(0, 0)
    cibles.tooltip = t("commande.cibles_infobulle")
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
        corps = _corps_de(entite)
        if corps is None:
            occurrence = adsk.fusion.Occurrence.cast(entite)
            if occurrence is not None and len(_solides(occurrence)) > 1:
                messages.append(t("erreur.plusieurs_corps", nom=occurrence.component.name))
            continue
        if not any(meme_piece(corps, p.corps) for p in pieces):
            pieces.append(fonction.Piece(corps, nom_piece(corps)))
    return pieces, messages


def _analyser(entrees) -> fonction.Plan | None:
    """Refait le plan après chaque changement, puis le résumé. Rend le plan s'il est bon pour OK."""
    _dialogue["plan"] = None
    _dialogue["apercu"] = []
    r = _lire(entrees)
    armatures, messages = _pieces(entrees, "armature")
    cibles, autres = _pieces(entrees, "cibles")
    messages += autres
    if not armatures:
        _afficher(entrees, "\n".join(messages + [t("commande.invite")]))
        return None
    armature = armatures[0]
    if not cibles:
        _afficher(entrees, "\n".join(messages + [t("commande.invite_cibles")]))
        return None
    boite_armature = boite_monde(armature.corps)
    analyses: list[Analyse] = []
    for p in cibles:
        if meme_piece(p.corps, armature.corps):
            analyses.append(Analyse(probleme="erreur.cible_est_l_armature"))
            continue
        boite = boite_monde(p.corps)
        analyses.append(analyser(boite_armature, boite, r.jeu, r.profondeur))
        _dialogue["apercu"].append((boite, analyses[-1]))
    plan = fonction.Plan(armature, cibles, analyses, r)
    texte = resume([(p.nom, a) for p, a in zip(cibles, analyses)])
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


def _solides(occurrence) -> list:
    """Corps solides d'un composant choisi : les visibles s'il y en a, sinon tous (panneau caché)."""
    tous = [occurrence.bRepBodies.item(j) for j in range(occurrence.bRepBodies.count)]
    solides = [b for b in tous if b.isSolid]
    visibles = [b for b in solides if b.isVisible]
    return visibles or solides


def _corps_de(entite):
    """Le corps d'une entité choisie : elle-même, ou le corps solide unique d'un composant ; sinon None."""
    corps = adsk.fusion.BRepBody.cast(entite)
    if corps is not None:
        return corps
    occurrence = adsk.fusion.Occurrence.cast(entite)
    if occurrence is None:
        return None
    solides = _solides(occurrence)
    return solides[0] if len(solides) == 1 else None


def _nettoyer_cibles(entrees) -> bool:
    """« Cibles » sans l'armature ni doublon : Fusion peut y verser la sélection courante (changement de
    ligne active, activation de plus). L'API ne retire pas une sélection seule : tout est vidé, les bonnes
    remises (méthode de Cabineo, `_retirer`). Rend vrai si la ligne a été refaite."""
    ligne = adsk.core.SelectionCommandInput.cast(entrees.itemById("cibles"))
    armature = adsk.core.SelectionCommandInput.cast(entrees.itemById("armature"))
    corps_armature = _corps_de(armature.selection(0).entity) if armature.selectionCount else None
    entites = [ligne.selection(i).entity for i in range(ligne.selectionCount)]
    gardees, vus = [], []
    for e in entites:
        corps = _corps_de(e)
        if corps is not None:
            if corps_armature is not None and meme_piece(corps, corps_armature):
                continue
            if any(meme_piece(corps, v) for v in vus):
                continue
            vus.append(corps)
        gardees.append(e)
    if len(gardees) == len(entites):
        return False
    _dialogue["occupe"] = True
    try:
        ligne.clearSelection()
        for e in gardees:
            ligne.addSelection(e)
    finally:
        _dialogue["occupe"] = False
    journal().info("cibles : %d sélection(s) en trop retirée(s)", len(entites) - len(gardees))
    return True


def _focaliser_cibles(entrees) -> None:
    armature = adsk.core.SelectionCommandInput.cast(entrees.itemById("armature"))
    if armature.selectionCount:
        adsk.core.SelectionCommandInput.cast(entrees.itemById("cibles")).hasFocus = True


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
    _dialogue["graphiques"] = Apercu()


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
            _focaliser_cibles(entrees)
        except Exception:
            journal().error("ouverture du dialogue :\n%s", traceback.format_exc())


class _EditionCreee(adsk.core.CommandCreatedEventHandler):
    """Double-clic sur une ligne Feuillure / rainure : même dialogue, prérempli."""

    def notify(self, args):
        try:
            commande = adsk.core.CommandCreatedEventArgs.cast(args).command
            selection = ui().activeSelections
            entite = selection.item(0).entity if selection.count else None
            editee = fonction.fonction_editee(entite) if entite is not None else None
            if editee is None:
                ancienne = adsk.fusion.CustomFeature.cast(entite) if entite is not None else None
                if (
                    ancienne is not None
                    and ancienne.definition is not None
                    and ancienne.definition.id == fonction.DEFINITION_ID
                ):
                    raise ErreurFeuillure(t("commande.ancienne_version"))
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
    lues sur ses dépendances.

    Une seule fois : Fusion peut rappeler `activate` pendant la commande (essai du 2026-11-02 : en
    réédition, « Cibles » passait de 2 à 5 et, après Échap, l'armature restait sélectionnée). Un second
    passage remettait les pièces une deuxième fois (l'armature, de trop dans sa ligne d'une seule pièce,
    tombait dans « Cibles ») et notait comme position d'origine du marqueur la timeline déjà reculée."""

    def notify(self, args):
        commande = adsk.core.CommandEventArgs.cast(args).command
        entrees = commande.commandInputs
        try:
            edition = _dialogue["edition"]
            if "marqueur" in edition:
                journal().info("réédition : activation de plus, ignorée")
                if edition.get("pret"):
                    _nettoyer_cibles(entrees)
                    _analyser(entrees)
                return
            edition["marqueur"] = Marqueur(design_actif().timeline)
            fonction.reculer_avant(edition["fonction"])
            # Le recul reste hors de la transaction de l'aperçu, annulée à chaque changement.
            commande.beginStep()
            armature, cibles, _ = fonction.pieces_de(edition["fonction"])
            _dialogue["occupe"] = True
            try:
                ligne_armature = adsk.core.SelectionCommandInput.cast(entrees.itemById("armature"))
                ligne_cibles = adsk.core.SelectionCommandInput.cast(entrees.itemById("cibles"))
                ligne_armature.clearSelection()
                ligne_cibles.clearSelection()
                ligne_armature.addSelection(en_contexte(armature))
                for corps in cibles:
                    ligne_cibles.addSelection(en_contexte(corps))
            finally:
                _dialogue["occupe"] = False
            edition["pret"] = True
            _nettoyer_cibles(entrees)
            _analyser(entrees)
        except ErreurFeuillure as e:
            _afficher(entrees, str(e))
        except Exception:
            journal().error("réédition :\n%s", traceback.format_exc())
            _afficher(entrees, t("erreur.inattendue"))


class _Changement(adsk.core.InputChangedEventHandler):
    def notify(self, args):
        a = adsk.core.InputChangedEventArgs.cast(args)
        entrees = _entrees()
        if _dialogue.get("occupe"):
            return  # sélection refaite par le plugin lui-même : traitée à la fin
        try:
            edition = _dialogue.get("edition")
            if edition is not None and not edition.get("pret"):
                return  # activation pas encore faite : les pièces ne sont pas relues
            _nettoyer_cibles(entrees)
            _analyser(entrees)
            if a.input.id == "armature":
                _focaliser_cibles(entrees)
        except ErreurFeuillure as e:
            _afficher(entrees, str(e))
        except Exception:
            journal().error("changement dans le dialogue :\n%s", traceback.format_exc())
            _afficher(entrees, t("erreur.inattendue"))


class _Preselection(adsk.core.SelectionEventHandler):
    """Dans « Cibles », l'armature ne s'allume pas au survol."""

    def notify(self, args):
        a = adsk.core.SelectionEventArgs.cast(args)
        try:
            entree = a.activeInput
            if entree is None or entree.id != "cibles":
                return
            armatures, _ = _pieces(_entrees(), "armature")
            corps = adsk.fusion.BRepBody.cast(a.selection.entity)
            if armatures and corps is not None and meme_piece(corps, armatures[0].corps):
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
            graphiques: Apercu = _dialogue["graphiques"]
            graphiques.effacer()
            paires = _dialogue.get("apercu") or []
            if paires:
                graphiques.montrer(design_actif().rootComponent, paires)
        except Exception:
            journal().error("aperçu :\n%s", traceback.format_exc())


def _derniere_ligne(trace: str) -> str:
    """La cause en une ligne, pour que l'utilisateur puisse la recopier sans ouvrir le journal."""
    lignes = [ligne.strip() for ligne in trace.strip().splitlines() if ligne.strip()]
    return lignes[-1][:200] if lignes else "?"


def _plan_valide(entrees) -> fonction.Plan:
    plan = _analyser(entrees)
    if plan is None:
        raise ErreurFeuillure(t("erreur.rien_a_faire"))
    return plan


class _Execution(adsk.core.CommandEventHandler):
    def notify(self, args):
        a = adsk.core.CommandEventArgs.cast(args)
        try:
            _dialogue["graphiques"].effacer()
            design_parametrique()
            plan = _plan_valide(a.command.commandInputs)
            debut = time.perf_counter()
            f = fonction.creer(plan)
            journal().info("%s créée en %.0f ms", f.name, (time.perf_counter() - debut) * 1000)
            _ecrire(plan.r)
        except ErreurFeuillure as e:
            a.executeFailed, a.executeFailedMessage = True, str(e)
        except Exception:
            trace = traceback.format_exc()
            journal().error("création :\n%s", trace)
            a.executeFailed = True
            a.executeFailedMessage = t("commande.echec", detail=_derniere_ligne(trace))


class _EditionValidee(adsk.core.CommandEventHandler):
    def notify(self, args):
        a = adsk.core.CommandEventArgs.cast(args)
        try:
            _dialogue["graphiques"].effacer()
            edition = _dialogue["edition"]
            plan = _plan_valide(a.command.commandInputs)
            debut = time.perf_counter()
            f = fonction.mettre_a_jour(edition["fonction"], plan)
            _vider_selections()
            edition["marqueur"].rendre()
            edition["rendu"] = True
            journal().info("réédition de %s en %.0f ms", f.name, (time.perf_counter() - debut) * 1000)
            _ecrire(plan.r)
        except ErreurFeuillure as e:
            a.executeFailed, a.executeFailedMessage = True, str(e)
        except Exception:
            trace = traceback.format_exc()
            journal().error("réédition :\n%s", trace)
            a.executeFailed = True
            a.executeFailedMessage = t("commande.echec_reedition", detail=_derniere_ligne(trace))


def _vider_selections() -> None:
    commande = _dialogue.get("commande")
    for ident in ("armature", "cibles"):
        try:
            ligne = adsk.core.SelectionCommandInput.cast(commande.commandInputs.itemById(ident)) if commande else None
            if ligne is not None:
                ligne.clearSelection()
        except Exception:
            pass  # dialogue déjà défait : la sélection générale est vidée juste après
    try:
        ui().activeSelections.clear()
    except Exception:
        journal().warning("sélection non vidée :\n%s", traceback.format_exc())


class _Fermeture(adsk.core.CommandEventHandler):
    """Annulation ou échec d'une réédition : Fusion abandonne la transaction de la commande, mais pas
    forcément le recul fait avant `beginStep` ; on rend donc le marqueur."""

    def notify(self, args):
        try:
            graphiques = _dialogue.get("graphiques")
            if graphiques is not None:
                graphiques.effacer()
            # Sélections vidées avant de rendre le marqueur : sinon l'armature, lue timeline reculée, reste
            # en surbrillance une fois la commande fermée (essai du 2026-11-02, même cachée).
            _vider_selections()
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
