# Compte rendu de l'après-midi du 13 novembre 2026 (13:40 - 18:00)

Détail : `research/RESEARCH.md` (entrées du 2026-11-13 à partir de 14:16). Carte : `research/map/gamestate_fields.md`
(lisible) et `research/map/live_state.json`. Outil : `research/tools/live.py`.

## Le changement de méthode

Ce matin, je mesurais ce que le jeu lit après **un** chargement. La bonne question est : après **chaque** frontière
de frame, le prochain accès à un octet est-il une lecture ? Elle ne demande aucun chargement : dans un combat normal,
la build de trace note pour chaque octet, à chaque frame, si son premier accès est une lecture ou une écriture. Un
combat de 2 000 frames donne 2 000 points de chargement, en 3 min 30.

Chaque octet (et chaque champ) tombe dans une classe :
- **porté** : lu avant d'être écrit après au moins une frontière, et écrit pendant le combat. C'est l'état du jeu.
- **recalculé** : écrit avant d'être lu après toutes les frontières. Un chargement n'a pas besoin de le restaurer.
- **constant** : lu, jamais écrit pendant le combat (pointeurs, tables). Un chargement ne le change jamais.
- **passé entre threads** : écrit par un thread, lu par un autre avant la frontière. Gardé comme de l'état.

## Deux erreurs de la matinée, retirées

1. **Le branchement de `memchr` était faux** : il déclarait lue toute la longueur demandée, souvent « sans limite ».
   4,7 % des octets « lus d'abord » de la matinée ne le sont pas. Corrigé ; les ordres de grandeur du matin tiennent.
2. **La table par module de la matinée ne mesurait pas les modules des combattants**, mais quatre autres objets.
   Trouvé avec une sonde : l'objet pris pour le module de statut n'était jamais lu. Cette table est retirée ;
   le suivi prend maintenant les modules à partir des vrais combattants.

## Résultats

### 1. La carte des champs des combattants

28 combats entiers suivis : les 7 matchs de validation deux fois, 3 matchs jamais utilisés avant, puis 11 autres
(22 combattants de plus). Les champs sont ceux de la lecture de code d'hier (1 168 champs des modules d'un combattant).

