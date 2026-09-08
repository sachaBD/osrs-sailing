//! The rules-based baseline: the floor everything else is measured against.
//!
//! It is one rule, stated as a player would state it. Rank the work by what it
//! pays, go and look for the best of it, take it if it is there and move on if
//! it is not, and stop when nothing left on offer would make the trip better.
//!
//! ```text
//!   1. Rank tasks by XP per hour of their delivery leg. Charter to the best
//!      one's board. If it is on offer, accept it; if not, that board is now
//!      read, so move on to the next task on the list.
//!   2. From then on rank by delta: what accepting would do to the XP/hr of
//!      the whole held set, sequenced and priced as a route.
//!   3. Stop when the slots are full or nothing has a positive delta.
//!   4. Rejoin the boat and sail the route.
//!   5. Whenever a delivery frees a slot at a board, take what is worth taking
//!      there and then.
//! ```
//!
//! Two measures on purpose, and the first one is not the second one with an
//! empty hold. Step 1 ranks a task standalone, by its delivery leg alone, which
//! is what makes the inbound tasks - board at the destination - come out on top:
//! at level 67 the ten best tasks by that measure are all inbound, where by the
//! round trip from their board only three of the ten are. The first pick is
//! deliberately made on the optimistic measure.
//!
//! **A score has to price what the policy actually does.** Step 4 charters out
//! to the longest run's origin and recalls the boat there, so the outbound leg
//! is never sailed - and while the ranking still charged for it, a 106-tick
//! shuttle priced at 49,189 xp/hr and was then run at 98,377. Pricing each
//! candidate set from where its own boat would meet it was worth 18%, and it is
//! what lets step 3 refuse work: correctly priced, the rule sails on two of its
//! four slots rather than four.
//!
//! Three constraints come from the map rather than from the rule, and all three
//! live in `tables/transport.tsv`:
//!
//! - **A board we cannot reach without the boat cannot be scouted.** At level
//!   67 that is Ardougne, Ruins of Unkah and Void Knights' Outpost - everywhere
//!   else is a charter ship or a teleport. Their tasks are still delivered
//!   *to*; they are just never somewhere we go to look.
//! - **A recall needs a shipwright.** Scouting can end at Etceteria, Port Tyras
//!   or The Summer Shore, which have boards and no shipwright, so a route
//!   cannot start there: we charter on to a port that has one and recall.
//! - **Never leave the boat with cargo aboard.** Rejoining it means recalling
//!   it, and a recall destroys the cargo. Taking work is always safe; walking
//!   away from the boat is not.

use crate::instance::{Instance, NONE};
use crate::route::{self, Leg};
use crate::sim::{Action, Sim, State};

/// One decision at a time.
///
/// A policy may read `Sim::offers_at` and `Sim::observed`, which hide every
/// board the player has not stood at this epoch, and must never read
/// `Sim::true_offers`. That restraint is not enforced by the types; it is the
/// difference between a policy and a cheat, and `docs/RESULTS.md` records what
/// happened last time one of them cheated by accident.
pub trait Policy {
    fn act(&mut self, sim: &Sim, state: &State) -> Action;
}

pub struct Baseline {
    /// Boards we can reach without the boat, so the only ones worth ranking.
    scoutable: Vec<bool>,
    shipwrights: Vec<usize>,
}

impl Baseline {
    pub fn new(inst: &Instance) -> Baseline {
        Baseline {
            scoutable: (0..inst.n_ports)
                .map(|p| inst.has_board[p] && inst.travel[p] != NONE)
                .collect(),
            shipwrights: (0..inst.n_ports)
                .filter(|&p| inst.recall[p] != NONE)
                .collect(),
        }
    }
}

