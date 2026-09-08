//! Experiments on top of the baseline. Nothing here is the baseline.
//!
//! `policy.rs` holds the rule as measured and committed; this module holds
//! attempts to beat it. The split is deliberate: a tuned variant that wins gets
//! promoted by changing `Tuning::default`, and one that loses gets written down
//! in `docs/RESULTS.md` and left here, because a negative result nobody
//! recorded gets re-run by the next person.
//!
//! Everything is measured paired, against the baseline, on the same seeds. The
//! project has been burned once by an unpaired eight-seed result that did not
//! reproduce, and the interval on a difference is much tighter than the
//! interval on either side of it.

use rand::{Rng, SeedableRng};
use rand_pcg::Pcg64Mcg;

use crate::instance::{Instance, NONE};
use crate::policy::{Baseline, Policy, Tuning};
use crate::sim::{Action, Sim, State};

/// Policy rollout over the baseline: take each candidate move, let the
/// baseline finish the job, and play whichever led somewhere best.
///
/// This is one step of policy iteration, so in expectation it is at least as
/// good as its base - but `docs/RESULTS.md` records three ways this project
/// got it wrong before, and all three are designed against here:
///
/// - **A weakened base caps it.** The base is the committed baseline, untuned.
/// - **A blind future collapses it.** With unread boards empty, no new work
///   ever appears, every candidate scores alike and rollout returns its base.
///   Futures come from [`Sim::imagining`], which redraws unread boards from
///   their true pools - the same draw the environment makes.
/// - **One future is worse than none.** It chases whichever board drew the
///   luckiest hand. Several futures, and *the same* futures scoring every
///   candidate, so the comparison carries no sampling noise of its own.
///
/// Candidates are every take and every journey off the boat, plus whatever the
/// base would have done. Sailing somewhere the base did not choose is left out:
/// it is twenty-odd actions that are nearly always wrong, and they cost more
/// than they have ever been worth.
pub struct Rollout {
    base: Baseline,
    futures: usize,
    /// Ticks to look ahead. Every candidate is scored to the same *absolute*
    /// clock, not for the same number of steps - actions have durations, and
    /// comparing a 5-tick take against a 700-tick sail over equal step counts
    /// would be comparing different amounts of time.
    horizon: i64,
    /// Score every candidate on this many futures first, keep the best half,
    /// and only they pay for the rest.
    heat: usize,
}

impl Rollout {
    pub fn new(inst: &Instance) -> Rollout {
        Rollout::with(inst, 8, 1_800, 4)
    }

    pub fn with(inst: &Instance, futures: usize, horizon: i64, heat: usize) -> Rollout {
        Rollout {
            base: Baseline::new(inst),
            futures,
            horizon,
            heat,
        }
    }

    /// Moves worth considering: what the base would do, plus the decisions it
    /// makes myopically - what to accept, and which board to go and read.
    ///
    /// Deliberately not every legal action. Sailing somewhere the base did not
    /// choose is twenty-odd candidates that are nearly always wrong, and
    /// chartering to a board already read this epoch tells us nothing we do not
    /// know. Both were in the first version and both cost more than they paid.
    fn candidates(&mut self, sim: &Sim, state: &State) -> Vec<Action> {
        let base = self.base.act(sim, state);
        let mut out = vec![base];
        for action in sim.legal(state) {
            let keep = match action {
                Action::Take { .. } | Action::Recall => true,
                Action::Charter(p) => !state.has_seen(p) && sim.inst.has_board[p],
                Action::Sail(_) => false,
            };
            if keep && action != base {
                out.push(action);
            }
        }
        out
    }

    /// Total XP from taking `action` now and letting the base finish, in one
    /// already-sampled world. Every candidate is scored to the same *absolute*
    /// clock - actions have durations, and judging a 5-tick take against a
    /// 700-tick sail over equal step counts compares different amounts of time.
    fn value(&self, world: &Sim, state: &State, action: Action, until: i64) -> f64 {
        let mut here = world.step(state, action).state;
        let mut base = Baseline::new(world.inst);
        while here.ticks < until {
            let next = base.act(world, &here);
            here = world.step(&here, next).state;
        }
        (here.xp - state.xp) as f64
    }

