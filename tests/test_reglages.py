"""Réglages : JSON tolérant, derniers réglages, noms de timeline, résumé du dialogue."""

import pytest
from feuillure_rainure import langues
from feuillure_rainure.calcul import analyser
from feuillure_rainure.erreurs import ErreurFeuillure
from feuillure_rainure.geometrie import Boite
from feuillure_rainure.reglages import (
    Reglages,
    depuis_json,
    ecrire_derniers,
    expression_mm,
    lire_derniers,
    nom_fonction,
    nombre,
    resume,
    vers_json,
)
from formes import ARRETEE, CIBLE, TRAVERSANTE, TRAVERSANTE_CONTACT


def test_aller_retour_json():
    r = Reglages(jeu=0.2, profondeur=8, expression_jeu="jeu_rainure")
    assert depuis_json(vers_json(r)) == r


def test_json_tolerant():
    r = depuis_json('{"jeu": "beaucoup", "profondeur": -3, "inconnu": 1, "expression_jeu": 5}')
    assert r == Reglages()


def test_json_illisible():
    with pytest.raises(ErreurFeuillure):
        depuis_json("pas du json")
    with pytest.raises(ErreurFeuillure):
        depuis_json("[1, 2]")


def test_derniers_reglages(tmp_path):
    chemin = tmp_path / "derniers_reglages.json"
    assert lire_derniers(chemin) == Reglages()
    ecrire_derniers(chemin, Reglages(jeu=0.5))
    assert lire_derniers(chemin).jeu == 0.5
    chemin.write_text("{abîmé", encoding="utf-8")
    assert lire_derniers(chemin) == Reglages()


def test_nombre_selon_la_langue():
    assert nombre(0.3) == "0,3" and nombre(10.0) == "10" and nombre(19.6) == "19,6"
    langues.choisir("en")
    assert nombre(0.3) == "0.3"


def test_expression_mm():
    assert expression_mm("", 0.3) == "0.3 mm"
    assert expression_mm(" jeu_rainure ", 0.3) == "jeu_rainure"


def test_noms_de_timeline():
    r = Reglages()
    deux = [analyser(b, CIBLE, 0.3, 10) for b in (TRAVERSANTE, ARRETEE)]
    assert nom_fonction(deux, r, "Étagère") == "Rainure ×2 · Étagère · jeu 0,3"
    assert nom_fonction(deux[:1], r, "Étagère") == "Rainure · Étagère · jeu 0,3"
    fond = analyser(*_feuillure(), 0.3, 10)
    assert nom_fonction([fond], r, "Fond") == "Feuillure · Fond · jeu 0,3"
    assert nom_fonction([fond, deux[0]], r, "Fond") == "Feuillure + rainure ×2 · Fond · jeu 0,3"


def _feuillure():
    from feuillure_rainure.geometrie import Boite

    return Boite.alignee((10, 392, 0), (590, 400, 700)), Boite.alignee((0, 0, 0), (19, 400, 700))


def test_resume_du_dialogue():
    """Une ligne par cible : son nom, l'usinage, ce que devient l'armature."""
    loin = Boite.alignee((300, 0, 0), (310, 5, 5))
    texte = resume(
        [
            ("Côté gauche", analyser(TRAVERSANTE, CIBLE, 0.3, 10)),
            ("Côté droit", analyser(TRAVERSANTE_CONTACT, CIBLE, 0.3, 10)),
            ("Dessus", analyser(loin, CIBLE, 0.3, 10)),
        ]
    )
    lignes = texte.splitlines()
    assert lignes[0] == "Côté gauche : rainure 19,6 × 10,3 mm (chevauchement de 10 mm, armature inchangée)"
    assert lignes[1] == "Côté droit : rainure 19,6 × 10,3 mm (armature allongée de 10 mm)"
    assert lignes[2] == "Dessus : l'armature ne la touche pas"
    assert lignes[3] == "2 cibles prêtes"


def test_resume_vide():
    assert resume([]) == "Choisissez l'armature, puis les cibles."
