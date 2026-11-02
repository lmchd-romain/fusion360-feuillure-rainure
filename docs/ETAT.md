# État du plugin Feuillure / rainure

- Date : 2026-11-02
- Version du manifest : **0.1.0**
- Légende : **[vérifié]** = constaté dans Fusion, preuve citée ; **[supposé]** = déduit du code ou des docs,
  pas constaté dans Fusion. Ce plugin n'a **pas encore tourné dans Fusion** : la session qui l'a écrit n'avait
  pas Fusion. Chaque brique reprend une méthode constatée dans un autre plugin de l'atelier.

## Ce que fait le plugin

Feuillures et rainures avec jeu entre panneaux, en une ligne de timeline : la cible est usinée, les armatures
qui la touchent seulement sont allongées de la profondeur. Voir `README.md`.

## Fonctions

| Fonction | État | Preuve |
|---|---|---|
| Calcul (chevauchement, contact, jeu, feuillure / rainure, caisson tourné) | testé hors Fusion | [vérifié] pytest : résultat de `exemples/apres.step` au millième de mm³ (`tests/test_calcul.py`) |
| Bouton dans SOLIDE → Modifier, dialogue, résumé, aperçu | codé | [supposé] |
| Une ligne de timeline, armatures d'autres composants comprises | codé | [supposé] — méthode Cabineo S1–S5 + Flight Case T7/T12 |
| Recalcul quand un panneau change en amont | codé | [supposé] — méthode Cabineo S2/S4 |
| Réédition en place / par remplacement | codé | [supposé] — Cabineo S3, Flight Case T6 |
| Textes en 4 langues | codé | [vérifié] pytest (mêmes clés, mêmes variables) |
| Icône clair / sombre | générée | planche `docs/icones/planche.png` ; affichage dans Fusion [supposé] |

## Relecture du code (2026-11-02)

Relecture indépendante de la couche Fusion, sans Fusion (lecture du code et de la doc de l'API). Corrigé :

1. Plusieurs armatures en contact : la 2e jonction prenait le mauvais corps de la base (hors édition,
   `BaseFeature.bodies` ne rend que les corps restants). Jonctions faites du dernier rang au premier, corps
   pris dans un instantané lu juste après la base.
2. Réédition en place : la direction d'entrée des armatures est réécrite avec les réglages.
3. Dépendance : la forme native est essayée même si la vue depuis la racine lève.
4. Marqueur de timeline parti du tout début : remis au début après une réédition.

## Avancement estimé

**60 %** : tout est codé et le calcul est prouvé ; reste à le voir tourner dans Fusion (recette, puis la liste
ci-dessous).

## Prochaine étape recommandée

Jouer la recette automatique : coller `essai/recette/MESSAGE.md` dans Claude Desktop, Fusion ouvert, add-in
lancé. Puis la liste « À vérifier dans Fusion ». Message prêt à coller ensuite dans une session Claude Code :

> Dans le dépôt fusion360-feuillure-rainure, lis `docs/ETAT.md` et le dernier rapport de `essai/resultats/`.
> Corrige ce qui est KO, mets à jour ETAT.md (passe en [vérifié] ce qui est confirmé), commit et push sur main.

## À vérifier dans Fusion

D'abord : GitHub Desktop → **Pull** ; Utilitaires → Scripts et compléments → Compléments → « + » →
dossier `FeuillureRainure` → **Exécuter** (cocher Exécuter au démarrage).

| # | Geste | Résultat attendu |
|---|---|---|
| V1 | Exécuter l'add-in | Bouton « Feuillure / rainure » dans SOLIDE → Modifier ; pas de `demarrage.log` dans `FeuillureRainure` |
| V2 | Recette automatique (`essai/recette/MESSAGE.md`) | 17 OK, 0 KO |
| V3 | Ouvrir `exemples/avant-chevauchement.step` ; Feuillure / rainure ; cible = grand panneau, armatures = les deux autres ; OK | Résumé « rainure 19,6 × 10,3 mm » ×2 ; une ligne « Rainure ×2 · jeu 0,3 » ; même forme que `exemples/apres.step` |
| V4 | Même chose avec `exemples/avant-contact.step` | Armatures allongées de 10 (orange dans l'aperçu), même cible usinée |
| V5 | Double-clic sur la ligne, jeu 0,5, OK | La ligne reste à sa place, rainures de 20 × 10,5 |
| V6 | Double-clic, puis Échap | Rien ne change ; le marqueur de timeline revient au bout |
| V7 | Reculer la timeline avant la ligne, épaissir une armature, revenir au bout | La rainure suit, sans commande |
| V8 | Thèmes clair, bleu foncé, gris foncé | Icône nette dans la barre, le menu et la timeline |
| V9 | Enregistrer, arrêter l'add-in, rouvrir le fichier | Il s'ouvre, la géométrie reste ; relancer l'add-in, tout se recalcule |

## Questions produit

Aucune en attente (réponses du 2026-11-02 dans `docs/DECISIONS.md`).

## Notes pour l'écosystème

- Identifiants (à ne jamais changer) : manifest `0134ae06-1eff-42e0-acf7-3e446f9b0b23`, commandes
  `feuillureRainureCmd`, `feuillureRainureModifierCmd`, fonction `feuillureRainure`, groupe d'attributs
  `feuillureRainure`.
- API preview (fonctions personnalisées) : point bloquant pour une vente tant qu'Autodesk ne l'a pas sortie de
  preview.
- Code commun avec les autres plugins : point d'entrée, `journal.py`, `langues.py`, `fusion_api.py` (repris de
  Dogbone).
