"""Dialogue de réédition, joué sans Fusion : ce que l'essai du 2026-11-02 a montré (activation rappelée,
« Cibles » passée de 2 à 5, armature restée en surbrillance après Échap) ne doit plus arriver."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from test_chargement import _charger, _purger


class Corps:
    def __init__(self, nom):
        self.nom = nom

    def __repr__(self):
        return self.nom


class Ligne:
    """Fausse ligne de sélection : garde ses entités et ce qu'on lui a fait."""

    def __init__(self, journal, nom, entites=()):
        self.entites, self.journal, self.nom = list(entites), journal, nom

    @property
    def selectionCount(self):  # noqa: N802 (nom de l'API Fusion)
        return len(self.entites)

    def selection(self, i):
        return SimpleNamespace(entity=self.entites[i])

    def clearSelection(self):  # noqa: N802
        self.entites.clear()
        self.journal.append(("vider", self.nom))

    def addSelection(self, e):  # noqa: N802
        self.entites.append(e)
        return True


@pytest.fixture
def dialogue(monkeypatch, tmp_path):
    _entree, adsk = _charger(monkeypatch, tmp_path)
    from feuillure_rainure import commande, journal, langues

    langues.choisir("fr")
    adsk.fusion.BRepBody.cast.side_effect = lambda e: e if isinstance(e, Corps) else None
    adsk.fusion.Occurrence.cast.side_effect = lambda e: None
    adsk.core.SelectionCommandInput.cast.side_effect = lambda e: e
    adsk.core.CommandEventArgs.cast.side_effect = lambda a: a
    monkeypatch.setattr(commande, "meme_piece", lambda a, b: a is b)
    monkeypatch.setattr(commande, "en_contexte", lambda e: e)
    trace: list = []
    lignes = {"armature": Ligne(trace, "armature"), "cibles": Ligne(trace, "cibles")}
    entrees = SimpleNamespace(itemById=lambda ident: lignes.get(ident))
    cmd = SimpleNamespace(commandInputs=entrees, beginStep=lambda: trace.append("etape"))
    commande._dialogue.clear()
    commande._dialogue.update(commande=cmd, graphiques=SimpleNamespace(effacer=lambda: None))
    yield commande, lignes, trace, cmd
    commande._dialogue.clear()
    journal.fermer()
    _purger()


def test_nettoyer_cibles(dialogue):
    commande, lignes, _, cmd = dialogue
    a, t1, t2 = Corps("Etagere"), Corps("Gauche"), Corps("Droite")
    lignes["armature"].entites = [a]
    lignes["cibles"].entites = [t1, t2, a, t1, t2]
    assert commande._nettoyer_cibles(cmd.commandInputs)
    assert lignes["cibles"].entites == [t1, t2]
    assert not commande._nettoyer_cibles(cmd.commandInputs)  # déjà propre : rien à refaire


def test_activation_rappelee_ne_remet_rien(dialogue, monkeypatch):
    commande, lignes, trace, cmd = dialogue
    a, t1, t2 = Corps("Etagere"), Corps("Gauche"), Corps("Droite")
    marqueurs, reculs = [], []

    class Marqueur:
        def __init__(self, timeline):
            marqueurs.append(self)

        def rendre(self):
            trace.append("rendre")

    monkeypatch.setattr(commande, "Marqueur", Marqueur)
    monkeypatch.setattr(commande, "design_actif", lambda: SimpleNamespace(timeline=None))
    monkeypatch.setattr(commande.fonction, "reculer_avant", lambda f: reculs.append(f))
    monkeypatch.setattr(commande.fonction, "pieces_de", lambda f: (a, [t1, t2], []))
    monkeypatch.setattr(commande, "_analyser", lambda entrees: None)
    commande._dialogue["edition"] = {"fonction": "ligne"}
    activation = commande._EditionActivee()
    activation.notify(SimpleNamespace(command=cmd))
    activation.notify(SimpleNamespace(command=cmd))  # Fusion rappelle activate
    assert len(marqueurs) == 1 and len(reculs) == 1 and trace.count("etape") == 1
    assert lignes["armature"].entites == [a] and lignes["cibles"].entites == [t1, t2]


def test_echap_vide_les_selections_avant_de_rendre_la_timeline(dialogue, monkeypatch):
    commande, lignes, trace, _ = dialogue
    lignes["armature"].entites = [Corps("Etagere")]
    monkeypatch.setattr(
        commande,
        "ui",
        lambda: SimpleNamespace(
            activeSelections=SimpleNamespace(clear=lambda: trace.append("vider la sélection générale"))
        ),
    )
    commande._dialogue["edition"] = {
        "fonction": "ligne",
        "marqueur": SimpleNamespace(rendre=lambda: trace.append("rendre")),
    }
    commande._Fermeture().notify(None)
    assert trace == [("vider", "armature"), ("vider", "cibles"), "vider la sélection générale", "rendre"]
    assert not lignes["armature"].entites and not commande._dialogue
