"""Analyse d'une armature face à la cible : chevauchement ou contact, outil de coupe, allongement.

Module pur : n'importe jamais `adsk`. Longueurs en mm, repère du monde.

Les deux cas de la description (docs/description.txt) :

- **chevauchement** : l'armature rentre déjà dans la cible. Elle ne bouge pas ; l'usinage est sa
  boîte agrandie du jeu de chaque côté et au fond (exemple : armature de 19 qui rentre de 10 →
  rainure de 19,6 × 10,3 pour un jeu de 0,3).
- **contact** : l'armature touche seulement la cible. Elle est allongée de la profondeur réglée,
  mesurée depuis la face d'entrée de la cible, puis la cible est usinée comme pour un chevauchement.

L'usinage est une **feuillure** s'il débouche sur un côté de la cible (l'armature est au bord), une
**rainure** sinon.
"""

from __future__ import annotations

from dataclasses import dataclass

from .geometrie import TOL, Boite, Vec, aire_polygone, ajouter, couper_polygone, fois, recouvrement, scalaire

CHEVAUCHEMENT = "chevauchement"
CONTACT = "contact"
RAINURE = "rainure"
FEUILLURE = "feuillure"
AIRE_MIN = 1.0  # mm² : en deçà, deux faces qui se frôlent ne sont pas un contact
TOL_CONTACT = 0.05  # mm : jour ou chevauchement plus petit que ça = les pièces se touchent (arrondis de Fusion)


@dataclass(frozen=True)
class Analyse:
    """Ce que l'opération fera d'une armature. `probleme` : clé de traduction ; vide si tout va bien."""

    mode: str = ""
    probleme: str = ""
    type: str = ""  # RAINURE ou FEUILLURE
    enfoncement: float = 0.0  # mm : l'armature dans la cible, depuis sa face d'entrée
    largeur: float = 0.0  # mm : largeur de l'usinage dans la cible, jeu compris
    profondeur: float = 0.0  # mm : profondeur de l'usinage, jeu compris
    traversante: bool = False
    allongement: float = 0.0  # mm : contact, de combien l'armature s'allonge
    entree: Vec | None = None  # direction (unitaire) de l'armature vers la cible
    outils: tuple[Boite, ...] = ()  # leur union, coupée par la cible, est l'usinage
    tranche: Boite | None = None  # contact : boîte d'allongement, à couper par la cible
    interieur: Vec | None = None  # un point au cœur de l'armature

    @property
    def utilisable(self) -> bool:
        return not self.probleme


def epaisseurs(points: list[Vec], b: Boite) -> tuple[float, float, float]:
    """Étendue de points le long des trois axes de la boîte b."""
    if not points:
        return (0.0, 0.0, 0.0)
    sortie = []
    for k in range(3):
        valeurs = [scalaire(p, b.axes[k]) for p in points]
        sortie.append(max(valeurs) - min(valeurs))
    return tuple(sortie)


def contact(a: Boite, t: Boite) -> tuple[int, int, float] | None:
    """La face (k, s) de l'armature a posée contre une face de la cible t, et l'aire commune ; None si
    aucune. Deux faces en contact sont coplanaires, de normales opposées, et se recouvrent."""
    meilleur = None
    plans_t = t.plans()  # rang 2m (côté -) et 2m + 1 (côté +)
    for k in range(3):
        for s in (-1, 1):
            n_a = a.normale(k, s)
            d_a = scalaire(n_a, a.centre) + a.demi[k]
            for m in range(3):
                for n_t, d_t in plans_t[2 * m : 2 * m + 2]:
                    if scalaire(n_a, n_t) > -1.0 + 1e-6 or abs(d_a + d_t) > TOL_CONTACT:
                        continue
                    face = list(a.face(k, s))
                    for i, (n, d) in enumerate(plans_t):
                        if i // 2 != m and face:
                            face = couper_polygone(face, n, d + TOL)
                    aire = aire_polygone(face) if len(face) >= 3 else 0.0
                    if aire > AIRE_MIN and (meilleur is None or aire > meilleur[2]):
                        meilleur = (k, s, aire)
    return meilleur


def _axe_largeur(a: Boite, k_entree: int) -> int:
    """Axe de l'armature qui donne la largeur de l'usinage : le plus petit côté hors de l'axe d'entrée
    (l'épaisseur du panneau, sauf panneau posé à plat)."""
    autres = [k for k in range(3) if k != k_entree]
    return min(autres, key=lambda k: a.demi[k])


def _forme(a: Boite, t: Boite, k_entree: int, jeu: float) -> tuple[str, float]:
    """(type, largeur dans la cible) : feuillure si l'usinage, jeu compris, déborde de la cible sur un
    côté de sa largeur, rainure sinon."""
    k = _axe_largeur(a, k_entree)
    axe = a.axes[k]
    usinage = a.agrandie(jeu).etendue(axe)
    cible = t.etendue(axe)
    deborde = usinage[0] < cible[0] - TOL or usinage[1] > cible[1] + TOL
    return (FEUILLURE if deborde else RAINURE), recouvrement(usinage, cible)


