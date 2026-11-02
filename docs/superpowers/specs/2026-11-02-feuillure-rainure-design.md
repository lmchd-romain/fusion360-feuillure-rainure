# Feuillure / rainure — conception

Statut : **v0.2.0 construite** (une armature, plusieurs cibles), **à vérifier dans Fusion** (recette `essai/recette`, liste « À vérifier » de
`docs/ETAT.md`). Légende : **(décidé)** l'utilisateur, **(mon choix)** l'agent, **[vérifié]** constaté dans
Fusion (preuve citée), **[supposé]** pas encore constaté.

## Intention

Remplacer la combinaison « couper » que l'utilisateur fait aujourd'hui entre panneaux (`exemples/booleen-actuel.step`)
par une opération qui laisse un **jeu**, sait **allonger** une armature posée contre la cible, et tient sur
**une ligne de timeline** qui suit le meuble.

## Contexte

Description : `docs/description.txt`. Exemples relevés le 2026-11-02 (OpenCascade, mm) :

| Fichier | Contenu |
|---|---|
| `avant-chevauchement.step` | cible 200 × 19 × 200 ; deux armatures de 19 qui y rentrent de 10 (l'une sur toute la hauteur, l'autre arrêtée, 106,282 de haut) |
| `avant-contact.step` | les mêmes armatures, posées contre la cible |
| `booleen-actuel.step` | la combinaison « couper » d'aujourd'hui : rainures 19 × 10, sans jeu |
| `apres.step` | le résultat voulu : rainures 19,6 × 10,3, arrêtée allongée de 0,3 à chaque bout ; armatures inchangées ; volume de la cible 698 046,663 mm³ |

Habitudes de l'utilisateur (octobre 2026) : documents Hybrides, un panneau = un composant (parfois un corps),
modifications en reculant dans la timeline.

## Objectifs v1

1. D'abord une armature, puis une ou plusieurs cibles, choisies comme des corps ou des composants (décidé le
   2026-11-02 après le premier essai ; la v0.1 faisait l'inverse).
2. Jeu unique, de chaque côté et au fond (décidé) ; armature en chevauchement inchangée, profondeur = son
   chevauchement (décidé) ; armature en contact allongée de la profondeur réglée (décidé).
3. Une ligne de timeline, avec son icône, double-clic pour modifier (décidé).
4. Aucun corps supprimé (décidé).

## Hors périmètre

Plusieurs armatures d'un coup ; panneaux non rectangulaires suivis au plus près (la boîte du panneau fait foi) ;
congés de fraise dans les angles (plugin Dogbone, qui peut se poser après).

## Anti-objectifs

- Un corps outil, un paramètre ou un composant laissé en plus dans le design.
- Un usinage posé au mauvais endroit sans prévenir : dans le doute, refus avec un message clair.
- Un fichier qui ne s'ouvre plus sans l'add-in.

## Comportement

### Dialogue (SOLIDE → Modifier, « Feuillure / rainure »)

| Champ | Type | Défaut | Rôle |
|---|---|---|---|
| Armature | sélection, corps ou composant, 1 | — | le panneau qui s'emboîte |
| Cibles | sélection, corps ou composants, 1 et plus | — | les panneaux usinés |
| Jeu | valeur mm | 0,3 (dernier validé) | de chaque côté et au fond |
| Profondeur | valeur mm | 10 (dernier validé) | enfoncement de l'armature dans les cibles qu'elle touche seulement |
| Résumé | texte | — | une ligne par cible : « Côté gauche : rainure 19,6 × 10,3 mm (armature allongée de 10 mm) » |

Un composant choisi donne son corps solide unique ; plusieurs corps : message, choisir le corps. L'armature ne
s'allume pas au survol dans « Cibles ». OK reste grisé tant qu'une cible pose problème.

### Détection et calcul (noyau pur, `calcul.py`)

Chaque panneau est sa boîte orientée minimale (exacte pour un panneau rectangulaire, à tout angle).

- **Chevauchement** : l'intersection armature ∩ cible a une épaisseur dans les trois directions. L'axe d'entrée
  est celui où l'armature dépasse de la cible (hors épaisseur du panneau, sinon le plus long) ; enfoncement =
  épaisseur de l'intersection sur cet axe ; traversante si elle dépasse des deux côtés.
- **Contact** : une face de l'armature est dans le plan d'une face de la cible, normales opposées, avec une aire
  commune (> 1 mm²).
