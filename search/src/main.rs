//! The search, from the command line.
//!
//!     cargo run --release -- 30        describe the level-30 instance
//!
//! There is nothing to run yet but the seam: this prints what the crate read,
//! so a mismatch with Python shows up here rather than inside a policy.

use porttasks_search::Instance;

fn main() {
    let levels: Vec<u32> = std::env::args()
        .skip(1)
        .map(|a| {
            a.parse()
                .unwrap_or_else(|_| fail(&format!("not a level: {a}")))
        })
        .collect();

    for level in if levels.is_empty() { vec![30] } else { levels } {
        match Instance::at_level(level) {
            Ok(instance) => println!("{}", instance.describe()),
            Err(why) => fail(&why),
        }
    }
}

fn fail(why: &str) -> ! {
    eprintln!("error: {why}");
    std::process::exit(1)
}
