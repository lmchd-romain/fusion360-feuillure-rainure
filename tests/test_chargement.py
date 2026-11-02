"""Chargement de l'add-in sans Fusion : un faux module `adsk` (mocks) remplace l'API.

Vérifie que le point d'entrée s'importe, que `run()` puis `stop()` passent sans exception, que les
handlers restent référencés puis sont vidés, et qu'une panne d'import s'écrit dans `demarrage.log`.
Ne prouve rien sur le comportement réel dans Fusion.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest import mock

import pytest

ADDIN = Path(__file__).resolve().parents[1] / "FeuillureRainure"
PAQUET = "feuillure_rainure"


def _faux_module(nom: str) -> types.ModuleType:
    """Module dont chaque attribut est un mock, sauf les classes de handlers, vraies classes à dériver."""
    module = types.ModuleType(nom)
    cache: dict = {}

    def __getattr__(attr):
        if attr.startswith("__"):
            raise AttributeError(attr)
        if attr not in cache:
            cache[attr] = type(attr, (), {}) if attr.endswith("Handler") else mock.MagicMock(name=f"{nom}.{attr}")
        return cache[attr]

    module.__getattr__ = __getattr__
    return module


def _purger() -> None:
    for nom in [n for n in sys.modules if n == PAQUET or n.startswith(PAQUET + ".")]:
        del sys.modules[nom]


_open_reel = Path.open


def _ouvrir_hors_addin(tmp_path):
    """Pendant l'import, `demarrage.log` serait écrit dans le dossier de l'add-in : on le détourne."""

    def ouvrir(self, *args, **kwargs):
        if self.name == "demarrage.log":
            self = tmp_path / "demarrage.log"
        return _open_reel(self, *args, **kwargs)

    return ouvrir


def _charger(monkeypatch, tmp_path, nom="FeuillureRainure_essai"):
    adsk = types.ModuleType("adsk")
    adsk.core, adsk.fusion = _faux_module("adsk.core"), _faux_module("adsk.fusion")
    adsk.doEvents = mock.MagicMock()
    for n, module in (("adsk", adsk), ("adsk.core", adsk.core), ("adsk.fusion", adsk.fusion)):
        monkeypatch.setitem(sys.modules, n, module)
    adsk.core.Application.get.return_value.userInterface.commandDefinitions.itemById.return_value = None
    monkeypatch.setattr(sys, "path", list(sys.path))
    spec = importlib.util.spec_from_file_location(nom, ADDIN / "FeuillureRainure.py")
    entree = importlib.util.module_from_spec(spec)
    monkeypatch.setattr(Path, "open", _ouvrir_hors_addin(tmp_path), raising=True)
    spec.loader.exec_module(entree)
    monkeypatch.setattr(entree, "_JOURNAL_DEMARRAGE", tmp_path / "demarrage.log")
    from feuillure_rainure import journal

    journal.fermer()
    monkeypatch.setattr(journal, "FICHIER", tmp_path / "journal.log")
    return entree, adsk


@pytest.fixture
def addin(monkeypatch, tmp_path):
    entree, adsk = _charger(monkeypatch, tmp_path)
    yield entree, adsk, tmp_path
    from feuillure_rainure import journal

    journal.fermer()
    _purger()


def _lire(chemin: Path) -> str:
    return chemin.read_text(encoding="utf-8") if chemin.exists() else ""


def test_run_puis_stop(addin):
    entree, _adsk, dossier = addin
    from feuillure_rainure import commande, fonction

    entree.run(None)
    assert commande._handlers and len(fonction._handlers) == 2  # réédition + calcul
    assert commande._controle is not None
    entree.stop(None)
    assert not (commande._handlers or fonction._handlers)
    assert commande._definition is None and commande._controle is None
    assert not (dossier / "demarrage.log").exists()
    assert "arrêt de FeuillureRainure" in _lire(dossier / "journal.log")


def test_run_deux_fois_sans_doublon(addin):
    entree, _adsk, _ = addin
    from feuillure_rainure import commande, fonction

    entree.run(None)
    entree.run(None)
    assert len(commande._handlers) == 1 and len(fonction._handlers) == 2
    entree.stop(None)


def test_stop_libere_le_journal(addin):
    entree, _adsk, _ = addin
    from feuillure_rainure import journal

    entree.run(None)
    entree.stop(None)
    assert not journal._les_notres()


def test_panneau_absent_n_empeche_pas_le_demarrage(addin):
    entree, adsk, dossier = addin
    from feuillure_rainure import commande

    adsk.core.Application.get.return_value.userInterface.allToolbarPanels.itemById.return_value = None
    entree.run(None)
    assert commande._definition is not None
    assert "SolidModifyPanel" in _lire(dossier / "journal.log")
    entree.stop(None)


def test_stop_continue_malgre_une_erreur(addin):
    entree, _adsk, dossier = addin
    from feuillure_rainure import commande

    entree.run(None)
    commande._controle.deleteMe.side_effect = RuntimeError("déjà retiré")
    entree.stop(None)
    assert commande._definition is None
    assert "déjà retiré" in _lire(dossier / "demarrage.log")


def test_panne_d_import_ecrite_dans_demarrage_log(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "adsk", None)  # import adsk → ImportError
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(Path, "open", _ouvrir_hors_addin(tmp_path))
    spec = importlib.util.spec_from_file_location("FeuillureRainure_sans_adsk", ADDIN / "FeuillureRainure.py")
    entree = importlib.util.module_from_spec(spec)
    with pytest.raises(ImportError):
        spec.loader.exec_module(entree)
    assert "échec des imports" in _lire(tmp_path / "demarrage.log")
    _purger()


def test_dialogue_qui_plante_a_l_ouverture_le_dit(addin, monkeypatch):
    entree, adsk, dossier = addin
    from feuillure_rainure import commande, fusion_api

    entree.run(None)
    monkeypatch.setattr(commande, "_remplir", mock.MagicMock(side_effect=RuntimeError("champ refusé")))
    commande._Creation().notify(mock.MagicMock())
    message = adsk.core.Application.get.return_value.userInterface.messageBox
    assert message.called and "champ refusé" in message.call_args[0][0]
    assert "champ refusé" in _lire(dossier / "journal.log")
    assert fusion_api.SANS_BOITE is False
    entree.stop(None)