impl Policy for Baseline {
    fn act(&mut self, sim: &Sim, state: &State) -> Action {
        let inst = sim.inst;
        let here = state.port_player;
        let held = legs(inst, state);
        let free = state.free_slots(inst.capacity);
        // recalling the boat destroys whatever is aboard, so with cargo loaded
        // we may take work but must not walk away to look for it
        let dry = !state.loaded[..inst.capacity].iter().any(|&l| l);

        if free > 0 {
            if dry {
                // rank everything still worth going to get, wherever it is.
                // Standing at a board buys that board nothing: if the best
                // candidate is elsewhere we go there, which is the whole rule.
                if let Some((task, board)) = self.best(sim, state, &held, false) {
                    if board == here {
                        return Action::Take { task, victim: None };
                    }
                    return Action::Charter(board);
                }
            } else if let Some((task, _)) = self.best(sim, state, &held, true) {
                // cargo aboard: take what is under our feet and nothing further
                return Action::Take { task, victim: None };
            }
        }

        // Done looking: pick where the boat should meet us and call it there.
        //
        // This fires whether or not the boat is already underfoot, and that is
        // the point. A recall is a ten-tick teleport, so chartering out to the
        // far pickup and calling the boat to it costs twenty ticks and saves
        // the whole outbound leg - even when the boat is right here and sailing
        // it would have been legal. Only cargo already aboard stops us, because
        // a recall would destroy it.
        if dry && !held.is_empty() {
            let meet = self.rendezvous(inst, state, &held);
            if here != meet {
                return Action::Charter(meet);
            }
            if state.port_boat != here {
                return Action::Recall;
            }
        }

        // Cargo aboard and the boat elsewhere: nothing for it but to go back.
        if state.port_boat != here {
            if inst.recall[here] != NONE {
                return Action::Recall;
            }
            return Action::Charter(self.nearest_shipwright(inst, here));
        }

        // Sail the route.
        if let Some(port) = route::next_stop(inst, here, &held) {
            if port != here {
                return Action::Sail(port);
            }
        }

        // Nothing held and nothing worth taking anywhere - only reachable when
        // every board we can get to has been read and none of it is usable.
        self.wander(sim, state)
    }
}

impl Baseline {
    /// What the policy thought `task` was worth in this state, for `walk`.
    pub fn explain(&self, sim: &Sim, state: &State, task: i32) -> f64 {
        self.score(sim.inst, state, &legs(sim.inst, state), task)
    }

    /// Where to have the boat meet us: the origin of the longest run we hold.
    ///
    /// A recall is a teleport - it costs ten ticks wherever the boat is - so
    /// the leg you never sail is pure profit, and the leg worth never sailing
    /// is the longest one. Charter out to that pickup, call the boat to it,
    /// and the whole first run is cargo-laden instead of a deadhead out and a
    /// haul back.
    ///
    /// It has to be somewhere we can both reach without the boat and recall
    /// at, so a pickup with no charter or no shipwright is passed over for the
    /// next longest. The Summer Shore is exactly this case: scoutable, but no
    /// shipwright, so it is never the rendezvous.
    fn rendezvous(&self, inst: &Instance, state: &State, held: &[Leg]) -> usize {
        let mut runs: Vec<&Leg> = held.iter().filter(|l| !l.loaded).collect();
        runs.sort_by_key(|l| std::cmp::Reverse(inst.sail(l.origin, l.dest)));
        runs.iter()
            .map(|l| l.origin)
            .find(|&p| inst.recall[p] != NONE && (p == state.port_player || inst.travel[p] != NONE))
            .unwrap_or_else(|| self.recall_port(inst, state.port_player))
    }

    /// Where we would call the boat to from `from`: right here if this port has
    /// a shipwright, otherwise the nearest one that has.
    ///
    /// Standing on a shipwright and answering "somewhere else" is how the
    /// second oscillation in this policy happened: `nearest_shipwright` skips
    /// the port you are on, so Port Khazard's nearest was Brimhaven and
    /// Brimhaven's was Port Khazard, and one seed spent 92% of its episode
    /// chartering between the two. A rendezvous has to be a fixed point.
    fn recall_port(&self, inst: &Instance, from: usize) -> usize {
        if inst.recall[from] != NONE {
            from
        } else {
            self.nearest_shipwright(inst, from)
        }
    }

    fn nearest_shipwright(&self, inst: &Instance, from: usize) -> usize {
        *self
            .shipwrights
            .iter()
            .filter(|&&p| p != from)
            .min_by_key(|&&p| inst.sail(from, p))
            .expect("every instance has a shipwright to recall at")
    }

