# Compte rendu de la nuit du 12 novembre 2026

Mis à jour après chaque étape (dernière mise à jour : 03:59). Le détail et les chiffres complets sont dans
`research/RESEARCH.md` : un résumé « établi / probable / ouvert » est maintenant en tête du journal, et les
entrées de la nuit sont dans la section « Night of 2026-11-12 ».

## Où on en est

| Priorité | État |
|---|---|
| 1. Coloriage | fait : combats entiers, table par site, table du stage, parties mobiles du stage, longue traîne |
| 2. Nommage des gros blocs | fait pour ControlModule et les énergies (68 champs vérifiés par le jeu) ; GroundModule et CameraModule surtout « probables » |
| 3. Solidité | 4 séries longues (31 matchs de 3 min), erreurs injectées, oracle strict sur 5 nouveaux matchs, fin de combat ; le rollback à entrées corrigées est bloqué (gel de l'anneau) |
| 4. Ménage du journal | fait : résumé de tête, 8 passages annotés |

## Ce qui est fait

1. **Coloriage sur des combats entiers** (60 s, 4 matchs).
   - L'état lu par la simulation fait ~245 Ko par combat, dont ~150 Ko hors table du stage. Sur 300 frames, il fait
     183 Ko (et non 240 comme écrit hier : une région de code était comptée à tort comme simulation).
   - La mesure dépend encore de la durée observée (183 → 218 → 246 Ko pour 300, 1 200 et 3 600 frames).
   - **Conclusion d'hier tombée** : « aucun état dans un bloc créé pendant le combat ». Sur 60 s, environ 120 à 280 Ko
     d'état sont dans des blocs créés en combat, surtout des piles de fibres.
   - Table par site d'allocation : `research/map/sites.md`. La longue traîne (~95 Ko en ~320 sites) revient d'un match
     à l'autre.
2. **La table du stage n'est pas de l'état** : perturbée 10 s, elle ne change ni le hash ni aucune valeur nommée.
   Le témoin positif, lui, fait tout diverger dès la frame suivante.
3. **Les parties mobiles du stage pilotent des objets propres au stage**, créés au chargement du match (10 blocs
   sur Destination Finale, 13 sur le Champ de bataille, 25 sur le Château 64). Perturbés, ils changent le combat sur
   les deux stages testés. Leur nature (morceaux de collision ?) reste probable.
4. **Le bloc de 616 000 octets n'est pas la collision du stage**, mais le pool des 350 fiches de collision des objets.
5. **Les objets gimmick du Château 64 ne changent pas le combat.**
6. **Nommage par lecture du code** (`research/map/code_reading/`) : 43 champs de ControlModule et 24 des énergies,
   vérifiés par le jeu (les getters des énergies sont appelés sur l'énergie elle-même). La lecture du code a
   expliqué une différence que la vérification venait de trouver chez Ice Climbers ; le calcul du lecteur est
   corrigé. Quelques champs « probables » ont maintenant une seconde méthode (invariants d'une frame à l'autre).
7. **Erreurs injectées** : l'oracle strict détecte une erreur que le hash ne voit pas, au bon rejeu et dans le bon
   bloc.
8. **Oracle strict sur 5 matchs jamais vus par ses règles** : hash identique sur les 15 rejeux. Les lignes
   inexpliquées étaient des requêtes de son et la gestion des fibres (2 règles ajoutées, chacune par un invariant
   de code). Il en reste **une seule, ouverte** : un compteur double (+1 au rejeu), vu dans 2 matchs.
9. **Fin de combat** (1 vie, CPU contre CPU) : le lecteur reste exact jusqu'à la fin et pendant l'écran de fin
   (3,9 millions de valeurs, 0 différente).
10. **Tests élargis** : 31 matchs de 3 minutes en CPU contre CPU, avec items qui tombent dans 3 d'entre eux.
    Couverture : `research/map/coverage.md`.

## Chiffres clés

- Séries longues : 31 matchs lus. 0 différence sur 29 ; les 2 autres ont révélé une erreur du lecteur, corrigée
  depuis. Chaque match compte de 0,8 à 6,0 millions de valeurs.
- Vérification automatique : 169 getters simples et 1 026 appels avec argument ou receveur.
- Oracle strict : 10 matchs en tout ; 1 ligne encore inexpliquée.

## Couverture des tests

- Persos : environ 85 (tableau à jour à la fin).
- Stages : 16, dont deux à transformations (Stade Pokémon 2, Kalos) et cinq à plateformes ou décor mobiles.
- Situations : 2, 3 et 4 joueurs ; CPU contre CPU ; items qui tombent ; dangers ; fin de combat ; combats de 3 à
  5 minutes.
- Final Smash : pas établie (probable dans les matchs avec tous les items, mais non visible dans les logs).

## Ce qui a échoué

- **La porte de déterminisme échoue cette nuit, avec le runtime d'hier aussi.** Le jeu n'est pas en cause (en CPU
  contre CPU, ou avec une entrée calée sur la frame logique, les runs sont identiques). C'est l'entrée scriptée du
  joueur 1, qui dépend du minutage de l'hôte.
- **Le test de rollback à entrées corrigées n'a pas pu aller au bout.** L'outil est prêt, les références se répètent
  et le témoin négatif discrimine, mais l'anneau qui rejoue chaque frame (8 en arrière toutes les 6, sans rotation)
  fige le jeu avant son premier chargement, avec le runtime d'hier aussi.
- Mes erreurs, chacune corrigée et notée au journal : régénérer la liste des getters pendant une série ; relier
  l'exécutable pendant une série ; une injection écrite après un appel qui ne revient pas ; deux injections qui
  faisaient planter le jeu ; des heures de journal estimées au lieu d'être lues (corrigées) ; des traces supprimées
  avant d'en avoir fini (refaites).
- Pyra et Mythra : aucun nom essayé n'est reconnu par le jeu.

## Décisions et raisons

- Les comparaisons entre runs se font en CPU contre CPU, parce que les runs scriptés ne se répètent pas.
- Le compteur double vu deux fois est laissé inexpliqué plutôt que couvert par une règle : je ne sais pas ce qu'il
  est.
- Les champs « probables » de la lecture du code ne sont pas utilisés par le lecteur tant qu'une seconde méthode ne
  les confirme pas.
- Le test à entrées corrigées a été arrêté à sa limite de 45 minutes.

## Questions

- (à venir)
