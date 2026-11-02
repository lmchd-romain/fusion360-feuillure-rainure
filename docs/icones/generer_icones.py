"""Génère les PNG des icônes de FeuillureRainure depuis `icones.html` (Chrome sans fenêtre + Pillow), puis la planche.

    python docs/icones/generer_icones.py                       # toutes les icônes + planche
    python docs/icones/generer_icones.py boutons/mode-auto     # seulement ces dossiers (les autres ne bougent pas)
    python docs/icones/generer_icones.py --planche             # planche seule, depuis les PNG existants

Chaque PNG est photographié à sa taille exacte, sans réduction : 16x16 et 16x16@2x depuis le dessin de
16 px (`<nom>-16`, redessiné sur une grille de 16), 32x32, 32x32@2x, 64x64 et 64x64@2x depuis celui de
32 px (`<nom>-32`), dans FeuillureRainure/ressources/icone/.

Variantes sombres (skill dev-plugin-fusion360 § 8.1, en attendant le verdict de la sonde d'icônes) :
`-dark`, et la même image copiée en `-dark_blue` et `-dark_gray` (jeton avant l'échelle :
`32x32-dark_blue@2x.png`).

Chrome : variable d'environnement CHROME, sinon Chrome de Windows, sinon Chromium de Playwright.
Planche : docs/icones/planche.png, 100 % puis 200 %, sur fond clair #F5F5F5 et sombre #3B4453.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ICI = Path(__file__).resolve().parent
PAGE = ICI / "icones.html"
RESSOURCES = ICI.parents[1] / "FeuillureRainure" / "ressources"
PLANCHE = ICI / "planche.png"
CHROMES = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path("/opt/pw-browsers/chromium/chrome-linux64/chrome"),
)
FENETRE_MIN = 600  # px : Chrome sans fenêtre refuse les fenêtres plus petites
SOMBRES = ("-dark", "-dark_blue", "-dark_gray")

# dossier de ressources → nom du dessin dans la page (sans -16 / -32)
COMMANDES = {"icone": "icone"}  # bouton, ligne de timeline et commande de réédition
BOUTONS: dict[str, str] = {}
# fichier → (grille du dessin, côté en px)
FICHIERS_COMMANDE = {
    "16x16": (16, 16),
    "16x16@2x": (16, 32),
    "32x32": (32, 32),
    "32x32@2x": (32, 64),
    "64x64": (32, 64),
    "64x64@2x": (32, 128),
}
FICHIERS_BOUTON = {k: v for k, v in FICHIERS_COMMANDE.items() if not k.startswith("64")}
FONDS = {"clair": ((245, 245, 245), ""), "sombre": ((59, 68, 83), "-dark_blue")}


def dossiers() -> dict[str, tuple[str, dict]]:
    return {d: (n, FICHIERS_COMMANDE) for d, n in COMMANDES.items()} | {
        d: (n, FICHIERS_BOUTON) for d, n in BOUTONS.items()
    }


def chrome() -> Path:
    candidats = [Path(os.environ["CHROME"])] if os.environ.get("CHROME") else []
    candidats += list(CHROMES) + sorted(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux*/chrome"))
    trouve = next((c for c in candidats if c.is_file()), None)
    if trouve is None:
        raise SystemExit("Chrome introuvable : donnez son chemin dans la variable CHROME.")
    return trouve


def noms() -> list[str]:
    page = re.sub(r"<!--.*?-->", "", PAGE.read_text(encoding="utf-8"), flags=re.S)
    return re.findall(r'data-nom="([^"]+)"', page)


def photographier(taille: int, dossier: Path) -> Image.Image:
    """Toutes les icônes de la page à `taille` px : une ligne par thème (clair, puis sombre)."""
    png = dossier / f"planche-{taille}.png"
    largeur = max(FENETRE_MIN, len(noms()) * taille)
    hauteur = max(FENETRE_MIN, 2 * taille)
    subprocess.run(
        [
            str(chrome()),
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--hide-scrollbars",
            "--default-background-color=00000000",
            "--force-device-scale-factor=1",
            f"--window-size={largeur},{hauteur}",
            f"--screenshot={png}",
            f"{PAGE.as_uri()}?taille={taille}",
        ],
        check=True,
        capture_output=True,
    )
    return Image.open(png).convert("RGBA")


def case(planche: Image.Image, nom: str, taille: int, sombre: bool) -> Image.Image:
    i, ligne = noms().index(nom), 1 if sombre else 0
    return planche.crop((i * taille, ligne * taille, (i + 1) * taille, (ligne + 1) * taille))


def ecrire(image: Image.Image, dossier: Path, fichier: str, sombre: bool) -> None:
    base, _, double = fichier.partition("@")
    dossier.mkdir(parents=True, exist_ok=True)
    for jeton in SOMBRES if sombre else ("",):
        image.save(dossier / f"{base}{jeton}{'@' + double if double else ''}.png")


def generer(voulus: list[str]) -> None:
    tous = dossiers()
    inconnus = set(voulus) - set(tous)
    if inconnus:
        raise SystemExit("dossiers inconnus : " + ", ".join(sorted(inconnus)))
    manquants = {f"{n}-{g}" for n, f in tous.values() for g, _ in f.values()} - set(noms())
    if manquants:
        raise SystemExit("dessins absents de la page : " + ", ".join(sorted(manquants)))
    tailles = sorted({t for _, f in tous.values() for _, t in f.values()})
    with tempfile.TemporaryDirectory() as tmp:
        planches = {t: photographier(t, Path(tmp)) for t in tailles}
    for t, planche in planches.items():
        attendu = (max(FENETRE_MIN, len(noms()) * t), max(FENETRE_MIN, 2 * t))
        if planche.size != attendu:
            raise SystemExit(f"capture de {planche.size} px à {t} px, attendu {attendu}")
    n = 0
    for dossier, (nom, fichiers) in tous.items():
        if voulus and dossier not in voulus:
            continue
        for sombre in (False, True):
            for fichier, (grille, taille) in fichiers.items():
                ecrire(case(planches[taille], f"{nom}-{grille}", taille, sombre), RESSOURCES / dossier, fichier, sombre)
        n += 1
    print(f"{n} icônes écrites dans {RESSOURCES}")


def _police(taille: int) -> ImageFont.ImageFont:
    for nom in ("DejaVuSans.ttf", "arial.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(nom, taille)
        except OSError:
            continue
    return ImageFont.load_default()


def planche(sortie: Path) -> None:
    """Toutes les icônes à 100 % puis 200 % (pixels doublés, à droite), une bande par fond."""
    fichiers = {"16x16": 16, "16x16@2x": 32, "32x32": 32, "32x32@2x": 64}
    liste = list(dossiers())
    marge, col, titre, ecart = 14, 190, 46, 8
    largeurs = [3 * t + ecart + marge for t in fichiers.values()]
    hauteur_ligne = 2 * max(fichiers.values()) + marge
    largeur = col + sum(largeurs) + marge
    hauteur_bande = titre + len(liste) * hauteur_ligne
    image = Image.new("RGB", (largeur, len(FONDS) * hauteur_bande), "white")
    dessin = ImageDraw.Draw(image)
    police, petite = _police(15), _police(12)
    for b, (theme, (fond, jeton)) in enumerate(FONDS.items()):
        y0 = b * hauteur_bande
        dessin.rectangle((0, y0, largeur, y0 + hauteur_bande - 1), fill=fond)
        encre = (40, 40, 40) if sum(fond) > 380 else (225, 225, 225)
        texte = f"Fond {theme} (fichiers {jeton or 'normaux'}) : 100 % puis 200 %"
        dessin.text((marge, y0 + 6), texte, fill=encre, font=police)
        x = col
        for f, pas in zip(fichiers, largeurs, strict=True):
            dessin.text((x, y0 + 28), f, fill=encre, font=petite)
            x += pas
        for r, nom in enumerate(liste):
            y = y0 + titre + r * hauteur_ligne
            dessin.text((marge, y + 4), nom, fill=encre, font=petite)
            x = col
            for f, pas in zip(fichiers, largeurs, strict=True):
                base, _, double = f.partition("@")
                png = RESSOURCES / nom / f"{base}{jeton}{'@' + double if double else ''}.png"
                if png.is_file():
                    icone = Image.open(png).convert("RGBA")
                    image.paste(icone, (x, y), icone)
                    grande = icone.resize((icone.width * 2, icone.height * 2), Image.Resampling.NEAREST)
                    image.paste(grande, (x + icone.width + ecart, y), grande)
                else:
                    dessin.text((x, y + 4), "MANQUANT", fill=(220, 40, 40), font=petite)
                x += pas
    image.save(sortie)
    print(f"planche : {sortie}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dossiers", nargs="*", help="dossiers à refaire (défaut : tous)")
    parser.add_argument("--planche", action="store_true", help="planche seule, depuis les PNG existants")
    args = parser.parse_args()
    if not args.planche:
        generer(args.dossiers)
    planche(PLANCHE)


if __name__ == "__main__":
    main()
