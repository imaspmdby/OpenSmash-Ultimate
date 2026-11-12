# Compte rendu de la nuit du 12 novembre 2026

Mis à jour après chaque étape (dernière mise à jour : 01:50). Le détail et les chiffres complets sont dans
`research/RESEARCH.md`, section « Night of 2026-11-12 ».

## Où on en est

| Priorité | État |
|---|---|
| 1. Coloriage | remesure sur combats entiers faite ; table par site faite ; comparaison des stages et perturbation maintenue en cours |
| 2. Nommage des gros blocs | pas commencé |
| 3. Solidité en séries longues | série de fond en cours (12 matchs de 3 min, CPU contre CPU) |
| 4. Ménage du journal | pas commencé |

## Ce qui est fait

1. **Remesure du coloriage sur des combats entiers** (60 s, 3 600 frames tracées, 4 matchs : Destination Finale,
   Château 64 avec et sans dangers, Champ de bataille avec items qui tombent).
   - L'état lu par le code de simulation fait 242-251 Ko sur un combat entier. Sur 300 frames, il fait 183 Ko avec
     les catégories corrigées (et non 240 comme écrit hier : la région « engine? » était comptée comme simulation).
   - Il croît encore un peu avec la fenêtre (183 → 218 → 246 Ko pour 300, 1 200 et 3 600 frames). L'état total
     croît davantage (3,9 → 5,0 → 7,8 Mo).
   - Une conclusion d'hier tombe : « aucun état dans un bloc créé pendant le combat ». Sur un combat entier, 118 à
     279 Ko d'état sont dans des blocs créés en combat, dont 5 à 9 Ko lus par la simulation (surtout des piles de
     fibres de 64 Ko).
   - Table par site d'allocation : `research/map/sites.md` (6 005 lignes, 1 786 avec de l'état).
2. **Tests élargis.**
   - Le joueur 1 peut être un CPU (`p1type=cpu`) : combats CPU 9 contre CPU 9 sans script.
   - 12 nouveaux matchs : 26 nouveaux persos, 6 nouveaux stages (Stade Pokémon 2, Smashville, Lylat, Yoshi's Story,
     Kalos, Château 64 sans dangers).
   - Tableau de couverture : `research/map/coverage.md`.
3. **La vérification automatique a trouvé un champ faux sur un perso jamais testé** : `HitModule.get_total_status(2)`
   chez le Héros (0x100 pour le jeu, 0 pour le lecteur, sur 167 des 1 098 frames). La famille entière est retirée.

## Chiffres clés

- Série longue (3 min par match, CPU contre CPU) : 4 matchs lus, 6,9 millions de valeurs vérifiées, 167 différentes,
  toutes sur le champ retiré.

## Ce qui a échoué

- Deux runs de la série (Game & Watch–Palutena, Falco–Ike) n'ont pas pu être lus : j'ai régénéré la liste des getters
  pendant qu'ils tournaient. Ils seront relancés.
- Le nom `eflame_first` (Pyra) n'est pas reconnu par le jeu : Lucario l'a remplacé.

## Décisions et raisons

- J'ai mis l'ancien `build/ssbu.exe` de côté pour relier le build normal pendant que la série tournait. Les réglages
  ajoutés (`SSBU_POKE_HOLD`, `SSBU_POKE_SITES`) ne font rien tant qu'ils ne sont pas définis.
- Les sites d'allocation sont identifiés par deux adresses de retour : une seule regroupait des allocations sans
  rapport derrière un même enrobage.

## Questions

- (à venir)