def analyser(
    a: Boite,
    t: Boite,
    jeu: float,
    profondeur: float,
    mode: str | None = None,
    entree: Vec | None = None,
) -> Analyse:
    """L'armature a face à la cible t. À la création, `mode` est None : il se déduit de la géométrie.
    Au recalcul, le mode retenu à la création est imposé, avec sa direction d'entrée (contact)."""
    if jeu < 0:
        return Analyse(probleme="erreur.jeu_negatif")
    interieur = a.centre
    commun = a.couper(t)
    ep = epaisseurs(commun.sommets(), a) if not commun.vide else (0.0, 0.0, 0.0)
    chevauche = not commun.vide and min(ep) > TOL_CONTACT
    if mode is None:
        if chevauche:
            mode = CHEVAUCHEMENT
        else:
            touche = contact(a, t)
            if touche is None:
                return Analyse(probleme="erreur.pas_de_contact", interieur=interieur)
            mode, entree = CONTACT, a.normale(touche[0], touche[1])
    if mode == CHEVAUCHEMENT:
        return _chevauchement(a, t, jeu, commun.sommets() if chevauche else [], ep, interieur)
    if entree is None:
        return Analyse(mode=CONTACT, probleme="erreur.entree_perdue", interieur=interieur)
    return _contact(a, t, jeu, profondeur, entree, interieur)


def _chevauchement(a: Boite, t: Boite, jeu: float, sommets: list[Vec], ep, interieur: Vec) -> Analyse:
    outils = (a.agrandie(jeu),)
    if not sommets:
        # Recalcul : l'armature ne rentre plus dans la cible ; la découpe ne laisse que le jeu.
        return Analyse(mode=CHEVAUCHEMENT, probleme="erreur.plus_de_chevauchement", outils=outils, interieur=interieur)
    sortantes = []
    for k in range(3):
        a_min, a_max = a.etendue(a.axes[k])
        c_min, c_max = min(scalaire(p, a.axes[k]) for p in sommets), max(scalaire(p, a.axes[k]) for p in sommets)
        dessous, dessus = c_min > a_min + TOL, c_max < a_max - TOL
        if dessous or dessus:
            sortantes.append((k, dessous, dessus))
    if not sortantes:
        return Analyse(mode=CHEVAUCHEMENT, probleme="erreur.armature_dans_la_cible", interieur=interieur)
    epaisseur = min(range(3), key=lambda k: a.demi[k])
    candidates = [s for s in sortantes if s[0] != epaisseur] or sortantes
    k, dessous, dessus = max(candidates, key=lambda s: a.demi[s[0]])
    traversante = dessous and dessus
    # L'armature vient du côté où elle dépasse et entre dans la cible en allant vers l'autre.
    entree = a.normale(k, 1 if dessous else -1)
    enfoncement = ep[k]
    type_, largeur = _forme(a, t, k, jeu)
    return Analyse(
        mode=CHEVAUCHEMENT,
        type=type_,
        enfoncement=enfoncement,
        largeur=largeur,
        profondeur=enfoncement if traversante else enfoncement + jeu,
        traversante=traversante,
        entree=entree,
        outils=outils,
        interieur=interieur,
    )


def _contact(a: Boite, t: Boite, jeu: float, profondeur: float, entree: Vec, interieur: Vec) -> Analyse:
    k, s = a.axe_le_long(entree)
    avant = a.etendue(entree)[1]
    face_cible, fond_cible = t.etendue(entree)
    commun = dict(mode=CONTACT, entree=entree, interieur=interieur)
    if profondeur <= 0:
        return Analyse(probleme="erreur.profondeur_nulle", outils=(a.agrandie(jeu),), **commun)
    if avant < face_cible - TOL_CONTACT:
        # Recalcul : l'armature s'est écartée de la cible ; on ne l'allonge pas dans le vide.
        return Analyse(probleme="erreur.pas_de_contact", outils=(a.agrandie(jeu),), **commun)
    if face_cible + profondeur >= fond_cible - TOL:
        return Analyse(
            probleme="erreur.profondeur_trop_grande",
            outils=(a.agrandie(jeu),),
            enfoncement=fond_cible - face_cible,
            **commun,
        )
    allongement = face_cible + profondeur - avant
    tranche = None
    outils = [a.agrandie(jeu)]
    if allongement > TOL:
        demi = list(a.demi)
        demi[k] = allongement / 2.0
        centre = ajouter(a.centre, fois(a.axes[k], s * (a.demi[k] + allongement / 2.0)))
        tranche = Boite(centre, a.axes, tuple(demi))
        dans_la_cible = tranche.couper(t)
        if dans_la_cible.vide:
            return Analyse(probleme="erreur.pas_de_contact", outils=tuple(outils), **commun)
        boite = a.boite_de(dans_la_cible.sommets())
        if boite is not None:
            outils.append(boite.agrandie(jeu))
    type_, largeur = _forme(a, t, k, jeu)
    return Analyse(
        type=type_,
        enfoncement=profondeur,
        largeur=largeur,
        profondeur=profondeur + jeu,
        allongement=max(0.0, allongement),
        outils=tuple(outils),
        tranche=tranche,
        **commun,
    )
