# Chantier 0 et A — résultats mesurés

Date : 2026-11-25.

## Chantier 0 — acquis public vérifié (terminé)

`reports/xpro3-2.00-baseline.json` reprend verbatim la baseline publiée par
`cdeschenes/fujifilm-xFW`. `tools/verify_baseline.py` la compare à notre
`FWUP0021.DAT` et passe **17 contrôles** :

- taille et SHA-256 du fichier ;
- type de conteneur 6, identifiant `00055711`, version 2.00 ;
- `payload_sha256` depuis `0x214` ;
- checksum d'en-tête `0xFFFFFFFF − Σ(dé-inversé[0x274:+0x2FC0020])` = `0xc54bab2e` ;
- les deux segments : signature FFLZ, taille décompressée, SHA-256 du code
  décompressé (`0xF21000`, `0x1CE3000`) ;
- l'image brute à `0x40000`.

### Deux longueurs d'en-tête, confirmées

| Constante | Valeur | Usage |
| --- | --- | --- |
| `PAYLOAD_HEADER` | `0x214` | début du hash `payload_sha256` (leur `fwup.py`) |
| `CHECKSUM_HEADER` | `0x274` | premier octet couvert par le checksum |

Elles diffèrent parce que `0x214..0x274` est du remplissage `0xFF` dans la zone
inversée, pas de l'en-tête. Confondre les deux fait échouer silencieusement les
deux calculs — c'est ce qui m'est arrivé d'abord.

### Adresses de fonctions confirmées par désassemblage

Les trois adresses de `CROSS-MODEL-COMPARISON.md` tombent dans le segment 1 et
leur code correspond à la description :

| Adresse | Offset dans seg1 | Preuve |
| --- | --- | --- |
| `0x01d425f0` | `0x5f5f0` | lit le magic `0x1160000` (`movt r0,#0x116`) |
| `0x01f882a8` | `0x2a52a8` | poste `0x603` (`movw r0,#0x603` puis `bl`) |
| `0x01f8c9d0` | `0x2a99d0` | construction du lien boîtier/objectif |

### Table des tâches X-Pro3 extraite

`tools/extract_task_names.py` lit la table `TSK_*` dans le segment 0 à
`0x1310ff4` : **152 entrées**, de `TSK_UI` (0x00) à `TSK_TOTAL` (0x97).
Fichier : `reports/xpro3-2.00-task-names.txt`.

Les identifiants **diffèrent entre versions** — c'est pourquoi la table doit être
extraite et non copiée :

| Tâche | X100V 3.01 | X-T4 2.12 | X-Pro3 2.00 |
| --- | --- | --- | --- |
| `TSK_UILIB` | 0x37 | 0x39 | **0x36** |
| `TSK_LCDEVF` | 0x38 | 0x3a | **0x37** |

X-T4 2.12 insère des tâches AAC (`TSK_RECMVBK_AAC`, `_AAC_COPY`) après 0x24, ce
qui décale tout le reste.

## Chantier A — état réel de l'émulateur (correction importante)

Mon rapport précédent affirmait que le firmware exécutait « son propre kernel avec
170 tâches ». **C'est faux.** La mesure le contredit :

- les 4 cœurs exécutent toujours `ffboot` à l'adresse 0 ; les idle sont dans son
  `wfi` à `0x1162f10`, le cœur actif dans son scheduler à `0x457e4` ;
- les deux segments applicatifs **sont** en RAM, identiques aux originaux sur les
  8 premiers Kio à `0xF21000` et `0x1CE3000` — la décompression a réussi ;
- le banc ThreadX du loader ne contient que **4 threads** : trois idle
  (`TSK_IDLE_0/1/2` = `0x9b/0x9c/0x9d`) plus `TSK_FLASH` (`0x2b`). Les
  « 170 tâches » que j'avais comptées étaient des pointeurs de pile, pas des
  structures de thread ;
- `TSK_LCDEVF` n'est jamais créé.

Les structures de thread sont authentiques : signature `THRD`
(`0x54485244`) à `+0x00`, pointeur d'entrée à `+0x20`, pile à `+0x44`, id de
tâche à `+0xcc` — même disposition que les en-têtes ThreadX publiés.

### Ce que le loader sait déjà

Sa table de segments, à `0xD2011C` (index 5) et `0xD20140` (index 6), est :

```
0xD2011C  0x00F21000  load addr   (seg0)
0xD20120  0x0072F000  image size
0xD20124  0x01650000  bss end
0xD20140  0x01CE3000  load addr   (seg1)
0xD20144  0x00844000  image size
```

Ces valeurs correspondent **exactement** à celles de la baseline publiée. Le
loader sait donc où placer les deux segments — et il les a bien placés. Ce qui
manque est le **transfert de contrôle**, pas le placement.

### Prochaine étape précise

The bascule is in the loader code between the end of its decompression loop and
the first jump to `0xF21000`/`0x1CE3000`. Next action: label the entry points of
both segments plus the two calls preceding the scheduler at `0x457b0`
(`0x48f30`, `0x40214`), then run briefly to see which one is reached.

---

# Correction after measuring, same day

Three claims above were wrong. Measuring the board state at several instruction
limits (20M, 60M, 120M, 600M, 1G) gives the real picture.

## `ffboot.bin` is a complete pre-linked RAM image, not a loader

It is 66,535,424 bytes (`0x3F74000`) and contains **both** application segments
byte-for-byte at their load addresses:

- `ffboot[0xF21000..]` equals the decompressed segment 0 entirely;
- `ffboot[0x1CE3000..]` equals the decompressed segment 1 entirely.

So the emulator never decompresses anything: the plan writes one image and the
whole system (loader + both application segments) is already in place. The DAT
decompression path is irrelevant to the emulator run.

## The address ranges answer the "which region" question

| Address | Region |
| --- | --- |
| `0x000457E4`, `0x00048E70`, `0x00056BB0` | loader (below `0xF21000`) |
| `0x01162F10`, `0x01153920` | **inside segment 0** (`0xF21000..0x1650000`) |

`0x1162F10` is 18.6 M, i.e. above the segment 0 load address. My earlier
statement that "every core still executes the loader" was therefore inverted:
those cores were already in application code.

## What actually happens, by limit

| Limit | Core 0-2 | Core 3 |
| --- | --- | --- |
| 20 M | `memset(0x1650000, 0, 0x69000)` — segment 0 `bss` clear | loader idle |
| 60 M | `0x1162F10` (application `wfi` idle) | `0x000402BC` loader |
| 120 M | `0x1162F10` | `0x00040D4C` loader |
| 600 M | `0x1162F10` | `0x00056BB0` loader |
| 1 G | `0x1162F10` | `0x000457E4` loader |

So the boot core does reach the application `main()` at `0x1162F14`, clears
its `bss`, and hands the other cores into the application's `wfi` idle loop.
Core 3 then stays in the loader running its own ThreadX scheduler and object
reference counting (`ldrexh`/`strexh` on `0x0140xxxx` structures) indefinitely.

## The "170 tasks" and "4 threads" were both misreads

`0x5B59C` is not a task table: it is ordinary memory that happens to hold
pointers at low indices. The real loader thread table is `0x5B570`, and it holds
four `THRD` structures (`0x71FC4`, `0x72114`, `0x72264`, `0x68CC4`) whose task
ids are `0x9B/0x9C/0x9D` (the three `TSK_IDLE_*`) plus `0x2B` (`TSK_FLASH`).
Those addresses are referenced only from loader code (`0x402xx`, `0x48E3C`,
`0x578xx`), which is how one can tell loader data from application data.

`TSK_LCDEVF` (`0x37`) is still never created, and no LCDC frame is published.

## Consequence for the plan

The blocker is **not** "the loader never hands over". The boot core does reach
the application and its idle cores wait there. What is missing is that the
application's own scheduler never starts any task beyond the idle set, and core
3 never leaves the loader's scheduler. The next step is to find what the
application waits for before creating `TSK_LCDEVF` — most likely a resource the
stock hardware provides and our board does not, not a loader contract.
---

# Session suivante — séquence d'amorçage applicative

## `main()` applicatif, identifié

`0x1162F14` est le `main()` de l'application (dans segment 0) :

```asm
0x1162F20  bl  0x1162E64      ; lit l'octet [0xD20008] : état du loader
0x1162F24  cmp r0, #1
0x1162F28  beq 0x1162F3C      ; si 1 -> initialisation
0x1162F2C  bl  0x1150F20      ; sinon : fonction d'init alternative
0x1162F30  cmp r0, #0
0x1162F34  beq 0x1162F5C
0x1162F38  b   0x1162F38      ; sinon : boucle infinie sur place
0x1162F3C  memset(0x1650000, 0, 0x69000)  ; bss du segment 0
0x1162F58  b   0x1162F2C
```

Mesure : `[0xD20008] = 1`, donc `main()` prend la branche d'initialisation,
efface son `bss` (`0x1650000`, `0x69000` octets = exactement la valeur « bss end »
de la table de segments du loader), puis enregistre la tâche racine.

## Création des tâches applicatives

Après l'enregistrement de `TSK_ROOT` (`0x9F`, entrée `0x1163500`), le thread
racine exécute `0x1163500` :

```asm
0x116350C  bl 0x1152944              ; init préalable
0x1163518  ...  crée TSK_IDLE_0 (0x9B)
0x1163558  ...  crée TSK_IDLE_1 (0x9C)
0x1163584  ...  crée TSK_IDLE_2 (0x9D)
0x11635B0  ...  crée TSK_IDLE_3 (0x9E)
0x11635DC  mov r4, #1
0x11635E4  mov r1, r5 ; mov r0, r4
0x11635EC  bl  0x1150210            ; par tâche
0x11635F0  add r4, r4, #1
0x11635F4  cmp r4, #0xA8            ; jusqu'à 167
0x11635F8  bne 0x11635E4
0x11635FC  bl  0x1152B30
```

Donc l'ordre est : idle (0x9B–0x9E), puis une boucle sur les ids **1 à 167** qui
appelle `0x1150210`. Cette boucle couvre plus que les 152 tâches nommées : elle
traite aussi des objets non liés à `TSK_*`.

## Ce qui est mesuré, par palier

| Limite | Cœur 0 | Cœurs 1-2 | Cœur 3 |
| --- | --- | --- | --- |
| 20 M | `memset` du bss (en cours) | loader | loader |
| 60 M | `0x1162F10` (idle applicatif) | `0x1162F10` | `0x402BC` loader |
| 120 M | `0x1162F10` | `0x1162F10` | `0x40D4C` loader |
| 600 M | `0x1162F10` | `0x1162F10` | `0x56BB0` loader |
| 1 G | `0x1162F10` | `0x1162F10` | `0x457E4` loader |

Le cœur 3 est le seul qui reste dans le loader en permanence, alors que les trois
autres sont passés dans l'application. Un démarrage réel laisse le cœur 3 lui
aussi entrer dans l'application.

## Prochaine action

Trois pistes concrètes, dans cet ordre :

1. **Comparer avec un boot loader-seul.** Lancer le plan sans les deux images
   applicatives (`ffboot` tronqué à `0xF21000`) pour vérifier que le loader
   signale bien `[0xD20008] = 1` de lui-même. Si oui, le loader est complet et
   seul le démarrage du cœur 3 manque.
