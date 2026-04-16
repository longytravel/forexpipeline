"""Among profitable candidates only, does composite ranking differ from Sharpe?
This answers: do we even need composite, or is Sharpe alone sufficient?
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src" / "python"))

import numpy as np
import pyarrow.ipc as ipc

PROJECT_ROOT = Path(__file__).resolve().parent.parent
COMPARISON_DIR = PROJECT_ROOT / "artifacts" / "ma-crossover" / "v001" / "score-mode-comparison"


def collect_paired_scores():
    sharpe_scores, composite_scores = {}, {}
    for mode, store in [("sharpe", sharpe_scores), ("composite", composite_scores)]:
        mode_dir = COMPARISON_DIR / mode
        for f in sorted(mode_dir.rglob("scores.arrow")):
            r = ipc.open_file(str(f))
            t = r.read_all()
            key = str(f.relative_to(mode_dir).parent)
            store[key] = t.column("score").to_pylist()
    s_all, c_all = [], []
    for key in sorted(set(sharpe_scores) & set(composite_scores)):
        s, c = sharpe_scores[key], composite_scores[key]
        if len(s) == len(c):
            s_all.extend(s)
            c_all.extend(c)
    return np.array(s_all), np.array(c_all)


def main():
    sharpe, composite = collect_paired_scores()
    valid = np.isfinite(sharpe) & np.isfinite(composite)
    sharpe, composite = sharpe[valid], composite[valid]

    # Filter to profitable only
    profitable = sharpe > 0
    s = sharpe[profitable]
    c = composite[profitable]
    print(f"Profitable candidates: {len(s)} / {len(sharpe)} ({100*len(s)/len(sharpe):.1f}%)")

    # Rankings among profitable
    s_rank = np.argsort(-s)
    c_rank = np.argsort(-c)

    # Correlation among profitable only
    from scipy.stats import spearmanr
    rho, p = spearmanr(s, c)
    print(f"\nAmong profitable candidates:")
    print(f"  Spearman rho: {rho:.4f} (p={p:.2e})")
    print(f"  Pearson:      {np.corrcoef(s, c)[0,1]:.4f}")

    # Top-20 overlap
    N = 20
    s_top = set(int(x) for x in s_rank[:N])
    c_top = set(int(x) for x in c_rank[:N])
    overlap = s_top & c_top
    print(f"  Top-{N} overlap: {len(overlap)}/{N}")

    # Show side by side
    print(f"\n{'='*80}")
    print(f"  SIDE-BY-SIDE: Top-{N} among profitable candidates")
    print(f"{'='*80}")
    print(f"\n  {'--- Ranked by Sharpe ---':<40} {'--- Ranked by Composite ---'}")
    print(f"  {'#':>3} {'Sharpe':>8} {'Comp':>8} {'CRank':>6}   {'#':>3} {'Comp':>8} {'Sharpe':>8} {'SRank':>6}")

    c_rank_map = {int(idx): rank for rank, idx in enumerate(c_rank)}
    s_rank_map = {int(idx): rank for rank, idx in enumerate(s_rank)}

    for i in range(N):
        si = int(s_rank[i])
        ci = int(c_rank[i])
        print(f"  {i+1:3d} {s[si]:8.4f} {c[si]:8.4f} {c_rank_map[si]+1:6d}   "
              f"{i+1:3d} {c[ci]:8.4f} {s[ci]:8.4f} {s_rank_map[ci]+1:6d}")

    # The key question: among profitable, what does composite add?
    # Show candidates that composite ranks high but Sharpe ranks low
    print(f"\n{'='*80}")
    print(f"  COMPOSITE PICKS THAT SHARPE MISSES (in top-50 composite, bottom-50% by Sharpe)")
    print(f"{'='*80}")
    mid_sharpe = len(s) // 2
    comp_top50 = set(int(x) for x in c_rank[:50])
    sharpe_bottom = set(int(x) for x in s_rank[mid_sharpe:])
    disagreements = comp_top50 & sharpe_bottom
    print(f"  Candidates in composite top-50 but Sharpe bottom-half: {len(disagreements)}")
    if disagreements:
        print(f"\n  {'Idx':>5} {'Sharpe':>8} {'ShpRank':>8} {'Composite':>10} {'CompRank':>9}")
        for idx in sorted(disagreements, key=lambda x: -c[x])[:15]:
            print(f"  {idx:5d} {s[idx]:8.4f} {s_rank_map[idx]+1:8d} {c[idx]:10.4f} {c_rank_map[idx]+1:9d}")

    # Sharpe picks that composite rejects
    print(f"\n{'='*80}")
    print(f"  SHARPE PICKS THAT COMPOSITE REJECTS (in top-50 Sharpe, bottom-50% by composite)")
    print(f"{'='*80}")
    sharpe_top50 = set(int(x) for x in s_rank[:50])
    comp_bottom = set(int(x) for x in c_rank[mid_sharpe:])
    sharpe_only = sharpe_top50 & comp_bottom
    print(f"  Candidates in Sharpe top-50 but Composite bottom-half: {len(sharpe_only)}")
    if sharpe_only:
        print(f"\n  {'Idx':>5} {'Sharpe':>8} {'ShpRank':>8} {'Composite':>10} {'CompRank':>9}")
        for idx in sorted(sharpe_only, key=lambda x: -s[x])[:15]:
            print(f"  {idx:5d} {s[idx]:8.4f} {s_rank_map[idx]+1:8d} {c[idx]:10.4f} {c_rank_map[idx]+1:9d}")

    # Bottom line
    print(f"\n{'='*80}")
    print(f"  BOTTOM LINE")
    print(f"{'='*80}")

    # Among profitable, how correlated are they?
    if rho > 0.8:
        print(f"\n  rho={rho:.2f}: Sharpe and composite agree strongly among profitable candidates.")
        print(f"  Composite adds little -- Sharpe alone is sufficient with a hard gate.")
        print(f"  RECOMMENDATION: Use Sharpe with profitability gate (simplest).")
    elif rho > 0.5:
        print(f"\n  rho={rho:.2f}: Moderate agreement -- composite adds some differentiation.")
        print(f"  Composite favors more balanced strategies (better R2, PF, lower DD).")
        print(f"  RECOMMENDATION: Use composite with hard gate (best of both worlds).")
    else:
        print(f"\n  rho={rho:.2f}: Weak agreement -- composite significantly reshuffles rankings.")
        print(f"  Need to determine which ranking produces better OOS survival.")
        print(f"  RECOMMENDATION: Run both through gauntlet to compare pass rates.")


if __name__ == "__main__":
    main()
