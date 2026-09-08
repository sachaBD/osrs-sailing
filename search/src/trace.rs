//! A recording of random legal play, for Python to check this crate against.
//!
//! There are two implementations of the dynamics and only one of them is the
//! definition. This module writes down everything the Rust one did - the offers
//! it drew, the actions it thought were legal, and the state after each one -
//! in a form `tests/routing/test_rust_parity.py` can replay through `sim.py`.
//!
//! Both halves see the same offers because the trace carries them: the draw is
//! defined in Rust (numpy's generator does not exist outside numpy), so the
//! test primes Python's cache from here rather than trying to agree on a seed.

use serde::Serialize;

use crate::instance::NONE;
use crate::sim::{Action, Sim, State};

/// Python's `sim.TAKE, SAIL, CHARTER, RECALL`.
fn encode(action: Action) -> (i32, i32, i32) {
    match action {
        Action::Take { task, victim } => (0, task, victim.unwrap_or(NONE)),
        Action::Sail(p) => (1, p as i32, NONE),
        Action::Charter(p) => (2, p as i32, NONE),
        Action::Recall => (3, NONE, NONE),
    }
}

#[derive(Serialize)]
struct WireState {
    port_player: usize,
    port_boat: usize,
    held: Vec<i32>,
    loaded: Vec<bool>,
    seen: Vec<bool>,
    epoch: u32,
    completions: u32,
    xp: i64,
    ticks: i64,
}

#[derive(Serialize)]
struct Record {
    /// Every action Rust believes is legal here, as Python's `(kind, arg, victim)`.
    legal: Vec<(i32, i32, i32)>,
    action: (i32, i32, i32),
    xp: i64,
    ticks: i64,
    after: WireState,
}

#[derive(Serialize)]
pub struct Trace {
    level: u32,
    seed: u64,
    start_port: usize,
    /// The draw for each epoch the run reached, indexed by epoch: `(P, K)`.
    offers: Vec<Vec<Vec<i32>>>,
    start: WireState,
    steps: Vec<Record>,
}

fn wire(sim: &Sim, state: &State) -> WireState {
    WireState {
        port_player: state.port_player,
        port_boat: state.port_boat,
        held: state.held[..sim.inst.capacity].to_vec(),
        loaded: state.loaded[..sim.inst.capacity].to_vec(),
        seen: (0..sim.inst.n_ports).map(|p| state.has_seen(p)).collect(),
        epoch: state.epoch,
        completions: state.completions,
        xp: state.xp,
        ticks: state.ticks,
    }
}

fn offers_for(sim: &Sim, seed: u64, epoch: u32) -> Vec<Vec<i32>> {
    let drawn = sim.true_offers(seed, epoch);
    (0..sim.inst.n_ports)
        .map(|p| drawn.at(p).to_vec())
        .collect()
}

/// Play `steps` uniformly random legal actions and record every one.
///
/// Random play is the point: it walks into swaps, recalls and rerolls that a
/// sensible policy would never try, which is exactly where two implementations
/// drift apart.
pub fn record(sim: &Sim, seed: u64, start_port: usize, steps: usize) -> Trace {
    use rand::{Rng, SeedableRng};
    let mut rng = rand_pcg::Pcg64Mcg::seed_from_u64(seed ^ 0x5EED_7ACE);

    let mut state = sim.reset(seed, start_port);
    let start = wire(sim, &state);
    let mut records = Vec::with_capacity(steps);
    let mut epochs = state.epoch;
    let mut legal = Vec::new();

    for _ in 0..steps {
        sim.legal_into(&state, &mut legal);
        let action = legal[rng.random_range(0..legal.len())];
        let step = sim.step(&state, action);
        records.push(Record {
            legal: legal.iter().map(|&a| encode(a)).collect(),
            action: encode(action),
            xp: step.xp,
            ticks: step.ticks,
            after: wire(sim, &step.state),
        });
        state = step.state;
        epochs = epochs.max(state.epoch);
    }

    Trace {
        level: sim.inst.level,
        seed,
        start_port,
        offers: (0..=epochs).map(|e| offers_for(sim, seed, e)).collect(),
        start,
        steps: records,
    }
}