    /// Where a *candidate* set is priced from.
    ///
    /// Never from where the player is standing. Chartering moves the player and
    /// leaves the boat, so a score measured from the player changes with every
    /// hop, and a ranking that changes as you walk oscillates - this policy has
    /// had that bug twice.
    ///
    /// With a dry hold we are free to rendezvous, and the rendezvous rule will
    /// put the boat at the longest run's origin - so the outbound leg from
    /// wherever the boat happens to sit now is never sailed, and charging for
    /// it prices a leg the policy does not sail. Score and execution have to
    /// agree or the ranking is answering a different question.
    fn priced_from(&self, inst: &Instance, state: &State, legs: &[Leg]) -> usize {
        let dry = !state.loaded[..inst.capacity].iter().any(|&l| l);
        if !dry || legs.is_empty() {
            return state.port_boat;
        }
        let mut runs: Vec<&Leg> = legs.iter().filter(|l| !l.loaded).collect();
        runs.sort_by_key(|l| std::cmp::Reverse(inst.sail(l.origin, l.dest)));
        runs.iter()
            .map(|l| l.origin)
            // strictly no reference to where the player is standing: this is a
            // score, and a score that moves as you walk is the oscillation this
            // policy has already had twice
            .find(|&p| inst.recall[p] != NONE && inst.travel[p] != NONE)
            .unwrap_or(state.port_boat)
    }

    /// What accepting `task` would do to the XP/hr of the whole held set.
    ///
    /// Both sides are re-sequenced and re-priced, and each from its own
    /// rendezvous: adding a task can change where the boat should meet us, and
    /// pricing the two sets from one port would hide that.
    fn delta(&self, inst: &Instance, state: &State, held: &[Leg], task: i32) -> f64 {
        let mut with = [Leg {
            origin: 0,
            dest: 0,
            loaded: false,
            xp: 0,
        }; crate::sim::MAX_HELD];
        with[..held.len()].copy_from_slice(held);
        with[held.len()] = leg(inst, task, false);
        let with = &with[..held.len() + 1];
        // each set priced from where its own boat would meet it
        let after = route::rate(inst, self.priced_from(inst, state, with), with);
        after - route::rate(inst, self.priced_from(inst, state, held), held)
    }

    /// Step 1's measure: XP per hour of the delivery leg alone, ignoring how
    /// you got to the origin. Optimistic, and inbound tasks dominate under it.
    fn standalone(&self, inst: &Instance, task: i32) -> f64 {
        let t = task as usize;
        let leg = inst.sail(inst.task_origin[t] as usize, inst.task_dest[t] as usize) as f64;
        if leg <= 0.0 {
            return 0.0;
        }
        inst.task_xp[t] as f64 / leg * 3600.0 / route::TICK
    }

    /// How good a task looks: the standalone rate for the first pick, the
    /// delta to the trip for every one after it.
    fn score(&self, inst: &Instance, state: &State, held: &[Leg], task: i32) -> f64 {
        if held.is_empty() {
            self.standalone(inst, task)
        } else {
            self.delta(inst, state, held, task)
        }
    }

    /// The best task still worth going to get, and the board holding it.
    ///
    /// A task is a candidate while it might still be there: its board is one we
    /// can charter to (or the one we are standing on), and either we have not
    /// read that board this epoch or we have and the task is on it. Reading a
    /// board and *not* finding the task is exactly what takes it off the list
    /// and moves us on to the next one.
    ///
    /// `here_only` restricts it to the board underfoot, which is what rule 5
    /// wants: with cargo aboard we can accept, but we cannot go anywhere.
    fn best(
        &self,
        sim: &Sim,
        state: &State,
        held: &[Leg],
        here_only: bool,
    ) -> Option<(i32, usize)> {
        let inst = sim.inst;
        let here = state.port_player;
        let offers = sim.true_offers(state.seed, state.epoch);

        (0..inst.n_tasks as i32)
            .filter(|&t| {
                let i = t as usize;
                let board = inst.task_board[i] as usize;
                let reachable = board == here || (!here_only && self.scoutable[board]);
                inst.task_eligible[i]
                    && reachable
                    && !state.holds(inst.capacity, t)
                    // a board we have read tells the truth; one we have not is
                    // still a hope, and going to look is the point of the rule
                    && (!state.has_seen(board) || offers.at(board).contains(&t))
            })
            .map(|t| (t, self.score(inst, state, held, t)))
            .filter(|&(_, s)| s > 0.0)
            .max_by(|a, b| a.1.total_cmp(&b.1))
            .map(|(t, _)| (t, inst.task_board[t as usize] as usize))
    }

