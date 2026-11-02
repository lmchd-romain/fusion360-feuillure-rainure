"""Fonction personnalisée « Feuillure / rainure » : création, recalcul, réédition.

Une opération = une armature et une ou plusieurs cibles, sur **une seule ligne de timeline**, avec
l'icône du plugin. Chaque combinaison reste dans le composant de ses corps, avec des corps natifs : la
méthode constatée de Cabineo (base + fonction + combinaison dans un même composant, essais S1–S4). Ce
qui touche d'autres composants est emboîté, comme Flight Case le fait (sondes T7, T12, T17) :

1. base de l'armature, dans son composant : un corps d'allongement par cible en contact (ou, s'il n'y en
   a aucun, un petit cube au cœur de l'armature), puis l'outil de chaque cible du même composant ;
2. la fonction de l'opération, créée juste après cette base ; dépendances : une face de l'armature et de
   chaque cible, encore intactes ;
3. pour chaque cible d'un autre composant, dans ce composant : sa base (l'outil de coupe), sa fonction à
   elle (créée juste après), sa découpe, puis sa fonction étendue de sa base à sa découpe ;
4. les découpes des cibles du composant de l'armature, outils pris dans la base de l'armature ;
5. la jonction des allongements à l'armature, en dernier ;
6. la fonction de l'opération étendue de sa base à la jonction : tout ce qui est entre les deux, fonctions
   des cibles comprises, reste sur sa ligne.

Calcul : chaque fonction refait sa propre base (celle de l'opération : allongements et outils du même
composant ; celle d'une cible : son outil), depuis les pièces telles qu'elles sont juste avant elle.
Rien tant que sa combinaison n'est pas regroupée (création en cours).

Attributs (groupe `feuillureRainure`) : `role` (« armature » : la ligne ; « cible » : une fonction
emboîtée), `operation` (identifiant commun), `reglages` (JSON), `cibles` (opération : JSON par cible) ou
`cible` (fonction emboîtée : JSON de sa cible). Par cible : `mode`, `entree` (direction d'entrée dans le
repère du composant de l'armature, contact seulement), `allongement` et `outil` (rangs dans la base de
l'armature, -1 si aucun). Les opérations de la version 0.1 (sans `role`) ne se recalculent plus.
"""

from __future__ import annotations

import json
import time
import traceback
import uuid
from dataclasses import dataclass
from pathlib import Path

import adsk.core
import adsk.fusion

from .calcul import CONTACT, Analyse, analyser
from .erreurs import ErreurFeuillure
from .fusion_api import (
    boite_monde,
    composant_de,
    design_parametrique,
    direction_locale,
    direction_monde,
    en_contexte,
    exemplaires,
    exiger,
    jeton,
    matrice_monde,
    meme_piece,
    natif,
    nom_piece,
    occurrence_de,
    retrouver,
    verifier_modifiable,
)
from .journal import journal
from .langues import t
from .outils import allongement, outil_de_coupe, remplissage
from .reglages import Reglages, depuis_json, nom_fonction, vers_json

DEFINITION_ID = "feuillureRainure"
ID_EDITION = "feuillureRainureModifierCmd"
GROUPE = "feuillureRainure"
ARMATURE = "armature"  # dépendance : une face de l'armature
CIBLE = "cible"  # dépendance d'une fonction emboîtée ; dans l'opération : « cible_0 », « cible_1 »…
ROLE_ARMATURE, ROLE_CIBLE = "armature", "cible"
ICONES = str(Path(__file__).resolve().parents[1] / "ressources" / "icone")

_definition = None
_handlers: list = []


class _Calcul(adsk.fusion.CustomFeatureEventHandler):
    def notify(self, args):
        a = adsk.fusion.CustomFeatureEventArgs.cast(args)
        try:
            debut = time.perf_counter()
            problemes = recalculer(a.customFeature)
            if problemes:
                a.computeStatus.statusMessages.addWarning("API_COMPUTE_WARNING", "")
            if problemes is not None:
                journal().info(
                    "recalcul de %s : %.0f ms, %d problème(s)",
                    a.customFeature.name,
                    (time.perf_counter() - debut) * 1000,
                    problemes,
                )
        except Exception:
            # Fusion ignore le texte d'une erreur de calcul (« Cannot compute this feature. ») : détail au journal.
            journal().error("recalcul de %s :\n%s", a.customFeature.name, traceback.format_exc())
            a.computeStatus.statusMessages.addError("API_COMPUTE_ERROR", "")


