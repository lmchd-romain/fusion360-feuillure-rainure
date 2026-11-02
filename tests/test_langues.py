"""Traductions : mêmes clés et mêmes variables dans les quatre langues, chaque clé du code présente."""

import json
import re
from pathlib import Path

import pytest
from feuillure_rainure import langues

DOSSIER = Path(__file__).resolve().parents[1] / "FeuillureRainure" / "ressources" / "langues"
CODE = Path(__file__).resolve().parents[1] / "FeuillureRainure" / "feuillure_rainure"


def _textes(code):
    return json.loads((DOSSIER / f"{code}.json").read_text(encoding="utf-8"))


def _variables(texte):
    return sorted(set(re.findall(r"\{(\w+)\}", texte)))


@pytest.mark.parametrize("code", langues.LANGUES)
def test_memes_cles_que_l_anglais(code):
    assert set(_textes(code)) == set(_textes("en"))


@pytest.mark.parametrize("code", langues.LANGUES)
def test_memes_variables_que_l_anglais(code):
    en, autre = _textes("en"), _textes(code)
    assert not {k: v for k, v in autre.items() if _variables(v) != _variables(en[k])}


@pytest.mark.parametrize("code", langues.LANGUES)
def test_aucun_texte_vide(code):
    assert all(v.strip() for v in _textes(code).values())


def test_toutes_les_cles_du_code_existent():
    en = _textes("en")
    sources = "".join(p.read_text(encoding="utf-8") for p in CODE.glob("*.py"))
    for cle in re.findall(r'\bt\("([a-z_.]+)"', sources):
        assert cle in en, cle
    for cle in re.findall(r'\btn\(\s*"([a-z_.]+)"', sources):
        assert f"{cle}.un" in en and f"{cle}.plusieurs" in en, cle
    for cle in re.findall(r'"((?:etape|erreur)\.[a-z_]+)"', sources):
        assert cle in en, cle


def test_secours_anglais_puis_cle(monkeypatch):
    langues.choisir("de")
    monkeypatch.setitem(langues._textes, "commande.nom", "")
    assert langues.t("commande.nom") == "Rabbet / groove"
    assert langues.t("cle.inconnue") == "cle.inconnue"


def test_variable_absente_ne_leve_pas():
    langues.choisir("fr")
    assert "{etape}" in langues.t("erreur.refuse")
