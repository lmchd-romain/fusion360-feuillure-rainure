"""Enchaînement de la création, joué sans Fusion : faux `adsk`, et les appels qui touchent au modèle
remplacés par un enregistreur. Vérifie qui est créé, dans quel composant, dans quel ordre, avec quels
corps de la base, et que le calcul et la réédition en place tournent. Ne prouve rien sur Fusion lui-même :
c'est la recette (`essai/recette`) qui le fait.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from formes import CIBLE, TRAVERSANTE, TRAVERSANTE_CONTACT
from test_chargement import _charger, _purger


@pytest.fixture
def module(monkeypatch, tmp_path):
    _charger(monkeypatch, tmp_path)
    from feuillure_rainure import fonction, journal, langues

    langues.choisir("fr")  # module rechargé : sa langue repart de l'anglais
    yield fonction
    journal.fermer()
    _purger()


class Corps:
    """Un corps vu par le module : un nom et son composant."""

    def __init__(self, nom, composant):
        self.nom, self.composant = nom, composant
        self.isValid = True

    def __repr__(self):
        return self.nom


def _enregistrer(fonction, monkeypatch, boites):
    """Remplace ce qui touche au modèle ; rend le journal des opérations."""
    journal: list[tuple] = []
    bases: dict = {}

    class Base:
        def __init__(self, composant, corps):
            self.composant, self.corps = composant, corps
            self.bodies = SimpleNamespace(count=len(corps), item=lambda i: f"{composant}#{i}")

    def base(composant, corps):
        b = Base(composant, corps)
        journal.append(("base", composant, len(corps)))
        bases[composant] = b
        return b

    def fonction_(composant, base_, dependances, attributs, nom):
        journal.append(("fonction", composant, attributs["role"], [i for i, _ in dependances]))
        return SimpleNamespace(composant=composant, attributs=attributs, name=nom, entityToken=composant)

    def combiner(composant, cible, outils, operation, etape):
        journal.append(("combinaison", composant, str(cible), list(outils), etape))
        return SimpleNamespace(composant=composant)

    def regrouper(f, debut, fin):
        journal.append(("regroupement", f.composant))

    monkeypatch.setattr(fonction, "_base", base)
    monkeypatch.setattr(fonction, "_fonction", fonction_)
    monkeypatch.setattr(fonction, "_combiner", combiner)
    monkeypatch.setattr(fonction, "regrouper", regrouper)
    monkeypatch.setattr(fonction, "verifier", lambda plan: None)
    monkeypatch.setattr(fonction, "composant_de", lambda c: c.composant)
    monkeypatch.setattr(fonction, "boite_monde", lambda c: boites[c.nom])
    monkeypatch.setattr(fonction, "matrice_monde", lambda c: "matrice")
    monkeypatch.setattr(fonction, "direction_locale", lambda c, v: v)
    monkeypatch.setattr(fonction, "_reperer", lambda c: ("jeton", None))
    monkeypatch.setattr(fonction, "_relire", lambda design, c, r: c)
    monkeypatch.setattr(fonction, "_corps_de_base", lambda base_, inst, rang: f"{base_.composant}#{rang}")
    monkeypatch.setattr(fonction, "allongement", lambda a, b, m: "allongement")
    monkeypatch.setattr(fonction, "outil_de_coupe", lambda a, b, m: "outil")
    monkeypatch.setattr(fonction, "remplissage", lambda p, m: "remplissage")
    design = SimpleNamespace(timeline=SimpleNamespace(markerPosition=3, count=3))
    monkeypatch.setattr(fonction, "design_parametrique", lambda: design)
    return journal, bases


def _plan(fonction, armature, cibles, boites):
    from feuillure_rainure.calcul import analyser
    from feuillure_rainure.reglages import Reglages

    r = Reglages()
    analyses = [analyser(boites[armature.nom], boites[c.nom], r.jeu, r.profondeur) for c in cibles]
    return fonction.Plan(
        fonction.Piece(armature, armature.nom), [fonction.Piece(c, c.nom) for c in cibles], analyses, r
    )


def test_etagere_entre_deux_cotes(module, monkeypatch):
    from feuillure_rainure.geometrie import Boite

    boites = {
        "Gauche": Boite.alignee((0, 0, 0), (19, 300, 700)),
        "Droite": Boite.alignee((581, 0, 0), (600, 300, 700)),
        "Etagere": Boite.alignee((19, 0, 300), (581, 300, 319)),
    }
    journal, bases = _enregistrer(module, monkeypatch, boites)
    etagere = Corps("Etagere", "E")
    plan = _plan(module, etagere, [Corps("Gauche", "G"), Corps("Droite", "D")], boites)
    f = module.creer(plan)
    assert journal == [
        ("base", "E", 2),  # un allongement par cible en contact
        ("fonction", "E", "armature", ["armature", "cible_0", "cible_1"]),
        ("base", "G", 1),
        ("fonction", "G", "cible", ["armature", "cible"]),
        ("combinaison", "G", "Gauche", ["G#0"], "etape.decoupe"),
        ("regroupement", "G"),
        ("base", "D", 1),
        ("fonction", "D", "cible", ["armature", "cible"]),
        ("combinaison", "D", "Droite", ["D#0"], "etape.decoupe"),
        ("regroupement", "D"),
        ("combinaison", "E", "Etagere", ["E#0", "E#1"], "etape.allongement"),
        ("regroupement", "E"),
    ]
    infos = json.loads(f.attributs["cibles"])
    assert [i["mode"] for i in infos] == ["contact", "contact"]
    assert [i["allongement"] for i in infos] == [0, 1] and f.attributs["remplissage"] == "-1"
    assert f.name == "Rainure ×2 · Etagere · jeu 0,3"


def test_chevauchement_seul_et_cible_du_meme_composant(module, monkeypatch):
    """Aucune cible en contact : la jonction prend le petit cube ; la cible du même composant est
    découpée dans ce composant, outil pris dans la base de l'armature."""
    boites = {"Cible": CIBLE, "Traversante": TRAVERSANTE}
    journal, _ = _enregistrer(module, monkeypatch, boites)
    armature = Corps("Traversante", "A")
    f = module.creer(_plan(module, armature, [Corps("Cible", "A")], boites))
    assert journal == [
        ("base", "A", 2),  # [0] petit cube, [1] outil de la cible du même composant
        ("fonction", "A", "armature", ["armature", "cible_0"]),
        ("combinaison", "A", "Cible", ["A#1"], "etape.decoupe"),
        ("combinaison", "A", "Traversante", ["A#0"], "etape.allongement"),
        ("regroupement", "A"),
    ]
    infos = json.loads(f.attributs["cibles"])
    assert infos == [{"mode": "chevauchement", "allongement": -1, "outil": 1}]
    assert f.attributs["remplissage"] == "0"


