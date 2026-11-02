"""Accès à l'API Fusion : petits outils communs aux modules qui importent `adsk`.

Fusion travaille en cm, le noyau en mm : les conversions passent par ici (`MM_PAR_CM`). Les corps sont
lus sous leur forme native (repère de leur composant), puis ramenés dans le repère du monde par la
matrice de leur occurrence : on ne dépend jamais de la façon dont Fusion range un proxy.
"""

from __future__ import annotations

import traceback

import adsk.core
import adsk.fusion

from .erreurs import ErreurFeuillure
from .geometrie import Boite, Vec, fois, longueur, scalaire, soustraire, unitaire, vectoriel
from .journal import journal
from .langues import t

MM_PAR_CM = 10.0
SANS_BOITE = False  # recette automatique : pas de boîte de message modale (elle bloquerait le script)


def app() -> adsk.core.Application:
    return adsk.core.Application.get()


def ui() -> adsk.core.UserInterface:
    return app().userInterface


def design_actif() -> adsk.fusion.Design:
    design = adsk.fusion.Design.cast(app().activeProduct)
    if design is None:
        raise ErreurFeuillure(t("erreur.pas_de_design"))
    return design


def design_parametrique() -> adsk.fusion.Design:
    design = design_actif()
    if design.designType != adsk.fusion.DesignTypes.ParametricDesignType:
        raise ErreurFeuillure(t("erreur.historique"))
    return design


def exiger(ok, etape: str) -> None:
    """Beaucoup de méthodes Fusion signalent un échec en rendant faux, sans exception. `etape` : clé de
    traduction (`etape.…`) de l'étape refusée."""
    if not ok:
        raise ErreurFeuillure(t("erreur.refuse", etape=t(etape)))


def natif(entite):
    """L'entité hors assemblage, dans le repère de son composant (un objet natif rend None)."""
    return entite.nativeObject or entite


def jeton(entite) -> str:
    """entityToken ; vide si Fusion le refuse (proxy dont le parent n'est pas la racine)."""
    try:
        return entite.entityToken
    except Exception:
        return ""


def retrouver(design: adsk.fusion.Design, jeton_: str):
    trouves = design.findEntityByToken(jeton_) if jeton_ else []
    return trouves[0] if trouves else None


def composant_de(entite) -> adsk.fusion.Component:
    n = natif(entite)
    corps = getattr(n, "body", None)
    return (corps if corps is not None else n).parentComponent


def occurrence_de(entite):
    """L'occurrence (vue depuis la racine) qui place l'entité dans le monde ; None à la racine. Une
    sélection du dialogue la porte (`assemblyContext`) ; une entité native prend la première."""
    contexte = getattr(entite, "assemblyContext", None)
    if contexte is not None:
        return contexte
    composant = composant_de(entite)
    racine = composant.parentDesign.rootComponent
    if composant == racine:
        return None
    occurrences = racine.allOccurrencesByComponent(composant)
    return occurrences.item(0) if occurrences.count else None


def matrice_monde(entite) -> adsk.core.Matrix3D:
    """Repère du composant de l'entité → monde."""
    occurrence = occurrence_de(entite)
    return occurrence.transform2.copy() if occurrence is not None else adsk.core.Matrix3D.create()


def inverse(m: adsk.core.Matrix3D) -> adsk.core.Matrix3D:
    copie = m.copy()
    exiger(copie.invert(), "etape.repere")
    return copie


def en_mm(p) -> Vec:
    return (p.x * MM_PAR_CM, p.y * MM_PAR_CM, p.z * MM_PAR_CM)


def point(v: Vec) -> adsk.core.Point3D:
    """Un point en mm → Point3D en cm."""
    return adsk.core.Point3D.create(v[0] / MM_PAR_CM, v[1] / MM_PAR_CM, v[2] / MM_PAR_CM)


def vecteur(v: Vec) -> adsk.core.Vector3D:
    """Une direction (sans unité)."""
    return adsk.core.Vector3D.create(v[0], v[1], v[2])


def vers_monde(m: adsk.core.Matrix3D, p) -> Vec:
    """Point3D (cm, repère du composant) → mm, monde."""
    q = p.copy()
    q.transformBy(m)
    return en_mm(q)


def direction_vers(m: adsk.core.Matrix3D, v: Vec) -> Vec:
    d = vecteur(v)
    d.transformBy(m)
    return unitaire((d.x, d.y, d.z))


def direction_locale(entite, v: Vec) -> Vec:
    """Direction du monde → repère du composant de l'entité (gardée dans les attributs : elle suit le
    composant s'il bouge ou tourne)."""
    return direction_vers(inverse(matrice_monde(entite)), v)


def direction_monde(entite, v: Vec) -> Vec:
    return direction_vers(matrice_monde(entite), v)


def _boite_exacte(n) -> Boite | None:
    """Boîte d'un panneau lue sur son B-rep, dans le repère de son composant (mm) : épaisseur selon la
    normale de sa plus grande face plane, longueur selon la plus longue arête droite de cette face,
    étendues par ses sommets. Exacte pour un panneau rectangulaire, à tout angle (la boîte orientée
    minimale de Fusion peut s'écarter du corps de quelques microns, et un contact se juge au micron)."""
    planes = []
    for i in range(n.faces.count):
        f = n.faces.item(i)
        plan = adsk.core.Plane.cast(f.geometry)
        if plan is not None:
            planes.append((f.area, f, plan))
    sommets = [en_mm(n.vertices.item(i).geometry) for i in range(n.vertices.count)]
    if not planes or len(sommets) < 4:
        return None
    _, face, plan = max(planes, key=lambda x: x[0])
    w = unitaire((plan.normal.x, plan.normal.y, plan.normal.z))
    lignes = [adsk.core.Line3D.cast(face.edges.item(i).geometry) for i in range(face.edges.count)]
    lignes = [ligne for ligne in lignes if ligne is not None]
    u = None
    if lignes:
        ligne = max(lignes, key=lambda l: l.startPoint.distanceTo(l.endPoint))
        d = soustraire(en_mm(ligne.endPoint), en_mm(ligne.startPoint))
        d = soustraire(d, fois(w, scalaire(d, w)))
        if longueur(d) > 1e-9:
            u = unitaire(d)
    if u is None:
        axe = (1.0, 0.0, 0.0) if abs(w[0]) < 0.9 else (0.0, 1.0, 0.0)
        u = unitaire(vectoriel(w, axe))
    return Boite.selon((u, vectoriel(w, u), w), sommets)


