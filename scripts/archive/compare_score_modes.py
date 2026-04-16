"""Compare score modes by re-running one generation with both scoring modes.

Reads an existing manifest from the wide run, redirects output_dir to
temp comparison dirs, runs the Rust binary in both modes, compares scores.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src" / "python"))

import numpy as np
import pyarrow.ipc as ipc

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WIDE_RUN = PROJECT_ROOT / "artifacts" / "ma-crossover" / "v001" / "optimization-wide-22yr"
BINARY = PROJECT_ROOT / "src" / "rust" / "target" / "release" / "forex_backtester.exe"
COMPARISON_DIR = PROJECT_ROOT / "artifacts" / "ma-crossover" / "v001" / "score-mode-comparison"


def norm(p) -> str:
    return str(p).replace("\\", "/")


def create_redirected_manifest(source_manifest: Path, mode: str) -> Path:
    """Read original manifest, redirect output_dirs to comparison dir."""
    manifest = json.loads(source_manifest.read_text())

    for group in manifest["groups"]:
        # Original: artifacts/.../gen_000000/grp_XXX/fold_Y
        orig_out = Path(group["output_dir"])
        # Redirect: .../score-mode-comparison/{mode}/grp_XXX/fold_Y
        parts = orig_out.parts
        # Find grp_ part
        grp_idx = next(i for i, p in enumerate(parts) if p.startswith("grp_"))
        new_out = COMPARISON_DIR / mode / "/".join(parts[grp_idx:])
        new_out.mkdir(parents=True, exist_ok=True)
        group["output_dir"] = norm(new_out)

        # Make spec_path and data_path absolute
        group["spec_path"] = norm(PROJECT_ROOT / group["spec_path"])
        group["data_path"] = norm(PROJECT_ROOT / group["data_path"])

    # Make top-level paths absolute
    if "market_data_path" in manifest:
        manifest["market_data_path"] = norm(PROJECT_ROOT / manifest["market_data_path"])
    if "cost_model_path" in manifest:
        manifest["cost_model_path"] = norm(PROJECT_ROOT / manifest["cost_model_path"])

    # Inject score_mode into manifest
    manifest["score_mode"] = mode

    dest = COMPARISON_DIR / mode / source_manifest.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(manifest, indent=2))
    return dest


def run_binary(manifest_path: Path, score_mode: str) -> float:
    args = [
        str(BINARY),
        "--manifest", norm(manifest_path),
        "--memory-budget", "2048",
        "--score-mode", score_mode,
    ]
    print(f"  Running: {score_mode} mode...")
    t0 = time.time()
    result = subprocess.run(args, capture_output=True, text=True, timeout=300)
    elapsed = time.time() - t0

    if result.returncode != 0:
        print(f"  ERROR (exit {result.returncode}):")
        print(f"  stderr: {result.stderr[:500]}")
        return elapsed

    print(f"  Completed in {elapsed:.1f}s")
    return elapsed


def collect_scores(mode: str) -> dict[str, list[float]]:
    mode_dir = COMPARISON_DIR / mode
    scores = {}
    for scores_file in sorted(mode_dir.rglob("scores.arrow")):
        reader = ipc.open_file(str(scores_file))
        table = reader.read_all()
        key = str(scores_file.relative_to(mode_dir).parent)
        scores[key] = table.column("score").to_pylist()
    return scores


def main():
    if not BINARY.exists():
        print(f"ERROR: Binary not found: {BINARY}")
        sys.exit(1)

    # Use fold 0 only for quick verification
    source_gen = 0
    folds = [0]

    print(f"Score Mode Comparison")
    print(f"Source: gen_{source_gen:06d}, folds: {folds}")
    print(f"Wide run: {WIDE_RUN.name}")
    print()

    for mode in ["sharpe", "composite"]:
        print(f"\n{'='*60}")
        print(f"  MODE: {mode}")
        print(f"{'='*60}")
        for fold in folds:
            src = WIDE_RUN / f"gen_{source_gen:06d}" / f"manifest_fold_{fold}.json"
            if not src.exists():
                print(f"  Skipping fold {fold} (manifest not found)")
                continue
            manifest = create_redirected_manifest(src, mode)
            run_binary(manifest, mode)

    # Collect and compare
    sharpe_scores = collect_scores("sharpe")
    composite_scores = collect_scores("composite")

    print(f"\n{'='*60}")
    print(f"  RESULTS")
    print(f"{'='*60}")
    print(f"  Sharpe groups: {len(sharpe_scores)}, total scores: {sum(len(v) for v in sharpe_scores.values())}")
    print(f"  Composite groups: {len(composite_scores)}, total scores: {sum(len(v) for v in composite_scores.values())}")

    # Flatten matching groups
    s_all, c_all = [], []
    for key in sorted(set(sharpe_scores) & set(composite_scores)):
        s = sharpe_scores[key]
        c = composite_scores[key]
        if len(s) == len(c):
            s_all.extend(s)
            c_all.extend(c)

    s_arr = np.array(s_all)
    c_arr = np.array(c_all)
    valid = np.isfinite(s_arr) & np.isfinite(c_arr)
    s = s_arr[valid]
    c = c_arr[valid]

    if len(s) == 0:
        print("\n  No valid paired scores to compare.")
        return

    print(f"\n  Paired candidates: {len(s)}")
    print(f"\n  {'Metric':<20} {'Sharpe Score':>15} {'Composite Score':>15}")
    print(f"  {'-'*50}")
    for label, fn in [("Min", np.min), ("Max", np.max), ("Mean", np.mean),
                       ("Median", np.median), ("Std", np.std)]:
        print(f"  {label:<20} {fn(s):>15.4f} {fn(c):>15.4f}")

    # Rankings
    s_rank = np.argsort(-s)
    c_rank = np.argsort(-c)
    N = min(20, len(s))

    print(f"\n  Top {N} by Sharpe score:")
    print(f"  {'#':>3} {'Sharpe':>10} {'Composite':>10} {'CompRank':>9}")
    c_rank_map = {int(idx): rank for rank, idx in enumerate(c_rank)}
    for i in range(N):
        idx = int(s_rank[i])
        print(f"  {i+1:3d} {s[idx]:10.4f} {c[idx]:10.4f} {c_rank_map.get(idx, -1)+1:9d}")

    print(f"\n  Top {N} by Composite score:")
    print(f"  {'#':>3} {'Composite':>10} {'Sharpe':>10} {'ShpRank':>9}")
    s_rank_map = {int(idx): rank for rank, idx in enumerate(s_rank)}
    for i in range(N):
        idx = int(c_rank[i])
        print(f"  {i+1:3d} {c[idx]:10.4f} {s[idx]:10.4f} {s_rank_map.get(idx, -1)+1:9d}")

    # Correlation
    corr = np.corrcoef(s, c)[0, 1]
    print(f"\n  Pearson correlation: {corr:.4f}")
    try:
        from scipy.stats import spearmanr
        rho, p = spearmanr(s, c)
        print(f"  Spearman rho:       {rho:.4f} (p={p:.2e})")
    except ImportError:
        pass

    # Top-N overlap
    s_top = set(int(x) for x in s_rank[:N])
    c_top = set(int(x) for x in c_rank[:N])
    overlap = s_top & c_top
    print(f"\n  Top-{N} overlap: {len(overlap)}/{N}")


if __name__ == "__main__":
    main()
