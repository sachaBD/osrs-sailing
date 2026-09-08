//! Policies over the port-task SMDP.
//!
//! `docs/PROBLEM.md` in the repo root says what the problem is; `APPROACH.md`
//! says how we mean to attack it. This crate is the third of the three layers
//! `porttasks/routing/` describes - the one that decides what to do - and it
//! is here rather than in Python because it is the only layer whose cost is
//! measured in states per second.
//!
//! The other two layers stay in Python and are read across a JSON seam:
//!
//! - `world/`   the sea chart. Never crosses; it is already folded into the sail matrix.
//! - `problem/` the SMDP. Its static half crosses as [`instance::Instance`].
//!
//! So Python owns every table and every number derived from one, and this
//! crate owns the dynamics it runs millions of times and the policies over
//! them.

pub mod evaluate;
pub mod instance;
pub mod lab;
pub mod policy;
pub mod route;
pub mod sim;
pub mod trace;

pub use instance::{Instance, NONE};
pub use policy::{Baseline, Policy};
pub use sim::{Action, Sim, State, Step};
