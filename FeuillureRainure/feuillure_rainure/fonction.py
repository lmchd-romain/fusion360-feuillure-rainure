"""Fonction personnalisée « Feuillure / rainure » : création, recalcul, réédition.

Une seule ligne de timeline par opération, même quand les armatures sont dans d'autres composants.
Méthode reprise des plugins de l'atelier, chaque brique constatée dans Fusion :

- fonction de base dans le composant de la cible, qui porte tous les corps calculés : [0] l'outil de
  coupe, puis l'allongement de chaque armature en contact (Cabineo, essai S2 : plusieurs corps
  d'un même composant) ;
- la fonction est créée juste après sa base, ses dépendances liées aux pièces encore intactes
  (Cabineo, essai S1) ; une face de chaque pièce la représente, jamais le corps entier (Dogbone 0.2.2) ;
- chaque allongement est une combinaison « joindre » dans le composant de son armature, outil pris dans
  la base (Fusion range une combinaison dans le composant de son corps cible : Cabineo, essai S5) ;
- la découpe de la cible vient en dernier : les bornes de la fonction (base, découpe) sont de son
  composant, et tout ce qui passe entre elles suit, même d'un autre composant (Flight Case, sonde T7,
  T12) ;
- calcul : rien tant que la découpe n'est pas regroupée ; ensuite, tous les corps de la base sont
  refaits depuis les pièces telles qu'elles sont juste avant la fonction (`updateBody`).

Attributs (groupe `feuillureRainure`) : `reglages` (JSON des réglages), `armatures` (JSON : pour
chaque armature, son mode, le rang de son allongement dans la base, et sa direction d'entrée dans le
repère de son composant).
"""

from __future__ import annotations

import json
import time
import traceback
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
from .outils import allongement, outil_de_coupe
from .reglages import Reglages, depuis_json, nom_fonction, vers_json

DEFINITION_ID = "feuillureRainure"
ID_EDITION = "feuillureRainureModifierCmd"
GROUPE = "feuillureRainure"
CIBLE = "cible"
ARMATURE = "armature_"
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
            # Fusion ignore le texte d'une erreur de calcul (« Cannot compute this feature. ») : le
            # détail va au journal.
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
    """Ce que le dialogue a préparé : la cible, les armatures utilisables et leur analyse."""

    cible: Piece
    armatures: list[Piece]
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
    """La pièce vue depuis la racine (forme validée par l'essai Cabineo), sinon native.
    `ajouter` rend faux (CustomFeatureInput) ou lève (CustomFeatureDependencies) en cas d'échec."""
    for forme in (en_contexte(entite), natif(entite)):
        try:
            if ajouter(ident, forme):
                return
        except Exception:
            journal().info("dépendance « %s » refusée sous une forme :\n%s", ident, traceback.format_exc())
    exiger(False, "etape.dependance")


def _infos(plan: Plan) -> list[dict]:
    """Pour chaque armature : mode, rang de son allongement dans la base (-1 : aucun), direction
    d'entrée dans le repère de son composant."""
    infos, rang = [], 1
    for piece, a in zip(plan.armatures, plan.analyses):
        info = {"mode": a.mode, "corps": -1}
        if a.mode == CONTACT and a.entree is not None:
            info["corps"] = rang
            info["entree"] = list(direction_locale(piece.corps, a.entree))
            rang += 1
        infos.append(info)
    return infos


def verifier(plan: Plan) -> None:
    """Refus qui protègent le meuble : composant lié, cible ou armature allongée partagée."""
    verifier_modifiable(plan.cible.corps)
    n = exemplaires(plan.cible.corps)
    if n > 1:
        raise ErreurFeuillure(t("erreur.cible_partagee", nom=nom_piece(plan.cible.corps), n=n))
    for piece, a in zip(plan.armatures, plan.analyses):
        if a.mode == CONTACT:
            verifier_modifiable(piece.corps)
            n = exemplaires(piece.corps)
            if n > 1:
                raise ErreurFeuillure(t("erreur.armature_partagee", nom=nom_piece(piece.corps), n=n))