    /// Nothing to do anywhere: head for the nearest board we have not read.
    fn wander(&self, sim: &Sim, state: &State) -> Action {
        let inst = sim.inst;
        let here = state.port_player;
        let target = (0..inst.n_ports)
            .filter(|&p| p != here && inst.has_board[p] && !state.has_seen(p))
            .min_by_key(|&p| inst.sail(here, p))
            .or_else(|| {
                (0..inst.n_ports)
                    .filter(|&p| p != here)
                    .min_by_key(|&p| inst.sail(here, p))
            })
            .expect("more than one port exists");
        if state.port_boat == here {
            Action::Sail(target)
        } else if inst.travel[target] != NONE {
            Action::Charter(target)
        } else {
            Action::Charter(self.nearest_shipwright(inst, here))
        }
    }
}

fn leg(inst: &Instance, task: i32, loaded: bool) -> Leg {
    let t = task as usize;
    Leg {
        origin: inst.task_origin[t] as usize,
        dest: inst.task_dest[t] as usize,
        loaded,
        xp: inst.task_xp[t] as i64,
    }
}

/// The held tasks as route legs, in slot order.
fn legs(inst: &Instance, state: &State) -> Vec<Leg> {
    (0..inst.capacity)
        .filter(|&s| state.held[s] != NONE)
        .map(|s| leg(inst, state.held[s], state.loaded[s]))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::evaluate;

    const LEVEL: u32 = 67;

    fn instance() -> Instance {
        Instance::at_level(LEVEL).expect("run `make instance` first")
    }

    /// The clock is the objective, so where it goes is the thing to guard.
    fn clock(inst: &Instance, seed: u64) -> (i64, i64) {
        let sim = Sim::new(inst);
        let mut policy = Baseline::new(inst);
        let mut state = sim.reset(seed, 0);
        let (mut sailing, mut walking) = (0i64, 0i64);
        while state.ticks < evaluate::HORIZON {
            let action = policy.act(&sim, &state);
            let step = sim.step(&state, action);
            match action {
                Action::Sail(_) => sailing += step.ticks,
                Action::Charter(_) | Action::Recall => walking += step.ticks,
                Action::Take { .. } => {}
            }
            state = step.state;
        }
        (sailing, walking)
    }

    /// Both bugs this policy has had were oscillations: a score or a
    /// rendezvous that depended on where the player stood, so two ports each
    /// looked better from the other and it chartered between them for the whole
    /// episode. Neither showed up as a crash - one cost a third of the rate,
    /// the other cost 92% of a seed's clock - so the guard is on the clock.
    #[test]
    fn does_not_oscillate_between_two_ports() {
        let inst = instance();
        for seed in 0..40 {
            let (sailing, walking) = clock(&inst, seed);
            assert!(
                walking * 4 < sailing,
                "seed {seed} spent {walking} ticks off the boat against {sailing} sailing"
            );
        }
    }

    /// Doing one task at a time, from the board it is on, is the floor a
    /// batching policy has to clear. At level 67 that is about 15k xp/hr.
    #[test]
    fn beats_doing_one_task_at_a_time() {
        let inst = instance();
        let score = evaluate::measure(&inst, Baseline::new, 30, evaluate::HORIZON, 0);
        assert!(score.mean > 20_000.0, "only {:.0} xp/hr", score.mean);
    }

    /// A recall destroys whatever is aboard, so the policy must never walk away
    /// from a laden boat. This is the rule that makes scouting safe at all.
    #[test]
    fn never_charters_away_with_cargo_aboard() {
        let inst = instance();
        let sim = Sim::new(&inst);
        for seed in 0..10 {
            let mut policy = Baseline::new(&inst);
            let mut state = sim.reset(seed, 0);
            while state.ticks < evaluate::HORIZON {
                let action = policy.act(&sim, &state);
                if let Action::Charter(_) = action {
                    let laden = state.loaded[..inst.capacity].iter().any(|&l| l);
                    assert!(!laden, "seed {seed} chartered away from loaded cargo");
                }
                state = sim.step(&state, action).state;
            }
        }
    }
}