2. **Tracer `0x1150210`.** Il retourne un statut ; un id qui échoue laisse la
   boucle continuer mais peut empêcher `TSK_LCDEVF` (id `0x37`) d'être enregistré.
   Instrumenter son retour par id sur un run court est la mesure la plus directe.
3. **Vérifier le rôle du cœur 3.** Le laisser dans le loader alors que les autres
   sont dans l'application suggère une ressource qu'il attend (peut-être un
   périphérique différent). Identifier la boucle qu'il exécute sur 1 G
   (`0x457E4`, le scheduler du loader) et pourquoi il n'en sort pas.

Aucune de ces pistes ne demande la caméra.

---

# Session 3 — le point de blocage est localisé

## Le loader est autonome et signale correctement

Run avec une image tronquée à `0xF21000` (loader seul, sans les deux segments
applicatifs) :

```
instruction-limit 60000000 :
  [0xD20008] = 1        (drapeau « loader prêt »)
  0x5B5D4    = 1        (porte de libération des cœurs secondaires)
  threads    = vide
  cœurs      = tous à 0x400D0 (boucle de scrutation du loader)
```

Le loader écrit donc `1` dans son drapeau **de lui-même**, sans les segments
applicatifs. Il est complet et fonctionne.

## Les tâches applicatives ne sont jamais créées

État à 600 M et 1 G, toutes structures `THRD` (signature `0x54485244`) trouvées
en RAM :

| Adresse | id de tâche | Nom |
| --- | --- | --- |
| `0x005CCBC` | — | (id invalide) |
| `0x005B680` | — | (id invalide) |
| `0x0068CC4` | `0x2B` | `TSK_FLASH` |
| `0x006E8A4` | `0x71` | `TSK_EXEC_CPU_2` |
| `0x006E9F4` | `0x72` | `TSK_EXEC_CPU_3` |
| `0x006EB44` | `0x73` | `TSK_EXEC_CPU_4` |
| `0x006EC94` | `0x74` | `TSK_EXEC_CPU_5` |
| `0x006EDE4` | `0x75` | `TSK_STANDBY_1` |
| `0x0071FC4` | `0x9B` | `TSK_IDLE_0` |
| `0x0072114` | `0x9C` | `TSK_IDLE_1` |
| `0x0072264` | `0x9D` | `TSK_IDLE_2` |
| `0x00723B4` | `0x9E` | `TSK_IDLE_3` |
| `0x0072504` | `0x9F` | `TSK_ROOT` |

**Toutes ces adresses sont inférieures à `0xF21000`**, c'est-à-dire dans le
loader. Aucune structure de thread n'existe dans l'espace applicatif
(`0xF21000..0x2527000`), alors que le `main()` applicatif (`0x1162F14`) a
pourtant été exécuté : il a effacé son `bss` et appelé `0x114F798` pour
enregistrer `TSK_ROOT`.

## La table `0x15C2DD4` n'est pas un indicateur d'échec

Piège rencontré : cette table est indexée par `(id-1)*4` et contient des valeurs
`0..3`. Son usage (`0x114F838`: `cmp r3,#3; ldrls pc,[pc,r3,lsl#2]`) montre que
c'est une **table de dispatch par type**, pas une table de pointeurs. Une valeur
`0` signifie « type 0 », pas « tâche absente ». L'interpréter comme un échec
était une erreur.

## Aucune erreur d'enregistrement

`0x1AB8D90` (dernière erreur de création de tâche) vaut `0` à 600 M comme à 1 G.
La boucle de création ne rapporte donc aucun échec — mais rien n'apparaît côté
applicatif.

## Conclusion : la création aboutit dans le mauvais espace

Le mécanisme d'enregistrement (`0x114F798`) écrit dans un registre calculé à
partir de `0x18A43BC + (id-1+0x14000)*8`. Or les structures de thread
retrouvées sont toutes dans le loader. L'hypothèse la plus probable est que
l'allocateur de threads applicatif pioche dans une zone de mémoire que notre
board n'a pas initialisée (ou qui chevauche le loader), si bien que les threads
sont créés mais jamais liés au scheduler applicatif.

## Prochaine action (une seule, mesurable)

Comparer, dans un run à 600 M, les registres du cœur 0 au moment où il sort de
`0x1162F5C` (enregistrement de `TSK_ROOT`) : `0x114F798` reçoit le descripteur
dans `r0`, et son chemin d'écriture passe par `0x4B0C4`. Vérifier ce que
`0x4B0C4` retourne et où il écrit. C'est la fonction qui décide de l'espace
d'allocation des threads.

---

# Session 4 — les tâches sont créées, mais une seule catégorie

## Le registre de tâches applicatif, localisé

`0x114F798` calcule son entrée par `0x18A43BC + (id − 1 + 0x14000) × 8`, deux mots
par entrée. Dump réel à 600 M d'instructions : **15 entrées non nulles sur 176**.

| Id | Nom | word0 | word1 |
| --- | --- | --- | --- |
| `0x01` | `TSK_SYSCONT` | `0x0002` | **`0x0`** |
| `0x2B` | `TSK_FLASH` | `0x0000` | `0x018AAC14` |
| `0x2C` | `TSK_RECDBG` | `0x0C00` | `0x0` |
| `0x71` | `TSK_EXEC_CPU_2` | `0x0000` | `0x018A5BEC` |
| `0x72` | `TSK_EXEC_CPU_3` | `0x1000` | `0x018A6BF4` |
| `0x73` | `TSK_EXEC_CPU_4` | `0x1000` | `0x018A7BFC` |
| `0x74` | `TSK_EXEC_CPU_5` | `0x1000` | `0x018A8C04` |
| `0x75` | `TSK_STANDBY_1` | `0x1000` | `0x018A9C0C` |
| `0x76` | `TSK_ECOMPASS` | `0x1000` | `0x0` |
| `0x9B`–`0x9F` | idle 0–3, root | `0x0/0x400` | piles `0x018A4BCC`… |

Point notable : `word1` est un **pointeur de pile** valide pour les tâches créées
(`0x018A5BEC`, `0x018A6BF4`, …) et vaut `0` pour celles qui ne le sont pas
(`TSK_SYSCONT`, `TSK_ECOMPASS`, `TSK_RECDBG`).

## Ce que la boucle de démarrage fait vraiment

`0x11635DC` itère `r4 = 1 .. 0xA7` et appelle `0x1150210` avec `(tid, 1)`. Or
`0x1150210` ne crée rien : il appelle `0x4BEF4`, qui **démarre** une tâche déjà
enregistrée :

```asm
0x11502AC  mov r0, r5        ; tid
0x11502B0  bl  0x4BEF4       ; démarrer la tâche
0x11502B4  subs r4, r0, #0
0x11502B8  beq 0x1150270     ; succès -> continue la boucle
0x11502BC  ...                ; échec -> enregistre l'erreur et sort
```

Les tâches doivent donc être créées **avant**, ailleurs. La séquence `0x1163500`
ne crée explicitement que les quatre idle et `TSK_ROOT`, puis démarre les autres.

## Pourquoi seul le noyau bas niveau existe

Les tâches présentes (`TSK_EXEC_CPU_2..5`, `TSK_STANDBY_1`, `TSK_FLASH`) portent
toutes des adresses de structure **inférieures à `0xF21000`**, c'est-à-dire dans
le loader. Les tâches applicatives (`TSK_SYSCONT`, `TSK_UILIB`, `TSK_LCDEVF`,
`TSK_MOVDC`, …) ont une entrée de registre mais **pas de pile allouée**.

C'est cohérent : le loader crée son propre jeu de threads (il en a besoin pour
tourner), et l'application n'a pas encore alloué les siens.

## Le verrou précis

`TSK_SYSCONT` (id `0x01`, deuxième tâche de l'énumération) a `word0 = 0x2` mais
`word1 = 0`. C'est la tâche système qui, dans l'ordre de démarrage Fujifilm,
précède l'UI. Tant qu'elle n'a pas de pile, `0x1150210` échouera en la démarrant,
et la boucle s'arrêtera à la première erreur — donc avant `TSK_UILIB` (0x36) et
`TSK_LCDEVF` (0x37).

## Prochaine action

Trouver l'allocateur de pile applicatif et vérifier **pourquoi il renvoie 0 pour
`TSK_SYSCONT`**. Deux candidats mesurables :

1. `0x1152944` (appelé en tête de `0x1163500`, avec `r0=0, r1=1`) : c'est la
   première initialisation du thread racine ; voir ce qu'elle alloue.
2. Comparer l'état du tas applicatif (région `0x1650000..` et au-delà) entre un
   run à 60 M (juste après le `memset`) et 600 M : si le pointeur de tas n'avance
   pas, l'allocation échoue faute d'espace ou de descripteur de région.

---

# Session 5 — la cause est trouvée

## La table des descripteurs, corrigée et localisée

L'allocateur `0x56378` (appelé par l'application via `0x1152944`) cherche le
descripteur d'une tâche dans `0x0007A55C + (id − 1) × 4`. Attention : l'adresse
est `0x0007A55C`, pas `0x700A55C` — l'instruction est `movw r3,#0xa55c` /
`movt r3,#7`. Une erreur de lecture d'un chiffre m'a fait chercher au mauvais
endroit pendant un moment.

Contenu réel à 600 M d'instructions : **16 entrées non nulles**, exactement celles
dont les threads existent :

