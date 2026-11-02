"""Point d'entrée de l'add-in FeuillureRainure.

Fusion charge le fichier du même nom que le dossier et appelle `run` / `stop` : ce sont les deux
seuls points d'entrée qu'il connaît.

Fusion n'ajoute pas toujours le dossier de l'add-in à `sys.path` au démarrage automatique
(constat MobPrez, 2026-08-02) : on le pose nous-mêmes avant le premier import du paquet.
Toute panne à l'import est journalisée dans `demarrage.log`, sinon l'add-in resterait muet.
"""

import importlib
import sys
import time
import traceback
from pathlib import Path

_DOSSIER = Path(__file__).resolve().parent
_JOURNAL_DEMARRAGE = _DOSSIER / "demarrage.log"


def _trace(message):
    try:
        with _JOURNAL_DEMARRAGE.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except Exception:
        pass  # un journal qui lève masquerait la panne qu'il doit révéler


if str(_DOSSIER) not in sys.path:
    sys.path.insert(0, str(_DOSSIER))

# « Exécuter » relit ce fichier, pas les modules du paquet restés dans sys.modules : sans ce ménage,
# un Arrêter / Exécuter garderait l'ancien code (constat Cabineo insertion, 2026-10-29).
for _nom in [n for n in sys.modules if n == "feuillure_rainure" or n.startswith("feuillure_rainure.")]:
    del sys.modules[_nom]

try:
    from feuillure_rainure.journal import fermer, journal

    _commande = importlib.import_module("feuillure_rainure.commande")
except BaseException:
    _trace("échec des imports :\n" + traceback.format_exc())
    raise


def run(context):
    try:
        # Langue de Fusion, lue une fois : un changement de langue demande un redémarrage, comme Fusion.
        importlib.import_module("feuillure_rainure.langues").charger()
    except BaseException:
        _trace("langue de Fusion illisible, textes en anglais :\n" + traceback.format_exc())
    try:
        _commande.demarrer()
    except BaseException:
        _trace("démarrage a échoué :\n" + traceback.format_exc())
        raise
    try:
        journal().info("démarrage de FeuillureRainure")
    except Exception:
        pass  # journal illisible : l'add-in tourne quand même


def stop(context):
    try:
        _commande.arreter()
    except BaseException:
        _trace("arrêt a échoué :\n" + traceback.format_exc())
    try:
        journal().info("arrêt de FeuillureRainure")
    except Exception:
        pass
    finally:
        fermer()  # libère journal.log (sous Windows, un fichier ouvert ne se déplace ni ne s'efface)