def enregistrer_definition(edition: adsk.core.CommandCreatedEventHandler) -> None:
    """Au démarrage : sans définition enregistrée, Fusion ne recalcule pas les opérations existantes.
    `edition` ouvre le dialogue de réédition (double-clic dans la timeline)."""
    global _definition
    oublier_definition()
    ui = adsk.core.Application.get().userInterface
    ancienne = ui.commandDefinitions.itemById(ID_EDITION)
    if ancienne is not None:
        ancienne.deleteMe()
    # editCommandId n'accepte qu'une commande déjà créée (« 3 : Invalid command Id », essai Cabineo).
    commande = ui.commandDefinitions.addButtonDefinition(ID_EDITION, t("edition.nom"), t("edition.description"), ICONES)
    commande.commandCreated.add(edition)
    # Rappelée avec le même identifiant, create rend la définition déjà enregistrée dans la session.
    _definition = adsk.fusion.CustomFeatureDefinition.create(DEFINITION_ID, t("fonction.nom"), ICONES)
    _definition.editCommandId = ID_EDITION
    calcul = _Calcul()
    _definition.customFeatureCompute.add(calcul)
    _handlers.extend((edition, calcul))


def oublier_definition() -> None:
    """À l'arrêt : la définition survit dans la session, ses gestionnaires doivent partir."""
    try:
        if _definition is not None:
            for h in _handlers:
                if isinstance(h, _Calcul):
                    _definition.customFeatureCompute.remove(h)
        edition = adsk.core.Application.get().userInterface.commandDefinitions.itemById(ID_EDITION)
        if edition is not None:
            edition.deleteMe()
    finally:
        _handlers.clear()


# ---------------------------------------------------------------- création


@dataclass
class Piece:
    """Un panneau choisi : son corps tel que la sélection le donne (vu depuis la racine)."""

    corps: adsk.fusion.BRepBody
    nom: str


@dataclass
class Plan:
    """Ce que le dialogue a préparé : l'armature, les cibles et l'analyse de chacune."""

    armature: Piece
    cibles: list[Piece]
    analyses: list[Analyse]
    r: Reglages


def reference(corps) -> adsk.fusion.BRepFace:
    """La face qui représente une pièce dans les dépendances : sa plus grande. Une dépendance au corps
    entier engloberait le résultat de la fonction elle-même : Fusion la laisserait reculée, sans
    calcul (Perfora, `body_reference` ; Dogbone 0.2.2)."""
    faces = [corps.faces.item(i) for i in range(corps.faces.count)]
    if not faces:
        raise ErreurFeuillure(t("erreur.piece_disparue"))
    return max(faces, key=lambda f: f.area)


def _dependre(ajouter, ident: str, entite) -> None:
    """L'entité vue depuis la racine (forme validée par l'essai Cabineo), sinon native.
    `ajouter` rend faux (CustomFeatureInput) ou lève (CustomFeatureDependencies) en cas d'échec."""
    for forme in (en_contexte, natif):
        try:
            if ajouter(ident, forme(entite)):
                return
        except Exception:
            journal().info("dépendance « %s » refusée sous une forme :\n%s", ident, traceback.format_exc())
    exiger(False, "etape.dependance")


def meme_composant(a, b) -> bool:
    return composant_de(a) == composant_de(b)


def _infos(plan: Plan) -> tuple[list[dict], int]:
    """Pour chaque cible : mode, direction d'entrée (repère du composant de l'armature), rangs de son
    allongement et de son outil dans la base de l'armature. Rend aussi le rang du petit cube de
    remplissage (-1 s'il y a au moins un allongement). Rangs : allongements d'abord, puis le remplissage,
    puis les outils des cibles du composant de l'armature (consommés en premier, du dernier rang au
    premier, sans décaler les autres)."""
    infos, rang = [], 0
    for a in plan.analyses:
        info = {"mode": a.mode, "allongement": -1, "outil": -1}
        if a.mode == CONTACT and a.entree is not None:
            info["entree"] = list(direction_locale(plan.armature.corps, a.entree))
            info["allongement"] = rang
            rang += 1
        infos.append(info)
    remplissage_ = -1
    if rang == 0:
        remplissage_ = 0
        rang = 1
    for info, piece in zip(infos, plan.cibles):
        if meme_composant(piece.corps, plan.armature.corps):
            info["outil"] = rang
            rang += 1
    return infos, remplissage_


