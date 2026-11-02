"""La recette se charge sans Fusion (faux `adsk`) et son rapport Markdown se lit."""

import importlib.util
import sys
import types
from pathlib import Path
from unittest import mock

RECETTE = Path(__file__).resolve().parents[1] / "essai" / "recette" / "recette.py"


def _charger(monkeypatch):
    adsk = types.ModuleType("adsk")
    adsk.core, adsk.fusion = mock.MagicMock(), mock.MagicMock()
    for n, m in (("adsk", adsk), ("adsk.core", adsk.core), ("adsk.fusion", adsk.fusion)):
        monkeypatch.setitem(sys.modules, n, m)
    spec = importlib.util.spec_from_file_location("recette_essai", RECETTE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rapport_markdown(monkeypatch):
    r = _charger(monkeypatch)
    rapport = {
        "fusion": "2706.1.17",
        "date": "20261102-120000",
        "addin_version": "0.1.0",
        "langue": "fr",
        "compte": {r.OK: 1, r.KO: 1, r.A_REGARDER: 0},
        "verifications": [
            {"ref": "R1", "titre": "a", "statut": r.OK, "mesure": [1], "attendu": "1", "detail": ""},
            {"ref": "R2", "titre": "b", "statut": r.KO, "mesure": None, "attendu": "2", "detail": "Trace"},
        ],
        "captures": [{"ref": "R3", "fichier": "x.png", "regarder": "regarder", "ecrite": True}],
        "a_la_main": [{"ref": "M1", "geste": "geste"}],
    }
    texte = r.markdown(rapport)
    assert "1 OK · 1 KO · 0 à regarder" in texte
    assert "## Détails des KO" in texte and "Trace" in texte
    assert "- M1 : geste" in texte


def test_volumes_attendus_coherents(monkeypatch):
    r = _charger(monkeypatch)
    assert abs((r.CIBLE_AVANT - r.CIBLE_APRES) - (19.6 * 10.3 * 200 + 19.6 * 10.3 * 106.882)) < 0.01
