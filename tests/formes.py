"""Pièces de test, en mm : celles des fichiers `exemples/*.step` de l'utilisateur (relevées au
2026-11-02 avec OpenCascade), et leurs variantes tournées."""

from __future__ import annotations

import math

from feuillure_rainure.geometrie import Boite, Vec

# exemples/avant-chevauchement.step : la cible et deux armatures qui y rentrent de 10 mm
CIBLE = Boite.alignee((0, 0, -200), (200, 19, 0))
TRAVERSANTE = Boite.alignee((54, 9, -200), (73, 222.42, 0))  # rainure sur toute la hauteur
ARRETEE = Boite.alignee((127, 9, -153.141), (146, 222.42, -46.859))  # rainure arrêtée aux deux bouts
# exemples/avant-contact.step : les mêmes armatures, posées contre la cible
TRAVERSANTE_CONTACT = Boite.alignee((54, 19, -200), (73, 232.42, 0))
ARRETEE_CONTACT = Boite.alignee((127, 19, -153.141), (146, 232.42, -46.859))
# exemples/apres.step : la cible usinée, jeu 0,3
VOLUME_CIBLE_APRES = 698046.663
VOLUME_CIBLE_AVANT = 760000.0


def tourner(b: Boite, degres: float, axe: int = 2, centre: Vec = (0.0, 0.0, 0.0)) -> Boite:
    """La boîte tournée autour d'un axe du monde passant par `centre`."""
    a = math.radians(degres)
    c, s = math.cos(a), math.sin(a)

    def r(v: Vec, origine: Vec = (0.0, 0.0, 0.0)) -> Vec:
        x, y, z = (v[0] - origine[0], v[1] - origine[1], v[2] - origine[2])
        if axe == 2:
            x, y = c * x - s * y, s * x + c * y
        elif axe == 1:
            z, x = c * z - s * x, s * z + c * x
        else:
            y, z = c * y - s * z, s * y + c * z
        return (x + origine[0], y + origine[1], z + origine[2])

    return Boite(r(b.centre, centre), tuple(r(u) for u in b.axes), b.demi)
