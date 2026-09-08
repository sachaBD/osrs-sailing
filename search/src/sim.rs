//! The port-task SMDP: `docs/PROBLEM.md`, made to run.
//!
//! This is a second implementation of `porttasks/routing/problem/sim.py`, and
//! that is a real cost, paid deliberately. Python stays the definition and the
//! oracle; a differential test walks both over random legal play and asserts
//! they agree, step for step. **If they ever disagree, Python is right.**
//!
//! What this end buys is the constant factor. A [`State`] is `Copy` and about
//! sixty bytes: branching is an assignment, and nothing is ever cloned,
//! undone, or reference-counted. That is the whole reason the search layer is
//! here rather than there.
//!
//! The one thing a state does not hold is what the boards really contain. It
//! does not have to - a draw is a pure function of `(seed, epoch)`, so
//! [`Sim::true_offers`] rebuilds any epoch from two integers. What a *policy*
//! may read is [`Sim::observed`], which hides every board the player has not
//! stood at since the last reroll. That masking is the whole partial
//! observability of the problem.

use std::cell::RefCell;

use rand::{Rng, SeedableRng};
use rand_pcg::Pcg64Mcg;

use crate::instance::{Instance, NONE};

/// The largest task capacity the game grants, at level 84. Slot arrays are
/// this long whatever the level, so a `State` is one fixed-size `Copy` value.
pub const MAX_HELD: usize = 5;

/// The most offers a board shows. `courier_per_board` is 5 and comes from
/// `tables/params.tsv`; this is only the array bound.
pub const MAX_OFFERS: usize = 8;

/// One action. `Take` is the only compound one: `victim` names the held task
/// it displaces, or `None` to fill a free slot. Accepting and abandoning are
/// deliberately not separate actions - see PROBLEM.md S4.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Action {
    Take { task: i32, victim: Option<i32> },
    Sail(usize),
    Charter(usize),
    Recall,
}

/// Everything that changes. Slot arrays are [`MAX_HELD`] long and
/// [`NONE`]-padded, so this is `Copy` and cloning it is an assignment.
///
/// `seed` and `epoch` together name the current draw of every board, so the
/// hidden half of the world is reconstructible rather than carried.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct State {
    pub port_player: usize,
    pub port_boat: usize,
    pub held: [i32; MAX_HELD],
    pub loaded: [bool; MAX_HELD],
    /// One bit per port, set where the board has been read this epoch.
    /// Cleared entirely by a reroll. 30 ports at most, so a `u32` covers it.
    pub seen: u32,
    pub seed: u64,
    pub epoch: u32,
    /// `k`, completions toward the next reroll.
    pub completions: u32,
    pub xp: i64,
    pub ticks: i64,
}

impl State {
    #[inline]
    pub fn free_slots(&self, capacity: usize) -> usize {
        self.held[..capacity].iter().filter(|&&t| t == NONE).count()
    }

    /// The held task ids, without the padding.
    #[inline]
    pub fn tasks(&self, capacity: usize) -> impl Iterator<Item = i32> + '_ {
        self.held[..capacity].iter().copied().filter(|&t| t != NONE)
    }

    #[inline]
    pub fn holds(&self, capacity: usize, task: i32) -> bool {
        self.held[..capacity].contains(&task)
    }

    #[inline]
    pub fn has_seen(&self, port: usize) -> bool {
        self.seen & (1 << port) != 0
    }
}

/// What one action did: what it paid for, and what it earned.
#[derive(Debug, Clone, Copy)]
pub struct Step {
    pub state: State,
    pub xp: i64,
    pub ticks: i64,
}

/// What every board holds this epoch, flat and [`NONE`]-padded.
#[derive(Debug, Clone)]
pub struct Offers {
    stride: usize,
    flat: Vec<i32>,
}

impl Offers {
    #[inline]
    pub fn at(&self, port: usize) -> &[i32] {
        &self.flat[port * self.stride..(port + 1) * self.stride]
    }
}

/// The dynamics of one [`Instance`].
///
/// Holds a one-entry memo of the current epoch's draw, which is a pure
/// function of `(seed, epoch)` and so changes nothing observable. One epoch is
/// live at a time, so one entry is all it ever needs.
///
/// Not `Sync`, on purpose: give every thread its own `Sim` over the shared
/// `&Instance` rather than sharing the memo.
pub struct Sim<'a> {
    pub inst: &'a Instance,
    draw: RefCell<Option<((u64, u32), Offers)>>,
    /// A believed world, for planning rather than for playing: the offers to
    /// report for one epoch instead of the true draw. See [`Sim::imagining`].
    belief: Option<(u32, Offers)>,
    /// The seed the imagined world's later epochs draw from.
    imagined: u64,
}

