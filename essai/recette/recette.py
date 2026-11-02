"""Recette automatique de FeuillureRainure, jouée dans Fusion (2026-11-02).

Lancée par Claude Desktop avec le MCP de Fusion (voir `MESSAGE.md`), ou à la main : Utilitaires →
Scripts et compléments → Scripts → « + » → ce dossier → Exécuter. L'add-in FeuillureRainure doit
tourner : la recette emprunte son code déjà chargé (`sys.modules["feuillure_rainure.…"]`).

Elle ne touche à aucun document de l'utilisateur : chaque essai se fait dans un document neuf, jamais
enregistré, fermé sans enregistrer à la fin. Chaque vérification rend OK, KO ou À REGARDER, avec ce
qui a été mesuré et ce qui était attendu ; une vérification qui plante est KO avec sa trace, les
suivantes continuent. Les pièces sont celles des fichiers `exemples/*.step` de l'utilisateur.

Ce que la recette ne prouve pas : l'aspect du dialogue et de l'icône, les clics dans la vue, Échap,
la réouverture d'un fichier sans l'add-in (liste « à la main » du rapport). La réédition est jouée
par les fonctions qu'appelle le dialogue, pas par le dialogue lui-même.

Rapport : `essai/resultats/recette-<horodatage>.json` et `.md`, captures `recette-<horodatage>-*.png`.
"""

from __future__ import annotations

import json
import math
import sys
import time
import traceback
from pathlib import Path

import adsk.core
import adsk.fusion

MM3_PAR_CM3 = 1000.0
TOL_VOLUME = 1.0  # mm³
OK, KO, A_REGARDER = "OK", "KO", "À REGARDER"
# Volumes attendus (mm³), calculés depuis exemples/*.step (voir tests/test_calcul.py)
CIBLE_AVANT = 760000.0
CIBLE_APRES = 698046.663  # exemples/apres.step : jeu 0,3, rainures 19,6 × 10,3
CIBLE_EPAISSE = CIBLE_AVANT - 25.6 * 10.3 * 200 - 19.6 * 10.3 * 106.882  # armature passée de 19 à 25
CIBLE_JEU_05 = CIBLE_AVANT - 20 * 10.5 * 200 - 20 * 10.5 * 107.282
CIBLE_ARRETEE_SEULE = CIBLE_AVANT - 19.6 * 10.3 * 106.882
TRAVERSANTE = 19 * 213.42 * 200
ARRETEE = 19 * 213.42 * 106.282
A_LA_MAIN = [
    ("M1", "Icône nette dans SOLIDE → Modifier, dans le menu et sur la ligne de timeline, thèmes clair et sombre"),
    (
        "M2",
        "Dialogue : cible puis armatures à la souris ; résumé à jour ; aperçu bleu (usinage) et orange (allongement)",
    ),
    ("M3", "Double-clic sur la ligne : dialogue prérempli ; changer le jeu, OK : la ligne reste à sa place"),
    ("M4", "Double-clic puis Échap : rien ne change, le marqueur de timeline revient au bout"),
    (
        "M5",
        "Enregistrer, fermer, arrêter l'add-in, rouvrir : le fichier s'ouvre, la géométrie reste ; relancer l'add-in",
    ),
    ("M6", "Fusion en anglais (puis redémarrer) : bouton, dialogue et nom de ligne en anglais"),
]


def _depot() -> Path:
    try:
        return Path(__file__).resolve().parents[2]
    except NameError:
        return Path.home()


def _module(nom: str):
    module = sys.modules.get(f"feuillure_rainure.{nom}")
    if module is None:
        raise RuntimeError("Add-in FeuillureRainure non lancé : Scripts et compléments → Compléments → Exécuter.")
    return module


def _vi(texte: str):
    return adsk.core.ValueInput.createByString(texte)