def creer(plan: Plan) -> adsk.fusion.CustomFeature:
    """L'opération entière, au marqueur de timeline. Rend sa fonction."""
    if not plan.armatures or not all(a.utilisable for a in plan.analyses):
        raise ErreurFeuillure(t("erreur.rien_a_faire"))
    verifier(plan)
    design = design_parametrique()
    timeline = design.timeline
    au_bout = timeline.markerPosition == timeline.count
    cible = plan.cible.corps
    composant = composant_de(cible)
    occurrence_cible = occurrence_de(cible)
    monde_cible = matrice_monde(cible)
    boite_cible = boite_monde(cible)
    # Chaque opération recalcule le modèle et peut invalider les objets lus : jetons des natifs d'abord.
    reperes = [(natif(p.corps), jeton(natif(p.corps)), occurrence_de(p.corps)) for p in plan.armatures]
    natif_cible, jeton_cible = natif(cible), jeton(natif(cible))
    infos = _infos(plan)

    corps = [outil_de_coupe(plan.analyses, boite_cible, monde_cible)]
    for a, info in zip(plan.analyses, infos):
        if info["corps"] >= 0:
            corps.append(allongement(a, boite_cible, monde_cible))
    base = composant.features.baseFeatures.add()
    exiger(base.startEdit(), "etape.edition_base")
    try:
        for c in corps:
            exiger(composant.bRepBodies.add(c, base), "etape.ajout_outil")
    finally:
        exiger(base.finishEdit(), "etape.fin_edition_base")

    entree = composant.features.customFeatures.createInput(_definition)
    _dependre(entree.addDependency, CIBLE, reference(cible))
    for i, p in enumerate(plan.armatures):
        _dependre(entree.addDependency, f"{ARMATURE}{i}", reference(p.corps))
    exiger(entree.setStartAndEndFeatures(base, base), "etape.regroupement_base")
    fonction = composant.features.customFeatures.add(entree)
    exiger(fonction, "etape.creation_fonction")
    fonction.name = nom_fonction(plan.analyses, plan.r)
    fonction.attributes.add(GROUPE, "reglages", vers_json(plan.r))
    fonction.attributes.add(GROUPE, "armatures", json.dumps(infos))

    for (n, j, occurrence), info in zip(reperes, infos):
        if info["corps"] < 0:
            continue
        armature = _relire(design, n, j)
        _joindre(design, armature, occurrence, base.bodies.item(info["corps"]), occurrence_cible)

    outils = adsk.core.ObjectCollection.create()
    outils.add(base.bodies.item(0))
    entree_coupe = composant.features.combineFeatures.createInput(_relire(design, natif_cible, jeton_cible), outils)
    entree_coupe.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
    entree_coupe.isKeepToolBodies = False
    coupe = composant.features.combineFeatures.add(entree_coupe)
    exiger(coupe, "etape.decoupe")

    regrouper(fonction, base, coupe)
    if au_bout and timeline.markerPosition < timeline.count:
        exiger(timeline.moveToEnd(), "etape.fin_timeline")
    journal().info("%s posée sur %s : %d armature(s)", fonction.name, plan.cible.nom, len(plan.armatures))
    return fonction


def _relire(design, objet, jeton_: str):
    try:
        if objet.isValid:
            return objet
    except Exception:
        pass
    trouve = retrouver(design, jeton_)
    if trouve is None:
        raise ErreurFeuillure(t("erreur.piece_disparue"))
    return trouve


def _joindre(design, armature, occurrence, outil, occurrence_cible) -> adsk.fusion.CombineFeature:
    """Allonge l'armature : combinaison « joindre » avec son corps d'allongement, pris dans la base de
    la cible. Les deux corps sont vus depuis la racine, comme une sélection à la souris ; Fusion range
    la combinaison dans le composant de l'armature (Cabineo, essai S5). Même composant : natifs."""
    meme_composant = natif(armature).parentComponent == outil.parentComponent
    cible_vue = armature if meme_composant or occurrence is None else armature.createForAssemblyContext(occurrence)
    outil_vu = outil if meme_composant or occurrence_cible is None else outil.createForAssemblyContext(occurrence_cible)
    collections = [natif(armature).parentComponent.features.combineFeatures]
    if not meme_composant:
        collections.insert(0, design.rootComponent.features.combineFeatures)
    for collection in collections:
        try:
            outils = adsk.core.ObjectCollection.create()
            outils.add(outil_vu)
            e = collection.createInput(cible_vue, outils)
            e.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
            e.isKeepToolBodies = False
            jonction = collection.add(e)
            if jonction is not None:
                return jonction
        except Exception:
            journal().warning("allongement refusé par une voie :\n%s", traceback.format_exc())
    raise ErreurFeuillure(t("erreur.refuse", etape=t("etape.allongement")))


def regrouper(fonction: adsk.fusion.CustomFeature, debut, fin) -> None:
    """Étend la fonction de `debut` à `fin` (de son composant) ; Fusion exige la timeline reculée."""
    exiger(fonction.timelineObject.rollTo(True), "etape.recul_timeline")
    try:
        exiger(fonction.setStartAndEndFeatures(debut, fin), "etape.regroupement")
    finally:
        exiger(fonction.timelineObject.rollTo(False), "etape.retour_timeline")


# ---------------------------------------------------------------- recalcul


def _attribut(fonction, cle: str) -> str:
    trouve = natif(fonction).attributes.itemByName(GROUPE, cle)
    if trouve is None:
        raise ErreurFeuillure(t("erreur.reglage_absent", cle=cle))
    return trouve.value


def reglages(fonction) -> Reglages:
    return depuis_json(_attribut(fonction, "reglages"))


def infos(fonction) -> list[dict]:
    try:
        donnees = json.loads(_attribut(fonction, "armatures"))
    except ValueError as e:
        raise ErreurFeuillure(t("erreur.reglages_illisibles", detail=e)) from e
    return [d for d in donnees if isinstance(d, dict)] if isinstance(donnees, list) else []