def verifier(plan: Plan) -> None:
    """Refus qui protègent le meuble : composant lié, cible partagée, armature allongée partagée."""
    if any(a.mode == CONTACT for a in plan.analyses):
        verifier_modifiable(plan.armature.corps)
        n = exemplaires(plan.armature.corps)
        if n > 1:
            raise ErreurFeuillure(t("erreur.armature_partagee", nom=nom_piece(plan.armature.corps), n=n))
    for piece in plan.cibles:
        verifier_modifiable(piece.corps)
        n = exemplaires(piece.corps)
        if n > 1:
            raise ErreurFeuillure(t("erreur.cible_partagee", nom=nom_piece(piece.corps), n=n))


def _reperer(entite) -> tuple:
    """De quoi retrouver une pièce si une opération l'invalide : jeton du natif, occurrence qui la place."""
    return jeton(natif(entite)), occurrence_de(entite)


def _relire(design, entite, repere: tuple):
    """L'entité telle qu'elle est maintenant, vue depuis la racine comme la sélection."""
    try:
        if entite.isValid:
            return entite
    except Exception:
        pass
    trouve = retrouver(design, repere[0])
    if trouve is None:
        raise ErreurFeuillure(t("erreur.piece_disparue"))
    occurrence = repere[1]
    try:
        if occurrence is not None and occurrence.isValid:
            return trouve.createForAssemblyContext(occurrence)
    except Exception:
        pass
    return en_contexte(trouve)


def _base(composant, corps: list) -> adsk.fusion.BaseFeature:
    base = composant.features.baseFeatures.add()
    exiger(base.startEdit(), "etape.edition_base")
    try:
        for c in corps:
            exiger(composant.bRepBodies.add(c, base), "etape.ajout_outil")
    finally:
        exiger(base.finishEdit(), "etape.fin_edition_base")
    return base


def _fonction(composant, base, dependances: list[tuple[str, object]], attributs: dict, nom: str):
    entree = composant.features.customFeatures.createInput(_definition)
    for ident, entite in dependances:
        _dependre(entree.addDependency, ident, reference(entite))
    exiger(entree.setStartAndEndFeatures(base, base), "etape.regroupement_base")
    fonction = composant.features.customFeatures.add(entree)
    exiger(fonction, "etape.creation_fonction")
    fonction.name = nom
    for cle, valeur in attributs.items():
        fonction.attributes.add(GROUPE, cle, valeur)
    return fonction


def _combiner(composant, cible, outils: list, operation, etape: str):
    """Combinaison dans le composant de la cible, corps natifs (méthode Cabineo)."""
    collection = adsk.core.ObjectCollection.create()
    for o in outils:
        collection.add(natif(o))
    entree = composant.features.combineFeatures.createInput(natif(cible), collection)
    entree.operation = operation
    entree.isKeepToolBodies = False
    combinaison = composant.features.combineFeatures.add(entree)
    exiger(combinaison, etape)
    return combinaison


def _corps_de_base(base, instantane: list, rang: int):
    """Corps de la base de ce rang : l'instantané lu juste après la base tant qu'il est valide, sinon relu
    (hors édition, `BaseFeature.bodies` ne rend que les corps encore là)."""
    if rang < len(instantane):
        try:
            if instantane[rang].isValid:
                return instantane[rang]
        except Exception:
            pass
    return base.bodies.item(rang)


def regrouper(fonction: adsk.fusion.CustomFeature, debut, fin) -> None:
    """Étend la fonction de `debut` à `fin` (de son composant) ; Fusion exige la timeline reculée."""
    exiger(fonction.timelineObject.rollTo(True), "etape.recul_timeline")
    try:
        exiger(fonction.setStartAndEndFeatures(debut, fin), "etape.regroupement")
    finally:
        exiger(fonction.timelineObject.rollTo(False), "etape.retour_timeline")


def _corps_armature(plan: Plan, infos: list[dict], remplissage_: int, boites: list, armature_boite) -> list:
    """Les corps de la base de l'armature, dans l'ordre des rangs."""
    monde = matrice_monde(plan.armature.corps)
    corps: dict[int, object] = {}
    for a, info, boite in zip(plan.analyses, infos, boites):
        if info["allongement"] >= 0:
            corps[info["allongement"]] = allongement(a, boite, monde)
        if info["outil"] >= 0:
            corps[info["outil"]] = outil_de_coupe(a, boite, monde)
    if remplissage_ >= 0:
        corps[remplissage_] = remplissage(armature_boite.centre, monde)
    return [corps[k] for k in sorted(corps)]


