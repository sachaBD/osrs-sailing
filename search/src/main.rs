//! The search, from the command line.
//!
//!     cargo run --release -- run 60          the baseline, 30 seeds
//!     cargo run --release -- walk 67 0 3000  one episode, action by action
//!     cargo run --release -- tally 67 300      which tasks it actually accepts
//!     cargo run --release -- describe 60
//!     cargo run --release -- trace 60 7 400 > out/trace.json
//!
//! `describe` prints what the crate read across the seam, so a mismatch with
//! Python shows up here rather than inside a policy. `trace` records random
//! legal play for `tests/routing/test_rust_parity.py` to check against `sim.py`.

use std::time::Instant;

use porttasks_search::evaluate::{self, HORIZON, SEEDS};
use porttasks_search::policy::Baseline;
use porttasks_search::policy::Policy;
use porttasks_search::route::TICK;
use porttasks_search::{trace, Action, Instance, Sim};

const DEFAULT_LEVEL: u32 = 67;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let rest = if args.is_empty() {
        &args[..]
    } else {
        &args[1..]
    };
    match args.first().map(String::as_str) {
        None | Some("run") => run(rest),
        Some("describe") => describe(rest),
        Some("walk") => walk(rest),
        Some("tally") => tally(rest),
        Some("trace") => emit_trace(rest),
        Some(other) => fail(&format!("unknown command: {other}")),
    }
}

fn describe(args: &[String]) {
    let levels: Vec<u32> = if args.is_empty() {
        vec![DEFAULT_LEVEL]
    } else {
        args.iter().map(|a| num(a) as u32).collect()
    };
    for level in levels {
        println!("{}", load(level).describe());
    }
}

fn emit_trace(args: &[String]) {
    let level = args.first().map(num).unwrap_or(DEFAULT_LEVEL as u64) as u32;
    let seed = args.get(1).map(num).unwrap_or(0);
    let steps = args.get(2).map(num).unwrap_or(400) as usize;
    let instance = load(level);
    let sim = Sim::new(&instance);
    let recorded = trace::record(&sim, seed, 0, steps);
    println!(
        "{}",
        serde_json::to_string(&recorded).expect("a trace is plain data")
    );
}

fn run(args: &[String]) {
    let level = args.first().map(num).unwrap_or(DEFAULT_LEVEL as u64) as u32;
    let seeds = args.get(1).map(num).unwrap_or(SEEDS);
    let instance = load(level);
    println!("{}", instance.describe());
    println!(
        "{seeds} seeds, {:.1}h each\n",
        HORIZON as f64 * TICK / 3600.0
    );

    let clock = Instant::now();
    let score = evaluate::measure(&instance, Baseline::new, seeds, HORIZON, 0);
    let each = clock.elapsed().as_secs_f64() / seeds as f64;
    println!(
        "  {:20} {:9.0} +/- {:5.0} xp/hr   {:.0} ms/episode",
        "baseline",
        score.mean,
        score.error,
        each * 1000.0
    );
}

/// One episode, narrated. The Python side has `make sim` for this; a policy
/// that scores surprisingly well is a policy to read a transcript of.
fn walk(args: &[String]) {
    let level = args.first().map(num).unwrap_or(DEFAULT_LEVEL as u64) as u32;
    let seed = args.get(1).map(num).unwrap_or(0);
    let horizon = args.get(2).map(num).unwrap_or(3_000) as i64;
    let instance = load(level);
    let sim = Sim::new(&instance);
    let mut policy = Baseline::new(&instance);
    let mut state = sim.reset(seed, 0);
    let mut spent = [0i64; 5];

    while state.ticks < horizon {
        let action = policy.act(&sim, &state);
        let before = state;
        let step = sim.step(&state, action);
        let what = match action {
            Action::Take { task, .. } => format!(
                "take   {} ({} xp, d={:+.0})",
                instance.task_names[task as usize],
                instance.task_xp[task as usize],
                policy.explain(&sim, &before, task)
            ),
            Action::Sail(p) => format!("sail   {}", instance.port_names[p]),
            Action::Charter(p) => format!("charter {}", instance.port_names[p]),
            Action::Recall => "recall".to_string(),
        };
        let earned = if step.xp > 0 {
            format!("  +{} xp", step.xp)
        } else {
            String::new()
        };
        println!(
            "t={:>6}  {:<22} {:<44} {:>3} ticks{}",
            before.ticks, instance.port_names[before.port_player], what, step.ticks, earned
        );
        // where the clock goes: a leg with nothing aboard is a leg wasted
        let laden = before.loaded[..instance.capacity].iter().any(|&l| l);
        match action {
            Action::Sail(_) if laden => spent[0] += step.ticks,
            Action::Sail(_) => spent[1] += step.ticks,
            Action::Charter(_) => spent[2] += step.ticks,
            Action::Recall => spent[3] += step.ticks,
            Action::Take { .. } => spent[4] += step.ticks,
        }
        state = step.state;
    }
    println!(
        "\n{} xp in {} ticks = {:.0} xp/hr",
        state.xp,
        state.ticks,
        state.xp as f64 / state.ticks as f64 * 3600.0 / TICK
    );
    for (label, ticks) in ["sail laden", "sail empty", "charter", "recall", "board"]
        .iter()
        .zip(spent)
    {
        println!(
            "  {label:12} {ticks:>6} ticks  {:>5.1}%",
            100.0 * ticks as f64 / state.ticks as f64
        );
    }
}

