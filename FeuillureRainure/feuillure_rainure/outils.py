"""Corps temporaires de l'opération (outil de coupe, allongements) et aperçu dans le dialogue.

Tout se calcule dans le repère du monde, en boîtes (`TemporaryBRepManager`), puis se ramène dans le
repère du composant de la cible : c'est là que vit la fonction de base qui porte les corps.
"""

from __future__ import annotations

import traceback

import adsk.core
import adsk.fusion

from .calcul import Analyse
from .fusion_api import MM_PAR_CM, exiger, inverse, point, vecteur
from .geometrie import Boite, Vec
from .journal import journal

PETIT_CM = 0.01  # 0,1 mm : corps de remplacement, sans effet sur les pièces
COULEUR_USINAGE = (40, 120, 200)  # bleu de l'aperçu, comme les autres plugins de l'atelier
COULEUR_ALLONGEMENT = (232, 113, 10)  # orange : ce que l'armature gagne
OPACITE = 0.5


def _tbm() -> adsk.fusion.TemporaryBRepManager:
    return adsk.fusion.TemporaryBRepManager.get()


def boite_temporaire(b: Boite) -> adsk.fusion.BRepBody:
    """Boîte du noyau (mm, monde) → corps temporaire (cm, monde)."""
    obb = adsk.core.OrientedBoundingBox3D.create(
        point(b.centre),
        vecteur(b.axes[0]),
        vecteur(b.axes[1]),
        b.cote(0) / MM_PAR_CM,
        b.cote(1) / MM_PAR_CM,
        b.cote(2) / MM_PAR_CM,
    )
    corps = _tbm().createBox(obb)
    if corps is None:
        raise RuntimeError("boîte temporaire refusée par Fusion")
    return corps


def _union(boites: list[Boite]) -> adsk.fusion.BRepBody | None:
    total = None
    for b in boites:
        if min(b.demi) <= 0:
            continue
        morceau = boite_temporaire(b)
        if total is None:
            total = morceau
        else:
            union = adsk.fusion.BooleanTypes.UnionBooleanType
            exiger(_tbm().booleanOperation(total, morceau, union), "etape.ajout_outil")
    return total


def _intersection(a: Boite, b: Boite) -> adsk.fusion.BRepBody | None:
    if min(a.demi) <= 0 or min(b.demi) <= 0:
        return None
    corps = boite_temporaire(a)
    try:
        ok = _tbm().booleanOperation(corps, boite_temporaire(b), adsk.fusion.BooleanTypes.IntersectionBooleanType)
    except Exception:
        return None
    return corps if ok and corps.volume > 1e-9 else None


def petit_cube(centre_mm: Vec) -> adsk.fusion.BRepBody:
    return _tbm().createBox(
        adsk.core.OrientedBoundingBox3D.create(
            point(centre_mm),
            adsk.core.Vector3D.create(1, 0, 0),
            adsk.core.Vector3D.create(0, 1, 0),
            PETIT_CM,
            PETIT_CM,
            PETIT_CM,
        )
    )


def hors_de(b: Boite) -> Vec:
    """Un point à 10 mm au-delà d'un coin de la boîte : la découpe y passe sans rien toucher."""
    return tuple(c + 10.0 + sum(h for h in b.demi) for c in b.centre)


def vers_composant(corps: adsk.fusion.BRepBody, monde_du_composant: adsk.core.Matrix3D) -> adsk.fusion.BRepBody:
    """Corps calculé dans le monde → repère du composant de la cible."""
    exiger(_tbm().transform(corps, inverse(monde_du_composant)), "etape.repere")
    return corps


def outil_de_coupe(analyses: list[Analyse], cible: Boite, monde_cible: adsk.core.Matrix3D) -> adsk.fusion.BRepBody:
    """L'union des usinages (jeu compris) ; aucune : un petit cube hors de la cible (la découpe reste
    en place et reprendra au prochain recalcul)."""
    corps = _union([b for a in analyses for b in a.outils])
    if corps is None:
        corps = petit_cube(hors_de(cible))
    return vers_composant(corps, monde_cible)


def allongement(a: Analyse, cible: Boite, monde_cible: adsk.core.Matrix3D) -> adsk.fusion.BRepBody:
    """Ce que l'armature gagne : sa tranche d'allongement, coupée par la boîte de la cible. Rien à
    ajouter : un petit cube au cœur de l'armature (la jonction ne change rien)."""
    corps = _intersection(a.tranche, cible) if a.tranche is not None and a.utilisable else None
    if corps is None:
        corps = petit_cube(a.interieur or cible.centre)
    return vers_composant(corps, monde_cible)


def _couleur(rgb: tuple[int, int, int]):
    return adsk.fusion.CustomGraphicsSolidColorEffect.create(adsk.core.Color.create(*rgb, 255))


class Apercu:
    """Graphiques du dialogue, dans la racine (repère du monde) : l'usinage en bleu, l'allongement des
    armatures en orange. Effacés avant chaque aperçu et à la fermeture."""

    def __init__(self):
        self._groupes: list = []

    def effacer(self) -> None:
        for g in self._groupes:
            try:
                if g.isValid:
                    g.deleteMe()
            except Exception:
                pass
        self._groupes.clear()

    def montrer(self, racine: adsk.fusion.Component, cible: Boite, analyses: list[Analyse]) -> None:
        groupe = racine.customGraphicsGroups.add()
        self._groupes.append(groupe)
        for a in analyses:
            try:
                if a.outils:
                    usinage = _union(list(a.outils))
                    if usinage is not None and _tbm().booleanOperation(
                        usinage, boite_temporaire(cible), adsk.fusion.BooleanTypes.IntersectionBooleanType
                    ):
                        self._dessiner(groupe, usinage, COULEUR_USINAGE)
                if a.tranche is not None and a.utilisable:
                    gain = _intersection(a.tranche, cible)
                    if gain is not None:
                        self._dessiner(groupe, gain, COULEUR_ALLONGEMENT)
            except Exception:
                journal().warning("aperçu d'une armature :\n%s", traceback.format_exc())

    @staticmethod
    def _dessiner(groupe, corps, couleur) -> None:
        graphique = groupe.addBRepBody(corps)
        graphique.color = _couleur(couleur)
        graphique.setOpacity(OPACITE, True)
        graphique.depthPriority = 1
        graphique.isSelectable = False