- **Usinage** : la boîte de l'armature agrandie du jeu (et, en contact, la tranche d'allongement coupée par la
  cible, agrandie du jeu), coupée par la cible.
- **Allongement** (contact) : tranche de la section de l'armature, de sa face avant jusqu'à la profondeur
  mesurée depuis la face d'entrée de la cible, coupée par la boîte de la cible.
- **Feuillure / rainure** : feuillure si l'usinage déborde de la cible dans l'épaisseur de l'armature.

Exemple chiffré (exemples) : armature x 54 → 73, y 9 → 222,42 ; cible y 0 → 19 ; jeu 0,3 → usinage
x 53,7 → 73,3, y 8,7 → 19 : rainure 19,6 × 10,3. Les deux armatures enlèvent 61 953,337 mm³ : cible
698 046,663 mm³, comme `apres.step`.

### Timeline (`fonction.py`)

v0.1 faisait les allongements par une combinaison entre deux composants (outil dans la base de la cible) et lisait
le volume d'un corps temporaire : au premier essai, le cas contact a échoué (cause exacte non lue, journal non
transmis). v0.2 n'a plus que des combinaisons dans un seul composant, avec des corps natifs (Cabineo, constaté) :

1. base de l'armature, dans son composant : un allongement par cible en contact (ou un petit cube au cœur de
   l'armature s'il n'y en a aucun), puis l'outil de chaque cible du même composant ;
2. la fonction de l'opération, juste après ; dépendances : la plus grande face de l'armature et de chaque cible ;
3. pour chaque cible d'un autre composant, dans ce composant : sa base (outil), sa fonction emboîtée, sa
   découpe, sa fonction étendue ;
4. les découpes des cibles du composant de l'armature ;
5. la jonction des allongements à l'armature, en dernier ;
6. la fonction de l'opération étendue de sa base à la jonction : une seule ligne.

Briques : base + fonction + combinaison dans un composant [vérifié — Cabineo S1–S4] ; fonction emboîtée et
opérations d'autres composants entre les bornes, une ligne [vérifié — Flight Case T7, T12, T17] ; l'ensemble
ici : [supposé], recette R8, R12, R16.

Boîtes des panneaux lues sur le B-rep (normale de la plus grande face plane, plus longue arête, sommets) : exactes
pour un panneau rectangulaire ; boîte orientée minimale de Fusion en repli. Contact à 0,05 mm près.

**Calcul** : chaque fonction refait sa base (celle de l'opération : allongements, outils du même composant,
petit cube ; une emboîtée : son outil), depuis les pièces telles qu'elles sont juste avant elle ; chaque cible
garde le mode choisi à la création. Une cible que l'armature ne touche plus : avertissement sur la ligne.

**Réédition** (double-clic, même sur une fonction emboîtée) : timeline reculée avant la ligne, dialogue prérempli.
Même armature, mêmes cibles, mêmes modes : réglages réécrits et chaque base refaite en place [vérifié —
Cabineo S3, pour une base] ; sinon la ligne est supprimée et refaite au même rang [vérifié — Flight Case T6, T15].

**Fichier sans l'add-in** : la géométrie reste, icône générique, pas de recalcul [vérifié — Cabineo M2].

### Refus

Cible ou armature allongée dans un composant utilisé plusieurs fois ; composant lié ; cible que l'armature ne
touche pas ; cible qui est aussi l'armature ; profondeur ≥ épaisseur de la cible ; armature entièrement dans la
cible ; jeu négatif.

## Questions pour la recette (et replis)

| # | Question | Repli si non |
|---|---|---|
| Q1 | Fonctions emboîtées des cibles d'autres composants sur la ligne de l'opération (R8, R12) ? | groupe de timeline replié (Dogbone) |
| Q2 | Allongement par jonction dans le composant de l'armature, cas contact (R9, R12) ? | — (combinaison d'un seul composant, méthode constatée) |
| Q3 | Le calcul suit-il une armature épaissie en amont (R4, R10) ? | commande « Mettre à jour » |
| Q4 | Réédition en place avec fonctions emboîtées (R13) ? | remplacement au même rang |
| Q5 | Caisson tourné, armature et cible dans un même composant (R16) ? | — |

## Laissé au constructeur

Noms des modules, découpage des fonctions, tolérances numériques (1 µm géométrique, 1 mm² de contact).
