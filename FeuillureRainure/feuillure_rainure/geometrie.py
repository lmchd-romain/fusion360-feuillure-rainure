"""Géométrie pure : vecteurs, boîtes orientées, polyèdres convexes.

Module pur : n'importe jamais `adsk`. Longueurs en mm, repère du monde (racine du design).

Un panneau est vu comme sa boîte orientée minimale (`Boite`) : c'est exact pour un panneau
rectangulaire, quelle que soit son orientation. Les intersections de boîtes passent par un polyèdre
convexe coupé plan par plan (`Polyedre.couper`), exact lui aussi.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

Vec = tuple[float, float, float]

TOL = 1e-3  # mm : en deçà, deux plans sont confondus, une épaisseur est nulle
_EPS = 1e-9


def ajouter(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def soustraire(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def fois(a: Vec, k: float) -> Vec:
    return (a[0] * k, a[1] * k, a[2] * k)


def scalaire(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vectoriel(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def longueur(a: Vec) -> float:
    return math.sqrt(scalaire(a, a))


def unitaire(a: Vec) -> Vec:
    n = longueur(a)
    if n < _EPS:
        raise ValueError("vecteur nul")
    return fois(a, 1.0 / n)


def oppose(a: Vec) -> Vec:
    return (-a[0], -a[1], -a[2])


def normale_polygone(points: tuple[Vec, ...] | list[Vec]) -> Vec:
    """Normale de Newell, de longueur le double de l'aire : sens donné par l'ordre des sommets."""
    nx = ny = nz = 0.0
    for i, a in enumerate(points):
        b = points[(i + 1) % len(points)]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    return (nx, ny, nz)


def aire_polygone(points) -> float:
    return longueur(normale_polygone(points)) / 2.0 if len(points) >= 3 else 0.0


def _sans_doublons(points: list[Vec]) -> list[Vec]:
    sortie: list[Vec] = []
    for p in points:
        if not sortie or longueur(soustraire(p, sortie[-1])) > _EPS * 1e3:
            sortie.append(p)
    while len(sortie) > 1 and longueur(soustraire(sortie[0], sortie[-1])) <= _EPS * 1e3:
        sortie.pop()
    return sortie


def couper_polygone(points: list[Vec], n: Vec, d: float) -> list[Vec]:
    """Sutherland-Hodgman : la partie du polygone où n·x ≤ d."""
    sortie: list[Vec] = []
    for i, a in enumerate(points):
        b = points[(i + 1) % len(points)]
        da, db = scalaire(n, a) - d, scalaire(n, b) - d
        if da <= _EPS:
            sortie.append(a)
        if (da < -_EPS and db > _EPS) or (da > _EPS and db < -_EPS):
            sortie.append(ajouter(a, fois(soustraire(b, a), da / (da - db))))
    return _sans_doublons(sortie)


@dataclass(frozen=True)
class Polyedre:
    """Polyèdre convexe : faces planes, sommets dans le sens direct vu de l'extérieur."""

    faces: tuple[tuple[Vec, ...], ...]

    @property
    def vide(self) -> bool:
        return not self.faces

    def sommets(self) -> list[Vec]:
        vus: list[Vec] = []
        for face in self.faces:
            for p in face:
                if not any(longueur(soustraire(p, q)) <= TOL / 10 for q in vus):
                    vus.append(p)
        return vus

    def volume(self) -> float:
        total = 0.0
        for face in self.faces:
            a = face[0]
            for b, c in zip(face[1:-1], face[2:]):
                total += scalaire(a, vectoriel(b, c))
        return total / 6.0

    def etendue(self, direction: Vec) -> tuple[float, float]:
        valeurs = [scalaire(p, direction) for p in self.sommets()]
        return (min(valeurs), max(valeurs)) if valeurs else (0.0, 0.0)

    def couper(self, n: Vec, d: float) -> Polyedre:
        """La partie du polyèdre où n·x ≤ d (n unitaire)."""
        distances = [scalaire(n, p) - d for face in self.faces for p in face]
        if not distances or max(distances) <= _EPS:
            return self
        if min(distances) >= -_EPS:
            return Polyedre(())
        faces: list[tuple[Vec, ...]] = []
        sur_le_plan: list[Vec] = []
        for face in self.faces:
            coupee = couper_polygone(list(face), n, d)
            if len(coupee) >= 3 and aire_polygone(coupee) > _EPS:
                faces.append(tuple(coupee))
            sur_le_plan += [p for p in coupee if abs(scalaire(n, p) - d) <= 1e-7]
        couvercle = _polygone_sur_plan(sur_le_plan, n)
        if len(couvercle) >= 3:
            faces.append(tuple(couvercle))
        return Polyedre(tuple(faces))


def _polygone_sur_plan(points: list[Vec], n: Vec) -> list[Vec]:
    """Points d'un même plan rangés en polygone convexe, sens direct autour de n."""
    uniques: list[Vec] = []
    for p in points:
        if not any(longueur(soustraire(p, q)) <= 1e-7 for q in uniques):
            uniques.append(p)
    if len(uniques) < 3:
        return []
    centre = fois(
        (sum(p[0] for p in uniques), sum(p[1] for p in uniques), sum(p[2] for p in uniques)), 1.0 / len(uniques)
    )
    e1 = _perpendiculaire(n)
    e2 = vectoriel(n, e1)
    uniques.sort(key=lambda p: math.atan2(scalaire(soustraire(p, centre), e2), scalaire(soustraire(p, centre), e1)))
    return uniques