def creer(plan: Plan) -> adsk.fusion.CustomFeature:
    """L'opération entière, au marqueur de timeline. Rend la fonction de la ligne."""
    if not plan.cibles or not all(a.utilisable for a in plan.analyses):
        raise ErreurFeuillure(t("erreur.rien_a_faire"))
    verifier(plan)
    debut = time.perf_counter()
    design = design_parametrique()
    timeline = design.timeline
    au_bout = timeline.markerPosition == timeline.count
    operation = uuid.uuid4().hex
    reglages_json = vers_json(plan.r)
    armature = plan.armature.corps
    composant = composant_de(armature)
    boites = [boite_monde(p.corps) for p in plan.cibles]
    infos, remplissage_ = _infos(plan)
    reperes = [_reperer(armature)] + [_reperer(p.corps) for p in plan.cibles]

    base = _base(composant, _corps_armature(plan, infos, remplissage_, boites, boite_monde(armature)))
    instantane = [base.bodies.item(i) for i in range(base.bodies.count)]
    journal().info("base de l'armature : %d corps", len(instantane))
    dependances = [(ARMATURE, armature)] + [(f"{CIBLE}_{i}", p.corps) for i, p in enumerate(plan.cibles)]
    attributs = {
        "role": ROLE_ARMATURE,
        "operation": operation,
        "reglages": reglages_json,
        "cibles": json.dumps(infos),
        "remplissage": str(remplissage_),
    }
    fonction = _fonction(
        composant, base, dependances, attributs, nom_fonction(plan.analyses, plan.r, plan.armature.nom)
    )

    for i, (piece, a, info, boite) in enumerate(zip(plan.cibles, plan.analyses, infos, boites)):
        if info["outil"] >= 0:
            continue  # cible du composant de l'armature : découpée plus bas, outil dans la base de l'armature
        armature_vue = _relire(design, armature, reperes[0])
        cible_vue = _relire(design, piece.corps, reperes[i + 1])
        composant_cible = composant_de(cible_vue)
        base_cible = _base(composant_cible, [outil_de_coupe(a, boite, matrice_monde(cible_vue))])
        emboitee = _fonction(
            composant_cible,
            base_cible,
            [(ARMATURE, armature_vue), (CIBLE, cible_vue)],
            {"role": ROLE_CIBLE, "operation": operation, "reglages": reglages_json, "cible": json.dumps(info)},
            t("timeline.interne", nom=piece.nom),
        )
        coupe = _combiner(
            composant_cible,
            _relire(design, cible_vue, reperes[i + 1]),
            [base_cible.bodies.item(0)],
            adsk.fusion.FeatureOperations.CutFeatureOperation,
            "etape.decoupe",
        )
        regrouper(emboitee, base_cible, coupe)
        journal().info("cible %s usinée (%s)", piece.nom, a.mode)

    propres = sorted(((info["outil"], i) for i, info in enumerate(infos) if info["outil"] >= 0), reverse=True)
    for rang, i in propres:
        _combiner(
            composant,
            _relire(design, plan.cibles[i].corps, reperes[i + 1]),
            [_corps_de_base(base, instantane, rang)],
            adsk.fusion.FeatureOperations.CutFeatureOperation,
            "etape.decoupe",
        )
    rangs = [info["allongement"] for info in infos if info["allongement"] >= 0] or [remplissage_]
    jonction = _combiner(
        composant,
        _relire(design, armature, reperes[0]),
        [_corps_de_base(base, instantane, k) for k in rangs],
        adsk.fusion.FeatureOperations.JoinFeatureOperation,
        "etape.allongement",
    )
    regrouper(fonction, base, jonction)
    if au_bout and timeline.markerPosition < timeline.count:
        exiger(timeline.moveToEnd(), "etape.fin_timeline")
    journal().info(
        "%s posée : %d cible(s) en %.0f ms", fonction.name, len(plan.cibles), (time.perf_counter() - debut) * 1000
    )
    return fonction


# ---------------------------------------------------------------- recalcul


def _attribut(fonction, cle: str) -> str | None:
    trouve = natif(fonction).attributes.itemByName(GROUPE, cle)
    return trouve.value if trouve is not None else None


