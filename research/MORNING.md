# Compte rendu de la nuit du 12 novembre 2026

Mis à jour après chaque étape (dernière mise à jour : 02:35). Le détail et les chiffres complets sont dans
`research/RESEARCH.md`, section « Night of 2026-11-12 ».

## Où on en est

| Priorité | État |
|---|---|
| 1. Coloriage | fait : combats entiers, table par site, table du stage, parties mobiles du stage, longue traîne |
| 2. Nommage des gros blocs | 3 lectures du code faites ; ~70 champs ajoutés, vérification automatique en cours |
| 3. Solidité | 2 séries longues faites (20 matchs de 3 min) ; erreurs injectées faites ; rollbacks à entrées corrigées en cours |
| 4. Ménage du journal | 5 conclusions annotées ; résumé de tête en préparation |

## Ce qui est fait

1. **Coloriage sur des combats entiers** (60 s, 3 600 frames tracées, 4 matchs).
   - L'état lu par le code de simulation fait 242-251 Ko sur un combat entier. Sur 300 frames, il fait 183 Ko avec
     les catégories corrigées (et non 240 comme écrit hier).
   - Il croît encore avec la fenêtre (183 → 218 → 246 Ko pour 300, 1 200 et 3 600 frames) : la taille mesurée dépend
     de la durée observée.
   - **Conclusion d'hier tombée** : « aucun état dans un bloc créé pendant le combat ». Sur 60 s, environ 120 à 280 Ko
     d'état sont dans des blocs créés en combat, dont environ 5 à 9 Ko lus par la simulation (surtout des piles de
     fibres).
   - Table par site d'allocation : `research/map/sites.md`.
   - Sans la table du stage, la simulation lit environ 150 Ko par combat : objets de combat ~18 Ko, fiches de
     collision ~3 Ko, objets du stage 1 à 7 Ko, piles 3 à 7 Ko. Le reste (~95 Ko) se répartit en ~320 sites, qui
     reviennent d'un match à l'autre.
2. **La table du stage (1 024 entrées) n'est pas de l'état**, confirmé par une seconde méthode. Perturbée en continu
   pendant 10 s, elle ne change ni le hash ni aucune des 836 000 valeurs nommées. Le témoin positif (la position de
   Mario perturbée) fait, lui, diverger les deux dès la frame suivante.
3. **Les parties mobiles du stage pilotent des objets propres au stage**, créés au chargement du match (3 sites ;
   10 blocs sur Destination Finale, 13 sur le Champ de bataille, 25 sur le Château 64). Les dangers activés y font
   9 fois plus d'état. Perturbés, ils changent le combat en 1 à 10 frames, sur le Château 64 comme sur Destination
   Finale. Leur nature (morceaux de collision ?) reste probable.
4. **Le bloc de 616 000 octets n'est pas la collision du stage** : c'est le pool des 350 fiches de collision des
   objets (une par objet qui a un GroundModule). Établi par la lecture du code et vérifié sur un dump. Quatre passages
   du journal annotés.
5. **Les objets gimmick ne changent pas le combat** : deux runs CPU contre CPU, l'un avec et l'autre sans ces objets,
   sont identiques.
6. **Nommage par lecture du code** (3 sous-agents, sans lancer le jeu) : `research/map/code_reading/`.
   - Énergies : les 11 classes identifiées. 24 champs (gravité, contrôleur, motion) sont vérifiés par le jeu en
     appelant le getter de chaque énergie.
   - ControlModule : 43 champs (sticks courant et précédent, boutons, compteurs de flick et d'appuis).
   - **La lecture du code a expliqué une différence que la vérification automatique venait de trouver** chez Ice
     Climbers : sous l'effet d'un coup ou de la gravité, la vitesse d'une énergie est lue ailleurs. Lecteur corrigé.
7. **Erreurs injectées exprès** : l'oracle strict détecte une erreur que le hash ne voit pas (4 086 mots de la table
   modifiés au 2e rejeu : hash identique, oracle en échec, au bon rejeu et dans le bon bloc).
8. **Tests élargis** : joueur 1 CPU possible (`p1type=cpu`). 20 matchs de 3 minutes en CPU contre CPU, avec 39 persos
   et 11 stages jamais testés, de 2 à 4 joueurs. Tableau : `research/map/coverage.md` (69 persos, 15 stages).

## Chiffres clés

- Séries longues : 20 matchs de 3 min lus. 17 sans aucune différence (1,6 à 4,8 millions de valeurs chacun), 2 ont
  révélé une erreur du lecteur (un champ retiré, un calcul corrigé), et 2 ont été relancés après une erreur de ma part.
- État lu par la simulation : ~245 Ko par combat de 60 s, dont ~150 Ko hors table du stage.

## Ce qui a échoué

- **Deux runs d'un match avec joueur 1 scripté ne sont pas identiques** (une entrée du joueur 1 diffère dès la frame
  40). Les comparaisons entre runs se font donc en CPU contre CPU.
- Mes erreurs : régénérer la liste des getters pendant une série (2 runs illisibles) ; relier l'exécutable pendant
  une série (5 runs n'ont pas démarré) ; une injection écrite après un appel qui ne revient pas ; deux injections qui
  faisaient planter le jeu au lieu de tester l'oracle. Chaque cause est corrigée et notée au journal.
- Pyra et Mythra : aucun nom essayé n'est reconnu par le jeu.

## Décisions et raisons

- Les perturbations sont jugées sur des matchs CPU contre CPU, parce que les runs scriptés ne se répètent pas.
- Une ligne inexpliquée vue une seule fois par l'oracle (un compteur partagé +1) est laissée inexpliquée plutôt que
  couverte par une nouvelle règle.
- Les champs « probables » de la lecture du code ne sont pas utilisés par le lecteur tant qu'une seconde méthode ne
  les confirme pas.

## Questions

- (à venir)
