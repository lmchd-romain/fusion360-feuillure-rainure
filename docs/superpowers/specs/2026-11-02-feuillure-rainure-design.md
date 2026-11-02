# Feuillure / rainure — conception

Statut : **v0.1.0 construite, à vérifier dans Fusion** (recette `essai/recette`, liste « À vérifier » de
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

1. Une cible, une ou plusieurs armatures, choisies comme des corps ou des composants (décidé).
2. Jeu unique, de chaque côté et au fond (décidé) ; armature en chevauchement inchangée, profondeur = son
   chevauchement (décidé) ; armature en contact allongée de la profondeur réglée (décidé).
3. Une ligne de timeline, avec son icône, double-clic pour modifier (décidé).
4. Aucun corps supprimé (décidé).

## Hors périmètre

Plusieurs cibles d'un coup ; panneaux non rectangulaires suivis au plus près (la boîte du panneau fait foi) ;
congés de fraise dans les angles (plugin Dogbone, qui peut se poser après).

## Anti-objectifs

- Un corps outil, un paramètre ou un composant laissé en plus dans le design.
- Un usinage posé au mauvais endroit sans prévenir : dans le doute, refus avec un message clair.
- Un fichier qui ne s'ouvre plus sans l'add-in.

## Comportement

### Dialogue (SOLIDE → Modifier, « Feuillure / rainure »)

| Champ | Type | Défaut | Rôle |
|---|---|---|---|
| Cible | sélection, corps ou composant, 1 | — | le panneau usiné |
| Armatures | sélection, corps ou composants, 1 et plus | — | les panneaux qui s'emboîtent |
| Jeu | valeur mm | 0,3 (dernier validé) | de chaque côté et au fond |
| Profondeur | valeur mm | 10 (dernier validé) | enfoncement des armatures en contact |
| Résumé | texte | — | une ligne par armature : « Étagère : rainure 19,6 × 10,3 mm (chevauchement de 10 mm, armature inchangée) » |

Un composant choisi donne son corps solide unique ; plusieurs corps : message, choisir le corps. La cible ne
s'allume pas au survol dans « Armatures ». OK reste grisé tant qu'une armature pose problème.

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

Une fonction personnalisée dans le composant de la cible :

1. fonction de base de ce composant : corps [0] outil de coupe, puis un corps d'allongement par armature en
   contact (calculés dans le monde, ramenés dans le repère du composant) ;
2. la fonction, créée juste après sa base, ne regroupe d'abord qu'elle ; dépendances : la plus grande face de la
   cible et de chaque armature, encore intactes ;
3. une combinaison « joindre » par armature en contact, dans son composant, outil pris dans la base ;
4. la combinaison « couper » de la cible, en dernier ;
5. timeline reculée, la fonction étendue de la base à la découpe, timeline remise.

Les étapes 1, 2, 4, 5 sont la méthode de Cabineo [vérifié — Cabineo, résultats d'essai S1–S4]. Une combinaison
entre composants, outil dans une base d'un autre composant, est créée par Fusion dans le composant du corps
cible [vérifié — Cabineo, sonde S5]. Des opérations d'un autre composant entre les bornes d'une fonction restent
sur sa ligne [vérifié — Flight Case, sondes T7, T12]. L'ensemble (étape 3 entre les bornes) : [supposé], à
confirmer par la recette (R9).

**Calcul** : rien tant que la découpe n'est pas regroupée ; ensuite, tous les corps de la base sont refaits
depuis les pièces telles qu'elles sont juste avant la fonction ; chaque armature garde le mode choisi à sa
création (sa direction d'entrée est gardée dans le repère de son composant). Une armature qui ne touche plus
ou ne rentre plus : avertissement sur la ligne.

**Réédition** (double-clic) : timeline reculée avant la fonction, dialogue prérempli. Même cible, mêmes
armatures, mêmes modes : mise à jour en place [vérifié — Cabineo S3] ; sinon la fonction est supprimée et
refaite au même rang [vérifié — Flight Case T6].

**Fichier sans l'add-in** : la géométrie reste, icône générique, pas de recalcul [vérifié — Cabineo M2].

### Refus

Cible ou armature allongée dans un composant utilisé plusieurs fois ; composant lié ; armature qui ne touche
pas la cible ; profondeur ≥ épaisseur de la cible ; armature entièrement dans la cible ; jeu négatif.

## Questions pour la recette (et replis)

| # | Question | Repli si non |
|---|---|---|
| Q1 | Les « joindre » d'autres composants entre les bornes restent-ils sur la ligne (R9) ? | une fonction par composant d'armature, à la suite (comme Cabineo) |
| Q2 | La combinaison « joindre » accepte-t-elle un outil de la base d'un autre composant, vu depuis la racine (R10) ? | essai suivant dans le code : collection du composant de l'armature ; sinon base propre à l'armature |
| Q3 | Le calcul suit-il une armature épaissie en amont (R5, R11) ? | commande « Mettre à jour » |
| Q4 | Caisson tourné, sous-composants (R14, R15) ? | — |

## Laissé au constructeur

Noms des modules, découpage des fonctions, tolérances numériques (1 µm géométrique, 1 mm² de contact).