def reglages(fonction) -> Reglages:
    texte = _attribut(fonction, "reglages")
    if texte is None:
        raise ErreurFeuillure(t("erreur.reglage_absent", cle="reglages"))
    return depuis_json(texte)


def _json(fonction, cle: str, defaut):
    texte = _attribut(fonction, cle)
    if texte is None:
        raise ErreurFeuillure(t("erreur.reglage_absent", cle=cle))
    try:
        valeur = json.loads(texte)
    except ValueError as e:
        raise ErreurFeuillure(t("erreur.reglages_illisibles", detail=e)) from e
    return valeur if isinstance(valeur, type(defaut)) else defaut


def corps_de(fonction, ident: str):
    """Le corps d'une pièce, tel qu'il est juste avant la fonction (par sa face de référence)."""
    dependance = natif(fonction).dependencies.itemById(ident)
    entite = dependance.entity if dependance is not None else None
    face = adsk.fusion.BRepFace.cast(entite) if entite is not None else None
    if face is None:
        raise ErreurFeuillure(t("erreur.piece_disparue"))
    return face.body


def pieces_de(fonction) -> tuple:
    """(armature, [cibles], infos) d'une fonction d'opération."""
    infos = [d for d in _json(fonction, "cibles", []) if isinstance(d, dict)]
    cibles = [corps_de(fonction, f"{CIBLE}_{i}") for i in range(len(infos))]
    return corps_de(fonction, ARMATURE), cibles, infos


def analyse_de(armature, cible, info: dict, r: Reglages) -> Analyse:
    """Analyse au recalcul : la cible garde le mode choisi à la création."""
    entree = info.get("entree")
    direction = None
    if isinstance(entree, list) and len(entree) == 3:
        direction = direction_monde(armature, tuple(entree))
    return analyser(boite_monde(armature), boite_monde(cible), r.jeu, r.profondeur, info.get("mode"), direction)


def _a_une_combinaison(fonction) -> bool:
    proprietaire = fonction.parentComponent
    for f in fonction.features:
        try:
            if f.objectType == adsk.fusion.CombineFeature.classType() and f.parentComponent == proprietaire:
                return True
        except Exception:
            continue
    return False


def _base_de(fonction) -> adsk.fusion.BaseFeature:
    """La base du composant de la fonction : `CustomFeature.features` ne suit pas l'ordre de la timeline et
    celle de l'opération contient aussi les bases des cibles (Flight Case, T17)."""
    proprietaire = fonction.parentComponent
    for f in fonction.features:
        try:
            if f.objectType == adsk.fusion.BaseFeature.classType() and f.parentComponent == proprietaire:
                return adsk.fusion.BaseFeature.cast(f)
        except Exception:
            continue
    raise ErreurFeuillure(t("erreur.piece_disparue"))


def _remplacer(fonction, corps: dict) -> None:
    base = _base_de(fonction)
    exiger(base.startEdit(), "etape.edition_base")
    try:
        for rang, c in sorted(corps.items()):
            if rang < base.bodies.count:
                exiger(base.updateBody(base.bodies.item(rang), c), "etape.remplacement_outil")
    finally:
        exiger(base.finishEdit(), "etape.fin_edition_base")


def recalculer(fonction) -> int | None:
    """Calcul demandé par Fusion. Rend le nombre de cibles à problème ; None : rien à faire (création en
    cours, opération de la version 0.1)."""
    fonction = natif(fonction)
    role = _attribut(fonction, "role")
    if role not in (ROLE_ARMATURE, ROLE_CIBLE) or not _a_une_combinaison(fonction):
        return None
    r = reglages(fonction)
    if role == ROLE_CIBLE:
        info = _json(fonction, "cible", {})
        armature, cible = corps_de(fonction, ARMATURE), corps_de(fonction, CIBLE)
        a = analyse_de(armature, cible, info, r)
        _remplacer(fonction, {0: outil_de_coupe(a, boite_monde(cible), matrice_monde(cible))})
        return 0 if a.utilisable else 1
    armature, cibles, infos = pieces_de(fonction)
    monde = matrice_monde(armature)
    corps: dict[int, object] = {}
    problemes = 0
    for cible, info in zip(cibles, infos):
        a = analyse_de(armature, cible, info, r)
        problemes += 0 if a.utilisable else 1
        boite = boite_monde(cible)
        if isinstance(info.get("allongement"), int) and info["allongement"] >= 0:
            corps[info["allongement"]] = allongement(a, boite, monde)
        if isinstance(info.get("outil"), int) and info["outil"] >= 0:
            corps[info["outil"]] = outil_de_coupe(a, boite, monde)
    try:
        rang = int(_attribut(fonction, "remplissage") or -1)
    except ValueError:
        rang = -1
    if rang >= 0:  # le petit cube suit l'armature : déplacée en amont, la jonction ne doit rien ajouter
        corps[rang] = remplissage(boite_monde(armature).centre, monde)
    _remplacer(fonction, corps)
    return problemes


