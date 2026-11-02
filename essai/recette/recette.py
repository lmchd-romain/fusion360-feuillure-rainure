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


def panneau(parent, nom, x0, longueur, y0, y1, z0, z1):
    """Boîte paramétrique dans son propre composant (méthode de la sonde Cabineo) : esquisse dans un plan
    décalé de x0 du plan YZ, extrudée de `longueur` selon +X. Longueurs en mm."""
    occ = parent.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    comp = occ.component
    comp.name = nom
    entree_plan = comp.constructionPlanes.createInput()
    entree_plan.setByOffset(comp.yZConstructionPlane, _vi(f"{x0} mm"))
    plan = comp.constructionPlanes.add(entree_plan)
    esquisse = comp.sketches.add(plan)
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


def corps_vu(design, pan):
    """Le corps du panneau vu depuis la racine, comme une sélection à la souris."""
    occ = design.rootComponent.allOccurrencesByComponent(pan["comp"]).item(0)
    return pan["comp"].bRepBodies.item(0).createForAssemblyContext(occ)


def volume(pan) -> float:
    return sum(pan["comp"].bRepBodies.item(i).volume for i in range(pan["comp"].bRepBodies.count)) * MM3_PAR_CM3


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


def plan(design, cible, armatures, jeu=0.3, profondeur=10.0):
    """Ce que le dialogue préparerait pour ces pièces."""
    f, c, a, r = _module("fonction"), _module("calcul"), _module("fusion_api"), _module("reglages")
    vue_cible = corps_vu(design, cible) if isinstance(cible, dict) else cible
    vues = [corps_vu(design, p) if isinstance(p, dict) else p for p in armatures]
    boite = a.boite_monde(vue_cible)
    reglages = r.Reglages(jeu=jeu, profondeur=profondeur)
    analyses = [c.analyser(a.boite_monde(v), boite, jeu, profondeur) for v in vues]
    return f.Plan(f.Piece(vue_cible, "Cible"), [f.Piece(v, a.nom_piece(v)) for v in vues], analyses, reglages)


def sain(fonction) -> bool:
    return fonction.healthState == adsk.fusion.FeatureHealthStates.HealthyFeatureHealthState


def proche(mesure: float, attendu: float) -> bool:
    return abs(mesure - attendu) <= TOL_VOLUME


# ------------------------------------------------------------------ scénarios


def chevauchement(rec: Recette) -> None:
    design = rec.nouveau_document()
    cible, traversante, arretee = meuble(design, contact=False)
    f = _module("fonction")
    p = plan(design, cible, [traversante, arretee])
    rec.verifier(
        "R1",
        "Chevauchement : deux rainures détectées",
        "chevauchement ×2, rainure ×2",
        lambda: (
            [a.mode for a in p.analyses] == ["chevauchement"] * 2 and [a.type for a in p.analyses] == ["rainure"] * 2,
            [(a.mode, a.type, round(a.largeur, 3), round(a.profondeur, 3)) for a in p.analyses],
        ),
    )
    avant = design.timeline.count
    parametres = design.userParameters.count
    fonction = f.creer(p)
    adsk.doEvents()
    rec.verifier(
        "R2",
        "Une seule ligne de timeline, saine",
        f"{avant + 1} lignes, saine",
        lambda: (
            design.timeline.count == avant + 1 and sain(fonction),
            {"lignes": design.timeline.count, "sante": str(fonction.healthState), "nom": fonction.name},
        ),
    )
    rec.verifier(
        "R3",
        "Cible usinée comme exemples/apres.step",
        f"{CIBLE_APRES} mm³, 1 corps",
        lambda: (
            proche(volume(cible), CIBLE_APRES) and cible["comp"].bRepBodies.count == 1,
            {"volume": round(volume(cible), 3), "corps": cible["comp"].bRepBodies.count},
        ),
    )
    rec.verifier(
        "R4",
        "Armatures inchangées, aucun paramètre ajouté",
        "volumes d'origine, 0 paramètre",
        lambda: (
            proche(volume(traversante), TRAVERSANTE)
            and proche(volume(arretee), ARRETEE)
            and design.userParameters.count == parametres,
            {
                "traversante": round(volume(traversante), 3),
                "arretee": round(volume(arretee), 3),
                "parametres": design.userParameters.count,
            },
        ),
    )
    rec.capturer("R3", "chevauchement", "Deux rainures dans la cible, armatures en place ; une seule ligne de timeline")
    epaisseur(traversante, 25)
    rec.verifier(
        "R5",
        "Armature épaissie en amont : la rainure suit",
        f"{round(CIBLE_EPAISSE, 3)} mm³, saine",
        lambda: (
            proche(volume(cible), CIBLE_EPAISSE) and sain(fonction),
            {"volume": round(volume(cible), 3), "sante": str(fonction.healthState)},
        ),
    )
    epaisseur(traversante, 19)
    a = _module("fusion_api")
    marqueur = a.Marqueur(design.timeline)
    jeton = fonction.entityToken
    f.reculer_avant(fonction)
    cible_vue, armatures, _ = f.pieces_de(fonction)
    nouveau = plan(design, cible_vue, armatures, jeu=0.5)
    editee = f.mettre_a_jour(fonction, nouveau)
    marqueur.rendre()
    adsk.doEvents()
    rec.verifier(
        "R6",
        "Réédition du jeu (0,5) en place",
        f"même ligne, {round(CIBLE_JEU_05, 3)} mm³",
        lambda: (
            editee.entityToken == jeton
            and proche(volume(cible), CIBLE_JEU_05)
            and design.timeline.markerPosition == design.timeline.count,
            {"meme_ligne": editee.entityToken == jeton, "volume": round(volume(cible), 3), "nom": editee.name},
        ),
    )
    editee.deleteMe()
    adsk.doEvents()
    rec.verifier(
        "R7",
        "Suppression : tout revient",
        f"{CIBLE_AVANT} mm³, {avant} lignes",
        lambda: (
            proche(volume(cible), CIBLE_AVANT) and design.timeline.count == avant,
            {"volume": round(volume(cible), 3), "lignes": design.timeline.count},
        ),
    )