def test_contact_dans_un_autre_composant(module, monkeypatch):
    boites = {"Cible": CIBLE, "Traversante": TRAVERSANTE_CONTACT}
    journal, _ = _enregistrer(module, monkeypatch, boites)
    module.creer(_plan(module, Corps("Traversante", "A"), [Corps("Cible", "C")], boites))
    assert [e[0:2] for e in journal] == [
        ("base", "A"),
        ("fonction", "A"),
        ("base", "C"),
        ("fonction", "C"),
        ("combinaison", "C"),
        ("regroupement", "C"),
        ("combinaison", "A"),
        ("regroupement", "A"),
    ]


def test_cible_a_probleme_refusee(module, monkeypatch):
    from feuillure_rainure.erreurs import ErreurFeuillure
    from feuillure_rainure.geometrie import Boite

    boites = {"Cible": CIBLE, "Loin": Boite.alignee((500, 0, 0), (519, 100, 100))}
    _enregistrer(module, monkeypatch, boites)
    with pytest.raises(ErreurFeuillure):
        module.creer(_plan(module, Corps("Loin", "A"), [Corps("Cible", "C")], boites))


def test_infos_rangs(module, monkeypatch):
    """Rangs : allongements d'abord, puis le remplissage (aucun allongement), puis les outils du même composant."""
    boites = {"Cible": CIBLE, "Traversante": TRAVERSANTE_CONTACT, "Autre": CIBLE}
    _enregistrer(module, monkeypatch, boites)
    plan = _plan(module, Corps("Traversante", "A"), [Corps("Cible", "C"), Corps("Autre", "A")], boites)
    infos, remplissage = module._infos(plan)
    assert remplissage == -1
    assert [(i["allongement"], i["outil"]) for i in infos] == [(0, -1), (1, 2)]


class Attributs:
    def __init__(self, valeurs):
        self.valeurs = dict(valeurs)

    def itemByName(self, groupe, cle):  # noqa: N802 (nom de l'API Fusion)
        return SimpleNamespace(value=self.valeurs[cle]) if cle in self.valeurs else None

    def add(self, groupe, cle, valeur):
        self.valeurs[cle] = valeur


