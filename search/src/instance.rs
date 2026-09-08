//! The static problem, as flat arrays: what `porttasks.routing.problem.instance`
//! computes, read from the JSON that `..export` writes.
//!
//! Nothing here parses a table. `tables/` is the one source of truth and Python
//! owns it; this end only reads what Python already derived, so the two cannot
//! drift into disagreeing about what a port costs.
//!
//! Everything is an index. A port is `0..n_ports`, a task is `0..n_tasks`, and
//! `NONE` is the absent one - an empty slot, an unreachable port, a task that
//! does not exist. Ticks are `i32` throughout, as they are in Python: the
//! game's own quantum, so the arithmetic is exact.

use std::fs;
use std::path::{Path, PathBuf};

use serde::Deserialize;

/// The absent port, task or offer. Matches `instance.NONE` on the Python side.
pub const NONE: i32 = -1;

/// The format `export.py` writes. A mismatch means the two halves were built
/// from different revisions, which is worth refusing rather than guessing at.
const FORMAT: u32 = 2;

#[derive(Debug, Deserialize)]
pub struct Params {
    pub courier_per_board: usize,
    pub reroll_completions: u32,
    pub t_board: i32,
    pub t_drop: i32,
}

#[derive(Debug, Deserialize)]
struct Ports {
    names: Vec<String>,
    sail: Vec<Vec<i32>>,
    /// Ticks to reach without the boat - charter ship or magic teleport alike.
    travel: Vec<i32>,
    recall: Vec<i32>,
    has_board: Vec<bool>,
}

#[derive(Debug, Deserialize)]
struct Tasks {
    names: Vec<String>,
    board: Vec<i32>,
    origin: Vec<i32>,
    dest: Vec<i32>,
    xp: Vec<i32>,
    eligible: Vec<bool>,
}

#[derive(Debug, Deserialize)]
struct Pools {
    ptr: Vec<i32>,
    flat: Vec<i32>,
}

#[derive(Debug, Deserialize)]
struct Wire {
    format: u32,
    level: u32,
    capacity: usize,
    params: Params,
    ports: Ports,
    tasks: Tasks,
    pools: Pools,
}

/// The static problem at one level. Immutable for the life of a solve.
///
/// The sail matrix is stored row-major and flat rather than as `Vec<Vec<i32>>`:
/// it is read once per simulated action and wants to be one cache line away,
/// not two pointer hops.
#[derive(Debug)]
pub struct Instance {
    pub level: u32,
    pub capacity: usize,
    pub params: Params,

    pub n_ports: usize,
    sail: Vec<i32>, // n_ports * n_ports, row-major
    pub travel: Vec<i32>,
    pub recall: Vec<i32>,
    pub has_board: Vec<bool>,

    pub n_tasks: usize,
    pub task_board: Vec<i32>,
    pub task_origin: Vec<i32>,
    pub task_dest: Vec<i32>,
    pub task_xp: Vec<i32>,
    pub task_eligible: Vec<bool>,

    pool_ptr: Vec<i32>,
    pool: Vec<i32>,

    pub port_names: Vec<String>,
    pub task_names: Vec<String>,
}

impl Instance {
    /// Sail time in ticks. Includes docking and cargo handling, as Python's does.
    #[inline]
    pub fn sail(&self, from: usize, to: usize) -> i32 {
        self.sail[from * self.n_ports + to]
    }

    /// The tasks board `port` may offer. Empty where the port has no board.
    #[inline]
    pub fn board_pool(&self, port: usize) -> &[i32] {
        let (lo, hi) = (
            self.pool_ptr[port] as usize,
            self.pool_ptr[port + 1] as usize,
        );
        &self.pool[lo..hi]
    }

