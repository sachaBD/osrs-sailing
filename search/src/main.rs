//! The search, from the command line.
//!
//!     cargo run --release -- run 60          the baseline, 30 seeds
//!     cargo run --release -- walk 60 0 3000  one episode, action by action
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
