//! The search, from the command line.
//!
//!     cargo run --release -- describe 60
//!     cargo run --release -- trace 60 7 400 > out/trace.json
//!
//! `describe` prints what the crate read across the seam, so a mismatch with
//! Python shows up here rather than inside a policy. `trace` records random
//! legal play for `tests/routing/test_rust_parity.py` to check against `sim.py`.

use porttasks_search::{trace, Instance, Sim};

const DEFAULT_LEVEL: u32 = 60;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let rest = if args.is_empty() {
        &args[..]
    } else {
        &args[1..]
    };
    match args.first().map(String::as_str) {
        None | Some("describe") => describe(rest),
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
