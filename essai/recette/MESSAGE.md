Recette automatique de FeuillureRainure. Fais tout toi-même avec le MCP de Fusion ; ne me demande quelque chose
que si tu es bloqué ou si tu doutes d'une capture.

1. Prérequis. Le dépôt est sur mon PC dans `C:\Users\PC-ADMIN\Documents\GitHub\fusion360-feuillure-rainure` (sinon
   cherche le dossier `fusion360-feuillure-rainure` qui contient `essai\recette\recette.py`). Vérifie par le MCP de
   Fusion que l'add-in FeuillureRainure tourne : `import sys; print("feuillure_rainure.fonction" in sys.modules)`.
   S'il répond False, dis-moi : « Utilitaires → Scripts et compléments → Compléments → FeuillureRainure →
   Exécuter », et attends que je réponde « fait ». N'enregistre et ne ferme aucun de mes documents.

2. Lancement. Exécute ce Python dans Fusion par le MCP (environ une minute ; la recette crée ses propres pièces
   dans des documents neufs, jamais enregistrés, qu'elle ferme à la fin) :

   ```python
   import runpy

   m = runpy.run_path(r"C:\Users\PC-ADMIN\Documents\GitHub\fusion360-feuillure-rainure\essai\recette\recette.py")
   print(m["recette"]())
   ```

   La sortie donne le compte (OK / KO / à regarder) et le chemin du rapport
   `essai\resultats\recette-<horodatage>.md` (le `.json` à côté).

3. Rapport. Lis le `.md` (ou fais-le afficher par le MCP : `print(open(r"<chemin>", encoding="utf-8").read())`).
   Pour chaque KO, lis la mesure, l'attendu et la trace. Lis aussi la fin de
   `FeuillureRainure\journal.log` (les recalculs et leurs durées y sont notés).

4. Captures. Ouvre chaque image `recette-<horodatage>-*.png` du même dossier et juge-la d'après la phrase
   « à juger à l'œil » du rapport. Si tu ne peux pas ouvrir les images, ou si tu doutes, montre-moi le chemin
   et pose-moi une seule question fermée (oui / non).

5. Compte rendu, en 5 lignes au plus, en français simple : le compte OK / KO / à regarder ; ce qui ne va pas,
   en mots de menuisier ; ton avis sur les captures ; les gestes « à la main » du rapport (je les ferai
   moi-même) ; ce que tu proposes ensuite.

6. Résultats. Propose-moi de pousser le rapport et les captures sur GitHub. Seulement si je dis oui : avec git
   si tu y as accès (`git add essai/resultats`, commit « essai: recette <date> », `git pull --rebase`,
   `git push`, sur `main`), sinon explique-moi les clics dans GitHub Desktop (Changes → résumé → Commit to
   main → Push origin).