def contact(rec: Recette) -> None:
    design = rec.nouveau_document()
    cible, traversante, arretee = meuble(design, contact=True)
    f = _module("fonction")
    p = plan(design, cible, [traversante, arretee])
    rec.verifier(
        "R8",
        "Contact : deux armatures à allonger de 10",
        "contact ×2, allongement 10",
        lambda: (
            [a.mode for a in p.analyses] == ["contact"] * 2 and all(abs(a.allongement - 10) < 1e-6 for a in p.analyses),
            [(a.mode, a.type, round(a.allongement, 3)) for a in p.analyses],
        ),
    )
    avant = design.timeline.count
    fonction = f.creer(p)
    adsk.doEvents()
    rec.verifier(
        "R9",
        "Une seule ligne, allongements compris (autres composants)",
        f"{avant + 1} lignes, saine",
        lambda: (
            design.timeline.count == avant + 1 and sain(fonction),
            {"lignes": design.timeline.count, "sante": str(fonction.healthState)},
        ),
    )
    attendus = (TRAVERSANTE + 19 * 10 * 200, ARRETEE + 19 * 10 * 106.282)
    rec.verifier(
        "R10",
        "Cible usinée et armatures allongées",
        f"cible {CIBLE_APRES}, armatures {attendus}",
        lambda: (
            proche(volume(cible), CIBLE_APRES)
            and proche(volume(traversante), attendus[0])
            and proche(volume(arretee), attendus[1])
            and all(p_["comp"].bRepBodies.count == 1 for p_ in (cible, traversante, arretee)),
            {
                "cible": round(volume(cible), 3),
                "traversante": round(volume(traversante), 3),
                "arretee": round(volume(arretee), 3),
            },
        ),
    )
    rec.capturer("R10", "contact", "Armatures allongées dans les rainures (plus de jour au contact)")
    epaisseur(traversante, 25)
    epaisse = 25 * 213.42 * 200 + 25 * 10 * 200
    rec.verifier(
        "R11",
        "Armature épaissie en amont : allongement et rainure suivent",
        f"cible {round(CIBLE_EPAISSE, 3)}, armature {epaisse}",
        lambda: (
            proche(volume(cible), CIBLE_EPAISSE) and proche(volume(traversante), epaisse) and sain(fonction),
            {"cible": round(volume(cible), 3), "traversante": round(volume(traversante), 3)},
        ),
    )
    epaisseur(traversante, 19)
    a = _module("fusion_api")
    marqueur = a.Marqueur(design.timeline)
    jeton = fonction.entityToken
    f.reculer_avant(fonction)
    cible_vue, armatures, _ = f.pieces_de(fonction)
    nouveau = plan(design, cible_vue, armatures[1:])
    remplacee = f.mettre_a_jour(fonction, nouveau)
    marqueur.rendre()
    adsk.doEvents()
    rec.verifier(
        "R12",
        "Réédition sans la première armature : remplacée au même rang",
        f"nouvelle ligne, {avant + 1} lignes, cible {round(CIBLE_ARRETEE_SEULE, 3)}, traversante rendue",
        lambda: (
            remplacee.entityToken != jeton
            and design.timeline.count == avant + 1
            and proche(volume(cible), CIBLE_ARRETEE_SEULE)
            and proche(volume(traversante), TRAVERSANTE),
            {
                "lignes": design.timeline.count,
                "cible": round(volume(cible), 3),
                "traversante": round(volume(traversante), 3),
            },
        ),
    )
    remplacee.deleteMe()
    adsk.doEvents()
    rec.verifier(
        "R13",
        "Suppression : armatures et cible reviennent",
        "volumes d'origine",
        lambda: (
            proche(volume(cible), CIBLE_AVANT) and proche(volume(arretee), ARRETEE),
            {"cible": round(volume(cible), 3), "arretee": round(volume(arretee), 3)},
        ),
    )


