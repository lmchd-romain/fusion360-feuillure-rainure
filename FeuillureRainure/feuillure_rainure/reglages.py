"""Réglages d'une opération : valeurs, JSON, nom de timeline, résumé, derniers réglages utilisés.

Module pur : n'importe jamais `adsk`. Longueurs en mm.

Les réglages vivent dans un attribut JSON de la fonction (groupe `feuillureRainure`) : aucun
paramètre n'est ajouté au design. Un champ absent reprend sa valeur par défaut, pour que les
fichiers des versions précédentes restent lisibles.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

from .calcul import CHEVAUCHEMENT, CONTACT, FEUILLURE, RAINURE, Analyse
from .erreurs import ErreurFeuillure
from .langues import langue, t, tn

VERSION = 1
_NOMBRES = ("jeu", "profondeur")
_TEXTES = ("expression_jeu", "expression_profondeur")


@dataclass(frozen=True)
class Reglages:
    jeu: float = 0.3  # mm, de chaque côté et au fond (exemple de l'utilisateur)
    profondeur: float = 10.0  # mm : enfoncement des armatures en contact (exemple de l'utilisateur)
    expression_jeu: str = ""  # expression saisie (« 0,3 mm », « jeu_rainure ») ; vide : la valeur
    expression_profondeur: str = ""


def vers_json(r: Reglages) -> str:
    return json.dumps(asdict(r) | {"version": VERSION}, ensure_ascii=False)


def depuis_json(texte: str) -> Reglages:
    """Champs absents → défaut ; inconnus → ignorés ; nombre illisible ou négatif → défaut."""
    try:
        donnees = json.loads(texte)
    except (json.JSONDecodeError, TypeError) as e:
        raise ErreurFeuillure(t("erreur.reglages_illisibles", detail=e)) from e
    if not isinstance(donnees, dict):
        raise ErreurFeuillure(t("erreur.reglages_illisibles", detail=type(donnees).__name__))
    connus = {f.name for f in fields(Reglages)}
    valeurs = {k: v for k, v in donnees.items() if k in connus}
    for nom in _NOMBRES:
        v = valeurs.get(nom)
        if nom in valeurs and not (
            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0
        ):
            del valeurs[nom]
        elif nom in valeurs:
            valeurs[nom] = float(v)
    for nom in _TEXTES:
        if nom in valeurs and not isinstance(valeurs[nom], str):
            del valeurs[nom]
    return Reglages(**valeurs)


def lire_derniers(chemin: Path) -> Reglages:
    """Derniers réglages validés ; fichier absent, illisible ou d'une autre version → défauts."""
    try:
        return depuis_json(chemin.read_text(encoding="utf-8"))
    except (OSError, ErreurFeuillure):
        return Reglages()


def ecrire_derniers(chemin: Path, r: Reglages) -> None:
    chemin.write_text(vers_json(r), encoding="utf-8")


def nombre(x: float) -> str:
    """Nombre court, décimales utiles seulement, virgule en français et en allemand."""
    texte = f"{x:.2f}".rstrip("0").rstrip(".")
    if texte in ("-0", ""):
        texte = "0"
    return texte.replace(".", ",") if langue() in ("fr", "de") else texte


def expression_mm(expression: str, valeur: float) -> str:
    """Ce que le champ du dialogue affiche : l'expression saisie, sinon la valeur en mm."""
    return expression.strip() if expression and expression.strip() else f"{nombre(valeur).replace(',', '.')} mm"


def avec(r: Reglages, **changements) -> Reglages:
    return replace(r, **changements)


def nom_fonction(analyses: list[Analyse], r: Reglages) -> str:
    """Nom de la ligne de timeline : « Rainure ×2 · jeu 0,3 », « Feuillure · jeu 0,3 »,
    « Feuillure + rainure ×3 · jeu 0,3 »."""
    types = [a.type for a in analyses if a.type]
    n = len(types)
    if not types or all(x == RAINURE for x in types):
        cle = "timeline.rainure"
    elif all(x == FEUILLURE for x in types):
        cle = "timeline.feuillure"
    else:
        cle = "timeline.mixte"
    quantite = f" ×{n}" if n > 1 else ""
    return t(cle, n=quantite, jeu=nombre(r.jeu))


def ligne_resume(nom: str, a: Analyse) -> str:
    """Une ligne du résumé du dialogue pour une armature."""
    if a.probleme and not a.type:
        return t("resume.probleme", nom=nom, probleme=t(a.probleme, profondeur=nombre(a.enfoncement)))
    forme = t(f"resume.{a.type}", largeur=nombre(a.largeur), profondeur=nombre(a.profondeur))
    if a.traversante:
        forme = t(f"resume.{a.type}_traversante", largeur=nombre(a.largeur))
    if a.mode == CHEVAUCHEMENT:
        detail = t("resume.chevauchement", enfoncement=nombre(a.enfoncement))
    elif a.mode == CONTACT and a.allongement > 0:
        detail = t("resume.allongee", allongement=nombre(a.allongement))
    else:
        detail = t("resume.contact")
    return t("resume.ligne", nom=nom, forme=forme, detail=detail)


def resume(lignes: list[tuple[str, Analyse]]) -> str:
    """Le résumé complet : une ligne par armature, puis le compte."""
    if not lignes:
        return t("commande.invite")
    textes = [ligne_resume(nom, a) for nom, a in lignes]
    bonnes = sum(1 for _, a in lignes if a.utilisable)
    textes.append(tn("resume.compte", bonnes))
    return "\n".join(textes)