class Recette:
    def __init__(self):
        self.app = adsk.core.Application.get()
        self.horodatage = time.strftime("%Y%m%d-%H%M%S")
        self.dossier = _depot() / "essai" / "resultats"
        self.dossier.mkdir(parents=True, exist_ok=True)
        self.verifs: list[dict] = []
        self.captures: list[dict] = []
        self.documents: list = []

    def noter(self, ref, titre, statut, mesure, attendu, detail=""):
        self.verifs.append(
            {"ref": ref, "titre": titre, "statut": statut, "mesure": mesure, "attendu": attendu, "detail": detail}
        )

    def verifier(self, ref, titre, attendu, fonction_):
        """`fonction_()` rend (ok, mesure) ; une exception donne KO avec la trace."""
        try:
            resultat, mesure = fonction_()
            statut = resultat if resultat in (OK, KO, A_REGARDER) else (OK if resultat else KO)
            self.noter(ref, titre, statut, mesure, attendu)
        except Exception:
            self.noter(ref, titre, KO, None, attendu, traceback.format_exc(limit=8))

    def capturer(self, ref, nom, quoi_regarder):
        chemin = self.dossier / f"recette-{self.horodatage}-{nom}.png"
        try:
            vue = self.app.activeViewport
            vue.viewOrientation = adsk.core.ViewOrientations.IsoTopRightViewOrientation
            vue.fit()
            adsk.doEvents()
            ok = vue.saveAsImageFile(str(chemin), 1000, 700)
            self.captures.append({"ref": ref, "fichier": chemin.name, "regarder": quoi_regarder, "ecrite": bool(ok)})
        except Exception:
            self.captures.append(
                {
                    "ref": ref,
                    "fichier": chemin.name,
                    "regarder": quoi_regarder,
                    "ecrite": False,
                    "erreur": traceback.format_exc(limit=3),
                }
            )

    def nouveau_document(self):
        doc = self.app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        self.documents.append(doc)
        design = adsk.fusion.Design.cast(self.app.activeProduct)
        design.designType = adsk.fusion.DesignTypes.ParametricDesignType
        return design

    def fermer(self):
        for doc in self.documents:
            try:
                if doc.isValid:
                    doc.close(False)
            except Exception:
                pass

    def ecrire(self):
        compte = {s: sum(v["statut"] == s for v in self.verifs) for s in (OK, KO, A_REGARDER)}
        rapport = {
            "fusion": self.app.version,
            "date": self.horodatage,
            "addin_version": _version_addin(),
            "langue": _langue_active(),
            "compte": compte,
            "verifications": self.verifs,
            "captures": self.captures,
            "a_la_main": [{"ref": r, "geste": g} for r, g in A_LA_MAIN],
        }
        base = self.dossier / f"recette-{self.horodatage}"
        base.with_suffix(".json").write_text(json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")
        base.with_suffix(".md").write_text(markdown(rapport), encoding="utf-8")
        return rapport, base


def markdown(rapport: dict) -> str:
    """Rapport lisible ; fonction pure, testée hors Fusion."""
    c = rapport["compte"]
    lignes = [
        f"# Recette FeuillureRainure {rapport.get('addin_version', '?')} — {rapport['date']}",
        "",
        f"Fusion {rapport['fusion']} · langue de l'add-in : {rapport.get('langue', '?')} · "
        f"**{c.get(OK, 0)} OK · {c.get(KO, 0)} KO · {c.get(A_REGARDER, 0)} à regarder**",
        "",
        "| Réf. | Vérification | Statut | Mesuré | Attendu |",
        "|---|---|---|---|---|",
    ]
    for v in rapport["verifications"]:
        mesure = json.dumps(v["mesure"], ensure_ascii=False) if v["mesure"] is not None else "—"
        lignes.append(f"| {v['ref']} | {v['titre']} | {v['statut']} | {mesure} | {v['attendu']} |")
    details = [v for v in rapport["verifications"] if v.get("detail")]
    if details:
        lignes += ["", "## Détails des KO", ""]
        for v in details:
            lignes += [f"**{v['ref']} — {v['titre']}**", "", "```", v["detail"].rstrip(), "```", ""]
    lignes += ["", "## Captures (à juger à l'œil)", ""]
    for cap in rapport["captures"]:
        etat = "" if cap.get("ecrite") else " (non écrite)"
        lignes.append(f"- {cap['ref']} · `{cap['fichier']}`{etat} : {cap['regarder']}")
    lignes += ["", "## À la main", ""]
    lignes += [f"- {a['ref']} : {a['geste']}" for a in rapport["a_la_main"]]
    return "\n".join(lignes) + "\n"


def _version_addin() -> str:
    try:
        manifest = Path(_module("fonction").__file__).resolve().parents[1] / "FeuillureRainure.manifest"
        return json.loads(manifest.read_text(encoding="utf-8"))["version"]
    except Exception:
        return "?"


def _langue_active() -> str:
    try:
        return _module("langues").langue()
    except Exception:
        return "?"


# ------------------------------------------------------------------ pièces de test


def panneau(parent, nom, x0, longueur, y0, y1, z0, z1, composant=True):
    """Boîte paramétrique (méthode de la sonde Cabineo) : esquisse dans un plan décalé de x0 du plan YZ,
    extrudée de `longueur` selon +X. Dans son propre composant, ou corps de plus de `parent`. mm."""
    comp = parent
    if composant:
        comp = parent.occurrences.addNewComponent(adsk.core.Matrix3D.create()).component
        comp.name = nom
    entree_plan = comp.constructionPlanes.createInput()
    entree_plan.setByOffset(comp.yZConstructionPlane, _vi(f"{x0} mm"))
    plan_ = comp.constructionPlanes.add(entree_plan)
    esquisse = comp.sketches.add(plan_)
    p1 = esquisse.modelToSketchSpace(adsk.core.Point3D.create(x0 / 10, y0 / 10, z0 / 10))
    p2 = esquisse.modelToSketchSpace(adsk.core.Point3D.create(x0 / 10, y1 / 10, z1 / 10))
    esquisse.sketchCurves.sketchLines.addTwoPointRectangle(p1, p2)
    entree = comp.features.extrudeFeatures.createInput(
        esquisse.profiles.item(0), adsk.fusion.FeatureOperations.NewBodyFeatureOperation
    )
    normale = esquisse.xDirection.crossProduct(esquisse.yDirection)
    sens = (
        adsk.fusion.ExtentDirections.PositiveExtentDirection
        if normale.x > 0
        else adsk.fusion.ExtentDirections.NegativeExtentDirection
    )
    entree.setOneSideExtent(adsk.fusion.DistanceExtentDefinition.create(_vi(f"{longueur} mm")), sens)
    extrusion = comp.features.extrudeFeatures.add(entree)
    extrusion.bodies.item(0).name = nom
    return {"nom": nom, "comp": comp, "ext": extrusion}


def corps(pan):
    """Le corps du panneau, relu maintenant (par son nom : un composant peut en porter plusieurs)."""
    comp = pan["comp"]
    for i in range(comp.bRepBodies.count):
        if comp.bRepBodies.item(i).name == pan["nom"]:
            return comp.bRepBodies.item(i)
    return comp.bRepBodies.item(0)


def corps_vu(design, pan):
    """Le corps du panneau vu depuis la racine, comme une sélection à la souris."""
    racine = design.rootComponent
    if pan["comp"] == racine:
        return corps(pan)
    occ = racine.allOccurrencesByComponent(pan["comp"]).item(0)
    return corps(pan).createForAssemblyContext(occ)


def volume(pan) -> float:
    return corps(pan).volume * MM3_PAR_CM3


def corps_en_trop(*pans) -> int:
    """Corps de plus que de panneaux dans leurs composants (un outil laissé derrière)."""
    comps = {}
    for p in pans:
        comps.setdefault(p["comp"].entityToken, [p["comp"], 0])[1] += 1
    return sum(c.bRepBodies.count - n for c, n in comps.values())


def epaisseur(pan, mm: float) -> None:
    adsk.fusion.DistanceExtentDefinition.cast(pan["ext"].extentOne).distance.expression = f"{mm} mm"
    adsk.doEvents()


def meuble(design, contact: bool, parent=None):
    """La cible et ses deux armatures de `exemples/` : en chevauchement (y dès 9) ou en contact (y dès 19)."""
    parent = parent or design.rootComponent
    y = 19 if contact else 9
    cible = panneau(parent, "Cible", 0, 200, 0, 19, -200, 0)
    traversante = panneau(parent, "Traversante", 54, 19, y, y + 213.42, -200, 0)
    arretee = panneau(parent, "Arretee", 127, 19, y, y + 213.42, -153.141, -46.859)
    return cible, traversante, arretee


def plan(design, armature, cibles, jeu=0.3, profondeur=10.0):
    """Ce que le dialogue préparerait : une armature, ses cibles."""
    f, c, a, r = _module("fonction"), _module("calcul"), _module("fusion_api"), _module("reglages")
    vue = corps_vu(design, armature) if isinstance(armature, dict) else armature
    vues = [corps_vu(design, p) if isinstance(p, dict) else p for p in cibles]
    boite = a.boite_monde(vue)
    reglages = r.Reglages(jeu=jeu, profondeur=profondeur)
    analyses = [c.analyser(boite, a.boite_monde(v), jeu, profondeur) for v in vues]
    return f.Plan(f.Piece(vue, a.nom_piece(vue)), [f.Piece(v, a.nom_piece(v)) for v in vues], analyses, reglages)


def reediter(design, fonction, jeu=0.3, garder=None):
    """Double-clic + OK, joué par les fonctions du dialogue : timeline reculée, plan relu, mise à jour."""
    f, a = _module("fonction"), _module("fusion_api")
    marqueur = a.Marqueur(design.timeline)
    f.reculer_avant(fonction)
    armature, cibles, _ = f.pieces_de(fonction)
    cibles = cibles if garder is None else [cibles[i] for i in garder]
    nouvelle = f.mettre_a_jour(fonction, plan(design, armature, cibles, jeu=jeu))
    marqueur.rendre()
    adsk.doEvents()
    return nouvelle


def sain(fonction) -> bool:
    return fonction.healthState == adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState


def proche(mesure: float, attendu: float) -> bool:
    return abs(mesure - attendu) <= TOL_VOLUME


def volumes(**pans) -> dict:
    return {nom: round(volume(p), 3) for nom, p in pans.items()}


# ------------------------------------------------------------------ scénarios


def exemple(rec: Recette, contact: bool) -> None:
    """Les fichiers de l'utilisateur : chaque armature, puis la cible, en deux opérations."""
    cas = "contact" if contact else "chevauchement"
    r0 = "R1" if not contact else "R7"
    design = rec.nouveau_document()
    cible, traversante, arretee = meuble(design, contact=contact)
    f = _module("fonction")
    avant = design.timeline.count
    parametres = design.userParameters.count
    plans = [plan(design, traversante, [cible]), plan(design, arretee, [cible])]
    modes = [p.analyses[0].mode for p in plans]
    rec.verifier(r0, f"{cas} : modes détectés", f"{cas} ×2", lambda: (modes == [cas] * 2, modes))
    fonctions = [f.creer(p) for p in plans]
    adsk.doEvents()
    allonge = 19 * 10 if contact else 0
    attendus = {
        "cible": CIBLE_APRES,
        "traversante": TRAVERSANTE + allonge * 200,
        "arretee": ARRETEE + allonge * 106.282,
    }
    rec.verifier(
        f"R{int(r0[1:]) + 1}",
        f"{cas} : une ligne par opération, saines",
        f"{avant + 2} lignes, 0 paramètre ajouté",
        lambda: (
            design.timeline.count == avant + 2
            and all(sain(x) for x in fonctions)
            and design.userParameters.count == parametres,
            {
                "lignes": design.timeline.count,
                "noms": [x.name for x in fonctions],
                "sante": [str(x.healthState) for x in fonctions],
            },
        ),
    )
    rec.verifier(
        f"R{int(r0[1:]) + 2}",
        f"{cas} : cible comme exemples/apres.step, armatures {'allongées' if contact else 'inchangées'}",
        json.dumps({k: round(v, 3) for k, v in attendus.items()}),
        lambda: (
            all(
                proche(volume(p), attendus[n])
                for n, p in (("cible", cible), ("traversante", traversante), ("arretee", arretee))
            )
            and corps_en_trop(cible, traversante, arretee) == 0,
            volumes(cible=cible, traversante=traversante, arretee=arretee)
            | {"en_trop": corps_en_trop(cible, traversante, arretee)},
        ),
    )
    rec.capturer(f"R{int(r0[1:]) + 2}", cas, f"{cas} : rainures dans la cible, armatures dedans, sans jour visible")
    epaisseur(traversante, 25)
    epaisse = 25 * 213.42 * 200 + 25 * allonge / 19 * 200 if contact else 25 * 213.42 * 200
    rec.verifier(
        f"R{int(r0[1:]) + 3}",
        f"{cas} : armature épaissie en amont, l'opération suit",
        f"cible {round(CIBLE_EPAISSE, 3)}, armature {round(epaisse, 3)}",
        lambda: (
            proche(volume(cible), CIBLE_EPAISSE) and proche(volume(traversante), epaisse) and sain(fonctions[0]),
            volumes(cible=cible, traversante=traversante),
        ),
    )
    epaisseur(traversante, 19)
    if not contact:
        jeton = fonctions[0].entityToken
        editee = reediter(design, fonctions[0], jeu=0.5)
        attendu = CIBLE_AVANT - 20 * 10.5 * 200 - 19.6 * 10.3 * 106.882
        rec.verifier(
            "R5",
            "chevauchement : jeu 0,5 en réédition, en place",
            f"même ligne, cible {round(attendu, 3)}",
            lambda: (
                editee.entityToken == jeton
                and proche(volume(cible), attendu)
                and design.timeline.markerPosition == design.timeline.count,
                {"meme_ligne": editee.entityToken == jeton, "cible": round(volume(cible), 3), "nom": editee.name},
            ),
        )
        fonctions[0] = editee
    for x in reversed(fonctions):
        x.deleteMe()
    adsk.doEvents()
    rec.verifier(
        "R11" if contact else "R6",
        f"{cas} : suppression, tout revient",
        "volumes d'origine",
        lambda: (
            proche(volume(cible), CIBLE_AVANT)
            and proche(volume(traversante), TRAVERSANTE)
            and proche(volume(arretee), ARRETEE),
            volumes(cible=cible, traversante=traversante, arretee=arretee),
        ),
    )


def etagere(rec: Recette) -> None:
    """Une armature, deux cibles : étagère posée entre deux côtés, allongée aux deux bouts."""
    design = rec.nouveau_document()
    racine = design.rootComponent
    gauche = panneau(racine, "Gauche", 0, 19, 0, 300, 0, 700)
    droite = panneau(racine, "Droite", 581, 19, 0, 300, 0, 700)
    tablette = panneau(racine, "Etagere", 19, 562, 0, 300, 300, 319)
    f = _module("fonction")
    avant = design.timeline.count
    p = plan(design, tablette, [gauche, droite])
    fonction = f.creer(p)
    adsk.doEvents()
    cote_usine = 19 * 300 * 700 - 19.6 * 10.3 * 300
    rec.verifier(
        "R12",
        "Étagère entre deux côtés : une ligne, deux rainures, deux allongements",
        f"{avant + 1} lignes ; côtés {round(cote_usine, 3)} ; étagère {562 * 300 * 19 + 2 * 57000}",
        lambda: (
            design.timeline.count == avant + 1
            and sain(fonction)
            and proche(volume(gauche), cote_usine)
            and proche(volume(droite), cote_usine)
            and proche(volume(tablette), 562 * 300 * 19 + 2 * 57000)
            and corps_en_trop(gauche, droite, tablette) == 0,
            volumes(gauche=gauche, droite=droite, etagere=tablette)
            | {"lignes": design.timeline.count, "nom": fonction.name},
        ),
    )
    rec.capturer("R12", "etagere", "Étagère allongée dans une rainure de chaque côté")
    jeton = fonction.entityToken
    editee = reediter(design, fonction, jeu=0.5)
    cote_05 = 19 * 300 * 700 - 20 * 10.5 * 300
    rec.verifier(
        "R13",
        "Étagère : jeu 0,5 en réédition, en place (fonctions emboîtées comprises)",
        f"même ligne, côtés {round(cote_05, 3)}",
        lambda: (
            editee.entityToken == jeton and proche(volume(gauche), cote_05) and proche(volume(droite), cote_05),
            volumes(gauche=gauche, droite=droite) | {"meme_ligne": editee.entityToken == jeton},
        ),
    )
    remplacee = reediter(design, editee, jeu=0.3, garder=[0])
    rec.verifier(
        "R14",
        "Étagère : réédition sans le côté droit, ligne refaite au même rang",
        f"{avant + 1} lignes ; droite entière ; étagère {562 * 300 * 19 + 57000}",
        lambda: (
            design.timeline.count == avant + 1
            and proche(volume(droite), 19 * 300 * 700)
            and proche(volume(gauche), cote_usine)
            and proche(volume(tablette), 562 * 300 * 19 + 57000),
            volumes(gauche=gauche, droite=droite, etagere=tablette) | {"lignes": design.timeline.count},
        ),
    )
    remplacee.deleteMe()
    adsk.doEvents()
    rec.verifier(
        "R15",
        "Étagère : suppression, tout revient",
        "volumes d'origine",
        lambda: (
            proche(volume(gauche), 19 * 300 * 700) and proche(volume(tablette), 562 * 300 * 19),
            volumes(gauche=gauche, etagere=tablette),
        ),
    )


def meme_composant(rec: Recette) -> None:
    """Armature et une cible corps d'un même composant (l'autre cible ailleurs), caisson tourné de 30°,
    chevauchement d'un côté et contact de l'autre."""
    design = rec.nouveau_document()
    rotation = adsk.core.Matrix3D.create()
    rotation.setToRotation(math.radians(30), adsk.core.Vector3D.create(0, 0, 1), adsk.core.Point3D.create(0, 0, 0))
    caisson = design.rootComponent.occurrences.addNewComponent(rotation)
    caisson.component.name = "Caisson"
    parent = caisson.component
    gauche = panneau(parent, "Gauche", 0, 19, 0, 300, 0, 700, composant=False)
    tablette = panneau(parent, "Etagere", 9, 572, 0, 300, 300, 319, composant=False)  # rentre de 10 à gauche
    droite = panneau(parent, "Droite", 581, 19, 0, 300, 0, 700)
    p = plan(design, tablette, [gauche, droite])
    modes = [a.mode for a in p.analyses]
    fonction = _module("fonction").creer(p)
    adsk.doEvents()
    cote_usine = 19 * 300 * 700 - 19.6 * 10.3 * 300
    rec.verifier(
        "R16",
        "Caisson tourné, même composant d'un côté : chevauchement + contact",
        f"modes chevauchement/contact ; côtés {round(cote_usine, 3)} ; étagère {572 * 300 * 19 + 57000}",
        lambda: (
            modes == ["chevauchement", "contact"]
            and sain(fonction)
            and proche(volume(gauche), cote_usine)
            and proche(volume(droite), cote_usine)
            and proche(volume(tablette), 572 * 300 * 19 + 57000)
            and corps_en_trop(gauche, droite, tablette) == 0,
            volumes(gauche=gauche, droite=droite, etagere=tablette) | {"modes": modes},
        ),
    )
    rec.capturer("R16", "caisson-tourne", "Caisson tourné de 30° : rainures alignées sur l'étagère")


def refus(rec: Recette) -> None:
    """Une cible utilisée deux fois est refusée avec un message, sans rien poser."""
    design = rec.nouveau_document()
    cible, traversante, _ = meuble(design, contact=False)
    design.rootComponent.occurrences.addExistingComponent(cible["comp"], adsk.core.Matrix3D.create())
    p = plan(design, traversante, [cible])
    avant = design.timeline.count

    def essai():
        try:
            _module("fonction").creer(p)
        except Exception as e:  # ErreurFeuillure attendue
            return type(e).__name__ == "ErreurFeuillure" and design.timeline.count == avant, str(e)
        return False, "posée malgré une cible en deux exemplaires"

    rec.verifier("R17", "Cible en deux exemplaires : refus expliqué", "ErreurFeuillure, rien posé", essai)


def jouer():
    rec = Recette()
    a = None
    try:
        a = _module("fusion_api")
        a.SANS_BOITE = True
        definitions = rec.app.userInterface.commandDefinitions
        panneau_ = rec.app.userInterface.allToolbarPanels.itemById("SolidModifyPanel")
        rec.verifier(
            "R0",
            "Bouton dans SOLIDE → Modifier",
            "présent",
            lambda: (
                definitions.itemById("feuillureRainureCmd") is not None
                and panneau_ is not None
                and panneau_.controls.itemById("feuillureRainureCmd") is not None,
                "présent" if definitions.itemById("feuillureRainureCmd") else "absent",
            ),
        )
        scenarios = (
            ("chevauchement", lambda: exemple(rec, contact=False)),
            ("contact", lambda: exemple(rec, contact=True)),
            ("etagere", lambda: etagere(rec)),
            ("meme_composant", lambda: meme_composant(rec)),
            ("refus", lambda: refus(rec)),
        )
        for nom, scenario in scenarios:
            try:
                scenario()
            except Exception:
                rec.noter(nom, f"Scénario {nom}", KO, None, "sans erreur", traceback.format_exc(limit=10))
    finally:
        if a is not None:
            a.SANS_BOITE = False
        rapport, base = rec.ecrire()
        rec.fermer()
    return rapport, base


def recette() -> str:
    """Lancement par le MCP de Fusion : rend le résumé et le chemin du rapport."""
    rapport, base = jouer()
    c = rapport["compte"]
    return f"{c[OK]} OK · {c[KO]} KO · {c[A_REGARDER]} à regarder · rapport : {base}.md"


def run(context):
    """Lancement à la main (Scripts et compléments)."""
    try:
        adsk.core.Application.get().userInterface.messageBox(recette())
    except Exception:
        adsk.core.Application.get().userInterface.messageBox(traceback.format_exc())
