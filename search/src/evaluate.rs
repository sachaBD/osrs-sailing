//! Run a policy against the simulator and report XP per hour.
//!
//! Absolute numbers mean little while half of `tables/params.tsv` is guessed,
//! so what this reports is a comparison and an interval. The interval is the
//! point: `docs/RESULTS.md` records a headline result that did not survive
//! being rerun, and the reason it did not was eight seeds where thirty were
//! needed.
//!
//! Seeds are independent, so they go out to `rayon`. Each thread builds its
//! own `Sim` over the one shared `Instance`, which is why `Sim` holds its draw
//! memo behind a `RefCell` and is deliberately not `Sync`.

use rayon::prelude::*;

use crate::instance::Instance;
use crate::policy::Policy;
use crate::route::TICK;
use crate::sim::Sim;
use crate::sim::State;

/// About 3.3 hours of play, the horizon the Python harness used.
pub const HORIZON: i64 = 20_000;
pub const SEEDS: u64 = 30;

#[derive(Debug, Clone, Copy)]
pub struct Score {
    pub mean: f64,
    /// Half-width of the 95% interval over the seeds.
    pub error: f64,
    pub seeds: u64,
}

impl Score {
    pub(crate) fn of(rates: &[f64]) -> Score {
        let n = rates.len() as f64;
        let mean = rates.iter().sum::<f64>() / n;
        let var = rates.iter().map(|r| (r - mean).powi(2)).sum::<f64>() / (n - 1.0);
        Score {
            mean,
            error: 1.96 * (var / n).sqrt(),
            seeds: rates.len() as u64,
        }
    }
}

/// Mean XP/hr over `seeds` independent runs, with the policy rebuilt for each
/// so that one carrying state between steps gets a clean one every time.
pub fn measure<P, F>(inst: &Instance, make: F, seeds: u64, horizon: i64, start: usize) -> Score
where
    F: Fn(&Instance) -> P + Sync,
    P: Policy,
{
    let rates: Vec<f64> = (0..seeds)
        .into_par_iter()
        .map(|seed| {
            let sim = Sim::new(inst);
            let mut policy = make(inst);
            let mut act = |s: &Sim, st: &_| policy.act(s, st);
            let state = sim.run(sim.reset(seed, start), &mut act, horizon);
            state.xp as f64 / state.ticks as f64 * 3600.0 / TICK
        })
        .collect();
    Score::of(&rates)
}

/// Every seed's rate, kept rather than summarised, so two policies can be
/// compared on the same seeds afterwards.
pub fn rates<P, F>(inst: &Instance, make: F, seeds: u64, horizon: i64, start: usize) -> Vec<f64>
where
    F: Fn(&Instance) -> P + Sync,
    P: Policy,
{
    (0..seeds)
        .into_par_iter()
        .map(|seed| {
            let sim = Sim::new(inst);
            let mut policy = make(inst);
            let mut state = sim.reset(seed, start);
            while state.ticks < horizon {
                let action = policy.act(&sim, &state);
                state = sim.step(&state, action).state;
            }
            state.xp as f64 / state.ticks as f64 * 3600.0 / TICK
        })
        .collect()
}

/// The same, for a policy behind a `Box<dyn Policy>`, which is what the lab's
/// table of variants hands over.
pub fn rates_dyn(
    inst: &Instance,
    make: &(dyn Fn(&Instance) -> Box<dyn Policy> + Sync),
    seeds: u64,
    horizon: i64,
    start: usize,
) -> Vec<f64> {
    (0..seeds)
        .into_par_iter()
        .map(|seed| {
            let sim = Sim::new(inst);
            let mut policy = make(inst);
            let mut state: State = sim.reset(seed, start);
            while state.ticks < horizon {
                let action = policy.act(&sim, &state);
                state = sim.step(&state, action).state;
            }
            state.xp as f64 / state.ticks as f64 * 3600.0 / TICK
        })
        .collect()
}

/// The difference between two policies on the *same* seeds.
///
/// This is the number to read, not the gap between two independent means. Seed
/// variance here is large and shared - a lucky draw is lucky for everyone - so
/// pairing can tighten the interval on the difference far below the interval on
/// either policy. When it does not, that is worth knowing too: it says the
/// policies are diverging into genuinely different episodes rather than playing
/// the same one better or worse.
pub fn paired(mine: &[f64], theirs: &[f64]) -> Score {
    assert_eq!(mine.len(), theirs.len(), "paired needs the same seeds");
    let diffs: Vec<f64> = mine.iter().zip(theirs).map(|(a, b)| a - b).collect();
    Score::of(&diffs)
}

impl Score {
    pub fn summarise(rates: &[f64]) -> Score {
        Score::of(rates)
    }
}