# ---------------------------------------------------------------- réédition


def _fonctions_de_l_operation(design, operation: str) -> list:
    trouvees = []
    for i in range(design.allComponents.count):
        personnalisees = design.allComponents.item(i).features.customFeatures
        for j in range(personnalisees.count):
            f = personnalisees.item(j)
            if f.definition is not None and f.definition.id == DEFINITION_ID and _attribut(f, "operation") == operation:
                trouvees.append(f)
    return trouvees


def fonction_editee(entite) -> adsk.fusion.CustomFeature | None:
    """La fonction de la ligne (celle de l'armature), même si Fusion désigne une fonction emboîtée.
    None : pas une opération de ce plugin, ou une opération de la version 0.1."""
    f = adsk.fusion.CustomFeature.cast(entite)
    if f is None or f.definition is None or f.definition.id != DEFINITION_ID:
        return None
    f = natif(f)
    role = _attribut(f, "role")
    if role == ROLE_ARMATURE:
        return f
    if role != ROLE_CIBLE:
        return None
    for g in _fonctions_de_l_operation(f.parentComponent.parentDesign, _attribut(f, "operation")):
        if _attribut(g, "role") == ROLE_ARMATURE:
            return g
    return None


def reculer_avant(fonction) -> None:
    if not natif(fonction).timelineObject.rollTo(True):
        raise ErreurFeuillure(t("erreur.recul_refuse", fonction=fonction.name))


def meme_structure(fonction, plan: Plan) -> bool:
    """Même armature, mêmes cibles dans le même ordre, mêmes modes : la réédition se fait en place (les
    opérations posées après, sur les rainures, gardent leurs références)."""
    try:
        armature, cibles, infos = pieces_de(fonction)
    except ErreurFeuillure:
        return False
    if not meme_piece(armature, plan.armature.corps) or len(cibles) != len(plan.cibles):
        return False
    for corps, piece, info, a in zip(cibles, plan.cibles, infos, plan.analyses):
        if not meme_piece(corps, piece.corps) or info.get("mode") != a.mode:
            return False
    return True


def mettre_a_jour(fonction, plan: Plan) -> adsk.fusion.CustomFeature:
    """Réédition. L'appelant a reculé la timeline juste avant la fonction. En place si la structure n'a
    pas changé (réglages réécrits, chaque base refaite : Cabineo, essai S3), sinon remplacement au même
    rang (Flight Case, sonde T6). Rend la fonction (la nouvelle en cas de remplacement)."""
    fonction = natif(fonction)
    if meme_structure(fonction, plan):
        infos, _ = _infos(plan)
        reglages_json = vers_json(plan.r)
        operation = _attribut(fonction, "operation")
        fonction.attributes.add(GROUPE, "reglages", reglages_json)
        fonction.attributes.add(GROUPE, "cibles", json.dumps(infos))
        fonction.name = nom_fonction(plan.analyses, plan.r, plan.armature.nom)
        recalculer(fonction)
        emboitees = [
            f
            for f in _fonctions_de_l_operation(fonction.parentComponent.parentDesign, operation)
            if _attribut(f, "role") == ROLE_CIBLE
        ]
        for f in emboitees:
            cible = corps_de(f, CIBLE)
            info = next((i for i, p in zip(infos, plan.cibles) if meme_piece(p.corps, cible)), None)
            f.attributes.add(GROUPE, "reglages", reglages_json)
            if info is not None:
                f.attributes.add(GROUPE, "cible", json.dumps(info))
            recalculer(f)
        journal().info("%s modifiée en place", fonction.name)
        return fonction
    exiger(fonction.deleteMe(), "etape.suppression")
    nouvelle = creer(plan)
    journal().info("%s remplacée", nouvelle.name)
    return nouvelle