def _fonction_posee(module, monkeypatch, role, valeurs, pieces):
    """Une fonction déjà posée : attributs, et ses pièces rendues par `corps_de`."""
    f = SimpleNamespace(
        attributes=Attributs({"role": role, **valeurs}),
        name="ligne",
        nativeObject=None,
        parentComponent=SimpleNamespace(parentDesign=None),
    )
    monkeypatch.setattr(module, "_a_une_combinaison", lambda x: True)
    monkeypatch.setattr(module, "corps_de", lambda x, ident: pieces[ident])
    monkeypatch.setattr(module, "direction_monde", lambda c, v: v)
    remplacements = []
    monkeypatch.setattr(module, "_remplacer", lambda x, corps: remplacements.append(dict(corps)))
    return f, remplacements


def test_recalcul_de_l_operation(module, monkeypatch):
    from feuillure_rainure.geometrie import Boite
    from feuillure_rainure.reglages import Reglages, vers_json

    boites = {
        "Gauche": Boite.alignee((0, 0, 0), (19, 300, 700)),
        "Droite": Boite.alignee((581, 0, 0), (600, 300, 700)),
        "Etagere": Boite.alignee((19, 0, 300), (581, 300, 319)),
    }
    _enregistrer(module, monkeypatch, boites)
    infos = [
        {"mode": "contact", "allongement": 0, "outil": -1, "entree": [-1.0, 0.0, 0.0]},
        {"mode": "contact", "allongement": 1, "outil": -1, "entree": [1.0, 0.0, 0.0]},
    ]
    pieces = {"armature": Corps("Etagere", "E"), "cible_0": Corps("Gauche", "G"), "cible_1": Corps("Droite", "D")}
    valeurs = {"reglages": vers_json(Reglages()), "cibles": json.dumps(infos), "remplissage": "-1"}
    f, remplacements = _fonction_posee(module, monkeypatch, "armature", valeurs, pieces)
    assert module.recalculer(f) == 0
    assert remplacements == [{0: "allongement", 1: "allongement"}]


def test_recalcul_d_une_fonction_emboitee(module, monkeypatch):
    from feuillure_rainure.reglages import Reglages, vers_json

    boites = {"Cible": CIBLE, "Traversante": TRAVERSANTE}
    _enregistrer(module, monkeypatch, boites)
    pieces = {"armature": Corps("Traversante", "A"), "cible": Corps("Cible", "C")}
    valeurs = {"reglages": vers_json(Reglages()), "cible": json.dumps({"mode": "chevauchement"})}
    f, remplacements = _fonction_posee(module, monkeypatch, "cible", valeurs, pieces)
    assert module.recalculer(f) == 0
    assert remplacements == [{0: "outil"}]


def test_operation_v01_ignoree(module, monkeypatch):
    f, remplacements = _fonction_posee(module, monkeypatch, None, {}, {})
    f.attributes.valeurs.pop("role")
    assert module.recalculer(f) is None and not remplacements


def test_reedition_en_place(module, monkeypatch):
    """Même structure : réglages réécrits, l'opération et ses fonctions emboîtées recalculées."""
    from feuillure_rainure.reglages import Reglages, depuis_json, vers_json

    boites = {"Cible": CIBLE, "Traversante": TRAVERSANTE_CONTACT}
    _enregistrer(module, monkeypatch, boites)
    armature, cible = Corps("Traversante", "A"), Corps("Cible", "C")
    infos = [{"mode": "contact", "allongement": 0, "outil": -1, "entree": [0.0, -1.0, 0.0]}]
    valeurs = {"reglages": vers_json(Reglages()), "cibles": json.dumps(infos), "remplissage": "-1", "operation": "op"}
    pieces = {"armature": armature, "cible_0": cible, "cible": cible}  # l'opération, puis sa fonction emboîtée
    f, remplacements = _fonction_posee(module, monkeypatch, "armature", valeurs, pieces)
    emboitee = SimpleNamespace(attributes=Attributs({"role": "cible", "operation": "op"}), nativeObject=None)
    monkeypatch.setattr(module, "_fonctions_de_l_operation", lambda design, op: [f, emboitee])
    monkeypatch.setattr(module, "meme_piece", lambda a, b: a is b)
    recalculees = []
    vrai_recalcul = module.recalculer
    monkeypatch.setattr(module, "recalculer", lambda x: recalculees.append(x) or vrai_recalcul(x))
    plan = _plan(module, armature, [cible], boites)
    plan.r = Reglages(jeu=0.5)
    assert module.mettre_a_jour(f, plan) is f
    assert depuis_json(f.attributes.valeurs["reglages"]).jeu == 0.5
    assert depuis_json(emboitee.attributes.valeurs["reglages"]).jeu == 0.5
    assert json.loads(emboitee.attributes.valeurs["cible"])["mode"] == "contact"
    assert recalculees == [f, emboitee]
