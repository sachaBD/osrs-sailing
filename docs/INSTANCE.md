# The level-30 instance

A deliberately small slice of the problem in `PROBLEM.md`, to build and verify
the approach on before pointing it at the whole map. Everything here is
derived from `../data/port_distances.json` and `../model/params.tsv`; if either changes, so do
these numbers.

    sail_ticks(a, b) = port_distances[a][b] / sail_speed + t_dock
                     = tiles / 2 + 10

Ten ports, nine boards, 98 eligible tasks, **capacity 3**, four courier tasks
per board. No quest gating and no unknown-XP tasks - both live above level 30 -
so two whole classes of special case are absent.


## Ports

| port | dock | board | shipwright | charter |
| --- | --- | --- | --- | --- |
| Port Sarim | 1 | yes | yes | yes |
| The Pandemonium | 1 | yes | yes | yes (quest) |
| Hosidius | 5 | - | - | - |
| Land's End | 5 | yes | yes | yes |
| Musa Point | 10 | yes | yes | yes |
| Port Piscarilius | 15 | yes | yes | yes |
| Catherby | 20 | yes | yes | yes |
| Brimhaven | 25 | yes | yes | yes |
| Ardougne | 28 | yes | - | - |
| Port Khazard | 30 | yes | yes | yes |

Hosidius has no board and touches only 5 tasks; it is nearly inert at this
level. Ardougne is the only board without a shipwright, so it is the one place
you can read offers but not recall the boat.


## Sail time, ticks (1 tick = 0.6 s)

|  | Ard | Bri | Cat | Hos | LsE | Mus | PKh | PPi | PSa | Pan |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **Ardougne** | - | 61 | 116 | 786 | 858 | 172 | 59 | 843 | 255 | 269 |
| **Brimhaven** | 61 | - | 106 | 805 | 876 | 145 | 77 | 860 | 228 | 241 |
| **Catherby** | 116 | 106 | - | 871 | 943 | 179 | 144 | 927 | 261 | 275 |
| **Hosidius** | 786 | 805 | 871 | - | 123 | 884 | 738 | 198 | 915 | 831 |
| **Land's End** | 858 | 876 | 943 | 123 | - | 955 | 809 | 311 | 987 | 902 |
| **Musa Point** | 172 | 145 | 179 | 884 | 955 | - | 189 | 941 | 93 | 106 |
| **Port Khazard** | 59 | 77 | 144 | 738 | 809 | 189 | - | 794 | 272 | 286 |
| **Port Piscarilius** | 843 | 860 | 927 | 198 | 311 | 941 | 794 | - | 973 | 889 |
| **Port Sarim** | 255 | 228 | 261 | 915 | 987 | 93 | 272 | 973 | - | 115 |
| **The Pandemonium** | 269 | 241 | 275 | 831 | 902 | 106 | 286 | 889 | 115 | - |

Two clusters, and the gap between them is the dominant feature of the map:

- **Mainland** - Ardougne, Brimhaven, Catherby, Musa Point, Port Khazard,
  Port Sarim, The Pandemonium. Everything within 59-286 ticks (35 s - 3 min).
- **Zeah** - Hosidius, Land's End, Port Piscarilius. 738-987 ticks (7-10 min)
  from the mainland.

**78 of the 98 tasks stay inside the mainland cluster.** Whether an optimal
agent ever crosses to Zeah is an open question and a good first thing to ask
the solver, rather than something to assume either way.


## Tasks

98 eligible, 57 outbound and 41 inbound, spread over 54 distinct
origin-destination legs. XP runs 69 to 2,068, median 277.

The two directions have almost the same rate but completely different shape:

| | n | median cost from the board | median rate | ends |
| --- | --- | --- | --- | --- |
| outbound (board = origin) | 57 | 179 ticks, one leg | 6,639 xp/hr | somewhere new |
| inbound (board = destination) | 41 | 345 ticks, round trip | 6,994 xp/hr | back at the board |

Outbound tasks compose - a chain A -> B -> C does three tasks in three legs.
Inbound tasks are self-contained round trips. With capacity 3 the interesting
plays overlap them, so an inbound task's return leg carries somebody else's
cargo. A solver that does not batch will not find this.

**24 of the 54 legs have a task running the opposite way too**, so shuttle
patterns are structurally available. Catherby to Port Sarim has three tasks in
each direction.

Tasks touching each port: Port Sarim 31, Catherby 27, Musa Point 24, The
Pandemonium 23, Brimhaven 21, Port Khazard 20, Ardougne 19, Port Piscarilius
16, Land's End 10, Hosidius 5.


## Calibration anchors

Three numbers to bracket any result. A policy landing outside this band means
a bug, not a discovery.

| | xp/hr | what it is |
| --- | --- | --- |
| best single leg | ~19,100 | the best task's XP over its delivery leg alone, ignoring how you got to the origin. A hard ceiling no policy can average. |
| one task at a time | ~6,600-7,000 | median rate doing tasks singly from the board they are on. The floor a competent policy must beat. |
| median single leg | ~7,700 | the same ceiling calculation, taken at the median task. |

The wiki calls port tasks a "low to medium-intensity, medium xp/hr activity",
which is consistent with a real figure in the middle of that band.

The best *rate* task is 246 XP over a 77-tick leg (Brimhaven and Port Khazard,
both directions). The best *XP* task is 2,068. They are not the same task and
not close, so greedy-by-XP is wrong here - which is the point of using this
slice as a test: the selection problem is already non-trivial at toy scale.


## Health warning

`sail_speed = 2 tiles/tick` is an eyeball figure, and `t_dock`, `t_board`,
`t_drop`, `t_recall` are outright guesses (see `../model/params.tsv`). Absolute xp/hr
from this instance means very little. What it is for is **comparing policies**
and **verifying the approach**, both of which survive being wrong about the
constants as long as we check that the ranking is stable across a plausible
range of them.