def _perpendiculaire(n: Vec) -> Vec:
    axe = (1.0, 0.0, 0.0) if abs(n[0]) < 0.9 else (0.0, 1.0, 0.0)
    return unitaire(vectoriel(n, axe))


@dataclass(frozen=True)
class Boite:
    """Boîte orientée : centre, trois axes orthonormés, demi-côtés (mm)."""

    centre: Vec
    axes: tuple[Vec, Vec, Vec]
    demi: tuple[float, float, float]

    @staticmethod
    def alignee(mini: Vec, maxi: Vec) -> Boite:
        centre = fois(ajouter(mini, maxi), 0.5)
        demi = (abs(maxi[0] - mini[0]) / 2, abs(maxi[1] - mini[1]) / 2, abs(maxi[2] - mini[2]) / 2)
        return Boite(centre, ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)), demi)

    @staticmethod
    def selon(axes: tuple[Vec, Vec, Vec], points: list[Vec]) -> Boite:
        """La plus petite boîte d'axes donnés qui contient les points (axes orthonormés)."""
        mini = [min(scalaire(p, a) for p in points) for a in axes]
        maxi = [max(scalaire(p, a) for p in points) for a in axes]
        centre = (0.0, 0.0, 0.0)
        for k in range(3):
            centre = ajouter(centre, fois(axes[k], (mini[k] + maxi[k]) / 2))
        return Boite(centre, axes, tuple((maxi[k] - mini[k]) / 2 for k in range(3)))

    def cote(self, k: int) -> float:
        return 2.0 * self.demi[k]

    def agrandie(self, marge: float) -> Boite:
        return Boite(self.centre, self.axes, tuple(max(0.0, h + marge) for h in self.demi))

    def coins(self) -> list[Vec]:
        (u, v, w), (hu, hv, hw) = self.axes, self.demi
        return [
            ajouter(self.centre, ajouter(fois(u, su * hu), ajouter(fois(v, sv * hv), fois(w, sw * hw))))
            for su in (-1, 1)
            for sv in (-1, 1)
            for sw in (-1, 1)
        ]

    def etendue(self, direction: Vec) -> tuple[float, float]:
        """Projection de la boîte sur `direction` (unitaire) : (min, max)."""
        c = scalaire(self.centre, direction)
        r = sum(h * abs(scalaire(a, direction)) for a, h in zip(self.axes, self.demi))
        return (c - r, c + r)

    def locale(self, p: Vec) -> Vec:
        """Coordonnées de p dans le repère de la boîte (origine au centre)."""
        d = soustraire(p, self.centre)
        return (scalaire(d, self.axes[0]), scalaire(d, self.axes[1]), scalaire(d, self.axes[2]))

    def contient(self, p: Vec, marge: float = TOL) -> bool:
        return all(abs(c) <= h + marge for c, h in zip(self.locale(p), self.demi))

    def normale(self, k: int, s: int) -> Vec:
        return fois(self.axes[k], float(s))

    def plans(self) -> list[tuple[Vec, float]]:
        """Les six demi-espaces n·x ≤ d dont l'intersection est la boîte (n : normale sortante)."""
        sortie = []
        for k in range(3):
            for s in (-1, 1):
                n = self.normale(k, s)
                sortie.append((n, scalaire(n, self.centre) + self.demi[k]))
        return sortie

    def face(self, k: int, s: int) -> tuple[Vec, ...]:
        """Les quatre coins de la face (k, s), sens direct vu de l'extérieur."""
        i, j = (k + 1) % 3, (k + 2) % 3
        u, v = fois(self.axes[i], self.demi[i]), fois(self.axes[j], self.demi[j])
        c = ajouter(self.centre, fois(self.axes[k], s * self.demi[k]))
        points = [
            soustraire(soustraire(c, u), v),
            soustraire(ajouter(c, u), v),
            ajouter(ajouter(c, u), v),
            ajouter(soustraire(c, u), v),
        ]
        if scalaire(normale_polygone(points), self.normale(k, s)) < 0:
            points.reverse()
        return tuple(points)

    def polyedre(self) -> Polyedre:
        if min(self.demi) <= _EPS:
            return Polyedre(())
        return Polyedre(tuple(self.face(k, s) for k in range(3) for s in (-1, 1)))

    def couper(self, autre: Boite) -> Polyedre:
        """L'intersection des deux boîtes."""
        p = self.polyedre()
        for n, d in autre.plans():
            if p.vide:
                break
            p = p.couper(n, d)
        return p

    def axe_le_long(self, direction: Vec) -> tuple[int, int]:
        """(k, s) : l'axe de la boîte le plus proche de `direction`, et le sens."""
        k = max(range(3), key=lambda i: abs(scalaire(self.axes[i], direction)))
        return k, (1 if scalaire(self.axes[k], direction) >= 0 else -1)

    def boite_de(self, points: list[Vec]) -> Boite | None:
        """La plus petite boîte, dans le repère de celle-ci, qui contient les points."""
        if not points:
            return None
        locales = [self.locale(p) for p in points]
        mini = [min(p[k] for p in locales) for k in range(3)]
        maxi = [max(p[k] for p in locales) for k in range(3)]
        centre = self.centre
        for k in range(3):
            centre = ajouter(centre, fois(self.axes[k], (mini[k] + maxi[k]) / 2))
        return Boite(centre, self.axes, tuple((maxi[k] - mini[k]) / 2 for k in range(3)))


def recouvrement(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Longueur commune de deux intervalles (0 s'ils ne se touchent pas)."""
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