def boite_monde(corps) -> Boite:
    """Boîte du panneau, en mm, dans le repère du monde : lue sur son B-rep (exacte), sinon la boîte
    orientée minimale de Fusion, sinon la boîte du composant."""
    n = natif(corps)
    m = matrice_monde(corps)
    try:
        b = _boite_exacte(n)
        if b is not None:
            centre = vers_monde(m, point(b.centre))
            return Boite(centre, tuple(direction_vers(m, a) for a in b.axes), b.demi)
    except Exception:
        journal().warning("boîte exacte illisible pour %s :\n%s", n.name, traceback.format_exc())
    try:
        o = n.orientedMinimumBoundingBox
        axes = []
        for d in (o.lengthDirection, o.widthDirection, o.heightDirection):
            v = d.copy()
            v.transformBy(m)
            axes.append(unitaire((v.x, v.y, v.z)))
        demi = (o.length * MM_PAR_CM / 2, o.width * MM_PAR_CM / 2, o.height * MM_PAR_CM / 2)
        return Boite(vers_monde(m, o.centerPoint), tuple(axes), demi)
    except Exception:
        journal().warning("boîte orientée illisible pour %s, boîte du composant :\n%s", n.name, traceback.format_exc())
    bb = n.boundingBox
    a, b = bb.minPoint, bb.maxPoint
    centre = adsk.core.Point3D.create((a.x + b.x) / 2, (a.y + b.y) / 2, (a.z + b.z) / 2)
    axes = tuple(direction_vers(m, u) for u in ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)))
    demi = tuple(abs(hi - lo) * MM_PAR_CM / 2 for lo, hi in ((a.x, b.x), (a.y, b.y), (a.z, b.z)))
    return Boite(vers_monde(m, centre), axes, demi)


def nom_piece(corps) -> str:
    """Nom du panneau : son composant, ou son corps si le composant en porte plusieurs (ou la racine)."""
    n = natif(corps)
    composant = n.parentComponent
    if composant == composant.parentDesign.rootComponent or composant.bRepBodies.count > 1:
        return n.name
    return composant.name


def exemplaires(corps) -> int:
    """Nombre d'occurrences du composant du corps (1 pour la racine)."""
    composant = composant_de(corps)
    racine = composant.parentDesign.rootComponent
    if composant == racine:
        return 1
    return racine.allOccurrencesByComponent(composant).count


def meme_piece(a, b) -> bool:
    """Même corps natif, placé par la même occurrence."""
    if natif(a) != natif(b):
        return False
    oa, ob = occurrence_de(a), occurrence_de(b)
    if oa is None or ob is None:
        return oa is None and ob is None
    return oa.fullPathName == ob.fullPathName


def verifier_modifiable(corps) -> None:
    """Un composant lié (venu d'un autre design) ne reçoit aucune fonction."""
    composant = composant_de(corps)
    racine = composant.parentDesign.rootComponent
    if composant == racine:
        return
    occurrences = racine.allOccurrencesByComponent(composant)
    for i in range(occurrences.count):
        if occurrences.item(i).isReferencedComponent:
            raise ErreurFeuillure(t("erreur.composant_lie", composant=composant.name))


def en_contexte(entite):
    """L'entité vue depuis la racine, par l'occurrence qui la place ; native à la racine."""
    if getattr(entite, "assemblyContext", None) is not None:
        return entite
    occurrence = occurrence_de(entite)
    return entite.createForAssemblyContext(occurrence) if occurrence is not None else entite


def signaler_ouverture_ratee(ou: str) -> None:
    """Un dialogue qui plante pendant sa construction s'ouvrirait muet (aucun gestionnaire branché) :
    l'erreur va au journal et l'utilisateur la voit, avec sa dernière ligne."""
    trace = traceback.format_exc()
    journal().error("%s :\n%s", ou, trace)
    derniere = trace.strip().splitlines()[-1] if trace.strip() else "?"
    if SANS_BOITE:
        return
    try:
        ui().messageBox(t("erreur.ouverture", detail=derniere))
    except Exception:
        pass


class Marqueur:
    """Position du marqueur de timeline, à rendre après une réédition."""

    def __init__(self, timeline: adsk.fusion.Timeline):
        self.timeline = timeline
        self.au_bout = timeline.markerPosition == timeline.count
        self.objet = timeline.item(timeline.markerPosition - 1) if timeline.markerPosition else None

    def rendre(self) -> None:
        if self.au_bout:
            if self.timeline.markerPosition < self.timeline.count:
                exiger(self.timeline.moveToEnd(), "etape.fin_timeline")
        elif self.objet is None:
            exiger(self.timeline.moveToBeginning(), "etape.retour_marqueur")  # marqueur parti du tout début
        elif self.objet.isValid:
            exiger(self.objet.rollTo(False), "etape.retour_marqueur")
        # Objet remplacé (réédition par remplacement) : le marqueur est déjà au bon endroit.