    pub fn boards(&self) -> impl Iterator<Item = usize> + '_ {
        (0..self.n_ports).filter(|&p| self.has_board[p])
    }

    pub fn load(path: impl AsRef<Path>) -> Result<Instance, String> {
        let path = path.as_ref();
        let text = fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
        let wire: Wire =
            serde_json::from_str(&text).map_err(|e| format!("{}: {e}", path.display()))?;
        if wire.format != FORMAT {
            return Err(format!(
                "{}: format {} but this build reads {FORMAT}; rerun \
                 `python3 -m porttasks.routing.problem.export`",
                path.display(),
                wire.format
            ));
        }
        Ok(Instance::from(wire))
    }

    /// Load the export for `level` from the repo's `derived/`.
    pub fn at_level(level: u32) -> Result<Instance, String> {
        Instance::load(derived().join(format!("instance_l{level}.json")))
    }

    /// The one line `Instance.describe()` prints in Python, to the character.
    /// Cheap, and it is how we check the seam did not lose anything.
    pub fn describe(&self) -> String {
        let boards = self.has_board.iter().filter(|&&b| b).count();
        let live = self.task_eligible.iter().filter(|&&e| e).count();
        let sizes: Vec<i32> = self
            .boards()
            .map(|p| self.pool_ptr[p + 1] - self.pool_ptr[p])
            .collect();
        let (lo, hi) = (
            sizes.iter().min().copied().unwrap_or(0),
            sizes.iter().max().copied().unwrap_or(0),
        );
        format!(
            "level {}: {} ports, {boards} boards, {} tasks ({live} eligible), \
             capacity {}, {} offers from pools of {lo}-{hi}",
            self.level, self.n_ports, self.n_tasks, self.capacity, self.params.courier_per_board
        )
    }
}

impl From<Wire> for Instance {
    fn from(w: Wire) -> Instance {
        let n_ports = w.ports.names.len();
        Instance {
            level: w.level,
            capacity: w.capacity,
            params: w.params,
            n_ports,
            sail: w.ports.sail.into_iter().flatten().collect(),
            travel: w.ports.travel,
            recall: w.ports.recall,
            has_board: w.ports.has_board,
            n_tasks: w.tasks.names.len(),
            task_board: w.tasks.board,
            task_origin: w.tasks.origin,
            task_dest: w.tasks.dest,
            task_xp: w.tasks.xp,
            task_eligible: w.tasks.eligible,
            pool_ptr: w.pools.ptr,
            pool: w.pools.flat,
            port_names: w.ports.names,
            task_names: w.tasks.names,
        }
    }
}

/// The repo's `derived/`, found from the crate rather than the working
/// directory - `search/` sits one level below the root, exactly as
/// `porttasks.paths` anchors the Python half.
pub fn derived() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("the crate is a directory inside the repo")
        .join("derived")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn level_30() -> Instance {
        Instance::at_level(30).expect("run `python3 -m porttasks.routing.problem.export` first")
    }

    #[test]
    fn describes_itself_as_python_does() {
        assert_eq!(
            level_30().describe(),
            "level 30: 10 ports, 9 boards, 171 tasks (98 eligible), capacity 3, \
             5 offers from pools of 19-19"
        );
    }

    #[test]
    fn sail_matrix_is_symmetric_with_zero_diagonal() {
        let inst = level_30();
        for a in 0..inst.n_ports {
            assert_eq!(inst.sail(a, a), 0);
            for b in 0..inst.n_ports {
                assert_eq!(inst.sail(a, b), inst.sail(b, a));
            }
        }
    }

    #[test]
    fn every_board_can_fill_its_offers() {
        // the draw is without replacement, so a short pool would be unsatisfiable
        let inst = level_30();
        for port in inst.boards() {
            assert!(inst.board_pool(port).len() >= inst.params.courier_per_board);
        }
    }

    #[test]
    fn pools_keep_tasks_the_level_cannot_do() {
        // a board draws from its whole pool, so an ineligible task still burns
        // an offer slot; dropping them would inflate how much choice a board gives
        let inst = level_30();
        assert!(inst
            .boards()
            .flat_map(|p| inst.board_pool(p))
            .any(|&t| !inst.task_eligible[t as usize]));
    }
}
