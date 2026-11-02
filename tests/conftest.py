"""Les tests du noyau comparent des textes français : la langue est fixée à « fr » pour chacun.

Le test de chargement purge le paquet de `sys.modules` : les modules importés à la collecte gardent
l'ancienne instance de `langues`. Les deux instances (celle de la collecte, l'actuelle) sont réglées.
"""

import sys

import pytest
from feuillure_rainure import langues as _langues_collecte


@pytest.fixture(autouse=True)
def francais():
    instances = {id(_langues_collecte): _langues_collecte}
    actuelle = sys.modules.get("feuillure_rainure.langues")
    if actuelle is not None:
        instances[id(actuelle)] = actuelle
    for module in instances.values():
        module.choisir("fr")
    yield
    for module in instances.values():
        module.choisir(module.SECOURS)
