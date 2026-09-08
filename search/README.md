# search

Policies over the port-task SMDP. The third of the three layers
`../porttasks/routing/README.md` describes, and the only one not in Python.

It is separate, and in Rust, for one reason: it is the layer whose cost is
measured in states per second. `world/` is surveyed once and committed;
`problem/` is a definition. This is the part that gets run a few hundred
million times, across seeds, sampled futures, and every plausible value of the
constants we have not measured yet.

    make instance       export the problem into derived/  (Python)
    make search         build and run                     (Rust)
    make search-check   tests, clippy, rustfmt

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
