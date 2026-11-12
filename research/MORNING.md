# Compte rendu de la nuit du 12 novembre 2026

Version finale, écrite à 05:52. Le détail et les chiffres sont dans `research/RESEARCH.md` : un résumé « établi /
probable / ouvert » est en tête du journal, et les entrées de la nuit sont dans la section « Night of 2026-11-12 ».
Tout est poussé sur le fork, branche `gamestate-research`.

## Ce qui a été fait

1. **Coloriage (priorité 1).**
   - Sur des combats entiers (60 s, 4 matchs), la simulation lit ~245 Ko d'état par combat. Hier, j'avais écrit 240 Ko
     pour 300 frames ; avec les catégories corrigées, c'est 183 Ko. La mesure croît encore avec la durée observée
     (183 → 218 → 246 Ko).
   - Table par site d'allocation : `research/map/sites.md`. Répartition : la table de 1 024 entrées 96 Ko, objets de
     combat ~18 Ko, fiches de collision des objets ~3 Ko, géométrie du stage 1 à 7 Ko, piles 3 à 7 Ko, et une traîne de
     ~95 Ko en ~320 sites qui reviennent d'un match à l'autre.
   - **Les parties mobiles du stage gardent leur état dans la géométrie de collision du stage** : segments, sommets
     et groupes de lignes, créés au chargement du match. Trois méthodes concordent sur deux stages : les traces (avec
     et sans dangers), des perturbations maintenues (le combat change) et la lecture du code. Sur dump, les 61
     contacts au sol relevés pointent tous sur ces segments.
   - **La table de 1 024 entrées est portée d'une frame à l'autre, mais la perturber ne change rien au combat**. Perturbée
     pendant 10 s sur deux stages, elle ne change ni le hash ni aucune valeur nommée, alors que le témoin positif fait
     tout diverger. La lecture du code en fait une grille spatiale des lignes du stage. Je l'avais appelée
     « présentation », puis « recalculée chaque frame » : les deux étaient faux. Une erreur injectée y reste 60 frames.
     Son rôle reste ouvert.
   - Le bloc de 616 000 octets n'est pas la collision du stage, mais le pool des 350 fiches de collision des objets.
2. **Nommage par lecture du code (priorité 2).** Trois sous-agents ont lu le C généré sans lancer le jeu
   (`research/map/code_reading/`). 75 champs sont ajoutés et vérifiés par le jeu, sur 8 à 18 matchs selon le module :
   - 43 dans ControlModule (sticks courants et précédents, boutons, compteurs) ;
   - 24 dans les 11 énergies de KineticModule, dont le jeu appelle les getters sur l'énergie elle-même ;
   - 6 dans GroundModule (contacts, rebord, forme) et 2 dans CameraModule.
   - La lecture du code a aussi expliqué une différence que la vérification venait de trouver : chez Ice Climbers,
     la vitesse de l'énergie de dégâts ou de gravité est lue ailleurs. Le lecteur est corrigé.
   - Les champs que le jeu ne peut pas vérifier tiennent des invariants d'une frame à l'autre, sur 3 matchs.
3. **Solidité (priorité 3).**
   - Séries longues : 37 matchs de 3 ou 5 minutes, CPU contre CPU, de 2 à 4 joueurs.
   - Oracle de rollback : 31 nouveaux matchs, dont 3 avec items qui tombent.
   - Oracle strict : 8 nouveaux matchs.
   - Erreurs injectées : l'oracle strict voit une erreur que le hash ne voit pas.
   - Le lecteur reste exact à travers 2 Final Smash complètes et une fin de combat réelle.
4. **Ménage du journal (priorité 4).** Résumé de tête ajouté ; 11 passages devenus faux sont annotés en place, et mes
   propres erreurs de la nuit sont corrigées là où elles étaient écrites.

## Chiffres clés

- Lecteur et vérification automatique : 169 getters simples et 1 033 appels avec argument ou receveur.
- Séries longues (comptées depuis leurs fichiers) : 39 runs, 37 matchs distincts, **161 677 139 valeurs égales**.
  172 différaient : 167 sur le champ faux du Héros et 5 sur la vitesse d'Ice Climbers, deux erreurs du lecteur
  corrigées et revérifiées depuis.
- Oracle de rollback : 31 matchs à 150 chargements chacun, 0 frame rejouée différente.
- Oracle strict : 24 rejeux de nouveaux matchs, tous identiques au hash. 6 matchs passent ; 1 échoue sur une seule
  ligne ouverte ; le match à 4 joueurs avec items échoue sur 17 à 42 lignes (voir plus bas).
- Vérification de fin de nuit (05:38, exécutable relié à 04:20, à jour avec le code) : build normal à jour ; oracle
  de rollback 49/0 ; **témoin sans élagage 149/0 sur ses 3 matchs** ; porte de déterminisme CPU contre CPU identique
  (4 028 lignes).

## Couverture des tests (`research/map/coverage.md`)