def corps_de(fonction, ident: str):
    """Le corps d'une pièce, tel qu'il est juste avant la fonction (par sa face de référence)."""
    dependance = natif(fonction).dependencies.itemById(ident)
    entite = dependance.entity if dependance is not None else None
    face = adsk.fusion.BRepFace.cast(entite) if entite is not None else None
    if face is None:
        raise ErreurFeuillure(t("erreur.piece_disparue"))
    return face.body


def pieces_de(fonction) -> tuple:
    """(cible, [armatures], infos) de la fonction."""
    liste = infos(fonction)
    return corps_de(fonction, CIBLE), [corps_de(fonction, f"{ARMATURE}{i}") for i in range(len(liste))], liste


def analyses_de(cible, armatures: list, liste: list[dict], r: Reglages) -> list[Analyse]:
    """Analyse au recalcul : chaque armature garde le mode choisi à sa création."""
    boite_cible = boite_monde(cible)
    sortie = []
    for corps, info in zip(armatures, liste):
        entree = info.get("entree")
        direction = direction_monde(corps, tuple(entree)) if isinstance(entree, list) and len(entree) == 3 else None
        sortie.append(analyser(boite_monde(corps), boite_cible, r.jeu, r.profondeur, info.get("mode"), direction))
    return sortie


def _a_une_coupe(fonction) -> bool:
    return any(f.objectType == adsk.fusion.CombineFeature.classType() for f in fonction.features)


def _base(fonction) -> adsk.fusion.BaseFeature:
    for f in fonction.features:
        if f.objectType == adsk.fusion.BaseFeature.classType():
            return adsk.fusion.BaseFeature.cast(f)
    raise ErreurFeuillure(t("erreur.piece_disparue"))


def _remplacer_corps(fonction, cible, analyses: list[Analyse], liste: list[dict]) -> None:
    boite_cible, monde_cible = boite_monde(cible), matrice_monde(cible)
    nouveaux = {0: outil_de_coupe(analyses, boite_cible, monde_cible)}
    for a, info in zip(analyses, liste):
        rang = info.get("corps", -1)
        if isinstance(rang, int) and rang > 0:
            nouveaux[rang] = allongement(a, boite_cible, monde_cible)
    base = _base(fonction)
    exiger(base.startEdit(), "etape.edition_base")
    try:
        for rang, corps in nouveaux.items():
            if rang < base.bodies.count:
                exiger(base.updateBody(base.bodies.item(rang), corps), "etape.remplacement_outil")
    finally:
        exiger(base.finishEdit(), "etape.fin_edition_base")


def recalculer(fonction) -> int | None:
    """Calcul demandé par Fusion. Rend le nombre d'armatures à problème (None : création en cours)."""
    fonction = natif(fonction)
    if not _a_une_coupe(fonction):
        return None  # création en cours : la découpe n'est pas encore regroupée
    r = reglages(fonction)
    cible, armatures, liste = pieces_de(fonction)
    analyses = analyses_de(cible, armatures, liste, r)
    _remplacer_corps(fonction, cible, analyses, liste)
    return sum(1 for a in analyses if not a.utilisable)


# ---------------------------------------------------------------- réédition


def fonction_editee(entite) -> adsk.fusion.CustomFeature | None:
    f = adsk.fusion.CustomFeature.cast(entite)
    if f is None or f.definition is None or f.definition.id != DEFINITION_ID:
        return None
    return natif(f)


def reculer_avant(fonction) -> None:
    if not natif(fonction).timelineObject.rollTo(True):
        raise ErreurFeuillure(t("erreur.recul_refuse", fonction=fonction.name))


def meme_structure(fonction, plan: Plan) -> bool:
    """Même cible, mêmes armatures dans le même ordre, mêmes modes : la réédition se fait en place
    (les opérations posées après, sur la rainure, gardent leurs références)."""
    try:
        cible, armatures, liste = pieces_de(fonction)
    except ErreurFeuillure:
        return False
    if not meme_piece(cible, plan.cible.corps) or len(armatures) != len(plan.armatures):
        return False
    for corps, piece, info, a in zip(armatures, plan.armatures, liste, plan.analyses):
        if not meme_piece(corps, piece.corps) or info.get("mode") != a.mode:
            return False
    return True


def mettre_a_jour(fonction, plan: Plan) -> adsk.fusion.CustomFeature:
    """Réédition. L'appelant a reculé la timeline juste avant la fonction. En place si la structure
    n'a pas changé (chemin validé par Cabineo, essai S3), sinon remplacement au même rang (Flight
    Case, sonde T6). Rend la fonction (la nouvelle en cas de remplacement)."""
    fonction = natif(fonction)
    if meme_structure(fonction, plan):
        fonction.attributes.add(GROUPE, "reglages", vers_json(plan.r))
        fonction.name = nom_fonction(plan.analyses, plan.r)
        cible, _, liste = pieces_de(fonction)
        _remplacer_corps(fonction, cible, plan.analyses, liste)
        journal().info("%s modifiée en place", fonction.name)
        return fonction
    exiger(fonction.deleteMe(), "etape.suppression")
    nouvelle = creer(plan)
    journal().info("%s remplacée", nouvelle.name)
    return nouvelle
