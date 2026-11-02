"""Boîtes orientées et polyèdres convexes."""

import pytest
from feuillure_rainure.geometrie import Boite, aire_polygone, recouvrement
from formes import CIBLE, TRAVERSANTE, tourner


def test_volume_d_une_boite():
    assert Boite.alignee((0, 0, 0), (10, 20, 30)).polyedre().volume() == pytest.approx(6000)


def test_volume_d_une_boite_tournee():
    b = tourner(Boite.alignee((0, 0, 0), (10, 20, 30)), 37, axe=1)
    assert b.polyedre().volume() == pytest.approx(6000)


def test_faces_dans_le_sens_direct():
    b = tourner(CIBLE, 30)
    for k in range(3):
        for s in (-1, 1):
            assert aire_polygone(b.face(k, s)) == pytest.approx(b.cote((k + 1) % 3) * b.cote((k + 2) % 3))


def test_couper_par_un_plan_garde_la_moitie():
    p = Boite.alignee((0, 0, 0), (10, 10, 10)).polyedre().couper((1.0, 0.0, 0.0), 5.0)
    assert p.volume() == pytest.approx(500)
    assert p.etendue((1.0, 0.0, 0.0)) == pytest.approx((0, 5))


def test_couper_hors_du_polyedre():
    b = Boite.alignee((0, 0, 0), (10, 10, 10)).polyedre()
    assert b.couper((1.0, 0.0, 0.0), 20.0) is b
    assert b.couper((1.0, 0.0, 0.0), -1.0).vide


def test_intersection_de_deux_boites():
    commun = TRAVERSANTE.couper(CIBLE)
    assert commun.volume() == pytest.approx(19 * 10 * 200)


def test_intersection_tournee():
    commun = tourner(TRAVERSANTE, 25).couper(tourner(CIBLE, 25))
    assert commun.volume() == pytest.approx(19 * 10 * 200)


def test_boites_disjointes():
    assert Boite.alignee((0, 0, 0), (1, 1, 1)).couper(Boite.alignee((5, 5, 5), (6, 6, 6))).vide


def test_boite_de_points_dans_le_repere():
    b = tourner(Boite.alignee((0, 0, 0), (10, 10, 10)), 45)
    petite = b.boite_de(Boite.alignee((2, 2, 2), (4, 4, 4)).coins())
    assert petite is not None and min(petite.demi) > 0


def test_recouvrement():
    assert recouvrement((0, 10), (5, 20)) == 5
    assert recouvrement((0, 1), (2, 3)) == 0


def test_etendue():
    assert CIBLE.etendue((0.0, 1.0, 0.0)) == pytest.approx((0, 19))
    assert CIBLE.agrandie(1).etendue((1.0, 0.0, 0.0)) == pytest.approx((-1, 201))


def test_boite_selon_des_axes():
    b = Boite.selon(((1.0, 0, 0), (0, 1.0, 0), (0, 0, 1.0)), [(0, 0, 0), (10, 2, 0), (5, 1, 4)])
    assert b.centre == pytest.approx((5, 1, 2)) and b.demi == pytest.approx((5, 1, 2))
