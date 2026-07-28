"""Render the intake coding-quality figure.

Reads the extracts produced by intake_quality.py and writes a single
publication-quality PNG/SVG to outputs/figures/.
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import FancyBboxPatch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLEAU = os.path.join(ROOT, "outputs", "tableau")
FIGURES = os.path.join(ROOT, "outputs", "figures")

# Palette: one accent hue for the finding, neutral grey for context.
# Bar length already encodes magnitude, so colouring every bar by its own
# value would be redundant encoding. Grey + one accent directs the eye instead.
ACCENT = "#2a78d6"
NEUTRAL = "#c2ccd6"
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#8a8a84"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
})

GROUP_LABELS = {
    "MMTA_CARDIAC": "MMTA – Cardiac", "MMTA_ENDO": "MMTA – Endocrine",
    "MMTA_RESP": "MMTA – Respiratory", "WOUND": "Wound",
    "MS_REHAB": "MS Rehab", "MMTA_GI_GU": "MMTA – GI/GU",
    "NEURO_REHAB": "Neuro Rehab", "BEHAVE_HEALTH": "Behavioral Health",
    "MMTA_OTHER": "MMTA – Other", "MMTA_INFECT": "MMTA – Infectious",
    "COMPLEX": "Complex", "MMTA_AFTER": "MMTA – Surgical Aftercare",
}


def rounded_barh(ax, y, width, height, color, radius=0.28):
    """Horizontal bar with a rounded data-end, anchored flat at the baseline."""
    if width <= 0:
        return
    r = min(radius, height / 2, width / 2)
    box = FancyBboxPatch(
        (0, y - height / 2), max(width - r, 1e-9), height,
        boxstyle=f"round,pad=0,rounding_size={r}",
        linewidth=0, facecolor=color, mutation_aspect=1 / 40,
    )
    ax.add_patch(box)


def bar_panel(ax, labels, values, note_values, title, highlight_index=0):
    """Horizontal bars with the category on the axis and one combined label.

    Rate and count go in a single string at the bar end -- two separate label
    columns collide as soon as a bar is long.
    """
    n = len(labels)
    positions = list(range(n - 1, -1, -1))
    vmax = max(values)

    ax.set_title(title, loc="left", fontsize=12, fontweight="600",
                 color=INK, pad=12)

    for pos, value, note, i in zip(positions, values, note_values,
                                   range(n)):
        color = ACCENT if i == highlight_index else NEUTRAL
        rounded_barh(ax, pos, value, 0.6, color)
        ax.text(value + vmax * 0.025, pos,
                f"{value:.1f}%   {note:,.0f} codes",
                ha="left", va="center", fontsize=9,
                fontweight="600" if i == highlight_index else "normal",
                color=INK if i == highlight_index else INK_SECONDARY)

    ax.set_yticks(positions)
    ax.set_yticklabels(labels, fontsize=9.5, color=INK_SECONDARY)
    ax.tick_params(axis="y", length=0, pad=6)
    ax.set_xlim(0, vmax * 1.62)
    ax.set_ylim(-0.7, n - 0.3)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xticks([])


def main():
    os.makedirs(FIGURES, exist_ok=True)

    gates = pd.read_csv(os.path.join(TABLEAU, "06_intake_coding_gates.csv"))
    difficulty = pd.read_csv(os.path.join(TABLEAU,
                                          "07_coding_difficulty_by_group.csv"))

    clean = gates.loc[gates["gate"] == "Clean as PDGM primary"].iloc[0]
    fails = (gates.loc[gates["gate"] != "Clean as PDGM primary"]
             .sort_values("pct_of_all_codes", ascending=False)
             .reset_index(drop=True))

    difficulty = difficulty.sort_values("pct_with_pitfall", ascending=False)
    difficulty = difficulty.reset_index(drop=True)
    difficulty["label"] = difficulty["clinical_group"].map(GROUP_LABELS)

    fig = plt.figure(figsize=(13.2, 7.4), dpi=160)
    gs = fig.add_gridspec(
        2, 3, height_ratios=[0.16, 1.0], width_ratios=[0.80, 1.15, 1.15],
        left=0.035, right=0.985, top=0.88, bottom=0.085,
        hspace=0.05, wspace=0.42,
    )

    # ---- headline -------------------------------------------------------
    fig.text(0.035, 0.955, "Only 54% of ICD-10 codes can anchor a PDGM episode",
             fontsize=20, fontweight="700", color=INK, va="top")
    fig.text(0.035, 0.912,
             "Every primary diagnosis must clear seven independent gates. "
             "Difficulty is not evenly distributed across clinical groups.",
             fontsize=10.5, color=INK_SECONDARY, va="top")

    # ---- hero number ----------------------------------------------------
    ax_kpi = fig.add_subplot(gs[1, 0])
    ax_kpi.axis("off")
    ax_kpi.text(0, 0.80, f"{clean['pct_of_all_codes']:.1f}%", fontsize=50,
                fontweight="700", color=ACCENT, ha="left", va="center")
    ax_kpi.text(0, 0.655, "usable as a primary diagnosis", fontsize=11,
                color=INK, ha="left", va="center")
    ax_kpi.text(0, 0.595, f"{clean['codes_failing']:,.0f} of 74,719 codes",
                fontsize=9.5, color=INK_MUTED, ha="left", va="center")
    ax_kpi.text(0, 0.44,
                "The remaining 46% fail at least\n"
                "one gate and cannot anchor an\n"
                "episode without correction.",
                fontsize=9.5, color=INK_SECONDARY, ha="left", va="top",
                linespacing=1.55)
    ax_kpi.set_xlim(0, 1)
    ax_kpi.set_ylim(0, 1)

    # ---- gates ----------------------------------------------------------
    ax_gates = fig.add_subplot(gs[1, 1])
    bar_panel(
        ax_gates,
        labels=list(fails["gate"]),
        values=list(fails["pct_of_all_codes"]),
        note_values=list(fails["codes_failing"]),
        title="Why codes fail",
        highlight_index=0,
    )

    # ---- difficulty -----------------------------------------------------
    ax_diff = fig.add_subplot(gs[1, 2])
    bar_panel(
        ax_diff,
        labels=list(difficulty["label"]),
        values=list(difficulty["pct_with_pitfall"]),
        note_values=list(difficulty["codes"]),
        title="Coding difficulty varies 10× across clinical groups",
        highlight_index=0,
    )

    # ---- footer ---------------------------------------------------------
    fig.text(0.035, 0.022,
             "Source: CMS CY2026 HH PPS final rule (CMS-1828-F) and the CCFTF "
             "PDGM diagnosis mapping, 74,719 codes.  "
             "Pitfall = unspecified, manifestation, or code-first requirement.  "
             "No patient data.",
             fontsize=8.5, color=INK_MUTED, va="bottom")

    png = os.path.join(FIGURES, "01_intake_coding_quality.png")
    fig.savefig(png, dpi=160)
    fig.savefig(os.path.join(FIGURES, "01_intake_coding_quality.svg"))
    plt.close(fig)
    print("wrote", png)


if __name__ == "__main__":
    main()