| Classe | Champs | dont vérifiés par le jeu hier |
|---|---|---|
| portés (l'état) | 428 | 276 |
| recalculés | 135 | 97 |
| constants | 439 | 34 |
| jamais touchés | 166 | 13 |

- Portés, par exemple : position, position précédente, sens, échelle ; statut, situation ; animation, frame, vitesse ;
  journal de dégâts.
- Recalculés, par exemple : statut suivant, statut d'interruption, type de cinétique, position sauvegardée,
  position de départ.
- **La liste des « recalculés » converge** : 133 champs avec 7 matchs, 133 avec 10, 135 avec 21. Ce matin, avec
  la mauvaise méthode, elle fondait de 234 à 44.

### 2. Épreuve « d'un match à l'autre »

Carte construite sur 7 matchs, confrontée à 3 matchs jamais vus (autres combattants, autres stages), sans aucun
chargement : sur les 133 champs recalculés, 129 le sont aussi là-bas, 3 n'y sont pas touchés, **1 seul y est lu
d'abord** (un masque du module de recherche). Sur les 378 portés : 322 portés, 30 recalculés là-bas, 26 constants
ou non touchés.

### 3. Épreuve dans l'anneau (150 chargements, comparé au combat sans rollback)

Les champs recalculés des modules nommés (2 001 octets par combattant au plus, 8 500 à 12 000 octets laissés de côté
par chargement) ne sont plus restaurés :

| Essai | Résultat |
|---|---|
| Match de recherche (Samus, Fox) | passe : 0 ligne de hash différente sur 4 596 |
| Smashville (Corrin, Min Min) | passe : 0 sur 4 582 |
| Yoshi's Story (Wii Fit, King K. Rool) | passe : 0 sur 4 626 |
| Little Mac, Joker, avec la carte des 7 premiers matchs seulement (match jamais vu par elle) | passe : 0 sur 4 546 |
| Témoin négatif : position et statut seuls laissés de côté (168 octets) | échoue : 3 417 lignes différentes |
| Témoin négatif : les champs portés laissés de côté | échoue : plantage |

- Les seules valeurs que le lecteur voit différer sont dans trois modules de combattants (statut, contrôle,
  attaque) qui contiennent des champs laissés de côté : un champ non restauré garde une vieille valeur jusqu'à ce
  que le jeu le réécrive.
- Une première série (6 essais sur 6, build de trace) incluait 458 octets d'un objet sans nom ; refaite proprement.

### 4. À l'échelle des sites d'allocation, rien ne s'ajoute à l'ensemble d'hier

Sites entièrement « morts » (écrits, jamais portés) qui ne sont pas déjà dans l'ensemble d'hier : 5 sites GPU
(35 Mo), 110 sites connus (2,6 Mo), et 3 525 sites de blocs éphémères. Ajoutés à l'ensemble d'hier, ils bloquent le
jeu : 2 fois sur 2 avec tous, 2 fois sur 2 avec les seuls sites connus hors GPU (114 sites de la carte à 7 matchs).
Donc « jamais lu d'abord par le code du jeu » ne suffit pas pour retirer un site entier ; la cause n'a pas été lue.

### 5. La mémoire GPU : pourquoi on ne peut pas la laisser de côté telle quelle

- Pour le code du jeu, ses pages sont mortes à 95-99,5 % : il les écrit et ne les relit pas.
- Mais en comptant les lectures du thread graphique, 1 400 des 3 200 pages GPU écrites par le jeu contiennent des
  commandes écrites avant une frontière de frame et exécutées après. Cela reste vrai en vidant la file graphique à
  chaque frontière (1 382 pages) : ce n'est pas un retard du thread graphique.
- C'est cohérent avec le blocage lu dans les dumps : le thread principal attend un compteur écrit par le thread
  graphique, auquel il manque exactement une incrémentation (17 blocages sur 26). Les deux autres causes de
  blocage sont des listes chaînées d'allocateurs à moitié restaurées.
- Les options du runtime qui excluent la mémoire GPU : la première bloque (0 sur 3), la seconde passe 2 fois sur 3.

### 6. Les temps (un seul jeu, build normal)

Un rollback de 5 frames coûte 90 ms : 74 ms de chargement en moyenne, puis 7 frames rejouées à 3,2 ms chacune.
Exclure les données pures du GPU ne change rien (73,7 ms).

**Le chargement n'a pas un coût fixe : il grossit pendant l'anneau.** Les premiers remettent 12 000 pages en 21 ms,
les derniers 39 000 pages en 123 ms. La cause est mesurée :
- à partir de quelques dizaines de chargements, le jeu se met à rendre au système puis à reprendre 20 à 22 Mo de
  mémoire **à chaque frame** (son allocateur de grandes plages, celui d'un des trois blocages) ;
- chaque sauvegarde recopie alors ces pages en entier : 16 000 à 30 000 pages au lieu de 1 100, 10 à 25 ms au lieu de 2 ;
- le jeu ne fait **pas** cela sans rollback, ni avec une sauvegarde par frame sans aucun chargement (vérifié dans
  les deux cas) : ce sont les chargements qui le déclenchent. Pourquoi : non lu.

Pour comparaison, le code du jeu écrit environ 12 200 pages distinctes sur tout un combat, dont 8 600 portent de
l'état (comptage corrigé en fin d'après-midi).

## Ce qui n'est pas établi

- **Aucun gain de vitesse n'est obtenu.** Les champs recalculés font quelques Ko : ils valident la carte, ils
  n'allègent rien. Le coût d'un chargement est dans le nombre de pages remises.
- **Pourquoi les chargements déclenchent le va-et-vient de mémoire** n'est pas établi, ni si le contenu de ces
  pages est nécessaire (le suivi tourne sans chargement, donc sans ce phénomène).
- **Le lecteur n'a pas été comparé champ par champ** dans les essais d'anneau : seulement « quels modules diffèrent ».
- **Un champ recalculé sur 133 est contredit** par un match jamais vu, et l'anneau ne l'a pas détecté : l'anneau
  est un juge plus grossier que le suivi pour un champ isolé.
- **Armes, items, objets de stage** : classés par octet (dans `live_state.json`), sans nom de champ.
- « Porté » veut dire « lu avant d'être écrit par le code du jeu » ; les lecteurs natifs (thread graphique hors
  listes de commandes, fibres) ne sont pas tous comptés.
- Un des 12 matchs supplémentaires n'a pas tourné (nom introuvable dans la matrice).

## Pour reprendre

1. **Comprendre pourquoi, après des chargements, le jeu rend et reprend 20 Mo par frame** (fonctions
   `f_71037ca180` / `f_71037ca7f0`, appelées depuis `f_7103957ef0` et `f_7103958090`). C'est deux tiers des pages
   d'un chargement tardif. Si cela vient d'un état que le chargement ne remet pas (une horloge, par exemple), le
   corriger ramènerait un chargement de 123 ms vers 21 ms. C'est la piste d'allègement la plus concrète.
2. **Mémoire GPU** : distinguer les commandes en attente à la frontière (à garder) du reste (à exclure), puis
   refaire l'essai des options du runtime.
3. **Étendre les noms** aux armes, items et objets de stage (même méthode, à partir de leurs accesseurs).
4. **Séparer, dans « porté », ce qui change vraiment d'une frame à l'autre** de ce qui n'est écrit qu'une fois.

## État

Build normal : compilé, témoin identique, témoin négatif en échec. Rien ne tourne. Tout est poussé sur le fork,
branche `gamestate-research`.
