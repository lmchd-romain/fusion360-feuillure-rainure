"""Les deux cas de la description, chiffrés sur les fichiers de l'utilisateur (`exemples/`)."""

import pytest
from feuillure_rainure.calcul import CHEVAUCHEMENT, CONTACT, FEUILLURE, RAINURE, analyser, contact
from feuillure_rainure.geometrie import Boite, Polyedre
from formes import (
    ARRETEE,
    ARRETEE_CONTACT,
    CIBLE,
    TRAVERSANTE,
    TRAVERSANTE_CONTACT,
    VOLUME_CIBLE_APRES,
    VOLUME_CIBLE_AVANT,
    tourner,
)

JEU, PROFONDEUR = 0.3, 10.0


def _usinage(outils: tuple[Boite, ...], cible: Boite) -> list[Polyedre]:
    return [o.couper(cible) for o in outils]


def _bornes(p: Polyedre) -> list[float]:
    """xmin, xmax, ymin, ymax, zmin, zmax."""
    return [v for axe in ((1.0, 0, 0), (0, 1.0, 0), (0, 0, 1.0)) for v in p.etendue(axe)]


def _volume_enleve(analyses, cible) -> float:
    """Volume de l'union des usinages : ici, chaque armature ajoute sa plus grande boîte (les autres y
    sont incluses)."""
    total = 0.0
    for a in analyses:
        total += max(p.volume() for p in _usinage(a.outils, cible))
    return total


def test_chevauchement_rainure_sur_toute_la_hauteur():
    a = analyser(TRAVERSANTE, CIBLE, JEU, PROFONDEUR)
    assert a.utilisable and a.mode == CHEVAUCHEMENT and a.type == RAINURE
    assert (a.enfoncement, a.largeur, a.profondeur) == pytest.approx((10, 19.6, 10.3))
    assert a.allongement == 0 and a.tranche is None and not a.traversante
    assert _bornes(_usinage(a.outils, CIBLE)[0]) == pytest.approx([53.7, 73.3, 8.7, 19, -200, 0])


def test_chevauchement_rainure_arretee():
    a = analyser(ARRETEE, CIBLE, JEU, PROFONDEUR)
    assert a.type == RAINURE
    assert _bornes(_usinage(a.outils, CIBLE)[0]) == pytest.approx([126.7, 146.3, 8.7, 19, -153.441, -46.559])


def test_le_volume_enleve_est_celui_de_l_exemple():
    analyses = [analyser(b, CIBLE, JEU, PROFONDEUR) for b in (TRAVERSANTE, ARRETEE)]
    assert VOLUME_CIBLE_AVANT - _volume_enleve(analyses, CIBLE) == pytest.approx(VOLUME_CIBLE_APRES, abs=0.01)


def test_contact_allonge_l_armature_de_la_profondeur():
    a = analyser(TRAVERSANTE_CONTACT, CIBLE, JEU, PROFONDEUR)
    assert a.utilisable and a.mode == CONTACT and a.type == RAINURE
    assert a.allongement == pytest.approx(10)
    assert a.entree == pytest.approx((0, -1, 0))
    assert _bornes(a.tranche.polyedre()) == pytest.approx([54, 73, 9, 19, -200, 0])


def test_contact_donne_le_meme_resultat_que_l_exemple():
    analyses = [analyser(b, CIBLE, JEU, PROFONDEUR) for b in (TRAVERSANTE_CONTACT, ARRETEE_CONTACT)]
    assert VOLUME_CIBLE_AVANT - _volume_enleve(analyses, CIBLE) == pytest.approx(VOLUME_CIBLE_APRES, abs=0.01)
    arretee = max(_usinage(analyses[1].outils, CIBLE), key=lambda p: p.volume())
    assert _bornes(arretee) == pytest.approx([126.7, 146.3, 8.7, 19, -153.441, -46.559])


def test_jeu_nul_comme_le_booleen_actuel():
    a = analyser(TRAVERSANTE, CIBLE, 0.0, PROFONDEUR)
    assert a.profondeur == pytest.approx(10) and a.largeur == pytest.approx(19)


def test_feuillure_au_bord_de_la_cible():
    cote = Boite.alignee((0, 0, 0), (19, 400, 700))
    fond = Boite.alignee((10, 392, 0), (590, 400, 700))  # rentre de 9 dans le chant intérieur, au ras du dos
    a = analyser(fond, cote, JEU, PROFONDEUR)
    assert a.mode == CHEVAUCHEMENT and a.type == FEUILLURE
    assert (a.enfoncement, a.largeur, a.profondeur) == pytest.approx((9, 8.3, 9.3))


def test_feuillure_en_contact():
    cote = Boite.alignee((0, 0, 0), (19, 400, 700))
    fond = Boite.alignee((19, 392, 0), (590, 400, 700))
    a = analyser(fond, cote, JEU, 8)
    assert a.mode == CONTACT and a.type == FEUILLURE
    assert a.allongement == pytest.approx(8) and a.profondeur == pytest.approx(8.3)


def test_mortaise_traversante():
    a = analyser(Boite.alignee((54, -50, -100), (73, 100, -50)), CIBLE, JEU, PROFONDEUR)
    assert a.traversante and a.profondeur == pytest.approx(19)


def test_armature_loin_de_la_cible():
    a = analyser(Boite.alignee((300, 0, 0), (319, 100, 100)), CIBLE, JEU, PROFONDEUR)
    assert a.probleme == "erreur.pas_de_contact" and not a.outils


def test_contact_par_une_arete_seulement():
    a = analyser(Boite.alignee((200, 19, -10), (219, 100, 0)), CIBLE, JEU, PROFONDEUR)
    assert a.probleme == "erreur.pas_de_contact"