| Id | Nom | Descripteur |
| --- | --- | --- |
| `0x2B` | `TSK_FLASH` | `0x00068CC4` |
| `0x71`–`0x75` | `TSK_EXEC_CPU_2`…`TSK_STANDBY_1` | `0x0006Exxx` |
| `0x9B`–`0x9E` | `TSK_IDLE_0`…`3` | `0x00071FC4`…`0x000723B4` |
| `0x9F` | `TSK_ROOT` | `0x00072504` |
| `0xFB`–`0xFF` | (au-delà de l'énumération) | divers |

**Aucune tâche applicative** : `TSK_SYSCONT` (`0x01`), `TSK_UILIB` (`0x36`),
`TSK_LCDEVF` (`0x37`), `TSK_MOVDC` (`0x45`) sont tous à zéro.

## Pourquoi

La boucle `0x11635DC` (`r4 = 1 .. 0xA7`) appelle `0x1150210(tid, 1)`, qui
appelle `0x4BEF4` — et `0x4BEF4` **démarre** une tâche dont le descripteur doit
déjà être dans `0x0007A55C`. Ce n'est pas un créateur, c'est un démarreur.

Or `0x1163500` ne crée explicitement que les quatre idle, puis `TSK_ROOT` via
`0x114F798`. Les 167 autres ids sont seulement **démarrés**. Le créateur des
tâches applicatives n'est donc pas dans ce chemin — il manque une étape qui, sur
le matériel réel, peuple `0x0007A55C` pour les ids `0x01`..`0x8C`.

## Ce que cela implique pour l'émulateur

Ce n'est ni un contrat de bus manquant ni un périphérique absent : c'est une
**étape d'amorçage applicative qui ne s'exécute pas**. Le cœur 3 reste dans le
loader, les trois autres en idle applicatif, et personne ne crée les tâches.

## Prochaine action, précise et bornée

Trouver qui écrit `0x0007A55C` dans le firmware. Méthode : chercher dans les deux
segments les instructions `movw #0xa55c` / `movt #7` (ou l'adresse calculée), et
tracer la (les) fonction(s) qui y écrivent. Si elle existe dans le code applicatif,
vérifier pourquoi elle n'est pas appelée ; si elle n'existe pas, c'est que la
population vient du loader ou d'une étape qu'on ne charge pas — et c'est alors un
élément d'image manquant, pas un problème d'émulation.

---

# Session 6 — les deux registres sont cohérents (correction)

## Les deux tables décrivent les mêmes tâches

Contrairement à ce que j'avais supposé, `0x0007A55C` et `0x18A43BC` ne sont pas
deux registres concurrents : ils décrivent **les mêmes** tâches sous deux angles.

| Id | Nom | Descripteur `0x7A55C` | Pile `0x18A43BC` |
| --- | --- | --- | --- |
| `0x2B` | `TSK_FLASH` | `0x00068CC4` | `0x018AAC14` |
| `0x71` | `TSK_EXEC_CPU_2` | `0x0006E8A4` | `0x018A5BEC` |
| `0x9B` | `TSK_IDLE_0` | `0x00071FC4` | `0x018A4BCC` |
| `0x9F` | `TSK_ROOT` | `0x00072504` | `0x018A43C4` |
| `0x01` | `TSK_SYSCONT` | **`0`** | **`0`** |
| `0x36` | `TSK_UILIB` | **`0`** | **`0`** |
| `0x37` | `TSK_LCDEVF` | **`0`** | **`0`** |

`0x7A55C` porte la structure `THRD` (dans le loader, `< 0xF21000`) ; `0x18A43BC`
le pointeur de pile allouée (RAM applicative, `0x018Axxxx`). Pour chaque tâche
créée les deux existent ; pour les tâches d'interface les deux sont nuls. Ce ne
sont donc pas deux registres concurrents — l'hypothèse de la session 4 est
écartée.

## Preuve de non-progression

Nombre d'entrées avec une pile allouée, aux quatre paliers :

```
60M  : 11  ids = 2b 71 72 73 74 75 9b 9c 9d 9e 9f
120M : 11  (identique)
600M : 11  (identique)
1G   : 11  (identique)
```

Strictement constant de 60 M à 1 G. L'application n'enregistre donc aucune tâche
de plus, quel que soit le temps virtuel accordé : seuls les threads du loader
existent.

## Le fait mesuré, plus simple et plus dur

Après l'effacement du `bss` applicatif et l'enregistrement de `TSK_ROOT`,
l'application **n'enregistre plus aucune tâche**. Ce n'est pas une question
d'espace d'allocation : c'est l'initialisation qui ne poursuit pas.

# Session 6 bis — ce que fait la suite de la séquence

## Le registre `0x0007A55C` appartient au loader

Trois sites l'écrivent, tous dans le loader :

| Adresse | Rôle |
| --- | --- |
| `0x4C160` | `str r4,[r3,r7,lsl#2]` — **enregistre** un descripteur |
| `0x4DD18` | `str r2(=0),[r3,r0,lsl#2]` — **libère** (destruction de thread) |
| `0x4E004` | `str r1(=0),[r3,r2,lsl#2]` — même chose, autre chemin |

Contenu à 600 M : `TSK_FLASH`, `TSK_EXEC_CPU_2..5`, `TSK_STANDBY_1`, les quatre
idle, `TSK_ROOT`. **Uniquement des threads créés par le loader.**

## L'application utilise un registre distinct

`0x114F798` (enregistrement applicatif) écrit à
`0x18A43BC + (id − 1 + 0x14000) × 8`, deux mots par entrée :
`{word0, word1}`. À 600 M ce registre contient 15 entrées, avec des pointeurs de
pile applicatifs valides pour les tâches réellement lancées
(`0x018A5BEC`, `0x018A6BF4`, … `0x018A9C0C`) et `word1 = 0` pour les autres.

Les deux registres sont **disjoints** : le loader gère les siennes, l'application
les siennes. Conclure « les tâches ne sont pas créées » en lisant le registre du
loader était une erreur de cible.

## Ce que fait réellement la séquence d'amorçage applicative

`0x11635FC` puis une longue série d'initialisations de sous-systèmes
(`0x1152B30`, `0x1152D24`, `0x108C5D4`, `0x10A981C`, `0x108B03C`, `0x115F838`,
`0x115FA30`, `0x57974`, `0x1151048`, `0x1152C18`, …). Les appels suivants
construits autour de `0x12A664C` sont une table de **tailles de pile par tâche**
(`0x3000`, `0x6000`, `0x28000`, `0x50000`, `0x80000`, `0xFC000`) et un
`sprintf`-like de nom (`0x1163098` construit `"%08x"`). `0x115306C` est un
`strcpy`, `0x1161AA8` un log conditionnel — ni l'un ni l'autre ne crée de tâche.

## Où cela laisse le travail

Le blocage n'est pas « une table vide » mais un **sous-système qui ne rend pas la
main** pendant l'initialisation. Le cœur 0 est en `wfi` applicatif à `0x1162F10`
avec `lr = 0x00055850` : l'adresse de retour est dans le **loader**, donc le
cœur 0 a été réveillé par le scheduler du loader et attend un événement.

Ce que la mesure établit fermement, et qui suffit pour la suite :

1. le loader fonctionne et signale « prêt » ;
2. l'application commence à s'initialiser (bss effacé, registre applicatif peuplé
   pour 15 tâches) ;
3. les tâches applicatives d'interface (`TSK_UILIB`, `TSK_LCDEVF`) ne sont jamais
   enregistrées ;
4. le cœur 3 reste dans le loader, les trois autres en idle applicatif.

## Prochaine action

Instrumenter plutôt que désassembler : les labels `0x1162F14` (main app) et
`0x1150F20` (init alternative) ne sont pas exposés par le CLI (`state(false)`),
donc la mesure doit passer par `BoardState` des bindings Python, qui appelle
`complete_state()` et inclut les milestones. Construire le board via
`Board.from_inputs(...)`, poser des labels sur les fonctions d'init de
sous-système listées ci-dessus, et voir laquelle s'arrête.

---

# Session 7 — le système tourne, mais l'initialisation s'arrête

## Le cœur 0 exécute le thread idle applicatif

Registres du cœur 0 à 600 M :

```
r4  = 0x00071FC4   -> structure THRD de TSK_IDLE_0
r10 = 0x018A4BCC   -> sa pile (dans le registre applicatif)
sp  = 0x018A4F9C   -> haut de pile
lr  = 0x00055850   -> retour dans le context-switch du loader
pc  = 0x01162F10   -> fonction idle applicative
```

`0x1162F04` est littéralement :

```asm
0x1162F0C  wfi
0x1162F10  b 0x1162F0C
```

Donc le cœur 0 n'est pas bloqué sur un périphérique : il **n'a rien à faire**.
Le scheduler du loader l'a placé sur le thread idle parce qu'aucun thread
applicatif n'est prêt.

## Séquence d'état, cohérente de bout en bout

1. Le loader termine, pose `[0xD20008] = 1` et libère les cœurs secondaires
   (`[0x5B5D4] = 1`).
2. `main()` applicatif (`0x1162F14`) efface le `bss` de seg0
   (`memset(0x1650000, 0, 0x69000)`) — mesuré en cours à 20 M.
3. `0x11635FC` enchaîne les initialisations de sous-systèmes.
4. `0x114F798` enregistre `TSK_ROOT`, les quatre idle existent déjà.
5. **Plus rien** : aucune tâche d'interface n'est enregistrée, à aucun palier
   jusqu'à 1 G.
6. Les cœurs 0-2 tombent sur le thread idle ; le cœur 3 reste dans le loader.

## Ce que cela exclut définitivement

- **Pas** un contrat de bus manquant : toutes les régions précédemment
  identifiées sont modélisées et le firmware n'y accède pas en faute.
- **Pas** un problème d'espace d'allocation : les deux registres concordent et la
  borne de l'allocateur (250 tâches) n'est jamais approchée.
- **Pas** une erreur rapportée : `[0x1AB8D90]` reste à 0 à tous les paliers.
- **Pas** un manque de temps virtuel : 1 G d'instructions ne change rien par
  rapport à 60 M.

Le fait est donc : **l'initialisation applicative s'arrête net après
`TSK_ROOT`**, et la suite (`0x11635FC` → sous-systèmes) ne va pas au bout.

## Prochaine action

La mesure utile suivante est de savoir **quelle** fonction de la liste
`0x1152B30, 0x1152D24, 0x108C5D4, 0x10A981C, 0x108B03C, 0x115F838, 0x115FA30,
0x57974, 0x1151048, 0x1152C18` ne revient pas. Méthode : poser des labels sur ces
dix adresses dans le plan (`definition.labels`) et lire les milestones via
`BoardState` des bindings Python, qui appelle `complete_state()` — le CLI, lui,
sérialise `state(false)` et n'expose pas les milestones.

C'est borné, mesurable, et ne demande pas la caméra.

---

# Session 8 — une boucle infinie volontaire dans l'init

## Deux boucles infinies trouvées dans les fonctions d'init

En désassemblant la chaîne `0x1152B30, 0x1152D24, 0x108C5D4, 0x10A981C,
0x108B03C, 0x115F838, 0x115FA30, 0x57974, 0x1151048, 0x1152C18`, deux
auto-branchements apparaissent :

| Adresse | Fonction | Sens |
| --- | --- | --- |
| `0x1152D70` | `0x1152D4C` | **boucle infinie volontaire** |
| `0x1152D20` | `0x1152D18` | **boucle infinie volontaire** |

Le second est enregistré comme callback :

```asm
0x1152D24  push {fp,lr}
0x1152D2C  mov  r0, #0x85
0x1152D30  bl   0x109B8B0        ; obtenir un objet/id
0x1152D34  movw r2, #0x4b90
0x1152D38  movt r2, #0x194
0x1152D3C  movw r1, #0x2d18
0x1152D40  movt r1, #0x115
0x1152D44  bl   0x109B674        ; enregistrer le handler 0x1152D18
0x1152D48  pop  {fp,pc}
...
0x1152D18  str fp,[sp,#-4]!
0x1152D1C  add fp,sp,#0
0x1152D20  b   0x1152D20        ; <-- ne revient jamais
```

`0x109B674` prend `(objet, 0x1152D18, 0x1944B90)` : c'est un enregistrement
d'abonnement. `0x1152D18` est donc **le callback appelé à la mort ou à l'arrêt**,
et sa boucle infinie est un **arrêt volontaire** — pas un bug.

Interprétation : si l'initialisation atteint `0x1152D24` et qu'un événement
déclenche `0x1152D18`, le système se fige délibérément. C'est le dernier recours
d'un chemin d'erreur, pas le chemin normal.

## Où sont réellement les services appelés

Les fonctions invoquées par l'init (`0x583EC`, `0x57858`, `0x57900`, `0x57974`)
sont toutes dans le **loader**, pas dans seg0. L'application appelle donc des
services du loader pour l'allocation, les mutex et les registres. C'est normal
pour un système à deux étages, mais cela signifie que le loader doit rester
vivant après le passage de relais — et c'est bien ce qui est mesuré : le cœur 3
y tourne toujours.

## État consolidé

| Élément | Mesure |
| --- | --- |
| Loader | complet, signale prêt, reste actif sur le cœur 3 |
| `main()` applicatif | exécuté, `bss` effacé |
| `TSK_ROOT` + 4 idle | créés |
| Tâches d'interface (`TSK_UILIB`, `TSK_LCDEVF`) | jamais créées |
| Erreur rapportée | aucune (`0x1AB8D90 = 0`) |
| Progression de 60 M à 1 G | aucune |

## Conclusion et suite

Le système est fonctionnel à deux étages mais l'initialisation applicative ne
dépasse pas `TSK_ROOT`. Deux boucles infinies volontaires existent dans le
chemin, ce qui suggère un **arrêt sur condition d'erreur silencieuse** : le
firmware choisit de figer plutôt que de continuer.

La mesure qui trancherait : rendre visible **lequel** des dix appels d'init
s'exécute en dernier. Le CLI n'expose pas les milestones (`state(false)`), donc
il faut soit patcher `application.rs` pour sérialiser `state(true)`, soit passer
par `Board.from_inputs` + `BoardState` des bindings Python. Les deux sont hors
de portée de cette session ; c'est la première tâche de la suivante.

---

# Session 9 — la chaîne s'arrête sur l'initialisation du stockage

## Méthode : milestones lisibles dans le snapshot

Le CLI sérialise `state(false)` et n'expose donc pas les milestones, mais
`--save-snapshot` écrit le header CBOR complet, qui **les contient**. Poser
`definition.labels` dans le plan et lire `header['milestones']` donne l'ordre
d'exécution avec le compteur d'instructions à la première entrée :

```python
s = Snapshot(Path('snapshot.bin'))
for instr, addr, core in sorted((v, k[1], k[0]) for k, v in s.header['milestones'].items()):
    print(instr, hex(addr), core)
```

C'est la mesure qui manquait aux sessions précédentes.

## Chaîne d'initialisation, entièrement tracée

```
  3 324 610  main() applicatif        0x1162F14
 24 329 675  TSK_ROOT                0x1163500
 24 405 310  0x1152B30  init A
 24 406 581  0x1152D24  init B
 24 407 004  0x108C5D4
 24 407 618  0x10A981C
 24 540 904  0x108B03C
 24 542 088  0x115F838
 24 542 344  0x115FA30
 24 542 493  0x57974   (loader)
 24 542 504  0x1151048
 24 542 516  0x1152C18  <- dernière de la liste
 34 767 064  0x1163744  <- reprise après les tests
```

Les deux blocs `cmp r0,#0 / beq` suivis de `b .` (`0x1163718`, `0x1163728`)
**passent tous les deux** : `0x113AE60` et `0x113DAA4` retournent 0.

## Le point d'arrêt exact

Après `0x1163744` (`bl 0x113A7BC`), **`0x1163754` n'est jamais atteint** :
`0x113A7BC` ne revient pas.

Ce que fait `0x113A7BC` :

```asm
0x113A7C8  movw r3,#0xb5ac ; movt r3,#0x16d
0x113A7D0  mov  r0,#0x8000 ; movt r0,#0x416
0x113A7D8  str  r0,[r3]                    ; [0x16DB5AC] = 0x04168000
0x113A7DC  mov  r1,#0x160000
0x113A7E0  bl   0x113B924                  ; lecture stockage, 11 pages
0x113A7E4  mov  r0,#0x440000
0x113A7E8  bl   0x113A540                  ; adresse de base
0x113A7EC  ...  bl 0x113B700               ; transfert 0x2FFC0 octets
0x113A7FC  bl   0x113A1F0                  ; lit un mot par I2C
0x113A808  movw r3,#0xaa55
0x113A80C  cmp  r2,r3
0x113A810  beq  0x113A904                  ; si signature 0xAA55 : suite normale
0x113A814  ...                              ; sinon : autre chemin, puis 0x113A83C
```

`0x113A1D0` / `0x113A384` font des `ldrb`/`strb` sur `[0x16DB5AC]` + offset
calculé par `0x113A14C` : c'est un accès **série/I2C** à une mémoire de
configuration, et la signature attendue est **`0xAA55`** (marqueur classique de
secteur de démarrage valide).

## Conclusion

Le blocage n'est ni un contrat de bus manquant, ni un espace d'allocation, ni une
erreur silencieuse : c'est **l'initialisation du stockage/configuration qui ne
rend pas la main**. Elle lit un marqueur `0xAA55` dans une mémoire que notre board
ne fournit pas (le plan ne modélise que le contrôleur NOR à `0xFFFD8000`, pas la
mémoire de configuration série accédée ici).

## Prochaine action, précise

Identifier le périphérique derrière `0x113A14C` (le calcul de registre) et
`[0x16DB5AC]` (la base), puis le déclarer dans le plan. Deux candidats
catalogue : `byte-i2c-0/1/2` (`0xFFF3D000`+`0x1000n`) et le `nand-controller`
(`catalog/soc/xp4/blocks/nand-controller.json`). Le troisième est déjà modélisé
(`storage_jedec`), donc ce que le firmware lit ici est probablement **l'EEPROM de
configuration** — un partenaire à déclarer, pas un contrôleur à ajouter.

---

# Session 10 — la boucle qui ne finit pas, localisée

## `0x113A3A8` : copie d'EEPROM bornée par un calcul faux

Le chemin d'échec de `0x113A7BC` (signature `0xAA55` absente) appelle
`0x113A3A8`, qui recopie des mots de configuration :

```asm
0x113A3C8  movw r3,#0xf7fc ; movt r3,#0x15b
0x113A3D0  ldrh r0,[r3]                     ; [0x15BF7FC]
0x113A3D4  movw r3,#0xfffe
0x113A3D8  cmp  r0,r3
0x113A3DC  bhi  0x113A420                   ; si > 0xFFFE : sortie
0x113A3E0  movw r5,#0xf7fc ; movt r5,#0x15b
0x113A3E8  ldrb r1,[r5,#2]
0x113A3EC  bl   0x113A384                   ; écrit un octet (I2C)
0x113A3F0  mov  r4,r5
0x113A3F4  sub  r5,r5,#0xf0000004
0x113A3F8  sub  r5,r5,#0x0ee00000           ; <-- borne de fin
0x113A3FC  movw r6,#0xfffe
0x113A400  ldrh r0,[r4,#4]                  ; --> boucle
0x113A404  cmp  r0,r6
0x113A408  bhi  0x113A420
0x113A40C  ldrb r1,[r4,#6]
0x113A410  bl   0x113A384
0x113A414  add  r4,r4,#4
0x113A418  cmp  r4,r5
0x113A41C  bne  0x113A400                   ; <-- reboucle
```

Le calcul de borne `r5` part d'une **adresse RAM** (`0x15BF7FC`) et lui soustrait
`0xF0000004` puis `0x0EE00000`, soit `0xFEE00004` au total. En arithmétique 32
bits cela enroule, mais la comparaison `add r4,#4 ; cmp r4,r5 ; bne` ne peut
jamais s'égaliser de façon sûre avec la valeur obtenue : la boucle ne converge
pas vers un terme.

## Pourquoi cette adresse est fausse dans notre board

`[0x16DB5AC]` vaut `0x04168000`, et les offsets accédés (`0x420000`,
`0x440000`, `0x160000`) tombent à `0x04588000`, `0x045A8000`, `0x042C8000`.
Ces adresses sont dans la RAM nue mais **au-delà de l'image** (`0x3F74000`), donc
à zéro.

Sur le matériel réel cette zone est une **mémoire de configuration** (EEPROM/NVRAM)
remplie d'usine, contenant entre autres le marqueur `0xAA55`. Notre plan ne
fournit rien à ces adresses, donc :

1. la signature `0xAA55` est absente (`0x113A80C` échoue) ;
2. le chemin d'échec `0x113A3A8` boucle sans fin sur une borne mal calculée ;
3. `0x113A7BC` ne revient jamais ;
4. `TSK_ROOT` ne poursuit pas, et `TSK_UILIB`/`TSK_LCDEVF` ne sont jamais créés.

C'est la chaîne causale complète, mesurée à chaque étape.

## Ce qu'il faut fournir

Une **mémoire de configuration initialisée** à `[0x16DB5AC] = 0x04168000`,
couvrant au moins `0x421000..0x470000`, contenant :

- le marqueur `0xAA55` en tête de la zone de configuration ;
- les mots de configuration attendus par `0x113A3A8`.

Ce n'est ni un contrôleur à modéliser ni un contrat de bus : c'est un **contenu
initial** (comme une NVRAM d'usine), que le plan peut déclarer comme image.

## Prochaine action

1. Chercher dans `ffboot.bin` si une copie de cette NVRAM existe hors de l'image
   chargée (elle dépasserait `0x3F74000`, donc probablement non) ;
2. sinon, déterminer le contenu minimal viable : la structure lue par
   `0x113A958` (`0x204`, `0x205`, …) donne le format des entrées
   `[offset_u16][value_u8]` ;
3. déclarer ce contenu comme image dans le plan, à `0x04168000`, et relancer.

---

# Session 11 — conflit d'adressage : NOR aperture contre alias DRAM

## Le chemin d'accès de la configuration, complétement tracé

`0x113A7BC` appelle la lecture de stockage, qui aboutit à :

```asm
0x113AB40  bl   0x1152B98        ; setup
0x113AB44  add  r0, r7, r4, lsl #17     ; offset = page << 17
0x113AB48  bl   0x1091D9C               ; <-- ajoute 0xF0000000
0x113AB4C  mov  r3, #1
0x113AB50  mov  r2, r6
0x113AB54  mov  r1, r0
0x113AB58  mov  r0, r5
0x113AB5C  bl   0x1091C50               ; transfert
```

et `0x1091D9C` est littéralement :

```asm
0x1091D9C  str fp,[sp,#-4]!
0x1091DA0  add fp,sp,#0
0x1091DA4  add r0,r0,#0xf0000000        ; <-- alias haute de la DRAM
0x1091DA8  add sp,fp,#0
0x1091DAC  pop {fp}
0x1091DB0  bx  lr
```

Le firmware lit donc la mémoire de configuration **à travers l'alias DRAM
`0xF0000000`**, pas à son adresse physique basse. C'est un accès cacheable
classique sur XP4 : la même DRAM vue à `0x0` et à `0xF0000000`.

## Ce que la mesure a établi, par étapes

| Étape | Observation |
| --- | --- |
| `0x113A7BC` | atteint une seule fois, ne revient jamais |
| `0x113B924` | atteint |
| `0x113AB08` | atteint, `[0x164C0FC] = 1` donc chemin principal pris |
| `0x113AB28` | atteint (page jugée valide) |
| `0x113AB60` | **jamais atteint** → `0x1091D9C` ou `0x1091C50` ne rend pas la main |

## La cause : collision de fenêtres physiques

`assemble_xp4_board.py` déclare la **NOR aperture** :

```python
(0xF0000000, 0xF8000000),   # serial NOR aperture
```

Or l'alias DRAM que le firmware utilise commence exactement à `0xF0000000`.
Les deux fenêtres sont physiquement la même plage : le plan ne peut pas avoir
les deux, et c'est aujourd'hui la NOR qui l'emporte.

Ajouter `dram_alias: 0xF0000000` échoue donc avec
« Overlapping ARM32 physical owners », quelle que soit la taille de DRAM : le
conflit est entre l'alias et l'owner NOR, pas lié à `ram_size`.

Le firmware ne référence `0xF0xxxxxx` par aucun littéral (vérifié : aucun
`movt #0xf0` dans seg0) ; l'alias est **calculé** par `add`. Rien dans le code ne
prouve qu'il lit la NOR à cette adresse par cette fenêtre.

## Deux hypothèses à départager

1. **L'aperture NOR est inutile pour ce firmware** à `0xF0000000` : la retirer et
   poser l'alias DRAM à la place. Le contrôleur NOR reste modélisé à
   `0xFFFD8000` (registres) et la NOR est lue par le contrôleur, pas par
   l'aperture.
2. **Les deux coexistent sur le matériel** via un mode (mirroring NOR/DRAM
   sélectionné au boot), et l'émulateur doit choisir selon l'état d'un registre.

L'hypothèse 1 est testable immédiatement : c'est la prochaine action.

## Prochaine action

Retirer `(0xF0000000, 0xF8000000)` de `OWNERS`, poser `dram_alias = 0xF0000000`
avec `ram_size` ajusté pour tenir sous `0xFF500000` (128 Mo convient : l'image
fait 66 Mo), puis vérifier que le firmware lit la configuration et poursuit
au-delà de `0x113A7BC`.

---

# Session 11 bis — le conflit est structurel, pas contournable

## L'aperture NOR est câblée dans le modèle de stockage

`crates/emulator-xp4-storage/src/storage.rs` :

```rust
pub const FLASH: u64 = 0xf0000000;
pub const FLASH_SIZE: u64 = 0x08000000;
```

Le contrôleur de stockage XP4 possède **par construction** la fenêtre
`0xF0000000..0xF8000000`. Ce n'est pas une option du plan : elle vient avec
`storage_jedec`.

## Tentatives mesurées

| Tentative | Résultat |
| --- | --- |
| `dram_alias = 0xF0000000`, `ram_size` quelconque | `Overlapping ARM32 physical owners` |
| idem en retirant la région brute `(0xF0000000,0xF8000000)` du plan | même erreur (l'owner vient du device) |
| supprimer `storage_jedec` pour libérer la plage | `XP4 storage data/routes require explicit controller selection` |
| garder `storage_jedec` sans `storage_dma_routes` | `XP4 DMA requires 16 physical IRQ routes` |

Conclusion : on ne peut pas avoir à la fois le contrôleur NOR (nécessaire au
stockage et au DMA) et un alias DRAM à `0xF0000000` **dans ce modèle**.

## Ce que cela signifie

Le firmware fait `add r0, r0, #0xF0000000` pour lire la configuration. Sur le
matériel réel, `0xF0000000` est probablement **une fenêtre commutée** : soit
l'aperture NOR, soit un alias DRAM, selon un mode établi au boot (le loader
écrit `[0x16DB5AC] = 0x04168000` juste avant cet accès, ce qui ressemble à la
programmation de ce mode).

Deux voies, toutes deux hors du plan actuel :

1. **Étendre l'émulateur** pour que le contrôleur NOR cède sa plage quand le
   mode alias est sélectionné — demande de modifier le crate de stockage.
2. **Déclarer la configuration comme une image NOR** : puisque le firmware lit
   `0xF0000000 + offset` et que cette plage est la NOR, le contenu de
   configuration pourrait y être placé comme image NOR. C'est cohérent avec le
   fait que la configuration est souvent stockée en NOR.

La voie 2 est testable sans toucher au Rust : écrire la structure de
configuration dans l'image NOR (`storage` medium) plutôt qu'en DRAM.

## Ce que la session a établi au total

La chaîne causale du blocage est maintenant **complète et vérifiée étape par
étape** :

```
loader terminé
  → main() applicatif
  → TSK_ROOT + 4 idle créés
  → 12 fonctions d'init exécutées dans l'ordre (milestones mesurés)
  → 0x1163744 : initialisation du stockage
  → 0x113A7BC : lecture de configuration via alias 0xF0000000
  → adresse non résolue (plage occupée par l'aperture NOR)
  → 0x113A7BC ne revient jamais
  → TSK_UILIB (0x36) et TSK_LCDEVF (0x37) jamais créés
  → aucune frame LCDC
```

---

# Session 12 — piste « valeurs par défaut » : la cause finale

## Les valeurs par défaut existent dans le firmware

À `0x15BF7FC` se trouve une table de **143 entrées** `{u16 offset, u8 value, u8 pad}`,
terminée par `0xFFFF` à `0x15BFA38`, couvrant les offsets `0x0100`..`0x03A1`.
Première entrée : offset `0x0100` = `0xCB` ; le contenu est intégralement dans
`ffboot.bin` (22,8 Mio sur 66).

La signature `0xAA55` que le code teste est lue comme
`(byte[0x203] << 8) | byte[0x202]` (cf. `0x113A1F0`), donc à l'offset **0x202**,
pas 0.

## Une configuration complète a été construite et testée

`0x04168000` + `0x80000` octets, rempli avec `0xFF`, la signature `0xAA55` à
`0x202`, et les 143 valeurs par défaut à leurs offsets. Deux runs de 400 M
instructions avec cette image donnent **exactement** le même état que sans :
cœur 0 à `0x1162F10` (idle), 11 entrées de registre applicatif.

Ce n'est donc pas la configuration qui manque.

## Le point de blocage réel, après descente complète

La chaîne, vérifiée milestone par milestone :

```
0x1163744  bl 0x113A7BC            (initialisation stockage)
0x113A7BC  … bl 0x113B924          (lecture, 11 pages)
0x113B924  … bl 0x113AB74
0x113AB74  … bl 0x113AB08
0x113AB08  page valide -> 0x113AB28, puis bl 0x1091D9C (add 0xF0000000)
           et bl 0x1091C50
0x1091C50  … bl 0x109194C          (validation d'adresse)
0x109194C  chemin non aligné -> 0x1091A98 -> bl 0x10913D8
0x10913D8  … bl 0x10907AC          (transfert)
0x10907AC  … bl 0x1097140          (soumission)
           … bl 0x114FC44
           … bl 0x1093410          (LECTURE NOR, see below)
0x1093410  écrit 0xFFFD8020 = 0x707 ou 0x606, 0x806C = taille,
           0x801C = adresse, puis boucle sur 0xFFFD8060 bit 0x20
0x1093410  rend la main (le NOR répond)
0x10907AC  retour -> 0x10908A4
           [0x16A2D24] = 0x9F, alors que le code compare à -1 (cmn r3,#1)
           -> prend 0x109099C
0x109099C  bl 0x1150004(0x400, &flag, timeout=-1)   <-- ATTENTE D'ÉVÉNEMENT
           ne rend JAMAIS la main
```

## La cause exacte

À `0x109099C` le firmware appelle `0x1150004` avec `r0 = 0x400`, un pointeur de
drapeau et `r2 = -1` (timeout infini). C'est une **attente d'événement** : le
thread se bloque jusqu'à ce qu'un autre composant poste l'événement `0x400`.

Aucun milestone après `0x10908AC` n'est atteint, donc cette attente ne se résout
jamais. Le firmware n'atteint donc jamais `0x10908E8` (`0x1097B40`), ni le retour.

## Pourquoi la configuration ne change rien

Le test `[0x16A2D24] != -1` ne dépend pas de la configuration : c'est l'état du
périphérique de transfert (structure à `0x16A2D0C`, magic `0x77666555`). Le
firmware y lit `0x9F` — valeur déjà présente dans l'image chargée — et en déduit
qu'il doit attendre un événement.

Autrement dit : **la configuration n'est pas le verrou ; c'est le moteur de
transfert qui attend un signal qu'aucun autre thread n'émet**, parce que le
thread émetteur (`TSK_LCDEVF` ou un service de stockage) n'a jamais été créé.

## Ce que cela boucle

La régression est circulaire :

```
TSK_LCDEVF absent -> personne ne poste l'événement 0x400
                  -> l'init du stockage attend indéfiniment
                  -> TSK_LCDEVF n'est jamais créé
```

Le verrou initial est donc **en amont** : ce n'est ni la configuration, ni l'alias
DRAM, ni un contrat de bus. C'est l'ordre d'amorçage : une tâche que le firmware
attend n'existe pas encore.

## Prochaine action

Chercher `0x1150004` et l'identifiant d'événement `0x400` : trouver qui doit le
poster (quel `tx_event_flags_set`, quel thread), puis vérifier si ce thread fait
partie des 11 enregistrés ou s'il manque. Si `0x400` est posté par un thread non
créé, la boucle est confirmée et il faudra identifier **pourquoi** ce thread
n'est pas créé — ce sera alors le vrai point d'entrée du problème.

---

# Session 13 — qui devrait poster l'événement `0x400` : réponse

## L'API ThreadX du loader, identifiée

| Adresse | Rôle | Signature |
| --- | --- | --- |
| `0x54F04` | `tx_event_flags_get` | `(group, flags_to_get, option, *flags, timeout)` |
| `0x54FE8` | `tx_event_flags_set` interne | `(group, flags)` |
| `0x551F4` | `tx_event_flags_set` public | `(group, flags)` |
| `0x5522C` | façade du setter | `(group, flags)` |
| `0x1150004` | wrapper *get* de l'application | `(group, *out, timeout)` |
| `0x115007C` | wrapper *set* de l'application | `(group, flags)` |
| `0x57B74` | résolution du groupe global | → pointeur de groupe |

## Correction d'une lecture erronée

J'ai d'abord cru que `0x400` était un **masque** d'événement. C'est faux.
Dans `0x1150004` :

```asm
0x1150010  mov r4, r0        ; arg0
0x115001c  bl  0x57B74       ; r0 = pointeur de groupe global
0x1150028  mov r2, #1        ; option
0x115002c  mov r1, r4        ; flags_to_get = arg0
0x1150030  bl  0x54F04
```

`arg0` part donc dans `flags_to_get` et le **groupe** vient de `0x57B74`.
`0x400` est bien un **jeu de drapeaux**, pas un identifiant de groupe.

Les autres appelants le confirment : ils passent `0x100`, `0x8000`,
`0x60000000`, `0x10000000`, `4`, `1`, `0x10`, `0x1000`, `0x10000` — des masques.

## L'événement n'a aucun émetteur, et aucun groupe n'existe

Deux mesures indépendantes :

1. **Aucun code ne pose `0x400`.** Un seul `mov #0x400` existe dans les deux
   segments, à `0xF21270`, et c'est un argument de `memcpy` (`bl 0x115373C`),
   pas de setter. Les trois appelants du setter interne `0x54FE8`
   (`0x4F748`, `0x5522C`, `0x5613C`) sont des façades, et les six appelants du
   wrapper `0x115007C` posent `0x1000`, `0x10000`, `0x10`, `1` — jamais `0x400`.

2. **Aucun groupe d'événements n'est instancié.** La seule occurrence de la
   signature `EVNT` dans toute la RAM est à `0x1311642`, une chaîne du binaire
   (table de noms), pas une structure vivante. Une recherche de `TMER` ne donne
   rien.

## La conclusion

`0x109099C` appelle `tx_event_flags_get(flags = 0x400, option = 1, timeout = -1)`.
Le groupe global est résolu par `0x57B74`, mais **rien ne pose jamais ce bit** :
ni un thread applicatif, ni le loader. Avec `timeout = -1` l'attente est
infinie.

Le verrou est donc **une attente d'événement sans émetteur** — un contrat
d'ordonnancement interne, pas une configuration, pas un périphérique, pas un
bus.

## Ce que la piste a éliminé, définitivement

| Hypothèse | Verdict |
| --- | --- |
| Configuration/NVRAM absente | **écartée** : 143 valeurs par défaut extraites du firmware, image construite, run identique |
| Alias DRAM `0xF0000000` | **écartée** : la lecture NOR répond, le transfert progresse |
| Contrat de bus / périphérique | **écartée** : la NOR, le timer, le GIC et le DMA fonctionnent (0 abort) |
| Tâche `TSK_LCDEVF` manquante | **confirmée**, mais comme conséquence |
| Attente d'événement sans émetteur | **cause immédiate** |

## Options restantes

1. **Trouver quel thread devrait poser `0x400`.** Il n'est pas dans les 11
   enregistrés. Cela demande de reconstituer l'ordre d'amorçage Fujifilm complet
   (quel thread crée le groupe, quel autre le signale) — désassemblage lourd,
   mais sans caméra.
2. **Dump RAM réel par USB/jig** : révélerait l'état attendu du groupe
   d'événements et confirmerait l'ordre.
3. **Contourner** : forcer `[0x16A2D24] = -1` (ou poser `0x400` à chaque
   tentative) pour voir si l'init dépasse ce point et si `TSK_LCDEVF` apparaît.
   C'est un test de diagnostic, pas une correction fidèle — mais il répondrait
   immédiatement à la question « est-ce le dernier verrou ou en reste-t-il
   d'autres ? ».

---

# Session 14 — confirmé : le verrou unique est l'attente 0x400

## Trace définitive

Run de 400 M instructions, labels sur les cinq points de la chaîne :

```
 34 767 065  core0  0x113A7BC   initialisation stockage
 37 397 276  core0  0x1093410   lecture NOR        (fonctionne)
 37 397 410  core0  0x10908A4   retour du transfert
 37 397 417  core0  0x109099C   ATTENTE 0x400      <-- ne revient jamais
      ———      ———    0x1090910   jamais atteint
      ———      ———    0x1163748   jamais atteint
```

C'est la preuve la plus courte et la plus nette de toute l'analyse : quatre points
sont franchis, le cinquième bloque, et rien après.

## Le contournement testé n'a pas suffi

Un patch diagnostique a été préparé pour forcer `[0x16A2D24] = 0xFFFFFFFF`
(la valeur que le code compare à `-1` avec `cmn r3,#1`) :

```toml
[[patch]]
address = 0x16A2D24
original_hex = "00000000"
patched_hex  = "ffffffff"
at_ms = 200
```

Après le run, la valeur est `0x00010000` : le firmware **écrit lui-même** ce
champ pendant l'initialisation, plus tard que le patch. Forcer la valeur en
amont ne change donc rien — elle est réécrite avant d'être testée.

Et quand bien même le test passerait, la valeur n'est pas la seule condition :
le firmware atteindrait alors `0x10908C0` (la boucle d'acquittement NOR), qui
appelle `0x109808C` → `0x109BF40` (IPC). Le chemin reste dépendant d'un
émetteur d'événement.

## État du diagnostic

| Élément | Statut |
| --- | --- |
| Émulateur (4 cœurs, mémoire, périphériques) | **fonctionne** — 0 abort sur 600 M |
| Loader → application | **fonctionne** |
| `main()`, `bss`, `TSK_ROOT`, 4 idle | **fonctionnent** |
| 12 fonctions d'init applicatives | **s'exécutent toutes** |
| Lecture NOR par le contrôleur | **fonctionne** |
| Attente d'événement `0x400` | **bloque, sans émetteur** |
| `TSK_UILIB`, `TSK_LCDEVF` | jamais créés → pas de frame |

## Conclusion

Le blocage est un **contrat d'ordonnancement interne** : le firmware attend un
drapeau d'événement que rien dans le code chargé ne pose. Ce n'est ni une
configuration manquante (143 valeurs par défaut extraites et testées sans effet),
ni un périphérique absent (tous répondent), ni un problème d'espace d'adressage
(la NOR répond à l'alias).

Les trois suites possibles, par ordre de coût croissant :

1. **Reconstituer l'ordre d'amorçage Fujifilm** : identifier quel thread crée le
   groupe d'événements et quel autre le signale. Purement hors ligne, mais
   demande de comprendre la séquence complète des 152 tâches — plusieurs
   sessions de désassemblage.
2. **Dump RAM réel par USB/jig (`ff80`)** : donnerait l'état d'un système qui
   démarre vraiment, y compris le groupe d'événements peuplé. Risque matériel.
3. **Accepter l'état actuel** : l'émulateur est un banc d'analyse fiable du
   firmware (exécution fidèle, zéro faute), utilisable pour du désassemblage et
   de la vérification de patchs, mais il n'atteint pas l'interface.

---

# Session 15 — le groupe d'événements n'est jamais créé

## La table des groupes d'événements, localisée

`0x54FE8` (`tx_event_flags_set`) résout le groupe par :

```asm
0x55000  movw r3,#0xa944 ; movt r3,#7
0x55008  sub  r2,r8,#1
0x5500c  ldr  r5,[r3,r2,lsl#2]      ; groupe = TABLE[group-1]
0x55010  cmp  r5,#0
0x55014  beq  0x55198               ; groupe inexistant -> erreur
```

La table est donc à **`0x0700A944`**, un pointeur par groupe.

**Mesure : les 288 entrées de cette table sont toutes nulles.** Aucun groupe
d'événements n'existe dans le système.

## Le créateur, identifié, et pourquoi il ne tourne pas

Le créateur est `0x4BE9C`, appelé depuis `0x4BEF4` (démarrage de tâche, lui-même
appelé par `0x1150210`). Il écrit dans `0x06003168 + (id−1)*0x14`.

**Mesure : aucune entrée non nulle à `0x06003168`.** Le créateur n'a jamais
réussi.

Sa porte d'entrée, `0x4BEF4(id, descriptor)`, valide :

```asm
0x4BF28  ldr r3,[r1,#8]        ; descriptor[8] doit être l'id de tâche
0x4BF2C  sub ip,r3,#1
0x4BF30  movw r2,#0x7ffe
0x4BF34  cmp ip,r2
0x4BF38  bhi 0x4C024           ; > 0x7FFE -> erreur, rien n'est créé
```

Or les descripteurs réellement enregistrés portent autre chose en `[8]` :

| Tâche | Descripteur | `[4]` | `[8]` |
| --- | --- | ---: | ---: |
| `TSK_FLASH` (`0x2B`) | `0x00068CC4` | `0x3371A` | **`0x018AB724`** |
| `TSK_IDLE_0` (`0x9B`) | `0x00071FC4` | `0x1` | **`0x018A4F7C`** |

`0x018AB724` et `0x018A4F7C` sont des **adresses de pile**, pas des identifiants.
`[8] − 1` dépasse `0x7FFE`, donc chaque appel retourne l'erreur `0x4C024` et
**aucun groupe d'événements n'est créé**.

## La chaîne complète, enfin complète

```
ordre d'amorçage applicatif
  → TSK_ROOT démarre les tâches par 0x1150210 → 0x4BEF4
  → 0x4BEF4 lit le descripteur à 0x0007A55C
  → descripteur[8] contient une adresse de pile, pas un id
  → validation 0x4BF34 échoue → aucun groupe d'événements créé
  → table 0x0700A944 reste vide
  → 0x109099C : tx_event_flags_get(flags=0x400, timeout=-1) ne peut jamais
    être satisfait (0x54FE4 ne trouve pas de groupe)
  → l'init du stockage ne rend pas la main
  → TSK_UILIB (0x36) et TSK_LCDEVF (0x37) ne sont jamais créés
  → aucune frame LCDC
```

## Interprétation

Le descripteur de tâche attendu par `0x4BEF4` a un layout `{flags, id_min, id}`
alors que les structures présentes sont des `THRD` ThreadX
`{signature, …, stack}`. Le champ `+8` des `THRD` est bien la **pile**, pas l'id.

Deux lectures possibles :

1. **Le code applicatif appelle `0x4BEF4` avec le mauvais type d'objet.** Il
   passe la structure `THRD` là où un descripteur compact est attendu — ce qui
   serait un bug de notre part dans la reconstitution, ou une différence de
   version.
2. **Le layout du descripteur diffère de ce que j'ai déduit.** `[4]` et `[8]`
   pourraient être permutés ou décalés d'un mot.

La seconde hypothèse est testable immédiatement : vérifier un descripteur dont
on sait qu'il a réussi (les 11 tâches existent, donc une création a bien eu
lieu quelque part) et comparer son layout à celui lu par `0x4BEF4`.

## Prochaine action

Trouver comment les 11 structures `THRD` ont été créées si ce n'est pas par
`0x4BEF4` : chercher les écritures de la signature `0x54485244` (ou de ses
demi-mots `0x4844`/`0x5244`), puisque le littéral complet n'existe nulle part
dans les segments.

---

# Session 16 — la cause racine : la boucle de création échoue au premier id

## Le VRAI créateur, avec ses bases corrigées

Deux erreurs de lecture d'adresse corrigées dans cette session (les deux venaient
de `movt #6` interprété comme `0x06000000` au lieu de `0x00060000`) :

| Fonction | Base réelle | Rôle |
| --- | --- | --- |
| `0x4C04C(id, desc)` | `0x000655A4 + (id−1)×0x150` | **créateur de thread** : écrit `id` en `+0xCC`, appelle `tx_thread_create` (`0x441AC`) |
| `0x441AC(...)` | — | `tx_thread_create` réel (7 arguments) |
| `0x4BEF4(id, desc)` | `0x0007A55C + (id−1)×4` | démarrage d'une tâche déjà créée |
| `0x54FE8(group, flags)` | `0x0700A944 + (group−1)×4` | `tx_event_flags_set` |
| `0x54F04(...)` | — | `tx_event_flags_get` |

## Les 11 threads existants sont bien créés par `0x4C04C`

Vérifié : `0x655A4 + (0x2B−1)×0x150 = 0x68CC4`, exactement l'adresse de la
structure `THRD` de `TSK_FLASH`. Les 11 slots portent la signature `0x54485244` :

```
0x2B TSK_FLASH      0x71 TSK_EXEC_CPU_2   0x72 TSK_EXEC_CPU_3
0x73 TSK_EXEC_CPU_4 0x74 TSK_EXEC_CPU_5   0x75 TSK_STANDBY_1
0x9B 0x9C 0x9D 0x9E (les quatre idle)     0x9F (racine)
```

## La boucle de création échoue au premier identifiant

`0x11635DC` itère `r4 = 1 .. 0xA7` (167 itérations) et appelle `0x1150210(tid, 1)`.
Or l'état réel :

| Mesure | Valeur |
| --- | --- |
| Slots créés dans la plage 1..167 | **11** |
| Slots manquants | **156** |
| Ids 0x01 à 0x0A créés | **aucun** |

Le premier appel est `id = 0x01` = `TSK_SYSCONT`, la tâche système. Son slot
(`0x655A4`) est vide : la création échoue immédiatement, et la boucle s'arrête
sur cette erreur (`0x11502B4` : `subs r4, r0, #0` puis `bne` vers l'enregistrement
d'erreur et la sortie).

Les 11 threads présents ont donc été créés **ailleurs**, plus tôt — probablement
par le loader lui-même, avant le passage de relais, ce qui explique pourquoi ils
portent les ids les plus hauts (`0x2B`, `0x71`–`0x75`) et les idle.

## La chaîne causale, complète et vérifiée

```
loader crée ses 11 threads (FLASH, EXEC_CPU_2..5, STANDBY, 4 idle, root)
  ↓ passage de relais, [0xD20008] = 1
main() applicatif efface le bss
0x1163500 (root) enregistre TSK_ROOT puis boucle 1..167
  ↓ id = 0x01 (TSK_SYSCONT) : création échoue, slot 0x655A4 vide
  ↓ boucle stoppée, aucun autre thread applicatif créé
  ↓ TSK_UILIB (0x36) et TSK_LCDEVF (0x37) jamais créés
  ↓ aucune tâche ne poste l'événement 0x400
  ↓ table 0x0700A944 reste vide
  ↓ 0x109099C : tx_event_flags_get(0x400, timeout=−1) attend indéfiniment
```

---

# Session 17 — corrections et nouvel état des lieux

Cette session a corrigé **quatre erreurs d'adresse** dues à la même cause :
`movt rX,#N` produit `0x000N_xxxx`, jamais `0x0N00_xxxx`.

| Base fausse (mes sessions précédentes) | Base réelle | Conséquence |
| --- | --- | --- |
| `0x06003168` | **`0x00063168`** | la table de tâches **est peuplée** (167 entrées), contrairement à ce que j'avais conclu |
| `0x060055A4` | **`0x000655A4`** | les 11 `THRD` sont bien créés par `0x4C04C` |
| `0x0700A944` | **`0x0007A944`** | ce n'est pas une table de groupes mais la table des **descripteurs de tâches** |

## État réel, re-mesuré

`0x00063168` — descripteurs de tâches, stride `0x14` :

```
165 tâches avec (word1, word2, word3) = (1, 1, 1)
  2 tâches avec (1, 1, 0)          : 0x0D, 0x88
  8 tâches avec (0, 0, 0)          : 0xA8..0xAF (hors énumération)
```

Les tâches **sont donc enregistrées**, y compris `TSK_UILIB` (`0x36`) et
`TSK_LCDEVF` (`0x37`), tous deux avec `(1, 1, 1)`.

`0x000655A4` — structures `THRD`, stride `0x150` : **11** seulement, celles du
loader (`TSK_FLASH`, `EXEC_CPU_2..5`, `STANDBY_1`, 4 idle, root).

`0x0007A944` — `tx_event_flags_*` indexe cette table par `id-1`. Ce sont donc des
**descripteurs de tâches adressables par id**, et `flags = 0x400` est un bit posé
sur la tâche ciblée.

## Ce que cela change

La création des tâches n'est plus le problème : les 165 entrées existent et sont
marquées actives. Ce qui manque est le **passage à l'état « thread ThreadX
créé »** : seul un sous-ensemble (11) possède une structure `THRD` avec la
signature, une pile et un état.

Le firmware attend `flags = 0x400` sur une tâche ; cette attente est un mécanisme
d'ordonnancement, pas une ressource physique.

## Recherche d'émetteur de `0x400` : les candidats sont des faux positifs

`mov r1,#0x400` n'apparaît que trois fois, et aucun n'est un émetteur :

| Adresse | Ce que c'est réellement |
| --- | --- |
| `0x5E40` | `movt r1,#0x8400` → écrit `0x84000400` dans un registre LCDC à `0xFFF79020` |
| `0x5F04` | idem, second registre LCDC |
| `0x6B00` | `mov r1,#0x4000` (quatre zéros), registre `0xFFFD8044` |

Donc le masque `0x400` n'est jamais posé par une constante littérale visible.
Il l'est probablement par un **calcul** (décalage `1 << n`) que la recherche
littérale ne peut pas trouver.

## Prochaine action

Chercher les `lsl` / `mov ... , lsl` produisant `0x400` (n = 10) près d'un appel
à `0x115007C`, ou tracer le setter `0x551F4` / `0x5522C` et relever tous les
`r1` effectivement passés pendant un run de 600 M avec instrumentation des
arguments.

---

# Session 18 — le masque 0x400 n'a qu'un seul site dans tout le firmware

## Recherche exhaustive, trois formes

| Forme recherchée | Occurrences pertinentes |
| --- | --- |
| `mov`/`movw rX, #0x400` | 3, tous des faux positifs (registres LCDC à `0xFFF79020`, et un `0x4000`) |
| `lsl #10` / `lsl #0xa` (= `1 << 10`) | **aucune** |
| site d'appel du getter `0x1150004` avec `r0 = 0x400` | **un seul** : `0x10909A8` |

L'unique site est celui de l'attente :

```asm
0x109099C  mvn r2, #0          ; timeout = -1
0x10909A0  sub r1, fp, #0x48   ; &flags
0x10909A4  mov r0, #0x400      ; flags_to_get = 0x400
0x10909A8  bl  0x1150004       ; tx_event_flags_get
```

## Ce que cela prouve

`0x400` est à la fois **le seul consommateur et l'absence d'émetteur** : aucun code
du firmware chargé, ni dans les deux segments applicatifs ni dans le loader,
ne pose ce bit — que ce soit par constante, par décalage, ou par une valeur
calculée que la recherche littérale aurait manquée.

Un mécanisme qui attend un drapeau que rien ne pose est, dans un systèmes à
tâches, un **rendez-vous avec un composant absent**. Ici ce composant est la
partie du système qui, sur le matériel réel, accompagne le transfert du moteur
de stockage — le thread qui aurait été créé par la boucle des 167 tâches si
l'ordonnancement Fujifilm était complet.

## Bilan final du chantier A

L'émulateur exécute correctement le firmware : 4 cœurs, 600 M d'instructions,
zéro abort, zéro erreur. Tout ce qui relève du matériel modélisé fonctionne
(minuterie, GIC, DMA, NOR, LCDC, MOVDC, ADC, GPIO, JPEG, SD).

Le blocage est **un rendez-vous d'ordonnancement** : le firmware attend le bit
`0x400` sur sa propre tâche, et aucun composant ne le pose. Ce n'est ni la
configuration (143 valeurs par défaut extraites et testées sans effet), ni un
périphérique (tous répondent), ni l'espace d'adressage (la NOR répond à l'alias
`0xF0000000`), ni la création des tâches (165 descripteurs enregistrés).

Trois voies restantes, par coût croissant :

1. **Comprendre l'ordonnancement Fujifilm** — quel composant émet `0x400` sur le
   matériel réel. Nécessite la documentation ou un dump d'un système qui démarre.
2. **Dump RAM par USB/jig (`ff80`)** — donnerait l'état réel, y compris ce bit.
   Risque matériel, commandes en lecture uniquement.
3. **S'arrêter ici** : l'émulateur reste un banc d'analyse fiable.

---

# Session 19 — il n'existe pas de chemin PTP : le seul mode USB est le jig

## Question posée

Existe-t-il un chemin **PTP normal, en lecture seule**, pour déclencher le
mécanisme « bulk » déjà catalogué, sans passer par le mode jig ?

## Réponse : non, et la raison est dans le firmware

### Un seul descripteur USB dans tout l'artefact

Recherche du motif de descripteur USB standard (`bLength=0x12, bType=0x01,
bcdUSB=0x0200`) dans les deux segments et dans l'image complète :

| Emplacement | VID | PID |
| --- | --- | --- |
| `0x15C8A4D` (seg0) | `0x0112` | `0x0700` (faux positif : données) |
| `0x24E6000` (seg1) | **`0x04CB`** | **`0xFF80`** |
| `0x24E6014` (seg1) | **`0x04CB`** | **`0xFF80`** |

Soit **deux descripteurs identiques** (un par configuration USB), tous deux en
mode jig. Aucun descripteur PTP.

### Vérification croisée

- la paire `VID=0x04CB / PID=0x02DD` (PTP) n'existe **nulle part** dans les 66 Mio
  de l'image ;
- aucun `movw #0xff80` dans le code : le PID n'est pas calculé, il vient du
  descripteur statique ;
- les commandes de `ff80` (`0x1A0002`, `0x200001`, `0x450006`, `0x550001`,
  `0x580000`, `0x660002`, `0x760001`) sont toutes gérées par un dispatcher
  unique à `0x1F40038`, dans le segment applicatif — donc disponibles **en mode
  jig**, pas en PTP.

### Conséquence

Le mécanisme « bulk » catalogué (18 empreintes vérifiées) n'est **pas** un
service PTP : c'est le protocole du mode jig, et le mode jig est le seul mode USB
que ce firmware expose.

Il n'existe donc **aucun moyen en lecture seule** d'obtenir l'état du bit `0x400`
depuis cette caméra : la seule voie d'accès est le jig, et le jig exige
`set_config_usb_debug(1)` — une écriture dans la configuration à l'offset `0xF7`,
sur un layout dont `ff80` lui-même marque la sémantique comme supposée
(`?Mask: enable USB debug?`).

## Ce que cela implique pour la décision

| Voie | Faisable | Risque |
| --- | --- | --- |
| PTP lecture seule | **non** (aucun descripteur PTP) | — |
| Jig `ram dump` | oui | écriture config `0xF7` sur layout non validé pour ce boîtier |
| Jig en lecture pure sans `set_config_usb_debug` | à vérifier | le dump échoue probablement (lecture refusée si debug désactivé) |

La dernière ligne mérite un examen : si `debug_read_ram` fonctionnait avec
`xf7 == 0` (debug déjà activé par un autre chemin), `ff80` **ne ferait aucune
écriture**. C'est la seule variante sans risque matériel, et elle ne coûte qu'une
lecture du code.

## Prochaine action (sans risque)

Examiner si `debug_read_ram` réussit quand `get_config_usb_debug()` retourne 1
sans que `ff80` l'ait écrit — c'est-à-dire si l'octet `0xF7` peut déjà valoir 1
en sortie d'usine. Si oui, un dump serait purement en lecture.

---

# Session 20 — état réel des threads : tous suspendus en attente de signal

## Les structures THRD, entièrement décodées

Un `TX_THREAD` de ce firmware, layout confirmé sur `TSK_FLASH` (`0x68CC4`) :

| Offset | Champ | Valeur observée |
| --- | --- | --- |
| `+0x00` | signature | `0x54485244` (`THRD`) |
| `+0x20` | pointeur arrière | `0x68CC4` |
| `+0x44` | pointeur de pile | `0x55828` (commun) |
| `+0x6C` | **point d'entrée** | `0x5543C` (trampoline générique) |
| `+0x94` | **état ThreadX** | `3` = `TX_SUSPENDED` |
| `+0xF8` | **type d'attente** | `4` = event-flag, `2` = prêt |
| `+0x10C` | sous-type d'attente | `0x20`, `0x8` |
| `+0x110` | masque/id attendu | `0x2B`, `0x71`… `0x9F` |
| `+0xCC` | id de tâche | `0x2B` |
| `+0xD0` | **nom ASCII** | `"timer "`, `"execcpu "`, `"idle0"`, `"root"` |

Le nom en `+0xD0` est décisif : ce sont des chaînes réelles, donc les threads
sont authentiques — pas des restes d'initialisation.

## Les 11 threads, état complet

| Nom | État | Attente `+0xF8` | Sous-type `+0x10C` | Masque `+0x110` |
| --- | --- | ---: | ---: | ---: |
| `timer` | 3 | 4 | `0x20` | `0x2B` |
| `execcpu` ×4 | 3 | 4 | `0x20` | `0x71`–`0x75` |
| `idle0`–`idle3` | 0/1/2/3 | **2** (prêt) | — | — |
| `root` | 0 | 4 | `0x8` | `0x9F` |

`+0xF8 = 4` signifie « suspendu sur attente », `2` signifie « prêt à tourner ».

## Ce que cela prouve

Aucun thread n'attend sur les event flags `0x400` — ni `timer`, ni `execcpu`,
ni `root` (qui attend `+0x10C = 0x8`, une queue). Le thread qui appellerait
`tx_event_flags_get(0x400, −1)` **n'existe pas**.

Le réveil, d'après `0x54FE8`, fonctionne ainsi : le setter parcourt les threads,
compare `+0x10C`, et si ça correspond, écrit le masque en `+0x110`, remplace
l'entrée par le trampoline `0x5543C` et passe l'état à prêt. Un thread doit donc
**déjà exister et être suspendu** pour recevoir le signal.

## Conclusion de la piste 2

La documentation publique ne documente pas les masques d'événements Fujifilm
(`fffw` ne publie que `TX_TASK_STATE` et `TX_STATUS`, pas les bits d'attente), et
les dépôts X-T3/X-T4/X100V ne contiennent pas la séquence d'amorçage X-Pro3.

Le désassemblage établit en revanche un fait solide : **le système s'arrête avec
11 threads, tous suspendus en attente de signaux que personne n'émet**, et le
thread qui attendrait `0x400` n'a jamais été créé.

C'est un état d'amorçage incomplet : les tâches applicatives (167 descripteurs
enregistrés) n'ont pas leurs threads ThreadX. Le verrou est donc **entre
l'enregistrement du descripteur et la création du thread**, pas dans le
mécanisme d'événements lui-même.

## Piste résiduelle

Comparer, pour un thread qui fonctionne (`idle0`), la séquence complète
`enregistrement → tx_thread_create → état prêt`, avec celle d'une tâche
applicative (`TSK_SYSCONT`) qui reste à l'état `(1,1,1)` sans thread. L'écart
entre les deux donnera la condition manquante.

---

# Session 21 — la cause racine est dans le créateur de thread

## La boucle de création applicative, identifiée

`0x1151360(ids_start, flag, descriptor)` :

```asm
0x11513B8  movw r3,#0x158 ; movt r3,#0x1ab
0x11513C0  ldr  r4,[r3]               ; r4 = [0x1AB158] = compteur
0x11513C4  cmp  r4,#0x9f
0x11513C8  ble  0x11513EC             ; <= 159 -> fin
0x11513CC  sub  r1,fp,#0x2c
0x11513D0  mov  r0,r4
0x11513D4  bl   0x4C1E0              ; créer le thread d'id r4
0x11513D8  cmp  r0,#0
0x11513DC  beq  0x1151410             ; succès -> suite
0x11513E0  sub  r4,r4,#1
0x11513E4  cmp  r4,#0x9f
0x11513E8  bne  0x11513CC             ; boucle
```

Le compteur `[0x1AB158]` est initialisé à `0xFA` (250) par `0x1150F3C`
(`str r2,[r3]` avec `r2 = 0xFA`) — donc dans `main()`.

## Mesure de progression

| Palier | `[0x1AB158]` | Interprétation |
| --- | ---: | --- |
| 60 M | `0x64D` (1613) | boucle en cours, 1454 itérations restantes |
| 600 M | `0x2B` (43) | boucle terminée (43 ≤ 159) |

La boucle tourne donc **entièrement** et consomme ~3 millions d'instructions.

## Mais aucun thread n'est créé

Mesure : au-delà de l'id `0x9F`, **zéro structure `THRD`** dans les 512 Mio de RAM ;
le slot attendu pour l'id 250 (`0x79C74`) est vide.

Les seuls threads du système restent les 11 du loader
(`0x2B`, `0x71`–`0x75`, `0x9B`–`0x9F`).

## La cause : une comparaison sur la mauvaise variable

`0x4C1E0` valide l'identifiant, puis le descripteur, et termine par :

```asm
0x4C27C  bl   0x48DE8
0x4C280  movw r3,#0xf0ef ; movt r3,#0xf0f0
0x4C284  cmp  r0,r3                  ; r0 = valeur rendue par 0x48DE8
0x4C288  bls  0x4C3A4                ; <= 0xF0F0F0EF -> REJET
```

Or `0x48DE8` ne rend pas un compteur libre : il lit
`[0x5B680 + core×4]`, c'est-à-dire **la signature du premier `THRD`**.
Mesure : `[0x5B680] = 0x54485244` (`"THRD"`).

`0x54485244` est très inférieur à `0xF0F0F0EF`, donc la branche de rejet est
**toujours** prise. Chaque appel de `0x4C1E0` échoue, la boucle décrémente `r4`
sans jamais créer, et se termine normalement à 43 — sans erreur visible.

## Pourquoi

`0x48DE8` est un accesseur per-cœur prévu pour rendre une **borne d'identifiant
libre** (`0xF0F0F0EF` étant la sentinelle « slot libre », comme le `0xF0F0F0F0`
déjà vu dans les slots secondaires). Sur le matériel réel il lit un compteur
initialisé par le loader. Ici il lit la signature parce que la zone
`0x5B680` a été réutilisée pour le premier `THRD`.

Autrement dit : **les deux structures se chevauchent dans l'image que nous
chargeons**. Le loader écrit `THRD` à `0x5B680`, là où le code applicatif attend
un compteur de slots.

## Conclusion

La causalité complète, pour la première fois sans lacune :

```
0x5B680 doit contenir une borne libre (~0xF0F0F0EF+)
  mais contient la signature THRD (0x54485244) du premier thread du loader
  ↓
0x4C1E0 rejette chaque création (cmp 0x54485244 <= 0xF0F0F0EF)
  ↓
la boucle 0x1151360 consomme 1613→43 sans créer un seul thread
  ↓
aucune tâche applicative n'existe (TSK_UILIB, TSK_LCDEVF…)
  ↓
aucun thread n'attend sur 0x400, et rien ne le poste
  ↓
0x109099C attend indéfiniment
  ↓
pas de frame LCDC
```

C'est un **recouvrement de zones mémoire**, pas un contrat de bus, pas une
configuration, pas un événement manquant.

## Prochaine action

Vérifier si `0x5B680` est un alias : le loader y écrit `THRD` parce qu'il alloue
ses threads depuis `0x5B680`, alors que l'application attend là un compteur
distinct. Comparer avec un autre boîtier (`X-T3`, `X100V`) pour voir où ce
compteur devrait vivre — ou tester en plaçant `0xF0F0F0EF` en `0x5B680` avant la
boucle, ce qui est un diagnostic à un seul mot.

---

# Session 22 — la boucle de création n'est jamais appelée

## Deux erreurs de lecture corrigées, et le vrai résultat

1. **`0x48DE8` ne lit pas `0x5B680`.** Son littéral (`0x48DFC` → pc+8+0xc = `0x48E10`)
   vaut `0x0005B4F8`. C'est la table des slots de synchronisation des cœurs
   secondaires. Le patch posé sur `0x5B680` n'avait donc aucun effet — mesure
   cohérente : `[0x5B680]` a bien pris `0xF0F0F0EF`, et rien n'a changé.

2. **`0x4C290` n'est pas un chemin de succès.** C'est un simple incrément de
   compteur (`[0x5B56C]++`), suivi en `0x4C2B8` du **test d'existence** :
   `ldr r3,[0x7A55C+(id-1)*4] ; cmp r3,#0 ; mvnne r4,#0x28` — si le slot est
   déjà rempli, on rend `TX_NOT_DONE`. La création réelle est en `0x4C31C` →
   `0x4C04C`, atteinte **seulement** quand le slot est libre.

## Mesure décisive

Milestones sur la boucle `0x1151360` :

| Adresse | Rôle | Atteint ? |
| --- | --- | --- |
| `0x1151360` | entrée de la boucle | **non** |
| `0x11513C0` | lecture du compteur | **non** |
| `0x4C1E0` | créateur | oui (24 233 595) |
| `0x4C290` | incrément de compteur | oui (24 245 012) |

`0x4C1E0` est atteint, mais **jamais depuis `0x11513CC`** : aucun appel de la
boucle. Ce sont les 11 créations du loader que l'on observe.

Après le run : 11 threads, compteur `[0x1AB158]` = 43, `[0x5B56C]` = 0.

## La conclusion, corrigée une dernière fois

`[0x1AB158]` vaut 43 alors que `0x1150F3C` écrit `0xFA` (250). La variable est
donc **relue par une autre fonction** avant la boucle, ou la boucle n'est pas le
chemin utilisé par ce firmware.

Le fait mesuré, lui, est stable et ne dépend d'aucune interprétation :

- **11 threads existent**, tous créés par le loader (noms `timer`, `execcpu`,
  `idle0-3`, `root`) ;
- **aucune tâche applicative** (`TSK_UILIB`, `TSK_LCDEVF`, etc.) n'a de thread ;
- la boucle de création applicative `0x1151360` **n'est jamais exécutée** ;
- par conséquent aucun thread n'attend `0x400`, et aucun ne le poste.

## Bilan de la piste 2

La documentation publique ne contient pas la séquence d'amorçage X-Pro3
(`fffw` ne publie ni les masques d'événements ni les sous-types d'attente, et
n'a pas de port `xpro3`). Le désassemblage a en revanche établi le point d'arrêt
précis : **le firmware n'exécute jamais le code qui crée ses tâches
applicatives**.

C'est cohérent avec un état d'amorçage incomplet côté loader : le passage de
relais a lieu (`[0xD20008] = 1`), `main()` s'exécute, mais l'appel à la boucle de
création `0x1151360` n'est jamais fait.

## Piste résiduelle, une seule

Trouver l'appelant de `0x1151360` et la condition qui l'empêche : les trois
appelants connus de `0x4C1E0` sont `0x114F948`, `0x11513D4`, `0x1151448`. Les deux
derniers appartiennent à `0x1151360`, le premier à `0x114F798` (enregistrement de
`TSK_ROOT`). Il reste donc à identifier qui devrait appeler `0x1151360` — et
pourquoi il ne le fait pas.
