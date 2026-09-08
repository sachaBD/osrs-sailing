//! Sequencing a held set into a route, and pricing it.
//!
//! The same rule the route builder in `web/js/trip.js` uses: nearest
//! neighbour over the pending pickups and the cargo already aboard, a task's
//! pickup always before its delivery. It is not the best tour - we are ranking
//! additions, not solving the travelling salesman - but it is the tour the
//! policy actually sails, which is what makes a Δ XP/hr honest.
//!
//! One difference from the web app, and it is deliberate. The app prices a
//! route over raw tiles and charges docking per stop and cargo per handling;
//! here a leg is `Instance::sail`, which already carries both. That is what
//! the simulator charges for `Sail`, and a policy has to be ranked by the same
//! clock it is scored against or it optimises a route it never sails.

use crate::instance::Instance;
use crate::sim::MAX_HELD;

/// Seconds in a tick. The game's own quantum.
pub const TICK: f64 = 0.6;

/// One task's place on a route: where the cargo is, and where it must go.
#[derive(Debug, Clone, Copy)]
pub struct Leg {
    pub origin: usize,
    pub dest: usize,
    /// Cargo already aboard, so the origin has been dealt with.
    pub loaded: bool,
    pub xp: i64,
}

/// Ticks of water to clear `legs` from `start`, nearest stop first.
///
/// Sailing to where you already are is free, which is how the web app's
/// merging of consecutive visits to one port falls out rather than being coded.
pub fn ticks(inst: &Instance, start: usize, legs: &[Leg]) -> i64 {
    debug_assert!(legs.len() <= MAX_HELD);
    let mut aboard = [false; MAX_HELD];
    let mut done = [false; MAX_HELD];
    for (i, leg) in legs.iter().enumerate() {
        aboard[i] = leg.loaded;
    }

    let (mut here, mut total, mut left) = (start, 0i64, legs.len());
    while left > 0 {
        let mut best: Option<(i64, usize)> = None;
        for (i, leg) in legs.iter().enumerate() {
            if done[i] {
                continue;
            }
            let want = if aboard[i] { leg.dest } else { leg.origin };
            let d = inst.sail(here, want) as i64;
            if best.is_none_or(|(bd, _)| d < bd) {
                best = Some((d, i));
            }
        }
        let (d, i) = best.expect("something is left, so something is nearest");
        total += d;
        if aboard[i] {
            here = legs[i].dest;
            done[i] = true;
            left -= 1;
        } else {
            here = legs[i].origin;
            aboard[i] = true;
        }
    }
    total
}

/// XP per hour of sailing `legs` from `start`, or zero for an empty set.
pub fn rate(inst: &Instance, start: usize, legs: &[Leg]) -> f64 {
    let sailed = ticks(inst, start, legs);
    if sailed <= 0 {
        return 0.0;
    }
    let xp: i64 = legs.iter().map(|l| l.xp).sum();
    xp as f64 / sailed as f64 * 3600.0 / TICK
}

/// The port to head for next, or `None` when nothing is outstanding.
pub fn next_stop(inst: &Instance, start: usize, legs: &[Leg]) -> Option<usize> {
    legs.iter()
        .map(|leg| if leg.loaded { leg.dest } else { leg.origin })
        .min_by_key(|&port| inst.sail(start, port))
}

/// The exact stop order, by dynamic programming over (picked, delivered, here).
///
/// Nearest neighbour is a heuristic and this is not: with a capacity of four
/// there are at most eight events, so the state space is `3^n` assignments
/// times a port, which is a few thousand cells. Held-Karp for pickup and
/// delivery, small enough that "solve it exactly" costs less than thinking
/// about whether the heuristic is good enough.
///
/// It matters less for the route than for the *ranking* built on top of it: a
/// tour priced 5% long makes every delta slightly wrong, and the deltas are
/// what the policy actually reads.
pub fn ticks_exact(inst: &Instance, start: usize, legs: &[Leg]) -> i64 {
    let n = legs.len();
    if n == 0 {
        return 0;
    }
    debug_assert!(n <= MAX_HELD);
    let full = (1usize << n) - 1;
    let picked0: usize = legs
        .iter()
        .enumerate()
        .filter(|(_, l)| l.loaded)
        .map(|(i, _)| 1 << i)
        .sum();

    // memo[picked][delivered][here], i64::MAX for "not yet computed"
    let span = inst.n_ports;
    let mut memo = vec![i64::MAX; (1 << n) * (1 << n) * span];
    best(inst, legs, n, full, picked0, 0, start, &mut memo, span)
}

#[allow(clippy::too_many_arguments)]
fn best(
    inst: &Instance,
    legs: &[Leg],
    n: usize,
    full: usize,
    picked: usize,
    delivered: usize,
    here: usize,
    memo: &mut Vec<i64>,
    span: usize,
) -> i64 {
    if delivered == full {
        return 0;
    }
    let slot = (picked * (1 << n) + delivered) * span + here;
    if memo[slot] != i64::MAX {
        return memo[slot];
    }
    let mut found = i64::MAX;
    for i in 0..n {
        let bit = 1 << i;
        // deliver what is aboard, or go and pick up what is not
        let (port, next_picked, next_delivered) = if picked & bit != 0 {
            if delivered & bit != 0 {
                continue;
            }
            (legs[i].dest, picked, delivered | bit)
        } else {
            (legs[i].origin, picked | bit, delivered)
        };
        let step = inst.sail(here, port) as i64
            + best(
                inst,
                legs,
                n,
                full,
                next_picked,
                next_delivered,
                port,
                memo,
                span,
            );
        found = found.min(step);
    }
    memo[slot] = found;
    found
}

/// Ticks for a route, exactly or by nearest neighbour.
pub fn ticks_by(inst: &Instance, start: usize, legs: &[Leg], exact: bool) -> i64 {
    if exact {
        ticks_exact(inst, start, legs)
    } else {
        ticks(inst, start, legs)
    }
}

/// XP per hour of a route, exactly or by nearest neighbour.
pub fn rate_by(inst: &Instance, start: usize, legs: &[Leg], exact: bool) -> f64 {
    let sailed = ticks_by(inst, start, legs, exact);
    if sailed <= 0 {
        return 0.0;
    }
    let xp: i64 = legs.iter().map(|l| l.xp).sum();
    xp as f64 / sailed as f64 * 3600.0 / TICK
}