    fn mean_value(&self, worlds: &[Sim], state: &State, action: Action, until: i64) -> f64 {
        worlds
            .iter()
            .map(|w| {
                // the seed names later draws, so the future stays imagined past
                // a reroll rather than reverting to what really happens
                let start = State {
                    seed: w.imagined_seed(),
                    ..*state
                };
                self.value(w, &start, action, until)
            })
            .sum::<f64>()
            / worlds.len() as f64
    }
}

impl Policy for Rollout {
    fn act(&mut self, sim: &Sim, state: &State) -> Action {
        let moves = self.candidates(sim, state);
        if moves.len() == 1 {
            return moves[0];
        }

        // The worlds are built once per decision and shared by every candidate.
        // That is what makes the comparison carry no sampling noise of its own -
        // and, since a draw costs more than a rollout, most of the speed.
        let mut rng =
            Pcg64Mcg::seed_from_u64(state.seed ^ (state.ticks as u64).wrapping_mul(0x9E37_79B9));
        let worlds: Vec<Sim> = (0..self.futures)
            .map(|_| Sim::imagining(sim.inst, state, rng.random()))
            .collect();
        let until = state.ticks + self.horizon;

        let mut pool: Vec<Action> = moves.clone();
        if pool.len() > 3 && self.heat < self.futures {
            let mut heated: Vec<(f64, Action)> = pool
                .iter()
                .map(|&a| (self.mean_value(&worlds[..self.heat], state, a, until), a))
                .collect();
            heated.sort_by(|a, b| b.0.total_cmp(&a.0));
            heated.truncate((pool.len() / 2).max(3));
            pool = heated.into_iter().map(|(_, a)| a).collect();
            if !pool.contains(&moves[0]) {
                pool.push(moves[0]); // the base always gets a full hearing
            }
        }

        // The base's own move is the incumbent and only loses to a strict
        // improvement. Without this, candidates that all converge back to base
        // behaviour score alike, the argmax picks whichever noise favoured, and
        // rollout wanders - which is exactly what the first version did.
        let base_value = self.mean_value(&worlds, state, moves[0], until);
        let mut best = (base_value, moves[0]);
        for &action in &pool {
            if action == moves[0] {
                continue;
            }
            let value = self.mean_value(&worlds, state, action, until);
            if value > best.0 {
                best = (value, action);
            }
        }
        best.1
    }
}

/// A named policy, built fresh for each seed so one carrying state between
/// steps gets a clean one every time.
pub type Variant = (String, Box<dyn Fn(&Instance) -> Box<dyn Policy> + Sync>);

/// The variants under test. The baseline is first and every other row is
/// reported as a difference from it, on the same seeds.
pub fn variants(rho: f64) -> Vec<Variant> {
    let mut out: Vec<Variant> = Vec::new();
    out.push((
        "baseline".into(),
        Box::new(|i: &Instance| Box::new(Baseline::new(i)) as Box<dyn Policy>),
    ));
    out.push((
        "exact routing".into(),
        Box::new(|i: &Instance| {
            Box::new(Baseline::tuned(
                i,
                Tuning {
                    exact_route: true,
                    ..Default::default()
                },
            )) as Box<dyn Policy>
        }),
    ));
    out.push((
        format!("rho = {rho:.0}"),
        Box::new(move |i: &Instance| {
            Box::new(Baseline::tuned(
                i,
                Tuning {
                    rho: Some(rho),
                    ..Default::default()
                },
            )) as Box<dyn Policy>
        }),
    ));
    out.push((
        "rho + exact".to_string(),
        Box::new(move |i: &Instance| {
            Box::new(Baseline::tuned(
                i,
                Tuning {
                    rho: Some(rho),
                    exact_route: true,
                },
            )) as Box<dyn Policy>
        }),
    ));
    for (futures, horizon) in [(8usize, 1_800i64), (16, 1_800), (8, 3_600), (16, 3_600)] {
        out.push((
            format!("rollout {futures}x{horizon}"),
            Box::new(move |i: &Instance| {
                Box::new(Rollout::with(i, futures, horizon, futures / 2)) as Box<dyn Policy>
            }),
        ));
    }
    out
}

/// A port with a board that cannot be reached without the boat, for reference.
pub fn unreachable_boards(inst: &Instance) -> Vec<&str> {
    (0..inst.n_ports)
        .filter(|&p| inst.has_board[p] && inst.travel[p] == NONE)
        .map(|p| inst.port_names[p].as_str())
        .collect()
}
