use std::path::Path;
use std::process;

use cost_model::{load_from_file, EXPECTED_SESSIONS};

fn main() {
    let args: Vec<String> = std::env::args().collect();

    if args.len() < 3 {
        eprintln!("Usage: cost_model_cli <command> <path>");
        eprintln!("Commands:");
        eprintln!("  validate <path>  Validate a cost model artifact");
        eprintln!("  inspect  <path>  Inspect a cost model artifact");
        process::exit(1);
    }

    let command = &args[1];
    let path = Path::new(&args[2]);

    match command.as_str() {
        "validate" => cmd_validate(path),
        "inspect" => cmd_inspect(path),
        _ => {
            eprintln!("Unknown command: '{command}'. Use 'validate' or 'inspect'.");
            process::exit(1);
        }
    }
}

fn cmd_validate(path: &Path) {
    match load_from_file(path) {
        Ok(model) => {
            println!("Valid");
            println!("  pair:     {}", model.pair());
            println!("  version:  {}", model.version());
            println!("  sessions: {}", model.sessions().len());
        }
        Err(e) => {
            eprintln!("Validation failed: {e}");
            process::exit(1);
        }
    }
}

fn cmd_inspect(path: &Path) {
    match load_from_file(path) {
        Ok(model) => {
            println!("Cost Model Artifact");
            println!("  pair:          {}", model.pair());
            println!("  version:       {}", model.version());
            println!("  source:        {}", model.source());
            println!("  calibrated_at: {}", model.calibrated_at());

            if let Some(metadata) = model.metadata() {
                println!("  metadata:      {}", metadata);
            }

            let sessions = model.sessions();
            println!();
            println!("Session Profiles:");
            println!(
                "  {:<20} {:>12} {:>12} {:>12} {:>12}",
                "session", "spread_mean", "spread_std", "slip_mean", "slip_std"
            );
            println!("  {}", "-".repeat(72));

            for session_key in &EXPECTED_SESSIONS {
                if let Some(profile) = sessions.get(*session_key) {
                    println!(
                        "  {:<20} {:>12.4} {:>12.4} {:>12.4} {:>12.4}",
                        session_key,
                        profile.mean_spread_pips,
                        profile.std_spread,
                        profile.mean_slippage_pips,
                        profile.std_slippage
                    );
                }
            }
        }
        Err(e) => {
            eprintln!("Failed to load artifact: {e}");
            process::exit(1);
        }
    }
}