def test_profondeur_plus_grande_que_la_cible():
    a = analyser(TRAVERSANTE_CONTACT, CIBLE, JEU, 19)
    assert a.probleme == "erreur.profondeur_trop_grande" and a.enfoncement == pytest.approx(19)


def test_profondeur_nulle_en_contact():
    assert analyser(TRAVERSANTE_CONTACT, CIBLE, JEU, 0).probleme == "erreur.profondeur_nulle"


def test_jeu_negatif():
    assert analyser(TRAVERSANTE, CIBLE, -0.1, PROFONDEUR).probleme == "erreur.jeu_negatif"


def test_armature_entierement_dans_la_cible():
    a = analyser(Boite.alignee((10, 2, -20), (20, 10, -10)), CIBLE, JEU, PROFONDEUR)
    assert a.probleme == "erreur.armature_dans_la_cible"


@pytest.mark.parametrize("angle", [30, -47, 90])
def test_caisson_tourne(angle):
    cible = tourner(CIBLE, angle, centre=(100, 0, 0))
    a = analyser(tourner(TRAVERSANTE, angle, centre=(100, 0, 0)), cible, JEU, PROFONDEUR)
    assert a.mode == CHEVAUCHEMENT and a.type == RAINURE
    assert (a.enfoncement, a.largeur, a.profondeur) == pytest.approx((10, 19.6, 10.3))
    c = analyser(tourner(TRAVERSANTE_CONTACT, angle, centre=(100, 0, 0)), cible, JEU, PROFONDEUR)
    assert c.mode == CONTACT and c.allongement == pytest.approx(10)
    assert c.tranche.couper(cible).volume() == pytest.approx(19 * 10 * 200)


def test_recalcul_contact_devenu_chevauchement():
    """Une armature posée en contact, allongée en amont de 4 mm : elle ne s'allonge plus que de 6."""
    plus_longue = Boite.alignee((54, 15, -200), (73, 232.42, 0))
    a = analyser(plus_longue, CIBLE, JEU, PROFONDEUR, CONTACT, (0.0, -1.0, 0.0))
    assert a.utilisable and a.allongement == pytest.approx(6) and a.profondeur == pytest.approx(10.3)


def test_recalcul_contact_deja_assez_profond():
    a = analyser(TRAVERSANTE, CIBLE, JEU, 5, CONTACT, (0.0, -1.0, 0.0))
    assert a.utilisable and a.allongement == 0 and a.tranche is None


def test_recalcul_contact_ecarte():
    ecartee = Boite.alignee((54, 25, -200), (73, 232.42, 0))
    a = analyser(ecartee, CIBLE, JEU, PROFONDEUR, CONTACT, (0.0, -1.0, 0.0))
    assert a.probleme == "erreur.pas_de_contact" and a.outils  # la découpe garde un outil, sans effet


def test_recalcul_chevauchement_perdu():
    a = analyser(TRAVERSANTE_CONTACT, CIBLE, JEU, PROFONDEUR, CHEVAUCHEMENT)
    assert a.probleme == "erreur.plus_de_chevauchement" and len(a.outils) == 1


def test_recalcul_contact_sans_direction():
    assert analyser(TRAVERSANTE_CONTACT, CIBLE, JEU, PROFONDEUR, CONTACT).probleme == "erreur.entree_perdue"


def test_contact_trouve_la_bonne_face():
    k, s, aire = contact(TRAVERSANTE_CONTACT, CIBLE)
    assert TRAVERSANTE_CONTACT.normale(k, s) == pytest.approx((0, -1, 0))
    assert aire == pytest.approx(19 * 200)


def test_contact_malgre_un_jour_de_quelques_microns():
    """Fusion arrondit : une armature posée à 0,01 mm de la cible est en contact."""
    posee = Boite.alignee((54, 19.01, -200), (73, 232.42, 0))
    a = analyser(posee, CIBLE, JEU, PROFONDEUR)
    assert a.utilisable and a.mode == CONTACT and a.allongement == pytest.approx(10.01)


def test_contact_malgre_un_chevauchement_de_quelques_microns():
    """Un chevauchement de 0,01 mm est un contact, pas une rainure de 0,01."""
    posee = Boite.alignee((54, 18.99, -200), (73, 232.42, 0))
    a = analyser(posee, CIBLE, JEU, PROFONDEUR)
    assert a.utilisable and a.mode == CONTACT and a.profondeur == pytest.approx(10.3)


def test_jour_reel_pas_de_contact():
    ecartee = Boite.alignee((54, 19.2, -200), (73, 232.42, 0))
    assert analyser(ecartee, CIBLE, JEU, PROFONDEUR).probleme == "erreur.pas_de_contact"


def test_une_armature_entre_deux_cibles():
    """Étagère posée entre deux côtés : contact aux deux bouts, allongée de chaque côté."""
    gauche = Boite.alignee((0, 0, 0), (19, 300, 700))
    droite = Boite.alignee((581, 0, 0), (600, 300, 700))
    etagere = Boite.alignee((19, 0, 300), (581, 300, 319))
    for cote, sortie in ((gauche, (-1, 0, 0)), (droite, (1, 0, 0))):
        a = analyser(etagere, cote, JEU, PROFONDEUR)
        assert a.mode == CONTACT and a.type == RAINURE and a.entree == pytest.approx(sortie)
        assert a.tranche.couper(cote).volume() == pytest.approx(10 * 300 * 19)
        rainure = max((o.couper(cote) for o in a.outils), key=lambda p: p.volume())
        assert rainure.volume() == pytest.approx(10.3 * 300 * 19.6)
