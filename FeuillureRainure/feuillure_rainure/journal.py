"""Journal texte de l'add-in : `FeuillureRainure/journal.log` (créations, recalculs, erreurs, durées)."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

FICHIER = Path(__file__).resolve().parents[1] / "journal.log"
_journal = logging.getLogger("feuillure_rainure")
_journal.propagate = False  # le journal de Fusion (ou d'un autre add-in) ne reçoit pas nos lignes


def journal() -> logging.Logger:
    """Le journal, ouvert au premier appel. Fichier impossible à ouvrir (dossier en lecture seule,
    fichier verrouillé) : les messages sont perdus, mais l'appelant ne lève jamais ; il écrit souvent
    depuis un `except` qui doit encore afficher son message à l'utilisateur."""
    if not _les_notres():
        try:
            sortie = RotatingFileHandler(FICHIER, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        except OSError:
            sortie = logging.NullHandler()
        sortie.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        sortie.feuillure_rainure = True
        _journal.addHandler(sortie)
        _journal.setLevel(logging.INFO)
    return _journal


def fermer() -> None:
    """À l'arrêt : libère journal.log. Le journal survit au rechargement des modules (registre de
    `logging`) : sans cela, le fichier resterait ouvert par l'ancien code."""
    for sortie in _les_notres():
        _journal.removeHandler(sortie)
        sortie.close()


def _les_notres() -> list[logging.Handler]:
    """Nos sorties seulement : un outil (pytest, débogueur) peut en greffer d'autres sur ce journal."""
    return [h for h in _journal.handlers if getattr(h, "feuillure_rainure", False)]
