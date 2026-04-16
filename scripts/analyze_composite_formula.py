"""Data-driven analysis of composite scoring formula variants.

Uses the 10,185 candidates from gen_000000 scored in both modes to test
multiple formula variants and determine the best approach objectively.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src" / "python"))

import numpy as np
import pyarrow.ipc as ipc

PROJECT_ROOT = Path(__file__).resolve().parent.parent
COMPARISON_DIR = PROJECT_ROOT / "artifacts" / "ma-crossover" / "v001" / "score-mode-comparison"


def collect_paired_scores():
    """Collect sharpe and composite scores for all candidates."""
    sharpe_scores = {}
    composite_scores = {}
    for mode, store in [("sharpe", sharpe_scores), ("composite", composite_scores)]:
        mode_dir = COMPARISON_DIR / mode
        for scores_file in sorted(mode_dir.rglob("scores.arrow")):
            reader = ipc.open_file(str(scores_file))
            table = reader.read_all()
            key = str(scores_file.relative_to(mode_dir).parent)
            store[key] = table.column("score").to_pylist()

    s_all, c_all = [], []
    for key in sorted(set(sharpe_scores) & set(composite_scores)):
        s = sharpe_scores[key]
        c = composite_scores[key]
        if len(s) == len(c):
            s_all.extend(s)
            c_all.extend(c)

    return np.array(s_all), np.array(c_all)


def clamp01(v):
    return np.clip(v, 0.0, 1.0)


# --- Formula variants ---

def formula_current(sharpe, composite):
    """Current composite as-is."""
    return composite


def formula_hard_gate(sharpe, composite):
    """Hard gate: sharpe <= 0 → score = 0."""
    result = composite.copy()
    result[sharpe <= 0] = 0.0
    return result


def formula_soft_gate(sharpe, composite):
    """Soft gate: sigmoid multiplier centered at sharpe=0.
    score = sigmoid(sharpe * 5) * composite
    Sharpe=-0.5 → mult≈0.08, Sharpe=0 → mult=0.5, Sharpe=0.5 → mult≈0.92
    """
    mult = 1.0 / (1.0 + np.exp(-5.0 * sharpe))
    return mult * composite


def formula_tiered(sharpe, composite):
    """Tiered: unprofitable gets gradient signal [0, 0.1], profitable gets [0.1, 1.0].
    Ensures all profitable > all unprofitable, with smooth gradient in both regimes.
    """
    result = np.zeros_like(sharpe)
    unprofitable = sharpe <= 0
    profitable = ~unprofitable

    # Unprofitable: map sharpe [-2, 0] → [0, 0.1]
    result[unprofitable] = 0.1 * clamp01((sharpe[unprofitable] + 2.0) / 2.0)

    # Profitable: [0.1, 1.0] based on composite
    result[profitable] = 0.1 + 0.9 * composite[profitable]

    return result


def formula_sharpe_dominant(sharpe, composite):
    """Increase sharpe weight to 0.50, reduce others proportionally.
    Recompute composite with new weights.
    But we don't have individual components, so approximate:
    original composite = 0.25*s_sharpe + 0.75*rest
    new = 0.50*s_sharpe + 0.50*rest
    rest = (composite - 0.25*s_sharpe) / 0.75
    """
    s_sharpe = clamp01((sharpe + 1.0) / 4.0)
    rest = (composite - 0.25 * s_sharpe) / 0.75
    rest = np.clip(rest, 0, 1)
    return 0.50 * s_sharpe + 0.50 * rest


def formula_zero_floor_sharpe(sharpe, composite):
    """Change sharpe normalization to [0, 3] instead of [-1, 3].
    Negative sharpe → 0 contribution from sharpe component.
    Recompute with modified sharpe component.
    """
    s_sharpe_old = clamp01((sharpe + 1.0) / 4.0)
    s_sharpe_new = clamp01(sharpe / 3.0)
    rest = (composite - 0.25 * s_sharpe_old) / 0.75
    rest = np.clip(rest, 0, 1)
    return 0.25 * s_sharpe_new + 0.75 * rest


def formula_multiplicative(sharpe, composite):
    """Multiplicative: score = sharpe_quality * composite.
    sharpe_quality = clamp01(sharpe / 1.0) — only positive sharpe contributes.
    """
    sharpe_quality = clamp01(sharpe / 1.0)
    return sharpe_quality * composite


def evaluate_formula(name, scores, sharpe, n_top=20):
    """Evaluate a formula variant with objective metrics."""
    valid = np.isfinite(scores) & np.isfinite(sharpe)
    scores = scores[valid]
    sharpe_v = sharpe[valid]

    if len(scores) == 0:
        return None

    rank = np.argsort(-scores)
    top_idx = rank[:n_top]
    top_sharpe = sharpe_v[top_idx]

    # Key metrics
    metrics = {
        "name": name,
        # What % of top-N have positive sharpe (profitable)?
        "top_n_pct_profitable": 100 * np.mean(top_sharpe > 0),
        # Mean sharpe of top-N candidates
        "top_n_mean_sharpe": float(np.mean(top_sharpe)),
        # Min sharpe in top-N (worst case)
        "top_n_min_sharpe": float(np.min(top_sharpe)),
        # Max sharpe in top-N (best case)
        "top_n_max_sharpe": float(np.max(top_sharpe)),
        # Mean composite of top-N (are we still selecting robust ones?)
        "top_n_mean_composite_orig": float(np.mean(scores[top_idx])),
        # Score spread (good for optimizer gradient)
        "score_spread": float(np.std(scores)),
        # How many unique score values? (diversity)
        "unique_scores_pct": 100 * len(np.unique(np.round(scores, 4))) / len(scores),
        # Correlation with sharpe (should be positive and moderate)
        "corr_with_sharpe": float(np.corrcoef(scores, sharpe_v)[0, 1]) if len(scores) > 1 else 0,
    }
    return metrics


def main():
    print("Loading comparison data...")
    sharpe, composite = collect_paired_scores()
    valid = np.isfinite(sharpe) & np.isfinite(composite)
    sharpe = sharpe[valid]
    composite = composite[valid]
    print(f"Candidates: {len(sharpe)}")
    print(f"Sharpe range: [{sharpe.min():.4f}, {sharpe.max():.4f}]")
    print(f"Composite range: [{composite.min():.4f}, {composite.max():.4f}]")
    print(f"Pct with positive sharpe: {100*np.mean(sharpe > 0):.1f}%")
    print(f"Pct with sharpe > 0.1: {100*np.mean(sharpe > 0.1):.1f}%")

    # Distribution analysis
    print(f"\n{'='*70}")
    print("  SHARPE DISTRIBUTION")
    print(f"{'='*70}")
    for threshold in [-2, -1, -0.5, 0, 0.1, 0.2, 0.3, 0.5]:
        pct = 100 * np.mean(sharpe > threshold)
        print(f"  Sharpe > {threshold:5.1f}: {pct:6.1f}% ({int(np.sum(sharpe > threshold)):5d} candidates)")

    # Test all formula variants
    formulas = [
        ("A: Current composite", formula_current(sharpe, composite)),
        ("B: Hard gate (sharpe<=0 = 0)", formula_hard_gate(sharpe, composite)),
        ("C: Soft gate (sigmoid)", formula_soft_gate(sharpe, composite)),
        ("D: Tiered [0-0.1|0.1-1.0]", formula_tiered(sharpe, composite)),
        ("E: Sharpe weight 0.50", formula_sharpe_dominant(sharpe, composite)),
        ("F: Sharpe floor [0,3]", formula_zero_floor_sharpe(sharpe, composite)),
        ("G: Multiplicative", formula_multiplicative(sharpe, composite)),
    ]

    N = 20
    print(f"\n{'='*70}")
    print(f"  FORMULA COMPARISON (top-{N} analysis)")
    print(f"{'='*70}")

    results = []
    for name, scores in formulas:
        m = evaluate_formula(name, scores, sharpe, N)
        if m:
            results.append(m)

    # Print comparison table
    headers = [
        ("Formula", "name", "<35"),
        ("%Profit", "top_n_pct_profitable", ">7.0f"),
        ("MnSharpe", "top_n_mean_sharpe", ">9.4f"),
        ("MinShp", "top_n_min_sharpe", ">7.4f"),
        ("MaxShp", "top_n_max_sharpe", ">7.4f"),
        ("Spread", "score_spread", ">7.4f"),
        ("Corr(S)", "corr_with_sharpe", ">8.4f"),
    ]

    header_line = "  ".join(f"{h:{fmt[1:].replace('f','').replace('.','').replace('0','').replace('4','')}s}" if 's' not in fmt else f"{h:{fmt}}" for h, _, fmt in headers)
    # Just build it manually
    print(f"\n  {'Formula':<35} {'%Prof':>6} {'MnShp':>9} {'MinShp':>7} {'MaxShp':>7} {'Spread':>7} {'Corr':>8}")
    print(f"  {'-'*80}")
    for m in results:
        print(f"  {m['name']:<35} {m['top_n_pct_profitable']:>5.0f}% "
              f"{m['top_n_mean_sharpe']:>9.4f} {m['top_n_min_sharpe']:>7.4f} "
              f"{m['top_n_max_sharpe']:>7.4f} {m['score_spread']:>7.4f} "
              f"{m['corr_with_sharpe']:>8.4f}")

    # Detailed top-20 for best variants
    print(f"\n{'='*70}")
    print(f"  TOP-{N} DETAILS FOR PROMISING VARIANTS")
    print(f"{'='*70}")

    for name, scores in formulas:
        m = evaluate_formula(name, scores, sharpe, N)
        if m and m["top_n_pct_profitable"] >= 80:  # Show variants where >=80% top-N are profitable
            rank = np.argsort(-scores)
            print(f"\n--- {name} ---")
            print(f"  {'#':>3} {'Score':>10} {'Sharpe':>10} {'Composite':>10}")
            for i in range(N):
                idx = rank[i]
                print(f"  {i+1:3d} {scores[idx]:10.4f} {sharpe[idx]:10.4f} {composite[idx]:10.4f}")

    # RECOMMENDATION
    print(f"\n{'='*70}")
    print(f"  RECOMMENDATION")
    print(f"{'='*70}")

    # Find best: highest mean sharpe in top-20 while maintaining reasonable spread
    best = max(results, key=lambda m: (
        m["top_n_pct_profitable"],  # primary: all top candidates profitable
        m["top_n_mean_sharpe"],     # secondary: highest mean sharpe
        m["score_spread"],          # tertiary: good gradient for optimizer
    ))
    print(f"\n  Best formula: {best['name']}")
    print(f"  - Top-{N} profitability: {best['top_n_pct_profitable']:.0f}%")
    print(f"  - Top-{N} mean Sharpe:   {best['top_n_mean_sharpe']:.4f}")
    print(f"  - Score spread (std):     {best['score_spread']:.4f}")
    print(f"  - Correlation w/ Sharpe:  {best['corr_with_sharpe']:.4f}")


if __name__ == "__main__":
    main()
