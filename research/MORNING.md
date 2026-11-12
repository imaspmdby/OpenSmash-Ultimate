# Compte rendu de la nuit du 12 novembre 2026

Mis à jour après chaque étape (dernière mise à jour : 02:15). Le détail et les chiffres complets sont dans
`research/RESEARCH.md`, section « Night of 2026-11-12 ».

## Où on en est

| Priorité | État |
|---|---|
| 1. Coloriage | remesure sur combats entiers faite ; table par site faite ; table du stage confirmée non-état ; état des parties mobiles : candidat trouvé, en cours de vérification |
| 2. Nommage des gros blocs | 3 sous-agents lisent le C généré (énergies, ControlModule, Ground/Camera) ; tailles réelles des modules établies |
| 3. Solidité en séries longues | 1re série faite (12 matchs de 3 min) ; erreurs injectées en préparation |
| 4. Ménage du journal | pas commencé |

## Ce qui est fait

1. **Coloriage sur des combats entiers** (60 s, 3 600 frames tracées, 4 matchs).
   - L'état lu par le code de simulation fait 242-251 Ko sur un combat entier. Sur 300 frames, il fait 183 Ko avec les
     catégories corrigées (et non 240 comme écrit hier : la région « engine? » était comptée comme simulation).
   - Il croît encore avec la fenêtre (183 → 218 → 246 Ko pour 300, 1 200 et 3 600 frames), et l'état total aussi
     (3,9 → 5,0 → 7,8 Mo). La taille mesurée dépend de la durée observée.
   - **Conclusion d'hier tombée** : « aucun état dans un bloc créé pendant le combat ». Sur 60 s, 118 à 279 Ko d'état
     sont dans des blocs créés en combat, dont environ 5 à 9 Ko lus par la simulation (surtout des piles de fibres).
   - Table par site d'allocation : `research/map/sites.md` (6 005 lignes, 1 786 avec de l'état).
2. **La table du stage (1 024 entrées) n'est pas de l'état**, confirmé par une seconde méthode. Perturbée en continu
   pendant 10 s (5 835 mots par frame), elle ne change ni le hash ni aucune des 836 000 valeurs nommées. Le témoin
   positif (la position de Mario perturbée) fait, lui, diverger les deux dès la frame suivante.
3. **État des parties mobiles du Château 64 : un candidat.** De petits blocs créés au chargement du match, lus par du
   code `app` (sites 0x7100524308 et 0x710052fe0c). Ils ressortent de la comparaison des traces avec et sans dangers,
   et leur perturbation fait diverger le combat dès la frame 601. Reste à savoir s'ils sont propres au stage :
   essais par site et sur Destination Finale en cours.
4. **Les objets gimmick ne changent pas le combat.** Deux runs CPU contre CPU, l'un avec et l'autre sans ces objets,
   sont identiques (hash sur 6 440 lignes, 822 520 valeurs nommées).
5. **Tests élargis.**
   - Le joueur 1 peut être un CPU (`p1type=cpu`) : combats CPU 9 contre CPU 9 sans script.
   - Série de 12 matchs de 3 minutes, CPU contre CPU : 26 persos et 6 stages jamais testés.
   - Tableau de couverture : `research/map/coverage.md`.
6. **La vérification automatique a trouvé un champ faux sur un perso jamais testé** : `HitModule.get_total_status(2)`
   chez le Héros (0x100 pour le jeu, 0 pour le lecteur, sur 167 frames). La famille entière est retirée.
7. **Les tailles réelles des modules** sont maintenant connues (64 classes). Le dump copie 0x900 octets par module :
   les « octets non nommés » comptés hier pour GroundModule (368 octets) et CameraModule (88) étaient surtout la
   mémoire d'autres objets.

## Chiffres clés

- Série longue : 9 matchs lus sans aucune différence (1,6 à 4,8 millions de valeurs chacun) ; 1 match a révélé le
  champ faux ; 2 matchs à relancer (en cours).

## Ce qui a échoué

- **Deux runs d'un match avec joueur scripté ne sont pas identiques** (ils divergent vers la frame 665, et une entrée
  du joueur 1 diffère dès la frame 40). Les comparaisons entre runs se font donc en CPU contre CPU.
- Deux runs de la série n'ont pas pu être lus : j'avais régénéré la liste des getters pendant qu'ils tournaient.
  Corrigé (chaque run a sa copie de la liste) ; ils sont relancés.
- Le nom `eflame_first` (Pyra) n'est pas reconnu par le jeu ; d'autres noms seront essayés.

## Décisions et raisons

- Les perturbations sont jugées sur des matchs CPU contre CPU, parce que les runs scriptés ne se répètent pas.
- J'ai renommé `build/ssbu.exe` en cours d'exécution pour relier le build normal pendant les séries. Les réglages
  ajoutés ne font rien tant qu'ils ne sont pas définis.
- Les sites d'allocation sont identifiés par deux adresses de retour : une seule regroupait des allocations sans
  rapport derrière un même enrobage.

## Questions

- (à venir)
