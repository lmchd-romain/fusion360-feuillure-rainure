# État du plugin Feuillure / rainure

- Date : 2026-11-02
- Version du manifest : **0.2.1** (0.1.0 le matin du 02/11, 0.2.0 l'après-midi)
- Légende : **[vérifié]** = constaté dans Fusion, preuve citée ; **[supposé]** = déduit du code ou des docs,
  pas constaté dans Fusion. Ce plugin n'a **pas encore tourné dans Fusion** : la session qui l'a écrit n'avait
  pas Fusion. Chaque brique reprend une méthode constatée dans un autre plugin de l'atelier. Premier essai de
  l'utilisateur sur la 0.1.0 (2026-11-02) : chevauchement **marche** ; contact **en erreur** (message non
  transmis) ; demande : d'abord une armature, puis plusieurs cibles → version 0.2.0.

## Ce que fait le plugin

Feuillures et rainures avec jeu, en une ligne de timeline : une armature, une ou plusieurs cibles usinées ;
l'armature est allongée de la profondeur vers les cibles qu'elle touche seulement. Voir `README.md`.

## Fonctions

| Fonction | État | Preuve |
|---|---|---|
| Calcul (chevauchement, contact, jeu, feuillure / rainure, caisson tourné, étagère entre deux côtés) | testé hors Fusion | [vérifié] pytest : résultat de `exemples/apres.step` au millième de mm³ (`tests/test_calcul.py`) |
| Chevauchement, une cible (v0.1.0) | marche | [vérifié] essai de l'utilisateur, 2026-11-02 |
| Contact (v0.1.0) | en erreur | [vérifié] essai de l'utilisateur ; v0.2.0 refait ce chemin |
| Contact, une armature et deux cibles (v0.2.0) | marche | [vérifié] essai de l'utilisateur, 2026-11-02 |
| Réédition (v0.2.0) | en panne, corrigée en 0.2.1 | [vérifié] essai : « Cibles » passait de 2 à 5, armature en surbrillance après Échap ; correctif [supposé] |
| Bouton dans SOLIDE → Modifier, dialogue, résumé, aperçu | marche en 0.1.0 | [vérifié] essai de l'utilisateur ; flux armature → cibles de la 0.2.0 [supposé] |
| Une ligne de timeline, cibles d'autres composants comprises (fonctions emboîtées) | codé | [supposé] — Cabineo S1–S4 + Flight Case T7/T12/T17 |
| Recalcul quand un panneau change en amont | codé | [supposé] — méthode Cabineo S2/S4 |
| Réédition en place / par remplacement | codé | [supposé] — Cabineo S3, Flight Case T6 |
| Textes en 4 langues | codé | [vérifié] pytest (mêmes clés, mêmes variables) |
| Icône clair / sombre | générée | planche `docs/icones/planche.png` ; affichage dans Fusion [supposé] |

## Version 0.2.1 (2026-11-02, après le deuxième essai)

Constaté : création à une armature et deux cibles en contact, **bonne**. Réédition : « Cibles » passe de 2 à 5 ;
Échap laisse l'armature en surbrillance bleue, même cachée.

Cause [supposée, la plus probable] : Fusion rappelle `activate` pendant la commande. Le second passage remettait
les pièces (2 cibles de plus, et l'armature de trop dans sa ligne d'une seule pièce, versée dans « Cibles » :
2 + 2 + 1 = 5) et notait comme position d'origine du marqueur la timeline déjà reculée. Corrigé :

- activation traitée une seule fois (marqueur noté une fois, pièces remises une fois, lignes vidées avant) ;
- « Cibles » nettoyée à chaque changement : ni l'armature, ni doublon ;
- à la fermeture (OK ou Échap), sélections vidées **avant** de rendre le marqueur ;
- un composant dont le panneau est caché reste choisissable.

Tests : `tests/test_dialogue.py` rejoue ces trois situations sans Fusion.

## Version 0.2.0 (2026-11-02, après le premier essai)

- D'abord **une armature**, puis **plusieurs cibles** (demande de l'utilisateur).
- Cas contact refait : plus aucune combinaison entre deux composants (chaque cible d'un autre composant a sa
  fonction emboîtée, dans son composant) ; plus de lecture de volume sur un corps temporaire ; boîtes des
  panneaux lues sur le B-rep (exactes) ; contact jugé à 0,05 mm près. Une de ces trois choses causait l'erreur
  du premier essai [supposé] : la recette R7–R11 le dira.
- Message d'échec : la cause en une ligne, à recopier.
- Opérations de la 0.1.0 : gardent leur forme, ne se recalculent plus, à refaire.

## Relecture du code (2026-11-02)

Relecture indépendante de la couche Fusion, sans Fusion (lecture du code et de la doc de l'API). Corrigé :

1. Plusieurs armatures en contact : la 2e jonction prenait le mauvais corps de la base (hors édition,
   `BaseFeature.bodies` ne rend que les corps restants). Jonctions faites du dernier rang au premier, corps
   pris dans un instantané lu juste après la base.
2. Réédition en place : la direction d'entrée des armatures est réécrite avec les réglages.
3. Dépendance : la forme native est essayée même si la vue depuis la racine lève.
4. Marqueur de timeline parti du tout début : remis au début après une réédition.

## Avancement estimé

**65 %** : tout est codé, le calcul est prouvé, le chevauchement marche dans Fusion ; reste le contact et le
flux à plusieurs cibles à voir tourner (recette, puis la liste ci-dessous).

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
| V2 | Recette automatique (`essai/recette/MESSAGE.md`) | 18 OK, 0 KO |
| V3 | Ouvrir `exemples/avant-chevauchement.step` ; Feuillure / rainure ; armature = un petit panneau, cibles = le grand ; OK ; idem avec l'autre petit panneau | Résumé « rainure 19,6 × 10,3 mm » ; une ligne « Rainure · <armature> · jeu 0,3 » par opération ; même forme que `exemples/apres.step` |
| V4 | Même chose avec `exemples/avant-contact.step` | Armature allongée de 10 (orange dans l'aperçu), même cible usinée |
| V4b | Une étagère posée entre deux côtés : armature = l'étagère, cibles = les deux côtés | Une ligne ; une rainure dans chaque côté ; étagère allongée aux deux bouts |
| V5 | Double-clic sur la ligne, jeu 0,5, OK | Le dialogue montre la même armature et les mêmes cibles (pas plus) ; la ligne reste à sa place, rainures de 20 × 10,5 |
| V6 | Double-clic, puis Échap | Rien ne change ; le marqueur de timeline revient au bout ; plus rien en surbrillance |
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