impl<'a> Sim<'a> {
    pub fn new(inst: &'a Instance) -> Sim<'a> {
        assert!(
            inst.capacity <= MAX_HELD,
            "capacity {} exceeds MAX_HELD {MAX_HELD}",
            inst.capacity
        );
        assert!(
            inst.params.courier_per_board <= MAX_OFFERS,
            "courier_per_board {} exceeds MAX_OFFERS {MAX_OFFERS}",
            inst.params.courier_per_board
        );
        assert!(inst.n_ports <= 32, "the `seen` bitmask holds 32 ports");
        Sim {
            inst,
            draw: RefCell::new(None),
            belief: None,
            imagined: 0,
        }
    }

    /// A sim that plays out one guess at the world instead of the real one.
    ///
    /// Boards `state` has already read keep their true contents; every unread
    /// board is redrawn from its own pool. That is exactly the draw the
    /// environment makes at a reroll, so a planner sampling futures and the
    /// simulator generating them cannot disagree about the prior.
    ///
    /// Only the current epoch is imagined. Past it the guess is worthless
    /// anyway - a reroll replaces every board - so later epochs fall back to
    /// the ordinary draw under `sample` as the seed, which is what makes one
    /// sampled future differ from another.
    pub fn imagining(inst: &'a Instance, state: &State, sample: u64) -> Sim<'a> {
        let mut sim = Sim::new(inst);
        let k = inst.params.courier_per_board;
        let mut guess = sim.true_offers(state.seed, state.epoch);
        let mut rng = Pcg64Mcg::seed_from_u64(mix(sample, state.epoch));
        let mut bag: Vec<i32> = Vec::new();
        for port in 0..inst.n_ports {
            if !inst.has_board[port] || state.has_seen(port) {
                continue;
            }
            bag.clear();
            bag.extend_from_slice(inst.board_pool(port));
            let n = bag.len();
            for i in 0..k {
                bag.swap(i, i + rng.random_range(0..n - i));
            }
            guess.flat[port * k..port * k + k].copy_from_slice(&bag[..k]);
        }
        sim.belief = Some((state.epoch, guess));
        sim.imagined = sample;
        sim
    }

    /// The seed an imagined world's later epochs draw from, so a planner can
    /// keep the future imagined across a reroll instead of reverting to the
    /// real one - which would be reading the answer sheet.
    pub fn imagined_seed(&self) -> u64 {
        self.imagined
    }

    // ---- the hidden world ------------------------------------------------

    /// What every board really holds this epoch.
    ///
    /// Not for policies: this is the answer sheet. Read [`Sim::observed`].
    ///
    /// The draw is defined *here* rather than in Python. numpy's generator is
    /// not reproducible outside numpy, and one RNG in the project beats two
    /// that nearly agree, so this end owns it and the differential test feeds
    /// both sides the same offers rather than the same seed.
    pub fn true_offers(&self, seed: u64, epoch: u32) -> Offers {
        if let Some((believed, offers)) = &self.belief {
            if *believed == epoch {
                return offers.clone();
            }
        }
        if let Some((key, offers)) = self.draw.borrow().as_ref() {
            if *key == (seed, epoch) {
                return offers.clone();
            }
        }
        let offers = self.roll(seed, epoch);
        *self.draw.borrow_mut() = Some(((seed, epoch), offers.clone()));
        offers
    }

    fn roll(&self, seed: u64, epoch: u32) -> Offers {
        let k = self.inst.params.courier_per_board;
        let mut rng = Pcg64Mcg::seed_from_u64(mix(seed, epoch));
        let mut flat = vec![NONE; self.inst.n_ports * k];
        let mut bag: Vec<i32> = Vec::new();
        for port in 0..self.inst.n_ports {
            if !self.inst.has_board[port] {
                continue;
            }
            // a partial Fisher-Yates: k draws without replacement from the pool
            bag.clear();
            bag.extend_from_slice(self.inst.board_pool(port));
            let n = bag.len();
            for i in 0..k {
                bag.swap(i, i + rng.random_range(0..n - i));
            }
            flat[port * k..port * k + k].copy_from_slice(&bag[..k]);
        }
        Offers { stride: k, flat }
    }

    /// The true offers where the board has been read, [`NONE`] everywhere else.
    /// This is all a policy may look at.
    pub fn observed(&self, state: &State) -> Offers {
        let mut offers = self.true_offers(state.seed, state.epoch);
        let k = offers.stride;
        for port in 0..self.inst.n_ports {
            if !state.has_seen(port) {
                offers.flat[port * k..port * k + k].fill(NONE);
            }
        }
        offers
    }

    /// What one board shows, or nothing if it has not been read this epoch.
    pub fn offers_at(&self, state: &State, port: usize) -> Vec<i32> {
        if !state.has_seen(port) {
            return Vec::new();
        }
        self.true_offers(state.seed, state.epoch)
            .at(port)
            .iter()
            .copied()
            .filter(|&t| t != NONE)
            .collect()
    }

    // ---- dynamics --------------------------------------------------------

    pub fn reset(&self, seed: u64, start_port: usize) -> State {
        let state = State {
            port_player: start_port,
            port_boat: start_port,
            held: [NONE; MAX_HELD],
            loaded: [false; MAX_HELD],
            seen: 0,
            seed,
            epoch: 0,
            completions: 0,
            xp: 0,
            ticks: 0,
        };
        self.settle(state).0
    }

    /// Load, deliver, reroll and reveal - in that order.
    ///
    /// Not an action: it runs on arrival and after every take, and costs
    /// nothing. See PROBLEM.md S5.
    fn settle(&self, mut state: State) -> (State, i64) {
        let inst = self.inst;
        let port = state.port_player;
        let mut gained = 0;

        if state.port_boat == port {
            for slot in 0..inst.capacity {
                let task = state.held[slot];
                if task != NONE && inst.task_origin[task as usize] == port as i32 {
                    state.loaded[slot] = true;
                }
            }
            for slot in 0..inst.capacity {
                let task = state.held[slot];
                if task == NONE
                    || !state.loaded[slot]
                    || inst.task_dest[task as usize] != port as i32
                {
                    continue;
                }
                gained += inst.task_xp[task as usize] as i64;
                state.held[slot] = NONE;
                state.loaded[slot] = false;
                // the task stays in its board's pool and may be drawn again;
                // repeating one short profitable route is legal play
                state.completions += 1;
                if state.completions >= inst.params.reroll_completions {
                    state.epoch += 1;
                    state.completions = 0;
                    state.seen = 0; // every board redrawn; all observations stale
                }
            }
        }

        // reveal last, so a delivery that triggered a reroll shows the new board
        if inst.has_board[port] {
            state.seen |= 1 << port;
        }
        state.xp += gained;
        (state, gained)
    }

    /// Every action allowed here, appended to `out`. Never empty: charter
    /// always exists, so the agent can never be stranded.
    pub fn legal_into(&self, state: &State, out: &mut Vec<Action>) {
        let inst = self.inst;
        let here = state.port_player;
        out.clear();

        if state.has_seen(here) {
            let offers = self.true_offers(state.seed, state.epoch);
            for &task in offers.at(here) {
                if task == NONE
                    || !inst.task_eligible[task as usize]
                    || state.holds(inst.capacity, task)
                {
                    continue;
                }
                if state.free_slots(inst.capacity) > 0 {
                    out.push(Action::Take { task, victim: None });
                }
                for victim in state.tasks(inst.capacity) {
                    out.push(Action::Take {
                        task,
                        victim: Some(victim),
                    });
                }
            }
        }

        if state.port_boat == here {
            out.extend((0..inst.n_ports).filter(|&p| p != here).map(Action::Sail));
        }
        out.extend(
            (0..inst.n_ports)
                .filter(|&p| p != here && inst.travel[p] != NONE)
                .map(Action::Charter),
        );
        if inst.recall[here] != NONE && state.port_boat != here {
            out.push(Action::Recall);
        }
    }

    pub fn legal(&self, state: &State) -> Vec<Action> {
        let mut out = Vec::new();
        self.legal_into(state, &mut out);
        out
    }

    /// Apply an action. Only safe with one [`Sim::legal`] returned for this
    /// same state; anything else corrupts the state silently.
    pub fn step(&self, state: &State, action: Action) -> Step {
        let inst = self.inst;
        let mut moved = *state;
        let cost: i64 = match action {
            Action::Take { task, victim } => {
                let slot = match victim {
                    None => moved.held[..inst.capacity]
                        .iter()
                        .position(|&t| t == NONE)
                        .expect("Take with no victim needs a free slot"),
                    Some(v) => moved.held[..inst.capacity]
                        .iter()
                        .position(|&t| t == v)
                        .expect("the displaced task must be held"),
                };
                moved.held[slot] = task;
                moved.loaded[slot] = false;
                (inst.params.t_board
                    + if victim.is_none() {
                        0
                    } else {
                        inst.params.t_drop
                    }) as i64
            }
            Action::Sail(to) => {
                let cost = inst.sail(moved.port_player, to) as i64;
                moved.port_player = to;
                moved.port_boat = to;
                cost
            }
            Action::Charter(to) => {
                moved.port_player = to; // the boat stays behind
                inst.travel[to] as i64
            }
            Action::Recall => {
                moved.port_boat = moved.port_player;
                moved.loaded = [false; MAX_HELD]; // cargo destroyed, tasks survive
                inst.recall[moved.port_player] as i64
            }
        };
        moved.ticks += cost;
        let (state, xp) = self.settle(moved);
        Step {
            state,
            xp,
            ticks: cost,
        }
    }

    /// Drive a policy until `horizon` ticks have passed.
    pub fn run<P>(&self, mut state: State, policy: &mut P, horizon: i64) -> State
    where
        P: FnMut(&Sim<'a>, &State) -> Action,
    {
        while state.ticks < horizon {
            let action = policy(self, &state);
            state = self.step(&state, action).state;
        }
        state
    }
}

/// A seed and an epoch into one well-mixed word, so consecutive epochs do not
/// draw visibly related boards. SplitMix64's finaliser.
fn mix(seed: u64, epoch: u32) -> u64 {
    let mut z = seed
        .wrapping_mul(0x9E37_79B9_7F4A_7C15)
        .wrapping_add(epoch as u64 ^ 0xD1B5_4A32_D192_ED03);
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^ (z >> 31)
}
