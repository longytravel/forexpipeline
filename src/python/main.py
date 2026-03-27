"""Forex Pipeline -- main entry point.

Loads config, validates schema, sets up structured logging,
and dispatches to the requested stage.
"""
import argparse
import sys
from config_loader import load_config, validate_or_die, compute_config_hash
from logging_setup import setup_logging, get_logger
from artifacts.storage import clean_partial_files


def main():
    parser = argparse.ArgumentParser(description="Forex Pipeline")
    parser.add_argument("--stage", default=None,
                        help="Pipeline stage to run (e.g. pipeline-proof)")
    parser.add_argument("--env", default=None,
                        help="Config environment overlay")
    parser.add_argument("--skip-download", action="store_true",
                        help="Skip data download (pipeline-proof)")
    parser.add_argument("--skip-reproducibility", action="store_true",
                        help="Skip reproducibility check (pipeline-proof)")
    args = parser.parse_args()

    # 1. Load and validate config
    config = load_config(env=args.env)
    validate_or_die(config)

    # 2. Setup structured logging
    setup_logging(config)
    logger = get_logger("main")

    # 3. Compute and log config hash
    config_hash = compute_config_hash(config)
    logger.info("Forex Pipeline starting", extra={
        "ctx": {"config_hash": config_hash, "env": config.get("_env", "local")}
    })

    # 4. Clean any partial files from previous crashes
    cleaned = clean_partial_files(config["pipeline"]["artifacts_dir"])
    if cleaned:
        logger.warning("Cleaned partial files from previous crash", extra={
            "ctx": {"files": cleaned}
        })

    # 5. Dispatch to requested stage
    if args.stage == "pipeline-proof":
        from data_pipeline.pipeline_proof import run_pipeline_proof
        result = run_pipeline_proof(
            config, args.skip_download, args.skip_reproducibility)
        sys.exit(0 if result.overall_status == "PASS" else 1)
    elif args.stage is not None:
        logger.error("Unknown stage: %s", args.stage)
        sys.exit(1)
    else:
        logger.info("Foundation verified -- config, logging, and crash-safe writes operational")


if __name__ == "__main__":
    main()
