# search

Policies over the port-task SMDP. The third of the three layers
`../porttasks/routing/README.md` describes, and the only one not in Python.

It is separate, and in Rust, for one reason: it is the layer whose cost is
measured in states per second. `world/` is surveyed once and committed;
`problem/` is a definition. This is the part that gets run a few hundred
million times, across seeds, sampled futures, and every plausible value of the
constants we have not measured yet.

    make instance       export the problem into derived/  (Python)
    make search         run the baseline                  (Rust)
    make search-check   tests, clippy, rustfmt

    cargo run --release -- run 67 300     the baseline, 300 seeds
    cargo run --release -- walk 67 0      one episode, action by action
    cargo run --release -- tally 67 300   which tasks it actually accepts
    cargo run --release -- lab 67 100     every variant, paired against the baseline
    cargo run --release -- sweep 67 60 8  rollout against its horizon
    cargo run --release -- describe 67    what came across the seam

## The seam

Python owns every table and everything derived from one. This crate never
parses a TSV and never computes a distance; it reads
`derived/instance_l{level}.json`, which `porttasks.routing.problem.export`
writes straight out of the same `Instance` the Python simulator uses.

So the sail matrix, the task pools and the cost constants have exactly one
definition, in `tables/`, and there is no second place for them to drift.

`format` in that file is a version. Change a field's shape and bump it; this
end refuses a file it does not recognise rather than guessing.

    src/instance.rs   the static problem, read across the seam

## Layout

One crate, no workspace. `lib.rs` is the whole surface; `main.rs` is a thin
command line over it, so everything is reachable from a test.

    src/instance.rs   the static problem, read across the seam
    src/sim.rs        the dynamics, over `Copy` states
    src/route.rs      sequencing a held set into a route, and pricing it
    src/policy.rs     the rules baseline, and the `Policy` trait
    src/lab.rs        experiments on the baseline. Never the baseline itself
    src/evaluate.rs   xp/hr over independent seeds, and paired differences
    src/trace.rs      a recording of random play, for Python to check

`policy.rs` is the committed rule and `lab.rs` is everything trying to beat it.
The split is the point: a variant that wins gets promoted by changing
`Tuning::default`, and one that loses stays here with its result written down,
because a negative result nobody recorded gets re-run by the next person.

Rollout is the one that wins - 16% over the baseline, and the direction with
room left in it. Two ideas straight out of the textbook lose: the
rho-parametrisation the docs prescribe, and exact rather than heuristic
routing. `docs/RESULTS.md` says why.

`walk` and `tally` are diagnostics rather than decoration. Every bug this
policy has had was invisible in the mean and obvious in a transcript: two
oscillations that cost a third of the rate, and a score that priced a leg the
policy never sailed. Read the episode before believing the number.

## Two implementations of the dynamics

There is a simulator in Python (`porttasks/routing/problem/sim.py`) and there
will be one here. That is a real cost and the project has paid it before - the
old `core.py` was a second copy of the same dynamics, and it was worth 12x.

The rule that made it safe then applies now: **a differential test walks both
and asserts they agree**, step for step, over random legal play. Python stays
the definition and the oracle; Rust stays the thing that is fast. If they ever
disagree, Python is right.

The one place they cannot agree is the reroll draw, because numpy's generator
is not reproducible outside numpy. That draw is defined here instead, and the
differential test feeds both sides the same offers rather than the same seed.
