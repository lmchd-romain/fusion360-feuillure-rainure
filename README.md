# Feuillure / rainure — add-in Fusion 360

Usine dans un ou plusieurs panneaux (les **cibles**) la feuillure ou la rainure où s'emboîte un panneau
(l'**armature**), avec un **jeu**. Comme une combinaison « couper » de Fusion, mais avec le jeu et sans
supprimer aucun corps. On choisit d'abord l'armature, puis ses cibles (exemple : une étagère, puis les deux
côtés qui la reçoivent).

- **Chevauchement** : l'armature rentre déjà dans une cible. Elle ne bouge pas ; la rainure prend sa forme,
  agrandie du jeu de chaque côté et au fond.
- **Contact** : l'armature touche seulement une cible. Elle est allongée de la **profondeur** réglée vers
  cette cible, puis la cible est usinée comme ci-dessus. Les deux cas peuvent se mêler dans une opération.
- **Feuillure** si l'usinage débouche sur un côté de la cible (armature au bord), **rainure** sinon.
- **Une seule ligne de timeline** par opération, avec son icône, même quand les armatures sont dans d'autres
  composants. Elle suit le meuble : épaissir, allonger ou déplacer un panneau en amont refait l'usinage.

Exemple (fichiers `exemples/`) : armatures de 19 mm, jeu 0,3, profondeur 10 → rainures de 19,6 × 10,3 mm ;
le résultat est celui de `exemples/apres.step`, au millième de mm³ près (`tests/test_calcul.py`).

## Installation

1. GitHub Desktop → **Fetch / Pull** du dépôt `fusion360-feuillure-rainure`.
2. Fusion → **Utilitaires → Scripts et compléments → Compléments → « + »** → choisir le dossier
   `FeuillureRainure` du dépôt → **Exécuter**. Cocher **Exécuter au démarrage**.
3. Le bouton **Feuillure / rainure** apparaît dans **SOLIDE → Modifier**, à côté de « Combiner ».

## Utilisation

1. **Armature** : cliquer le panneau qui s'emboîte (corps ou composant).
2. **Cibles** : cliquer les panneaux à usiner (un ou plusieurs).
3. **Jeu** (0,3 mm par défaut) et **Profondeur** (10 mm, pour les cibles que l'armature touche seulement). Les
   champs acceptent les expressions et les paramètres (`jeu_rainure`).
4. Le résumé dit, pour chaque cible, ce qui sera fait ; l'aperçu montre l'usinage en bleu et ce que gagne
   l'armature en orange. **OK**.

**Modifier** : double-clic sur la ligne de timeline. Changer le jeu ou la profondeur garde la ligne à sa place
(les opérations faites après, sur la rainure, restent accrochées) ; changer d'armature ou de cibles refait la
ligne au même endroit.

Version 0.1 (une cible, plusieurs armatures) : ses opérations gardent leur forme mais ne se recalculent plus ;
les supprimer et les refaire.

Les derniers réglages validés sont repris à l'ouverture suivante.

## Limites

- Chaque panneau est pris comme sa **boîte** (panneau rectangulaire, à n'importe quel angle). Un panneau
  découpé ou percé est usiné d'après sa boîte extérieure.
- Une **cible utilisée plusieurs fois** (même composant copié) est refusée : l'usinage apparaîtrait dans chaque
  copie. Même refus pour une armature allongée. Faire « Coller nouveau » d'abord.
- Une armature par opération.
- Utilise l'API des **fonctions personnalisées**, en préversion chez Autodesk : usage à l'atelier, builds Fusion
  validés dans `docs/ETAT.md`.
- Fichier ouvert sans l'add-in : la géométrie reste, la ligne garde une icône générique et ne se recalcule plus ;
  relancer l'add-in suffit.

## Dépannage

- Rien ne se passe au démarrage : lire `FeuillureRainure/demarrage.log`.
- Une erreur dans le dialogue ou au recalcul : lire `FeuillureRainure/journal.log` (dernières lignes).
- Après une mise à jour : **Arrêter** puis **Exécuter** l'add-in (nouvelle icône : redémarrer Fusion).
- Message d'erreur à la validation : il donne la cause en une ligne ; la recopier avec les dernières lignes de
  `journal.log`.
- Ligne de timeline en jaune : l'armature ne touche plus une cible ou n'y rentre plus ; double-cliquer la ligne,
  le résumé dit laquelle.

## Recette dans Fusion

Coller `essai/recette/MESSAGE.md` dans Claude Desktop (Fusion ouvert, MCP de Fusion actif) : la recette
construit l'exemple dans des documents neufs, pose, modifie en amont, réédite, supprime, et écrit son rapport dans
`essai/resultats/`.

## Développement

- `FeuillureRainure/feuillure_rainure/` : noyau pur testé (`geometrie`, `calcul`, `reglages`, `langues`) et couche
  Fusion (`fusion_api`, `outils`, `fonction`, `commande`).
- Textes dans `FeuillureRainure/ressources/langues/` (français, anglais, allemand, japonais, selon la langue de
  Fusion).
- Tests : `python -m pytest` (Python 3.14 comme Fusion). Lint : `ruff check`.
- Icône : `docs/icones/icones.html` → `python docs/icones/generer_icones.py` (Chrome + Pillow).
- Conception : `docs/superpowers/specs/2026-11-02-feuillure-rainure-design.md` ; décisions : `docs/DECISIONS.md` ;
  état : `docs/ETAT.md`.