def caisson_tourne(rec: Recette) -> None:
    """Pièces dans un sous-composant tourné de 30° : une armature en chevauchement, une en contact."""
    design = rec.nouveau_document()
    rotation = adsk.core.Matrix3D.create()
    rotation.setToRotation(math.radians(30), adsk.core.Vector3D.create(0, 0, 1), adsk.core.Point3D.create(0, 0, 0))
    caisson = design.rootComponent.occurrences.addNewComponent(rotation)
    caisson.component.name = "Caisson"
    parent = caisson.component
    cible = panneau(parent, "Cible", 0, 200, 0, 19, -200, 0)
    traversante = panneau(parent, "Traversante", 54, 19, 9, 222.42, -200, 0)
    arretee = panneau(parent, "Arretee", 127, 19, 19, 232.42, -153.141, -46.859)
    p = plan(design, cible, [traversante, arretee])
    rec.verifier(
        "R14",
        "Caisson tourné : modes détectés",
        "chevauchement puis contact",
        lambda: (
            [a.mode for a in p.analyses] == ["chevauchement", "contact"],
            [(a.mode, round(a.profondeur, 3)) for a in p.analyses],
        ),
    )
    fonction = _module("fonction").creer(p)
    adsk.doEvents()
    rec.verifier(
        "R15",
        "Caisson tourné : usinage et allongement justes",
        f"cible {CIBLE_APRES}",
        lambda: (
            proche(volume(cible), CIBLE_APRES)
            and proche(volume(arretee), ARRETEE + 19 * 10 * 106.282)
            and sain(fonction),
            {"cible": round(volume(cible), 3), "arretee": round(volume(arretee), 3)},
        ),
    )
    rec.capturer("R15", "caisson-tourne", "Caisson tourné de 30° : rainures alignées sur les armatures")


def refus(rec: Recette) -> None:
    """Une cible utilisée deux fois est refusée avec un message, sans rien poser."""
    design = rec.nouveau_document()
    cible, traversante, _ = meuble(design, contact=False)
    racine = design.rootComponent
    racine.occurrences.addExistingComponent(cible["comp"], adsk.core.Matrix3D.create())
    p = plan(design, cible, [traversante])
    avant = design.timeline.count

    def essai():
        try:
            _module("fonction").creer(p)
        except Exception as e:  # ErreurFeuillure attendue
            return type(e).__name__ == "ErreurFeuillure" and design.timeline.count == avant, str(e)
        return False, "posée malgré une cible en deux exemplaires"

    rec.verifier("R16", "Cible en deux exemplaires : refus expliqué", "ErreurFeuillure, rien posé", essai)


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
        for scenario in (chevauchement, contact, caisson_tourne, refus):
            try:
                scenario(rec)
            except Exception:
                rec.noter(
                    scenario.__name__,
                    f"Scénario {scenario.__name__}",
                    KO,
                    None,
                    "sans erreur",
                    traceback.format_exc(limit=10),
                )
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
