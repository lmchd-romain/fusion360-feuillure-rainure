"""Textes visibles de l'add-in, dans la langue de Fusion (convention commune : `docs/i18n.md` du dépôt
fusion360-ecosystem-plugin).

Module pur : n'importe `adsk` que dans `langue_de_fusion`. Fichiers `ressources/langues/<code>.json`,
objets plats `{"cle": "texte"}`, variables `{nom}`. Langues : `en` (secours), `fr`, `ja`, `de`.
Clé absente → anglais → la clé elle-même : jamais d'exception pour un texte manquant.

La langue est lue au démarrage de l'add-in (`charger`) : un changement de langue de Fusion demande un
redémarrage, comme Fusion lui-même. Le journal (`journal.log`) reste en français.
"""

from __future__ import annotations

import json
from pathlib import Path

DOSSIER = Path(__file__).resolve().parents[1] / "ressources" / "langues"
SECOURS = "en"
LANGUES = ("en", "fr", "ja", "de")
# Nom de la valeur d'énumération `adsk.core.UserLanguages` → code ; jamais son numéro.
PAR_NOM_FUSION = {
    "EnglishLanguage": "en",
    "FrenchLanguage": "fr",
    "JapaneseLanguage": "ja",
    "GermanLanguage": "de",
}

_langue = SECOURS
_textes: dict[str, str] = {}
_secours: dict[str, str] = {}


def lire(code: str) -> dict[str, str]:
    """Les textes d'une langue ; fichier absent ou illisible : vide (le secours prend le relais)."""
    try:
        donnees = json.loads((DOSSIER / f"{code}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in donnees.items()} if isinstance(donnees, dict) else {}


def choisir(code: str) -> str:
    """Passe à la langue `code` (inconnue : anglais) ; rend la langue retenue."""
    global _langue, _textes, _secours
    _langue = code if code in LANGUES else SECOURS
    _secours = lire(SECOURS)
    _textes = _secours if _langue == SECOURS else lire(_langue)
    return _langue


def langue() -> str:
    return _langue


def langue_de_fusion() -> str:
    """Code de la langue de l'interface de Fusion ; anglais si elle n'est pas traduite ou illisible."""
    try:
        import adsk.core

        valeur = adsk.core.Application.get().preferences.generalPreferences.userLanguage
        enum = adsk.core.UserLanguages
        for nom, code in PAR_NOM_FUSION.items():
            if getattr(enum, nom, object()) == valeur:
                return code
    except Exception:
        pass
    return SECOURS


def charger() -> str:
    """Au démarrage de l'add-in : la langue de Fusion."""
    return choisir(langue_de_fusion())


def t(cle: str, **variables) -> str:
    """Le texte de `cle`, variables `{nom}` remplacées. Jamais d'exception."""
    if not _secours and not _textes:
        choisir(_langue)
    texte = _textes.get(cle) or _secours.get(cle) or cle
    if not variables:
        return texte
    try:
        return texte.format(**variables)
    except (KeyError, IndexError, ValueError):
        try:
            return (_secours.get(cle) or cle).format(**variables)
        except (KeyError, IndexError, ValueError):
            return texte


def tn(cle: str, n: int, **variables) -> str:
    """Texte au singulier (`cle.un`) ou au pluriel (`cle.plusieurs`), `{n}` remplacé. En français, 0 et 1
    sont au singulier (« 0 coin ») ; ailleurs, 1 seulement."""
    un = n <= 1 if _langue == "fr" else n == 1
    return t(f"{cle}.{'un' if un else 'plusieurs'}", n=n, **variables)


def prefixe(debut: str) -> dict[str, str]:
    """Toutes les clés qui commencent par `debut` (pour la page HTML du schéma), secours compris."""
    if not _secours and not _textes:
        choisir(_langue)
    cles = {k for k in _secours if k.startswith(debut)} | {k for k in _textes if k.startswith(debut)}
    return {k: t(k) for k in sorted(cles)}
