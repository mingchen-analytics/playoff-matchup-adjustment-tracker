"""Hero figure for the README: the Wembanyama G1 -> G2 decomposition.

    python -m research.make_hero_figure

Reads research/results (no recomputation) and writes docs/figures/.
"""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from research.data import RESULTS, ROOT  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e4e3df"
OVERLAP = "#2a78d6"     # categorical slot 1
ASSIGNMENT = "#eb6834"  # categorical slot 2
ENTRY = "#b4b2a9"       # neutral
OUT = ROOT / "docs" / "figures" / "wembanyama_g1_g2.png"
SHORT = {"Isaiah Hartenstein": "Hartenstein", "Alex Caruso": "Caruso",
         "Jalen Williams": "J. Williams", "Luguentz Dort": "Dort",
         "Chet Holmgren": "Holmgren"}


def main():
    case = json.loads((RESULTS / "case_wembanyama_g1_g2.json").read_text())
    noise = json.loads((RESULTS / "noise_summary.json").read_text())["case_wembanyama_g1_g2"]
    detail = pd.read_csv(RESULTS / "case_wembanyama_g1_g2.csv").head(5)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10.5,
                         "axes.edgecolor": GRID, "axes.labelcolor": MUTED,
                         "xtick.color": MUTED, "ytick.color": INK})
    fig, (top, bottom) = plt.subplots(
        2, 1, figsize=(9, 6.4), gridspec_kw={"height_ratios": [1, 3.2], "hspace": 0.55},
        facecolor=SURFACE)
    fig.text(0.03, 0.965, "OKC's Game 2 change on Wembanyama: half rotation, half assignment",
             fontsize=14, fontweight="bold", color=INK, va="top")
    fig.text(0.03, 0.915, "2026 West finals, Game 1 → Game 2. Overlap = who shared the floor with him; "
             "assignment = who guarded him when both were on.", fontsize=10, color=MUTED, va="top")

    # Top: total redistribution vs. the sampling-noise band
    top.set_facecolor(SURFACE)
    left = 0.0
    for value, color, label in ((case["overlap"], OVERLAP, "Overlap"),
                                (case["assignment"], ASSIGNMENT, "Assignment"),
                                (case["entry_exit"], ENTRY, "Entry/exit")):
        top.barh(0, value, left=left, height=0.5, color=color, edgecolor=SURFACE, linewidth=2)
        if value > 0.05:
            top.text(left + value / 2, 0, f"{label} {value:.2f}", ha="center", va="center",
                     color="white", fontsize=10, fontweight="bold")
        left += value
    top.axvspan(0, noise["null_median_time"], ymin=0.05, ymax=0.95, color=GRID, zorder=0)
    top.text(noise["null_median_time"] / 2, -0.52, f"typical noise ({noise['null_median_time']:.2f})", ha="center",
             va="top", fontsize=9, color=MUTED)
    top.text(left + 0.012, 0, f"{case['tvd']:.3f}", va="center", fontsize=11,
             fontweight="bold", color=INK)
    top.set_xlim(0, 0.75)
    top.set_ylim(-0.75, 0.45)
    top.set_yticks([])
    top.set_xlabel("Total change in matchup allocation (TVD, 0 = identical, 1 = completely different)",
                   fontsize=9.5)
    for side in ("top", "right", "left"):
        top.spines[side].set_visible(False)

    # Bottom: per-defender signed contributions, in percentage points
    bottom.set_facecolor(SURFACE)
    rows = list(range(len(detail)))[::-1]
    for y, row in zip(rows, detail.itertuples()):
        pos, neg = 0.0, 0.0
        for value, color in ((row.overlap * 100, OVERLAP), (row.assignment * 100, ASSIGNMENT)):
            start = pos if value >= 0 else neg
            bottom.barh(y, value, left=start, height=0.62, color=color,
                        edgecolor=SURFACE, linewidth=2)
            if value >= 0:
                pos += value
            else:
                neg += value
        net = row.share_change * 100
        bottom.plot([net, net], [y - 0.42, y + 0.42], color=INK, linewidth=2.2, zorder=5)
        edge = pos if net >= 0 else neg
        bottom.text(edge + (1.2 if net >= 0 else -1.2), y, f"{net:+.1f} pp",
                    ha="left" if net >= 0 else "right", va="center", fontsize=10, color=INK)
    bottom.axvline(0, color=MUTED, linewidth=1)
    bottom.set_yticks(rows)
    bottom.set_yticklabels([
        f"{SHORT.get(n, n)}  {b * 100:.0f}% → {a * 100:.0f}%"
        for n, b, a in zip(detail.def_player, detail.share_before, detail.share_after)
    ])
    bottom.set_xlim(-45, 75)
    bottom.set_xlabel("Change in share of Wembanyama's matchup time (percentage points)", fontsize=9.5)
    bottom.grid(axis="x", color=GRID, linewidth=0.8)
    bottom.set_axisbelow(True)
    for side in ("top", "right", "left"):
        bottom.spines[side].set_visible(False)
    bottom.tick_params(axis="y", length=0)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in (OVERLAP, ASSIGNMENT)]
    handles.append(plt.Line2D([0], [0], color=INK, linewidth=2.2))
    bottom.legend(handles, ["Overlap / rotation", "Assignment", "Net change"], loc="lower right",
                  frameon=False, fontsize=10)
    fig.text(0.03, 0.015,
             f"Above sampling noise on both time and possession bases (model-based league q ≈ "
             f"{noise['q_value_league_time']:.3f}). Source: NBA BoxScoreMatchupsV3; "
             "research/FINDINGS.md.", fontsize=8.5, color=MUTED)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=160, facecolor=SURFACE, bbox_inches="tight")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
