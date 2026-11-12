# Compte rendu de la nuit du 12 novembre 2026

Mis à jour après chaque étape (dernière mise à jour : 04:55 ; version finale après la vérification de 06:30).
Le détail et les chiffres sont dans `research/RESEARCH.md` : un résumé « établi / probable / ouvert » est en tête
du journal, et les entrées de la nuit sont dans la section « Night of 2026-11-12 ».

## Où on en est

| Priorité | État |
|---|---|
| 1. Coloriage | fait : combats entiers, table par site, table du stage, parties mobiles du stage, longue traîne |
| 2. Nommage des gros blocs | fait pour ControlModule, les énergies, le contact au sol, les sujets de caméra (75 champs vérifiés par le jeu) |
| 3. Solidité | 5 séries longues, 31 nouveaux matchs à l'oracle de rollback, oracle strict sur 7 nouveaux matchs, erreurs injectées, Final Smash, fin de combat ; rollback à entrées corrigées bloqué |
| 4. Ménage du journal | fait : résumé de tête, 9 passages annotés |

## Ce qui est fait

1. **Coloriage sur des combats entiers** (60 s, 4 matchs).
   - L'état lu par la simulation fait ~245 Ko par combat, dont ~150 Ko hors table du stage. Sur 300 frames, il fait
     183 Ko (et non 240 comme écrit hier : une région de code était comptée à tort comme simulation).
   - La mesure dépend encore de la durée observée (183 → 218 → 246 Ko pour 300, 1 200 et 3 600 frames).
   - **Conclusion d'hier tombée** : « aucun état dans un bloc créé pendant le combat ». Sur 60 s, environ 120 à 280 Ko
     d'état sont dans des blocs créés en combat, surtout des piles de fibres.
   - Table par site d'allocation : `research/map/sites.md`. La longue traîne (~95 Ko en ~320 sites) revient d'un match
     à l'autre.
2. **La table du stage n'est pas de l'état** : perturbée pendant 10 s, elle ne change ni le hash ni aucune valeur
   nommée. Le témoin positif, lui, fait tout diverger dès la frame suivante.
3. **Les parties mobiles du stage pilotent des objets propres au stage**, créés au chargement du match (10 blocs
   sur Destination Finale, 13 sur le Champ de bataille, 25 sur le Château 64). Perturbés, ils changent le combat sur
   les deux stages testés. Leur nature (morceaux de collision ?) reste probable.
4. **Le bloc de 616 000 octets n'est pas la collision du stage**, mais le pool des 350 fiches de collision des objets.
5. **Les objets gimmick, présents dans certains runs seulement, ne changent pas le combat**, ni sur le Château 64 ni
   sur le Stade Pokémon 2.
6. **Nommage par lecture du code** (`research/map/code_reading/`, 3 sous-agents qui ne lançaient pas le jeu) :
   - 43 champs de ControlModule, 24 des énergies (appels sur l'énergie elle-même), 5 du contact au sol, 2 de la caméra ;
     tous vérifiés par le jeu.
   - La lecture du code a expliqué une différence que la vérification venait de trouver chez Ice Climbers ; le calcul
     du lecteur est corrigé.
   - Des champs que le jeu ne peut pas vérifier tiennent des invariants d'une frame à l'autre, sur 3 matchs.
7. **Erreurs injectées** : l'oracle strict détecte une erreur que le hash ne voit pas, au bon rejeu et dans le bon
   bloc.
8. **Oracle strict sur 7 matchs que ses règles n'avaient jamais vus** : hash identique sur les 21 rejeux.
   - Les lignes inexpliquées étaient des requêtes de son et la gestion des fibres : 2 règles ajoutées, chacune par
     un invariant de code.
   - Il reste **une ligne ouverte** (un compteur double, +1 au rejeu, vu dans 2 matchs).
   - **Avec des items sur le stage, l'oracle n'est pas propre** : 17 à 42 lignes par rejeu. Ce sont des conteneurs
     indexés par des noms d'effets et de sons, et les tables de valeurs des scripts : le même contenu, rangé dans
     d'autres nœuds. Il faudra une comparaison par contenu.
9. **Oracle de rollback** (anneau avec rotation) : 31 nouveaux matchs, dont 3 avec items qui tombent ; 0 différence.
10. **Final Smash et fin de combat** : le lecteur reste exact à travers 2 Final Smash complètes (et une troisième commencée en fin de match) et jusqu'à l'écran de fin.

## Chiffres clés

- Séries longues de 3 minutes : 31 matchs lus, 0 différence sur 29 ; les 2 autres ont révélé une erreur du lecteur,
  corrigée depuis. Chaque match compte de 0,8 à 6,0 millions de valeurs.
- Vérification automatique : 169 getters simples et 1 033 appels avec argument ou receveur.
- État lu par la simulation : ~245 Ko par combat de 60 s, dont ~150 Ko hors table du stage.

## Couverture des tests (`research/map/coverage.md`)

- **Persos : 84 sur 89.** Il manque les trois Mii, que le match de débogage ne sait pas créer, et Pyra/Mythra, dont
  aucun nom essayé n'est reconnu.
- **Stages : 14**, dont le Stade Pokémon 2 et Kalos (transformations), et Smashville, Lylat, Halberd, Yoshi's Story,
  le Château 64, Delfino (décor ou plateformes mobiles).
- **Situations** : 2, 3 et 4 joueurs ; CPU niveau 9 contre CPU niveau 9 ; items qui tombent ; dangers ; 3 Final
  Smash ; une fin de combat ; combats de 3 et 5 minutes.

## Ce qui a échoué

- **La porte de déterminisme du dépôt échoue cette nuit, avec le runtime d'hier aussi.** Le jeu n'est pas en cause :
  en CPU contre CPU, ou avec une entrée calée sur la frame logique, les runs sont identiques. C'est l'entrée scriptée
  du joueur 1, qui dépend du minutage de l'hôte.
- **Le test de rollback à entrées corrigées n'a pas abouti.** L'outil est prêt, les références se répètent et le
  témoin négatif discrimine. Mais les anneaux qui rejouent chaque frame (8 en arrière toutes les 6 sans rotation,
  ou 4 toutes les 4) figent le jeu, avec le runtime d'hier aussi pour le premier.
- Mes erreurs, chacune corrigée et notée au journal : la liste des getters régénérée et l'exécutable relié pendant
  une série ; une injection écrite après un appel qui ne revient pas ; deux injections qui faisaient planter le jeu ;
  des heures de journal estimées au lieu d'être lues ; des traces supprimées trop tôt ; un PASS de l'oracle sans aucun
  rejeu (il dit maintenant NO REPLAYS).

## Décisions et raisons

- Les comparaisons entre runs se font en CPU contre CPU, parce que les runs scriptés ne se répètent pas.
- Le compteur double et les conteneurs des items restent inexpliqués plutôt que couverts par une règle : je ne sais pas
  encore les prouver inoffensifs.
- Les champs « probables » de la lecture du code ne sont pas utilisés par le lecteur tant qu'une seconde méthode ne
  les confirme pas.
- Le test à entrées corrigées a été arrêté à sa limite de 45 minutes.

## Questions

- (à venir)