/// Which tasks the baseline actually takes, over many episodes.
///
/// The policy is a ranking, so what it ends up holding is the ranking's
/// verdict on the task table - and a task the rule never touches is either
/// genuinely bad or evidence the rule cannot see it.
fn tally(args: &[String]) {
    let level = args.first().map(num).unwrap_or(DEFAULT_LEVEL as u64) as u32;
    let seeds = args.get(1).map(num).unwrap_or(SEEDS);
    let instance = load(level);
    let mut taken = vec![0u64; instance.n_tasks];
    // how full the hold was when this task was accepted: 0 = it anchored the set
    let mut at_hold = vec![[0u64; 5]; instance.n_tasks];
    let mut total = 0u64;
    // ticks spent holding n tasks, and how each acquisition phase ended
    let mut occupancy = [0i64; 5];
    let (mut ended_full, mut ended_short) = (0u64, 0u64);

    for seed in 0..seeds {
        let sim = Sim::new(&instance);
        let mut policy = Baseline::new(&instance);
        let mut state = sim.reset(seed, 0);
        while state.ticks < HORIZON {
            let action = policy.act(&sim, &state);
            if let Action::Take { task, .. } = action {
                let held = instance.capacity - state.free_slots(instance.capacity);
                taken[task as usize] += 1;
                at_hold[task as usize][held] += 1;
                total += 1;
            }
            let held = instance.capacity - state.free_slots(instance.capacity);
            let step = sim.step(&state, action);
            occupancy[held] += step.ticks;
            // a Sail with a free slot means acquisition gave up before filling
            if let Action::Sail(_) = action {
                if state.port_boat != state.port_player {
                } else if held == instance.capacity {
                    ended_full += 1;
                } else {
                    ended_short += 1;
                }
            }
            state = step.state;
        }
    }

    let clock: i64 = occupancy.iter().sum();
    println!("\nhold occupancy, by share of the clock:");
    for (n, ticks) in occupancy.iter().enumerate().take(instance.capacity + 1) {
        println!("  {n} held  {:5.1}%", 100.0 * *ticks as f64 / clock as f64);
    }
    let mean: f64 = occupancy
        .iter()
        .enumerate()
        .map(|(n, t)| n as f64 * *t as f64)
        .sum::<f64>()
        / clock as f64;
    println!(
        "  mean {mean:.2} of {} slots;  legs sailed with a full hold: {:.0}%\n",
        instance.capacity,
        100.0 * ended_full as f64 / (ended_full + ended_short) as f64
    );

    let mut rows: Vec<usize> = (0..instance.n_tasks).filter(|&t| taken[t] > 0).collect();
    rows.sort_by_key(|&t| std::cmp::Reverse(taken[t]));
    let eligible = (0..instance.n_tasks)
        .filter(|&t| instance.task_eligible[t])
        .count();

    println!("{}", instance.describe());
    println!(
        "{seeds} seeds, {:.1}h each: {total} tasks accepted, {} distinct of {eligible} eligible\n",
        HORIZON as f64 * TICK / 3600.0,
        rows.len()
    );
    println!("   %      n   xp     leg  xp/hr  1st%   task");
    for t in rows {
        let leg = instance.sail(
            instance.task_origin[t] as usize,
            instance.task_dest[t] as usize,
        );
        println!(
            "  {:5.2} {:6} {:6} {:5} {:7.0} {:5.0}   {}",
            100.0 * taken[t] as f64 / total as f64,
            taken[t],
            instance.task_xp[t],
            leg,
            instance.task_xp[t] as f64 / leg as f64 * 3600.0 / TICK,
            100.0 * at_hold[t][0] as f64 / taken[t] as f64,
            instance.task_names[t]
        );
    }
}

fn load(level: u32) -> Instance {
    Instance::at_level(level).unwrap_or_else(|why| fail(&why))
}

fn num(arg: &String) -> u64 {
    arg.parse()
        .unwrap_or_else(|_| fail(&format!("not a number: {arg}")))
}

fn fail(why: &str) -> ! {
    eprintln!("error: {why}");
    std::process::exit(1)
}