- **Persos : 84 sur 89.** Il manque les trois Mii (le match de débogage ne sait pas leur donner un Mii) et Pyra/Mythra
  (aucun nom essayé n'est reconnu).
- **Stages : 13** : Destination Finale, Champ de bataille, Grand Champ de bataille, Château 64 (avec et sans dangers),
  Stade Pokémon 2, Kalos, Smashville, Town and City, Lylat, Yoshi's Story, Delfino, Halberd, Château de Dracula.
- **Situations** : 2, 3 et 4 joueurs ; CPU niveau 9 contre CPU niveau 9 ; items qui tombent ; dangers ; Final Smash ;
  fin de combat ; combats de 3 et de 5 minutes.

## Ce qui a échoué ou reste ouvert

- **La porte de déterminisme du dépôt échoue cette nuit, avec le runtime d'hier aussi.** Le jeu est déterministe là
  où son entrée l'est : en CPU contre CPU, ou avec une entrée calée sur la frame logique, les runs sont identiques.
  La cause est l'entrée scriptée du joueur 1, probablement son minutage ; pourquoi la même porte passait hier n'est
  pas expliqué.
- **Le test de rollback à entrées corrigées n'a pas abouti.**
  - L'outil est prêt, les références se répètent et le témoin négatif discrimine.
  - Le gel est compris : **charger le tout premier état sauvegardé par l'anneau fige le jeu**. Cela arrive dès que la
    profondeur atteint l'intervalle : 6 en arrière toutes les 6 gèle, 5 toutes les 6 passe. C'est probablement un
    défaut du dépôt d'origine.
  - Le test a aussi un défaut à moi : la mauvaise prédiction commence avant la première frame de l'anneau. Il faudra
    la faire commencer avec lui (un changement du runtime).
- **L'oracle strict n'est pas propre avec des items sur le stage** (match à 4 joueurs) : 17 à 42 lignes par rejeu.
  Ce sont des conteneurs indexés par des noms d'effets et de sons, et les tables de valeurs des scripts : le même
  contenu, dans d'autres nœuds. Il faudrait une comparaison par contenu. Un match à 2 joueurs avec items passe.
- Une ligne de l'oracle reste inexpliquée : un compteur double, +1 au rejeu, vu dans 2 matchs.
- Mes erreurs, chacune corrigée et notée au journal :
  - la liste des getters régénérée, et l'exécutable relié, pendant une série ;
  - une injection écrite après un appel qui ne revient pas, et deux injections qui faisaient planter le jeu ;
  - des heures de journal estimées au lieu d'être lues ;
  - des traces supprimées trop tôt ;
  - un PASS de l'oracle sans aucun rejeu (il dit maintenant NO REPLAYS) ;
  - deux étiquettes fausses pour la table de 1 024 entrées ;
  - un « avant le premier chargement » que le log ne montrait pas.

## Décisions et raisons

- Les comparaisons entre runs se font en CPU contre CPU, parce que les runs scriptés ne se répètent pas.
- Je n'ajoute une règle à l'oracle que sur un invariant du code (requêtes de son, gestion des fibres) ; le compteur
  double et les conteneurs restent inexpliqués tant que je ne sais pas les prouver inoffensifs.
- Les champs « probables » de la lecture du code ne servent pas au lecteur tant qu'une seconde méthode ne les
  confirme pas.
- Le test à entrées corrigées a été arrêté à sa limite de 45 minutes.
- Aucun appel au jeu qui écrit ou prend des références (getters signalés par la lecture du code).

## Suite recommandée

1. **Une comparaison par contenu dans l'oracle strict** (suivre les pointeurs d'un conteneur au lieu de comparer des
   octets) : elle débloquerait les matchs avec items.
2. **Le test d'entrées corrigées** : faire commencer la mauvaise prédiction avec l'anneau, et utiliser un anneau dont
   la profondeur reste sous l'intervalle (5 toutes les 6), ou corriger le chargement du premier état.
3. **Caler la séquence d'entrées de la porte sur la frame logique**, ou utiliser la porte CPU contre CPU
   (`research/tools/final_check.sh`).
4. **Reprendre l'allègement de la sauvegarde par familles de sites**, jugé par l'oracle strict sur les matchs élargis,
   sans présumer que la table de 1 024 entrées peut être laissée de côté (elle est portée d'une frame à l'autre).
5. Nommer la suite par lecture du code : le reste de la fiche de collision, la géométrie du stage, les variables des
   armes et des items (une sonde sûre reste à faire).

## Questions

1. La porte scriptée du dépôt échoue sur votre PC cette nuit. Voulez-vous que je prépare, sans l'envoyer, une
   proposition pour le dépôt d'origine : séquence calée sur la frame logique, et signalement du gel au chargement du
   premier état de l'anneau ?
2. Pour la suite, que préférez-vous en premier : la comparaison par contenu dans l'oracle (fiabilité avec items), ou
   l'allègement de la sauvegarde par familles de sites (l'objectif de départ, passé au second plan) ?
3. Pour couvrir les Mii et Pyra/Mythra, il faudrait passer par les écrans de sélection. Est-ce utile, ou 84 persos
   suffisent-ils pour la carte ?
