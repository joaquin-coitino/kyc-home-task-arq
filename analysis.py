"""
KYC Analysis — ARQ Home Task
Generates a self-contained HTML report with embedded charts.
Open the output HTML in a browser and use Print → Save as PDF.
"""

import base64
import io
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd

warnings.filterwarnings("ignore")

# ── Config ──────────────────────────────────────────────────────────────────
REPO = Path(__file__).parent
DETAILS_CSV = REPO / "KYC_details.csv"
SUMMARY_CSV = REPO / "KYC_summary.csv"
OUTPUT_HTML = REPO / "kyc_report.html"

BRAND_BLUE = "#1A4FBA"
BRAND_DARK = "#0D2A6B"
PASS_GREEN = "#22C55E"
WARN_AMBER = "#F59E0B"
FAIL_RED   = "#EF4444"
GRAY       = "#6B7280"
LIGHT_GRAY = "#F3F4F6"

plt.rcParams.update({
    "font.family": "sans-serif",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.titlesize": 13,
    "axes.titleweight": "bold",
    "axes.titlepad": 10,
})

# ── Helpers ──────────────────────────────────────────────────────────────────
def fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()

def img_tag(b64: str, width: str = "100%") -> str:
    return f'<img src="data:image/png;base64,{b64}" style="width:{width};max-width:900px;">'

def pct(n, total) -> str:
    return f"{n:,} ({n/total*100:.1f}%)"

# ── Load & clean data ────────────────────────────────────────────────────────
details = pd.read_csv(DETAILS_CSV)
summary = pd.read_csv(SUMMARY_CSV)

# Normalise non-standard decision labels in both datasets
label_map = {"OK": "PASSED", "APPROVED": "PASSED", "PASSES": "PASSED"}
details["decision_label"] = details["decision_label"].replace(label_map)
summary["decision_type"]  = summary["decision_type"].replace(label_map)

# Parse dates on summary before merge
summary["date"] = pd.to_datetime(summary["date_"], utc=True)
summary["week"] = summary["date"].dt.to_period("W")
summary["day"]  = summary["date"].dt.date

# Merge: one row per user, details provides check-level columns, summary provides
# the authoritative outcome (decision_type) and date information
df = details.merge(
    summary[["user_reference", "decision_type", "date", "week", "day"]],
    on="user_reference",
    how="inner",
)

# Computed columns
df["age"] = 2023 - df["year_birth"]

CHECKS = [
    ("usability_decision",           "Usability"),
    ("image_checks_decision",        "Image Checks"),
    ("extraction_decision",          "Extraction"),
    ("data_checks_decision",         "Data Checks"),
    ("liveness_decision",            "Liveness"),
    ("similarity_decision",          "Similarity"),
    ("watchlist_screening_decision", "Watchlist"),
]

# ── Core metrics — use decision_type (summary) as authoritative outcome ───────
total       = len(df)
n_passed    = (df["decision_type"] == "PASSED").sum()
n_rejected  = (df["decision_type"] == "REJECTED").sum()
n_warning   = (df["decision_type"] == "WARNING").sum()
pass_rate   = n_passed / total * 100
date_min    = df["date"].min().strftime("%b %d, %Y")
date_max    = df["date"].max().strftime("%b %d, %Y")

# ── First failing check attribution ─────────────────────────────────────────
rejected_df = df[df["decision_type"] == "REJECTED"].copy()

def first_fail(row):
    # Usability is the root — always runs first
    if row["usability_decision"] == "REJECTED":
        return "usability_decision"

    # Extraction depends on Usability.
    # If extraction did not execute despite usability passing → extraction was blocked.
    if row["extraction_decision"] == "NOT_EXECUTED":
        if row["usability_decision"] == "PASSED":
            return "extraction_blocked"        # extraction failed to run
        if row["usability_decision"] == "WARNING":
            return "usability_warning_blocked" # usability warning cascaded downstream
        return "usability_not_executed"        # usability itself didn't run

    # Image Checks depends on Usability + Extraction
    if row["image_checks_decision"] == "REJECTED":
        return "image_checks_decision"

    # Data Checks depends on Usability + Extraction + Image Checks
    if row["data_checks_decision"] == "REJECTED":
        return "data_checks_decision"

    # Liveness depends only on selfie Usability — independent of doc chain
    if row["liveness_decision"] == "REJECTED":
        return "liveness_decision"

    # Similarity depends on Usability only for face detectability — mostly independent
    if row["similarity_decision"] == "REJECTED":
        return "similarity_decision"

    return "other"

rejected_df["first_fail"] = rejected_df.apply(first_fail, axis=1)
fail_counts = rejected_df["first_fail"].value_counts()

# Pre-compute failure category totals used across multiple HTML sections
n_extraction_blocked = fail_counts.get("extraction_blocked", 0)
n_usability_warn     = fail_counts.get("usability_warning_blocked", 0)
n_usability_noexec   = fail_counts.get("usability_not_executed", 0)
n_usability          = fail_counts.get("usability_decision", 0)
n_image              = fail_counts.get("image_checks_decision", 0)
n_liveness           = fail_counts.get("liveness_decision", 0)
n_similarity         = fail_counts.get("similarity_decision", 0)
n_datachecks         = fail_counts.get("data_checks_decision", 0)
n_pipeline_blocked   = n_extraction_blocked + n_usability_warn + n_usability_noexec

fail_labels_map = {
    "usability_decision":           "Usability\n(hard reject)",
    "usability_warning_blocked":    "Usability Warning\n(blocked downstream)",
    "usability_not_executed":       "Usability\n(not executed)",
    "extraction_blocked":           "Extraction\n(blocked despite usability pass)",
    "image_checks_decision":        "Image Checks",
    "liveness_decision":            "Liveness",
    "similarity_decision":          "Similarity",
    "data_checks_decision":         "Data Checks",
    "other":                        "Other",
}

# ── Weekly trend ─────────────────────────────────────────────────────────────
weekly = df.groupby("week")["decision_type"].value_counts().unstack(fill_value=0)
for col in ["PASSED", "REJECTED", "WARNING"]:
    if col not in weekly.columns:
        weekly[col] = 0
weekly["total"] = weekly.sum(axis=1)
weekly["rejection_rate"] = weekly["REJECTED"] / weekly["total"] * 100
weekly.index = [str(p) for p in weekly.index]

# Pre-compute spike/baseline variables used in multiple sections
spike_weeks   = ["2023-08-21/2023-08-27", "2023-08-28/2023-09-03"]
spike_rates   = [weekly.loc[w, "rejection_rate"] for w in spike_weeks if w in weekly.index]
baseline_rate = weekly["rejection_rate"].iloc[:4].mean()

# ── Pass rate by doc type ────────────────────────────────────────────────────
doc_stats = df.groupby("data_type").apply(
    lambda g: pd.Series({
        "total": len(g),
        "passed": (g["decision_type"] == "PASSED").sum(),
    })
).reset_index()
doc_stats["pass_rate"] = doc_stats["passed"] / doc_stats["total"] * 100
doc_stats = doc_stats.sort_values("pass_rate")

# ── Pass rate by country ──────────────────────────────────────────────────────
country_stats = df.groupby("data_issuing_country").apply(
    lambda g: pd.Series({
        "total": len(g),
        "passed": (g["decision_type"] == "PASSED").sum(),
    })
).reset_index()
country_stats["pass_rate"] = country_stats["passed"] / country_stats["total"] * 100

# ── Sub-type pass rates ───────────────────────────────────────────────────────
sub_stats = df.groupby(["data_issuing_country", "data_sub_type"]).apply(
    lambda g: pd.Series({"total": len(g), "passed": (g["decision_type"] == "PASSED").sum()})
).reset_index()
sub_stats["pass_rate"] = sub_stats["passed"] / sub_stats["total"] * 100
sub_stats = sub_stats[sub_stats["total"] >= 50]

# ── Failure reason breakdowns ─────────────────────────────────────────────────
def reasons_by_decision(col_decision, col_details, decision_type,
                         exclude=("OK", "PRECONDITION_NOT_FULFILLED"), top=8):
    """Return top detail labels for a specific check decision (REJECTED or WARNING)."""
    mask = df[col_decision] == decision_type
    result = df[mask][col_details].value_counts()
    result = result[~result.index.isin(exclude)]
    return result.head(top)

# Usability split by check decision
usability_rejected_reasons = reasons_by_decision(
    "usability_decision", "usability_decision_details", "REJECTED")
usability_warning_reasons  = reasons_by_decision(
    "usability_decision", "usability_decision_details", "WARNING",
    exclude=("OK", "PRECONDITION_NOT_FULFILLED", "liveness_UNDETERMINED"))  # exclude misrouted liveness label

image_reasons      = reasons_by_decision("image_checks_decision", "image_checks_decision_details", "REJECTED")
liveness_reasons   = reasons_by_decision("liveness_decision",     "liveness_decision_details",     "REJECTED")
similarity_reasons = reasons_by_decision("similarity_decision",   "similarity_decision_details",   "REJECTED",
                                          exclude=("OK", "PRECONDITION_NOT_FULFILLED", "MATCH"))

# ── Daily volume ──────────────────────────────────────────────────────────────
daily = df.groupby("day")["decision_type"].value_counts().unstack(fill_value=0)
for col in ["PASSED", "REJECTED", "WARNING"]:
    if col not in daily.columns:
        daily[col] = 0
daily["total"] = daily.sum(axis=1)
daily["rejection_rate"] = daily["REJECTED"] / daily["total"] * 100

# ── Anomaly Investigation computations ───────────────────────────────────────
rejected_df["is_pipeline_blocked"] = rejected_df["first_fail"].isin(
    ["extraction_blocked", "usability_warning_blocked", "usability_not_executed"])
rejected_df["week_str"] = rejected_df["week"].astype(str)

# Weekly rejection composition
_wbc = rejected_df.groupby("week_str")["is_pipeline_blocked"].agg(["sum", "count"]).rename(
    columns={"sum": "pipeline_blocked", "count": "total_rejected"})
_wbc["hard_fail"] = _wbc["total_rejected"] - _wbc["pipeline_blocked"]
weekly_blocked_by_week = _wbc.reindex(weekly.index, fill_value=0)

# Spike vs baseline pipeline blockage share
_spike_keys = [w for w in weekly_blocked_by_week.index if "08-21" in w or "08-28" in w]
_base_keys  = list(weekly_blocked_by_week.index[:4])
spike_blocked_pct    = (weekly_blocked_by_week.loc[_spike_keys, "pipeline_blocked"].sum() /
                        weekly_blocked_by_week.loc[_spike_keys, "total_rejected"].sum() * 100)
baseline_blocked_pct = (weekly_blocked_by_week.loc[_base_keys,  "pipeline_blocked"].sum() /
                        weekly_blocked_by_week.loc[_base_keys,  "total_rejected"].sum() * 100)

# Country rejection composition (as % of total attempts)
country_rj_comp = rejected_df.groupby("data_issuing_country")["is_pipeline_blocked"].agg(["sum", "count"]).rename(
    columns={"sum": "pipeline_blocked", "count": "total_rejected"})
country_rj_comp["hard_fail"] = country_rj_comp["total_rejected"] - country_rj_comp["pipeline_blocked"]
_country_total = df.groupby("data_issuing_country").size()
country_rj_comp["blocked_rate"] = country_rj_comp["pipeline_blocked"] / _country_total * 100
country_rj_comp["hard_rate"]    = country_rj_comp["hard_fail"]         / _country_total * 100
mex_blocked_pct = country_rj_comp.loc["MEX", "blocked_rate"]
arg_blocked_pct = country_rj_comp.loc["ARG", "blocked_rate"]

# Doc type rejection composition (ID_CARD vs PASSPORT only)
_dt_filter = rejected_df["data_type"].isin(["ID_CARD", "PASSPORT"])
doctype_rj_comp = rejected_df[_dt_filter].groupby("data_type")["is_pipeline_blocked"].agg(["sum", "count"]).rename(
    columns={"sum": "pipeline_blocked", "count": "total_rejected"})
doctype_rj_comp["hard_fail"] = doctype_rj_comp["total_rejected"] - doctype_rj_comp["pipeline_blocked"]
_dtype_total = df[df["data_type"].isin(["ID_CARD", "PASSPORT"])].groupby("data_type").size()
doctype_rj_comp["blocked_rate"] = doctype_rj_comp["pipeline_blocked"] / _dtype_total * 100
doctype_rj_comp["hard_rate"]    = doctype_rj_comp["hard_fail"]         / _dtype_total * 100
idcard_blocked_pct   = doctype_rj_comp.loc["ID_CARD",  "blocked_rate"]
passport_blocked_pct = doctype_rj_comp.loc["PASSPORT", "blocked_rate"]


# ════════════════════════════════════════════════════════════════════════════
# CHART 1 — Overall outcomes donut
# ════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(5, 4))
sizes  = [n_passed, n_rejected, n_warning]
colors = [PASS_GREEN, FAIL_RED, WARN_AMBER]
labels = [f"Passed\n{n_passed:,}", f"Rejected\n{n_rejected:,}", f"Warning\n{n_warning:,}"]
wedges, texts = ax.pie(sizes, colors=colors, startangle=90,
                       wedgeprops=dict(width=0.55))
ax.legend(wedges, labels, loc="center left", bbox_to_anchor=(0.85, 0.5), fontsize=10)
ax.set_title("Overall KYC Outcomes", pad=14)
centre = plt.Circle((0, 0), 0.35, color="white")
ax.add_patch(centre)
ax.text(0, 0, f"{pass_rate:.1f}%\npass rate", ha="center", va="center",
        fontsize=13, fontweight="bold", color=BRAND_DARK)
CHART_DONUT = fig_to_b64(fig)


# ════════════════════════════════════════════════════════════════════════════
# CHART 2 — Check dependency DAG (flowchart)
# ════════════════════════════════════════════════════════════════════════════
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch

def draw_box(ax, xy, text, color, width=1.8, height=0.55, fontsize=9.5):
    x, y = xy
    box = FancyBboxPatch((x - width/2, y - height/2), width, height,
                         boxstyle="round,pad=0.06", linewidth=1.2,
                         edgecolor=color, facecolor=color + "22")
    ax.add_patch(box)
    ax.text(x, y, text, ha="center", va="center", fontsize=fontsize,
            fontweight="bold", color=color)

def arrow(ax, src, dst, color="#9CA3AF"):
    ax.annotate("", xy=dst, xytext=src,
                arrowprops=dict(arrowstyle="-|>", color=color, lw=1.4))

# Node positions: (x, y)  — y increases upward, we'll invert
nodes = {
    "Usability":            (4.0, 5.0),
    "Extraction":           (2.5, 3.8),
    "Image Checks":         (2.5, 2.6),
    "Data Checks":          (1.2, 1.4),
    "Watchlist\nScreening": (3.8, 1.4),
    "Liveness":             (6.0, 3.8),
    "Similarity":           (7.2, 3.8),
}

# Edges: (from, to, label)
edges = [
    ("Usability",    "Extraction",           "doc"),
    ("Extraction",   "Image Checks",         "doc"),
    ("Image Checks", "Data Checks",          "doc"),
    ("Image Checks", "Watchlist\nScreening", "doc"),
    ("Usability",    "Liveness",             "selfie"),
    ("Usability",    "Similarity",           "face detect"),
]

node_colors = {
    "Usability":            BRAND_DARK,
    "Extraction":           BRAND_BLUE,
    "Image Checks":         BRAND_BLUE,
    "Data Checks":          BRAND_BLUE,
    "Watchlist\nScreening": BRAND_BLUE,
    "Liveness":             "#7C3AED",   # purple — independent branch
    "Similarity":           "#7C3AED",
}

fig, ax = plt.subplots(figsize=(10, 5))
ax.set_xlim(0, 9)
ax.set_ylim(0.6, 5.8)
ax.axis("off")
ax.set_facecolor("#FAFAFA")
fig.patch.set_facecolor("#FAFAFA")

# Draw edges first (behind boxes)
edge_colors = {"doc": BRAND_BLUE, "selfie": "#7C3AED", "face detect": "#7C3AED"}
for src, dst, etype in edges:
    sx, sy = nodes[src]
    dx, dy = nodes[dst]
    arrow(ax, (sx, sy), (dx, dy), color=edge_colors[etype])

# Edge labels
edge_label_positions = {
    ("Usability", "Liveness"):           (5.3, 4.5, "selfie\nusability"),
    ("Usability", "Similarity"):         (6.0, 4.5, "face\ndetectability"),
    ("Usability", "Extraction"):         (3.0, 4.5, ""),
}
for (src, dst), (lx, ly, lbl) in edge_label_positions.items():
    if lbl:
        ax.text(lx, ly, lbl, ha="center", va="center", fontsize=7.5,
                color="#6B7280", style="italic")

# Draw node boxes
for name, (x, y) in nodes.items():
    draw_box(ax, (x, y), name, node_colors[name])

# Legend
leg_items = [
    mpatches.Patch(facecolor=BRAND_DARK+"22", edgecolor=BRAND_DARK, label="Root check"),
    mpatches.Patch(facecolor=BRAND_BLUE+"22", edgecolor=BRAND_BLUE, label="Document chain"),
    mpatches.Patch(facecolor="#7C3AED22",     edgecolor="#7C3AED",  label="Selfie / identity checks"),
]
ax.legend(handles=leg_items, loc="lower center", ncol=3, fontsize=8.5,
          bbox_to_anchor=(0.5, -0.04), frameon=True, edgecolor="#E5E7EB")

ax.set_title("Jumio KYC Check Dependency Graph", fontsize=13, fontweight="bold",
             color=BRAND_DARK, pad=10)

plt.tight_layout()
CHART_DAG = fig_to_b64(fig)


# ════════════════════════════════════════════════════════════════════════════
# CHART 3 — First failing check bar
# ════════════════════════════════════════════════════════════════════════════
fc = fail_counts.rename(index=fail_labels_map).sort_values()

def bar_color(label):
    if "warning" in label.lower() or "blocked" in label.lower() or "not executed" in label.lower():
        return WARN_AMBER
    return FAIL_RED

colors_bar = [bar_color(l) for l in fc.index]
fig, ax = plt.subplots(figsize=(8, 4.5))
bars = ax.barh(fc.index, fc.values, color=colors_bar, edgecolor="none")
for bar in bars:
    ax.text(bar.get_width() + 30, bar.get_y() + bar.get_height()/2,
            f"{bar.get_width():,}", va="center", fontsize=9, color=GRAY)
ax.set_xlabel("Number of rejections")
ax.set_title("Root Cause of KYC Rejections (by first blocking check)")
ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
legend_items = [
    mpatches.Patch(color=FAIL_RED,   label="Hard rejection (check failed)"),
    mpatches.Patch(color=WARN_AMBER, label="Pipeline blocked (check not executed)"),
]
ax.legend(handles=legend_items, fontsize=8.5, loc="lower right")
plt.tight_layout()
CHART_FAIL_CHECK = fig_to_b64(fig)


# ════════════════════════════════════════════════════════════════════════════
# CHART 3 — Weekly rejection rate line
# ════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(9, 3.5))
x = range(len(weekly))
ax.fill_between(x, weekly["rejection_rate"], alpha=0.15, color=FAIL_RED)
ax.plot(x, weekly["rejection_rate"], color=FAIL_RED, marker="o", linewidth=2)
ax.set_xticks(list(x))
ax.set_xticklabels([w.replace("/2023-", "\n") for w in weekly.index], fontsize=8)
ax.axhline(weekly["rejection_rate"].iloc[:4].mean(), color=GRAY, linestyle="--",
           linewidth=1, label=f"Baseline avg ({weekly['rejection_rate'].iloc[:4].mean():.1f}%)")
ax.set_ylabel("Rejection rate (%)")
ax.set_title("Weekly Rejection Rate")
ax.legend(fontsize=9)
plt.tight_layout()
CHART_WEEKLY = fig_to_b64(fig)


# ════════════════════════════════════════════════════════════════════════════
# CHART 4 — Pass rate by document type
# ════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(6, 3.5))
bar_colors = [PASS_GREEN if r >= 92 else WARN_AMBER if r >= 88 else FAIL_RED
              for r in doc_stats["pass_rate"]]
bars = ax.barh(doc_stats["data_type"], doc_stats["pass_rate"],
               color=bar_colors, edgecolor="none")
ax.set_xlim(80, 100)
for bar, (_, row) in zip(bars, doc_stats.iterrows()):
    ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height()/2,
            f"{row['pass_rate']:.1f}%  (n={row['total']:,})",
            va="center", fontsize=9, color=GRAY)
ax.set_xlabel("Pass rate (%)")
ax.set_title("Pass Rate by Document Type")
plt.tight_layout()
CHART_DOC_TYPE = fig_to_b64(fig)


# ════════════════════════════════════════════════════════════════════════════
# CHART 5 — Pass rate by country
# ════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(5, 3))
bar_colors = [PASS_GREEN if r >= 92 else WARN_AMBER for r in country_stats["pass_rate"]]
bars = ax.bar(country_stats["data_issuing_country"], country_stats["pass_rate"],
              color=bar_colors, edgecolor="none", width=0.4)
ax.set_ylim(75, 100)
for bar, (_, row) in zip(bars, country_stats.iterrows()):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
            f"{row['pass_rate']:.1f}%\n(n={row['total']:,})",
            ha="center", va="bottom", fontsize=10, color=GRAY)
ax.set_ylabel("Pass rate (%)")
ax.set_title("Pass Rate by Country")
plt.tight_layout()
CHART_COUNTRY = fig_to_b64(fig)


# ════════════════════════════════════════════════════════════════════════════
# CHART 6 — Failure reasons: Usability
# ════════════════════════════════════════════════════════════════════════════
def reason_chart(series, title, color=FAIL_RED, figsize=(7, 3.5)):
    fig, ax = plt.subplots(figsize=figsize)
    bars = ax.barh(series.index, series.values, color=color, edgecolor="none")
    for bar in bars:
        ax.text(bar.get_width() + 3, bar.get_y() + bar.get_height()/2,
                f"{bar.get_width():,}", va="center", fontsize=9, color=GRAY)
    ax.set_xlabel("Count")
    ax.set_title(title)
    plt.tight_layout()
    return fig_to_b64(fig)

# Usability: two side-by-side subplots — REJECTED reasons and WARNING reasons
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4))

for ax, series, label, color in [
    (ax1, usability_rejected_reasons, "REJECTED reasons", FAIL_RED),
    (ax2, usability_warning_reasons,  "WARNING reasons",  WARN_AMBER),
]:
    bars = ax.barh(series.index, series.values, color=color, edgecolor="none")
    for bar in bars:
        ax.text(bar.get_width() + 3, bar.get_y() + bar.get_height()/2,
                f"{bar.get_width():,}", va="center", fontsize=9, color=GRAY)
    ax.set_xlabel("Count")
    ax.set_title(f"Usability — {label}", fontsize=11, fontweight="bold")

plt.suptitle("Usability Check: Failure Reasons by Decision Type", fontsize=13,
             fontweight="bold", color=BRAND_DARK, y=1.02)
plt.tight_layout()
CHART_USABILITY  = fig_to_b64(fig)

CHART_IMAGE      = reason_chart(image_reasons,      "Image Check Failure Reasons", FAIL_RED)
CHART_LIVENESS   = reason_chart(liveness_reasons,   "Liveness Failure Reasons", BRAND_BLUE)
CHART_SIMILARITY = reason_chart(similarity_reasons, "Similarity Failure Reasons", BRAND_DARK)


# ════════════════════════════════════════════════════════════════════════════
# CHART 7 — Sub-type pass rates (side-by-side MEX & ARG)
# ════════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(11, 4))
for ax, country in zip(axes, ["MEX", "ARG"]):
    sub = sub_stats[sub_stats["data_issuing_country"] == country].sort_values("pass_rate")
    bar_colors = [PASS_GREEN if r >= 92 else WARN_AMBER if r >= 88 else FAIL_RED
                  for r in sub["pass_rate"]]
    bars = ax.barh(sub["data_sub_type"], sub["pass_rate"], color=bar_colors, edgecolor="none")
    ax.set_xlim(75, 102)
    for bar, (_, row) in zip(bars, sub.iterrows()):
        ax.text(bar.get_width() + 0.2, bar.get_y() + bar.get_height()/2,
                f"{row['pass_rate']:.1f}%  n={row['total']:,}",
                va="center", fontsize=8.5, color=GRAY)
    ax.set_xlabel("Pass rate (%)")
    ax.set_title(f"{country} — Pass Rate by Document Subtype")
plt.tight_layout()
CHART_SUBTYPE = fig_to_b64(fig)


# ════════════════════════════════════════════════════════════════════════════
# CHART ANOM-A — Weekly: hard rejections vs pipeline blockages (stacked bar)
# ════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(9, 3.8))
x = range(len(weekly_blocked_by_week))
ax.bar(x, weekly_blocked_by_week["hard_fail"],
       label="Hard rejection", color=FAIL_RED, edgecolor="none")
ax.bar(x, weekly_blocked_by_week["pipeline_blocked"],
       bottom=weekly_blocked_by_week["hard_fail"],
       label="Pipeline blocked", color=WARN_AMBER, edgecolor="none")
ax.set_xticks(list(x))
ax.set_xticklabels([w.replace("/2023-", "\n") for w in weekly_blocked_by_week.index], fontsize=8)
ax.set_ylabel("Rejections")
ax.set_title("Weekly Rejection Composition: Hard Failures vs Pipeline Blockages")
ax.legend(fontsize=9)
plt.tight_layout()
CHART_ANOM_WEEKLY = fig_to_b64(fig)


# ════════════════════════════════════════════════════════════════════════════
# CHART ANOM-B — Country: pipeline vs hard rejection rates (grouped bar)
# ════════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(10, 3.5))
for ax, (df_comp, title, cats) in zip(axes, [
    (country_rj_comp, "MEX vs ARG — Rejection Composition\n(% of total attempts per country)", country_rj_comp.index.tolist()),
    (doctype_rj_comp, "ID Card vs Passport — Rejection Composition\n(% of total attempts per doc type)", doctype_rj_comp.index.tolist()),
]):
    w = 0.35
    xs = range(len(cats))
    ax.bar([i - w/2 for i in xs], df_comp["hard_rate"],    width=w, label="Hard rejection", color=FAIL_RED,   edgecolor="none")
    ax.bar([i + w/2 for i in xs], df_comp["blocked_rate"], width=w, label="Pipeline blocked", color=WARN_AMBER, edgecolor="none")
    for i, cat in enumerate(cats):
        ax.text(i - w/2, df_comp.loc[cat, "hard_rate"]    + 0.2, f"{df_comp.loc[cat, 'hard_rate']:.1f}%",    ha="center", fontsize=8.5, color=GRAY)
        ax.text(i + w/2, df_comp.loc[cat, "blocked_rate"] + 0.2, f"{df_comp.loc[cat, 'blocked_rate']:.1f}%", ha="center", fontsize=8.5, color=GRAY)
    ax.set_xticks(list(xs))
    ax.set_xticklabels(cats)
    ax.set_ylabel("% of total attempts")
    ax.set_title(title, fontsize=10)
    ax.legend(fontsize=8.5)
plt.tight_layout()
CHART_ANOM_SEGMENTS = fig_to_b64(fig)


# ════════════════════════════════════════════════════════════════════════════
# DATA QUALITY summary table
# ════════════════════════════════════════════════════════════════════════════
dq_issues = [
    ("Incorrect label casing: liveness_UNDETERMINED",
     "1,243 rows use <code>liveness_UNDETERMINED</code> (lowercase prefix) in "
     "<code>liveness_decision_details</code>. Per Jumio docs the correct label is "
     "<code>LIVENESS_UNDETERMINED</code> (all caps). The lowercase <code>liveness_</code> prefix "
     "indicates the pipeline is prepending the check name to the label — a data pipeline bug.",
     "Medium"),
    ("liveness_UNDETERMINED in usability_decision_details",
     "278 rows have <code>liveness_UNDETERMINED</code> in <code>usability_decision_details</code> "
     "with <code>usability_decision=WARNING</code>. Since Usability covers both ID and Selfie "
     "credentials, this most likely reflects the <strong>selfie credential</strong> failing usability "
     "with a liveness-undetermined result — consistent with these rows also having "
     "<code>liveness_decision=REJECTED</code>. Could also reflect an API label change since 2023. "
     "Worth clarifying with Jumio whether the API separates usability results by credential type.",
     "Low"),
    ("Non-standard top-level decision labels",
     "12 rows use <code>OK</code> (8) or <code>APPROVED</code> (4) in <code>decision_label</code> "
     "instead of <code>PASSED</code>; 1 row has <code>PASSED</code> in "
     "<code>usability_decision_details</code> instead of <code>OK</code>.",
     "Low"),
    ("Typo in check decisions",
     "3 rows use <code>PASSES</code> instead of <code>PASSED</code> across "
     "<code>image_checks_decision</code>, <code>extraction_decision</code>, "
     "<code>data_checks_decision</code>.",
     "Low"),
    ("Missing watchlist screening for pipeline blockages",
     f"2,889 rows have <code>NaN</code> in <code>watchlist_screening_decision</code> — all correspond "
     "to cases where Extraction did not execute. Per Jumio docs, Watchlist Screening depends on "
     "Usability, Extraction, and Image Checks, so this is expected — but it means these users "
     "were never screened against sanctions/PEP lists before being rejected.",
     "Medium"),
    ("decision_type vs decision_label mismatch",
     "1 user has <code>decision_type=PASSED</code> in KYC_Summary but <code>decision_label=REJECTED</code> "
     "in KYC_Details — the two datasets are inconsistent for this record. "
     "All individual checks passed except <code>liveness_decision=REJECTED</code> (LIVENESS_UNDETERMINED).",
     "Medium"),
    ("PASSED overall with liveness=REJECTED",
     "2 users have <code>liveness_decision=REJECTED</code> (LIVENESS_UNDETERMINED) but received "
     "an overall PASSED decision. This may reflect a deliberate policy to treat LIVENESS_UNDETERMINED "
     "as non-blocking — but if so, this policy should be documented and confirmed with compliance.",
     "Medium"),
    ("APPROVED despite similarity=NO_MATCH",
     "1 user has <code>similarity_decision=REJECTED</code> (NO_MATCH) — selfie does not match ID — "
     "but received a manual <code>APPROVED</code> override. Requires confirmation that this was "
     "an intentional, documented compliance decision.",
     "High"),
    ("PASSED with usability=NOT_EXECUTED (NOT_UPLOADED) — 201 users",
     "201 users have <code>usability_decision=NOT_EXECUTED</code> with detail <code>NOT_UPLOADED</code>, "
     "yet all downstream checks (Extraction, Image Checks, Liveness, Similarity) passed. "
     "This suggests a different verification workflow — possibly NFC or digital identity — "
     "where the standard document upload is not required. Should be confirmed with Jumio.",
     "Low"),
    ("Implausible ages",
     "Some <code>year_birth</code> values produce ages of 1 or 114 — likely input errors "
     "during document capture or OCR extraction.",
     "Low"),
]


# ════════════════════════════════════════════════════════════════════════════
# BUILD HTML
# ════════════════════════════════════════════════════════════════════════════
CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Segoe UI', Arial, sans-serif;
  font-size: 14px;
  color: #1F2937;
  background: #fff;
  padding: 0;
}
.cover {
  background: linear-gradient(135deg, #0D2A6B 0%, #1A4FBA 100%);
  color: white;
  padding: 80px 60px 60px;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.cover h1 { font-size: 40px; font-weight: 800; margin-bottom: 12px; }
.cover .subtitle { font-size: 20px; opacity: 0.85; margin-bottom: 40px; }
.cover .meta { font-size: 14px; opacity: 0.65; margin-top: 60px; }
.page { padding: 48px 60px; max-width: 1100px; margin: 0 auto; }
h2 {
  font-size: 22px; font-weight: 700;
  color: #0D2A6B;
  border-bottom: 3px solid #1A4FBA;
  padding-bottom: 8px;
  margin: 40px 0 20px;
}
h3 { font-size: 16px; font-weight: 600; color: #374151; margin: 24px 0 10px; }
p { line-height: 1.7; margin-bottom: 12px; color: #374151; }
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
  margin: 24px 0 36px;
}
.kpi {
  background: #F9FAFB;
  border-left: 4px solid #1A4FBA;
  padding: 20px;
  border-radius: 6px;
}
.kpi .value { font-size: 28px; font-weight: 800; color: #0D2A6B; }
.kpi .label { font-size: 12px; color: #6B7280; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.05em; }
.kpi.green { border-left-color: #22C55E; }
.kpi.red   { border-left-color: #EF4444; }
.kpi.amber { border-left-color: #F59E0B; }
.chart-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 32px;
  margin: 24px 0;
  align-items: start;
}
.chart-box { margin: 20px 0; }
.chart-box img { border-radius: 8px; }
.finding {
  background: #EFF6FF;
  border-left: 4px solid #1A4FBA;
  padding: 14px 18px;
  margin: 14px 0;
  border-radius: 0 6px 6px 0;
}
.finding.red   { background: #FEF2F2; border-left-color: #EF4444; }
.finding.amber { background: #FFFBEB; border-left-color: #F59E0B; }
.finding.green { background: #F0FDF4; border-left-color: #22C55E; }
.finding strong { display: block; margin-bottom: 4px; font-size: 14px; }
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  margin: 16px 0;
}
th {
  background: #0D2A6B;
  color: white;
  padding: 10px 14px;
  text-align: left;
  font-weight: 600;
}
td { padding: 9px 14px; border-bottom: 1px solid #E5E7EB; }
tr:nth-child(even) td { background: #F9FAFB; }
.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 9999px;
  font-size: 11px;
  font-weight: 600;
}
.badge.low    { background: #D1FAE5; color: #065F46; }
.badge.medium { background: #FEF3C7; color: #92400E; }
.badge.high   { background: #FEE2E2; color: #991B1B; }
.rec {
  counter-increment: rec-counter;
  display: flex;
  gap: 16px;
  margin: 20px 0;
  padding: 20px;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  background: #FAFAFA;
}
.rec-num {
  flex-shrink: 0;
  width: 36px; height: 36px;
  background: #1A4FBA;
  color: white;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 16px;
}
.rec-body strong { font-size: 15px; display: block; margin-bottom: 6px; color: #0D2A6B; }
.rec-body p { font-size: 13px; margin: 0; }
.toc { margin: 32px 0; }
.toc a { display: block; padding: 6px 0; color: #1A4FBA; text-decoration: none; font-size: 15px; }
.toc a.toc-sub { padding: 3px 0 3px 20px; font-size: 13.5px; color: #6B7280; }
.toc a:hover { text-decoration: underline; }
.section-intro { background: #F9FAFB; border-radius: 8px; padding: 16px 20px; margin-bottom: 24px; font-size: 13.5px; color: #374151; line-height: 1.7; }
.fr-pair {
  border: 1px solid #E5E7EB;
  border-radius: 10px;
  overflow: hidden;
  margin: 24px 0;
}
.fr-finding {
  padding: 18px 22px;
  background: #F9FAFB;
  border-bottom: 1px solid #E5E7EB;
}
.fr-finding .fr-label {
  display: inline-block;
  font-size: 11px; font-weight: 700; letter-spacing: 0.06em;
  text-transform: uppercase; color: #1A4FBA;
  background: #EFF6FF; border-radius: 4px;
  padding: 2px 8px; margin-bottom: 8px;
}
.fr-finding strong { display: block; font-size: 14.5px; color: #0D2A6B; margin-bottom: 6px; }
.fr-finding p { font-size: 13px; margin: 0; color: #374151; }
.fr-rec {
  padding: 18px 22px;
  background: #F0FDF4;
  border-left: 4px solid #22C55E;
}
.fr-rec .fr-label {
  display: inline-block;
  font-size: 11px; font-weight: 700; letter-spacing: 0.06em;
  text-transform: uppercase; color: #15803D;
  background: #DCFCE7; border-radius: 4px;
  padding: 2px 8px; margin-bottom: 8px;
}
.fr-rec strong { display: block; font-size: 14.5px; color: #14532D; margin-bottom: 6px; }
.fr-rec p { font-size: 13px; margin: 0; color: #374151; }
.placeholder {
  background: #F9FAFB; border: 2px dashed #D1D5DB;
  border-radius: 8px; padding: 32px;
  text-align: center; color: #9CA3AF; font-size: 14px;
  margin: 24px 0;
}
.analysis-section { border-top: 1px solid #E5E7EB; padding-top: 16px; margin-top: 40px; }
.analysis-section h3 {
  font-size: 18px; font-weight: 700; color: #1A4FBA;
  margin: 0 0 16px 0;
}
@media print {
  .cover { page-break-after: always; }
  h2 { page-break-before: auto; }
  .no-break { page-break-inside: avoid; }
  .fr-pair { page-break-inside: avoid; }
  body { font-size: 12px; }
}
"""

def badge(level: str) -> str:
    return f'<span class="badge {level.lower()}">{level}</span>'

def kpi_card(value, label, cls="") -> str:
    return f'<div class="kpi {cls}"><div class="value">{value}</div><div class="label">{label}</div></div>'

html_parts = []

def h(s):
    html_parts.append(s)

# ─── Cover ───────────────────────────────────────────────────────────────────
h(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>KYC Process Analysis — ARQ</title>
<style>{CSS}</style>
</head>
<body>
<div class="cover">
  <h1>KYC Process Analysis</h1>
  <div class="subtitle">Identifying Inefficiencies &amp; Actionable Recommendations</div>
  <p style="opacity:0.75;font-size:15px;">
    Analysis of {total:,} KYC attempts across two markets (MEX &amp; ARG)<br>
    Period: {date_min} – {date_max}
  </p>
  <div class="meta">
    Prepared for ARQ &nbsp;·&nbsp; March 2026
  </div>
</div>
""")

# ─── TOC ─────────────────────────────────────────────────────────────────────
h("""<div class="page">
<h2 id="toc">Table of Contents</h2>
<div class="toc">
  <a href="#objective">1. Objective</a>
  <a href="#findings-recommendations">2. Findings &amp; Recommendations</a>
  <a href="#methodology">3. Methodology</a>
  <a href="#limitations">4. Limitations &amp; Assumptions</a>
  <a href="#analysis">5. Analysis</a>
  <a href="#overview" class="toc-sub">5.1 Dataset Overview</a>
  <a href="#jumio-docs" class="toc-sub">5.2 Jumio Documentation</a>
  <a href="#qualitative" class="toc-sub">5.3 Qualitative Review of Jumio</a>
  <a href="#data-quality" class="toc-sub">5.4 Data Quality</a>
  <a href="#pass-rates" class="toc-sub">5.5 Pass Rates</a>
  <a href="#rejection-causes" class="toc-sub">5.6 Rejection Causes</a>
  <a href="#anomaly" class="toc-sub">5.7 Anomaly Investigation</a>
</div>
</div>
""")

# ─── Objective ────────────────────────────────────────────────────────────────
h("""<div class="page">
<h2 id="objective">1. Objective</h2>
  Identify issues and inefficiencies in ARQ's KYC process (as of September 2023) 
  and propose actionable improvements.
</p>
</div>
""")

# ─── Findings & Recommendations ───────────────────────────────────────────────
h(f"""<div class="page">
<h2 id="findings-recommendations">2. Findings &amp; Recommendations</h2>
<div class="section-intro">
  Each finding is paired with a specific recommendation. Findings are ordered by estimated
  business impact.
</div>

<div class="fr-pair no-break">
  <div class="fr-finding">
    <span class="fr-label">Finding 1 — Conversion</span>
    <strong>Pipeline blockages account for {n_pipeline_blocked/n_rejected*100:.0f}% of all rejections</strong>
    <p>{pct(n_pipeline_blocked, n_rejected)} of rejections occurred because the Extraction check never ran,
    stalling all downstream document checks. These are not genuine verification failures —
    they are infrastructure or UX problems. Sub-causes: Extraction blocked despite Usability passing
    ({n_extraction_blocked:,}), Usability WARNING cascading downstream ({n_usability_warn:,}),
    and Usability not executing at all ({n_usability_noexec:,}).</p>
  </div>
  <div class="fr-rec">
    <span class="fr-label">Recommendation</span>
    <strong>Diagnose and fix pipeline blockages</strong>
    <p>Investigate vendor API timeouts, upload failures, and whether Usability WARNINGs should
    truly block Extraction. Implement retry logic and pre-submission image quality checks in-app.
    Recovering 50% of these cases would add ~{int(n_pipeline_blocked*0.5):,} passed users.</p>
  </div>
</div>

<div class="fr-pair no-break">
  <div class="fr-finding">
    <span class="fr-label">Finding 2 — Conversion</span>
    <strong>Mexico's pass rate (81.5%) trails Argentina (92.1%) by 10.6 percentage points</strong>
    <p>Mexican users are disproportionately rejected. The gap is partly driven by MEX National ID
    having an 89.3% pass rate vs. Electoral ID at 95.8% — a 6.5pp difference within the same market.
    UNSUPPORTED_DOCUMENT_TYPE (509 usability WARNINGs) also suggests users are submitting
    unsupported document types that could be intercepted earlier.</p>
  </div>
  <div class="fr-rec">
    <span class="fr-label">Recommendation</span>
    <strong>Guide Mexican users toward Electoral IDs and add a document type selector</strong>
    <p>Add in-app guidance recommending Electoral ID as the preferred document for Mexican users.
    Introduce a document type selector before the capture step to prevent unsupported documents
    from reaching the pipeline at all.</p>
  </div>
</div>

<div class="fr-pair no-break">
  <div class="fr-finding">
    <span class="fr-label">Finding 3 — Conversion</span>
    <strong>{liveness_reasons.get('liveness_UNDETERMINED',0):,} liveness rejections are non-conclusive</strong>
    <p>Of {(df['liveness_decision']=='REJECTED').sum():,} liveness rejections, {liveness_reasons.get('liveness_UNDETERMINED',0):,}
    are <code>LIVENESS_UNDETERMINED</code> — per Jumio docs this means the system could not reach a
    confident verdict, not that the user failed. These are almost always caused by poor lighting,
    glasses, or partial face visibility rather than spoofing attempts.</p>
  </div>
  <div class="fr-rec">
    <span class="fr-label">Recommendation</span>
    <strong>Introduce a guided retry flow for LIVENESS_UNDETERMINED</strong>
    <p>Instead of hard-rejecting these users, prompt them to retry with specific guidance
    (better lighting, remove glasses, ensure full face is visible). This distinction
    between UNDETERMINED and hard fraud signals (e.g. ID_USED_AS_SELFIE) should
    drive different user flows.</p>
  </div>
</div>

<div class="fr-pair no-break">
  <div class="fr-finding">
    <span class="fr-label">Finding 4 — Operations</span>
    <strong>Rejection rate nearly doubled during Aug 21 – Sep 3</strong>
    <p>The weekly rejection rate spiked from a baseline of ~{baseline_rate:.1f}% to
    {max(spike_rates):.1f}% during this two-week window, then partially recovered
    but remained above baseline through the end of the observation period. The root
    cause is not identifiable from the dataset alone.</p>
  </div>
  <div class="fr-rec">
    <span class="fr-label">Recommendation</span>
    <strong>Investigate the root cause of the spike with Jumio</strong>
    <p>Cross-reference with Jumio SLA/incident reports, marketing campaign dates,
    and app release history. Hypotheses to test: vendor degradation, new user
    acquisition batch, increased fraud volume, or a UI change in the capture flow.</p>
  </div>
</div>

<div class="fr-pair no-break">
  <div class="fr-finding">
    <span class="fr-label">Finding 5 — Compliance</span>
    <strong>69 users matched a sanctions/PEP watchlist and all were passed</strong>
    <p>Per Jumio docs, a Watchlist WARNING carries the label <strong>ALERT</strong>, meaning
    the user was found on one or more global or regional sanctions lists or is a
    Politically Exposed Person. All 69 matches received an overall PASSED outcome.
    It is unclear from the data whether a manual review process exists for these cases.</p>
  </div>
  <div class="fr-rec">
    <span class="fr-label">Recommendation</span>
    <strong>Establish a documented manual review process for watchlist ALERT matches</strong>
    <p>Confirm with the compliance team that each ALERT match is individually reviewed,
    that a documented decision rationale exists, and that the current pass-through
    policy is explicitly approved by compliance leadership.</p>
  </div>
</div>

<div class="fr-pair no-break">
  <div class="fr-finding">
    <span class="fr-label">Finding 6 — Compliance</span>
    <strong>Manual overrides lack a documented policy</strong>
    <p>1 user was manually APPROVED despite <code>similarity=NO_MATCH</code> — their selfie
    did not match their ID. 2 users with <code>liveness=REJECTED</code> (LIVENESS_UNDETERMINED)
    received an overall PASSED. There is no evidence in the data of a formal override policy
    or audit trail for these decisions.</p>
  </div>
  <div class="fr-rec">
    <span class="fr-label">Recommendation</span>
    <strong>Audit and formalise manual override decisions</strong>
    <p>Each manual override should have a documented rationale, an authorised approver, and
    be logged for audit purposes. If LIVENESS_UNDETERMINED is intentionally treated as
    non-blocking, this policy should be formalised in writing with compliance sign-off.</p>
  </div>
</div>

<div class="fr-pair no-break">
  <div class="fr-finding">
    <span class="fr-label">Finding 7 — Data Quality</span>
    <strong>Multiple data quality issues indicate gaps in pipeline validation</strong>
    <p>Non-standard decision labels (OK, APPROVED, PASSES), inconsistent label casing
    (<code>liveness_UNDETERMINED</code> vs <code>LIVENESS_UNDETERMINED</code>), and
    implausible age values suggest the data pipeline lacks schema validation and
    output contracts with the vendor.</p>
  </div>
  <div class="fr-rec">
    <span class="fr-label">Recommendation</span>
    <strong>Enforce data quality at the pipeline level</strong>
    <p>Add schema validation to reject non-standard label values in real time.
    Define and enforce a data contract with Jumio covering all expected field
    values, ensuring analytics remain reliable as the API evolves.</p>
  </div>
</div>

</div>
""")

# ─── Methodology ──────────────────────────────────────────────────────────────
h("""<div class="page">
<h2 id="methodology">3. Methodology</h2>
<div class="placeholder">
  [ To be completed ]
</div>
</div>
""")

# ─── Limitations & Assumptions ────────────────────────────────────────────────
h("""<div class="page">
<h2 id="limitations">4. Limitations &amp; Assumptions</h2>
<div class="section-intro">
  The following limitations and open questions were identified during the analysis.
  They do not invalidate the findings but should be considered when acting on recommendations.
</div>
<table>
  <tr><th>Area</th><th>Limitation / Assumption</th></tr>
  <tr><td><strong>Retry behaviour</strong></td><td>The dataset contains one row per user with no retry history. It is unknown if some users re-attempted KYC and ultimately passed. Retry success rates would materially change the conversion impact estimates.</td></tr>
  <tr><td><strong>Workflow anomalies</strong></td><td>For 201 users, their usability check appears as not executed while at the same time the downstream checks have all passed. These may be users that have used a different workflow not shown on the dataset or, more likely, a data error.</td></tr>
  <tr><td><strong>Manual override policy</strong></td><td>4 users appear as <code>APPROVED</code> in the data. The exact difference between that label and <code>PASSED</code> is unclear — <code>APPROVED</code> may represent a manual decision and <code>PASSED</code> an automated one.</td></tr>
  <tr><td><strong>Liveness issue in usability check </strong></td><td>278 users show a liveness related failure in the usability check which is not expected as per Jumio's API documentation. This could reflect a pipeline bug or API change. We have assumed for these cases that the failure occurred at the liveness check stage and not at the usability one.</td></tr>
  <tr><td><strong>API version drift</strong></td><td>The dataset is from 2023; the Jumio documentation used reflects the current API (2026). Some label names or decision behaviours may have changed. This introduces a risk of the data being misinterpreted.</td></tr>
  <tr><td><strong>Time period</strong></td><td>The analysis covers ~2 months (Jul–Sep 2023). Seasonal patterns, long-term trends, and year-on-year comparisons are not possible with this data.</td></tr>
  <tr><td><strong>Dataset consistency</strong></td><td>1 user appears as <code>PASSED</code> in KYC_Summary but <code>REJECTED</code> in KYC_Details. The authoritative source for this record is unclear but we have decided to use KYC_Summary.</td></tr>
  <tr><td><strong>Colombia missing</strong></td><td>According to ARQ's website in July 2023, ARQ was live in Colombia (this can be seen using Wayback Machine). However, no records of Colombian users appear in the data set. At the time the company was known as DolarApp.</td></tr>
</table>
</div>
""")

# ─── Analysis wrapper ──────────────────────────────────────────────────────────
h("""<div class="page">
<h2 id="analysis">5. Analysis</h2>
  <div class="section-intro">
  Chain of reasoning that led to the findings and recommendations.
</div>
</div>
""")

# ─── Overview ─────────────────────────────────────────────────────────────────
h(f"""<div class="page">
<h2 id="overview">5.1 Dataset Overview</h2>
<div class="kpi-grid">
  {kpi_card(f"{total:,}", "Total KYC Attempts")}
  {kpi_card(f"{pass_rate:.1f}%", "Overall Pass Rate", "green")}
  {kpi_card(f"{n_rejected:,}", "Rejected", "red")}
  {kpi_card(f"{n_warning:,}", "Warnings", "amber")}
</div>
<div class="chart-row">
  <div class="chart-box">{img_tag(CHART_DONUT)}</div>
  <div>
    <h3>About the data</h3>
    <p>Two datasets analysed: <strong>KYC_Summary</strong> (one row per attempt with date and
    outcome) and <strong>KYC_Details</strong> (one row per attempt with the result of each
    individual check). Both contain {total:,} unique user references with no duplicates.</p>
    <p><strong>Date range:</strong> {date_min} – {date_max} ({(summary['date'].max()-summary['date'].min()).days} days)</p>
    <p><strong>Countries:</strong> Mexico (MEX) - {(df['data_issuing_country']=='MEX').sum():,} attempts &nbsp;|&nbsp;
    Argentina (ARG) - {(df['data_issuing_country']=='ARG').sum():,} attempts</p>
    <p><strong>Document types:</strong> ID Card ({(df['data_type']=='ID_CARD').sum():,}),
    Passport ({(df['data_type']=='PASSPORT').sum():,}),
    Driving License ({(df['data_type']=='DRIVING_LICENSE').sum():,}),
    Visa ({(df['data_type']=='VISA').sum():,})</p>
    <p><strong>KYC checks performed:</strong> Usability, Extraction, Image Checks,
    Data Checks / Watchlist Screening, Liveness, Similarity.</p>
    <h3>Conclusions</h3>
    <p>Warnings are only ~1% of total attempts so we will be focusing on the larger problem of rejections</p>
    <p>Analysing both Mexico and Argentina is important as they have roughly similar volumes </p>
    <p>We will only look at ID cards and passports as they represent 98% of documents used by users</p>
    <p></p>
  </div>
</div>
</div>
""")

# ─── 5.2 Jumio Documentation ──────────────────────────────────────────────────
h(f"""<div class="page">
<h2 id="jumio-docs">5.2 Jumio Documentation</h2>
<div class="section-intro">
  Jumio's KYC pipeline runs up to seven checks per transaction. Understanding each check is essential
  for interpreting the data and attributing failures correctly.
</div>

<h3>Check overview</h3>
<table>
  <tr><th>Check</th><th>What it tests</th><th>Depends on</th><th>Possible decisions</th></tr>
  <tr>
    <td><strong>Usability</strong></td>
    <td>Whether uploaded images (ID and selfie) are of sufficient quality to process</td>
    <td>None (root check)</td>
    <td>PASSED, REJECTED, WARNING, NOT_EXECUTED</td>
  </tr>
  <tr>
    <td><strong>Extraction</strong></td>
    <td>Whether mandatory fields can be extracted from the ID</td>
    <td>Usability (ID)</td>
    <td>PASSED, NOT_EXECUTED</td>
  </tr>
  <tr>
    <td><strong>Image Checks</strong></td>
    <td>Whether the ID passes integrity tests</td>
    <td>Usability + Extraction</td>
    <td>PASSED, REJECTED, WARNING, NOT_EXECUTED</td>
  </tr>
  <tr>
    <td><strong>Data Checks</strong></td>
    <td>Whether extracted data is internally consistent and does not match known fraud patterns or prior rejected transactions</td>
    <td>Usability + Extraction + Image Checks</td>
    <td>PASSED, REJECTED, WARNING, NOT_EXECUTED</td>
  </tr>
  <tr>
    <td><strong>Watchlist Screening</strong></td>
    <td>Whether the user appears on global sanctions lists, PEP databases, or adverse media sources</td>
    <td>Usability + Extraction + Image Checks (or standalone with name/DOB)</td>
    <td>PASSED, WARNING (ALERT), NOT_EXECUTED</td>
  </tr>
  <tr>
    <td><strong>Liveness</strong></td>
    <td>Whether the selfie was captured from a live person (detects spoofing, printed photos, screen recordings)</td>
    <td>Usability (selfie only) — independent of document chain</td>
    <td>PASSED, REJECTED, WARNING, NOT_EXECUTED</td>
  </tr>
  <tr>
    <td><strong>Similarity</strong></td>
    <td>Whether the face in the selfie matches the face on the ID document</td>
    <td>Usability (face detectability on ID only) — independent of document chain</td>
    <td>PASSED (MATCH), REJECTED (NO_MATCH), WARNING (NOT_POSSIBLE), NOT_EXECUTED</td>
  </tr>
</table>

<h3>Check dependency graph</h3>
<p>The pipeline is a dependency graph, not a linear sequence. Usability is the root check.
The document chain (Extraction → Image Checks → Data Checks / Watchlist) can only proceed if
Usability passes. Liveness and Similarity run off their own Usability conditions and are
independent of the document chain — a document failure does not block them.</p>
<div class="chart-box">{img_tag(CHART_DAG)}</div>
</div>
""")

# ─── 5.3 Qualitative Review of Jumio ─────────────────────────────────────────
h("""<div class="page">
<h2 id="qualitative">5.3 Qualitative Review of Jumio</h2>
<div class="section-intro">
  To complement the quantitative data, a conversation was held with <strong>Agustín Pividori</strong>,
  FinCrime lead at Personal Pay — a LATAM fintech and <strong>active Jumio customer</strong>. The insights below
  reflect his direct experience operating Jumio in production.
</div>

<h3>Key Points</h3>
<p> Personal Pay selected Jumio primarily on cost. </p>
<p> FaceTec is the main competitor (widely used by Mercado Libre and major banks).</p>
<p> DNI (national ID) is the only universally required document type across LATAM financial institutions.
Passports and driver's licenses are much less common — consistent with our dataset where ID Cards
represent 86% of all attempts.</p>
<p> Jumio's document capture is aggressive in rejecting images that do not meet its quality bar. This creates friction.
<p> False positives were a concern prior to SLA negotiations; once managed, they came within agreed limits.</p>
  
<h3>Conclusions</h3>
<p> Check false positives (if possible) during the analysis </p>
<p> Check for image quality failures </p>

</div>
""")

# ─── 5.4 Data Quality ────────────────────────────────────────────────────────
h("""<div class="page">
<h2 id="data-quality">5.4 Data Quality</h2>
<div class="section-intro">
  Several data quality issues were identified in the dataset. While most are minor, they can
  affect downstream analytics and should be addressed at the pipeline level.
</div>
<table>
  <tr>
    <th>Issue</th>
    <th>Description</th>
    <th>Severity</th>
  </tr>
""")
for title, desc, level in dq_issues:
    h(f"  <tr><td><strong>{title}</strong></td><td>{desc}</td><td>{badge(level)}</td></tr>")
h("""</table>
<p style="margin-top:16px;font-size:13px;color:#6B7280;">
  The label casing and column misrouting issues are symptomatic of a pipeline bug that should be
  fixed at the source. The watchlist and UNSUPPORTED_DOCUMENT_TYPE discrepancies should be
  clarified with Jumio directly. Schema validation and data contract enforcement at the pipeline
  level would prevent these issues from accumulating undetected.
</p>
</div>
""")

# ─── 5.5 Pass Rates ───────────────────────────────────────────────────────────
mex_total = (df["data_issuing_country"] == "MEX").sum()
arg_total = (df["data_issuing_country"] == "ARG").sum()

h(f"""<div class="page">
<h2 id="pass-rates">5.5 Pass Rates</h2>
<div class="section-intro">
  Pass rates are analysed across three dimensions: time (weekly trend), document type, and country.
</div>

<h3>Trend over time</h3>
<div class="chart-box">{img_tag(CHART_WEEKLY)}</div>
<div class="finding red no-break">
  <strong>Rejection spike: Aug 21 – Sep 3</strong>
  The rejection rate jumped from a baseline of ~{baseline_rate:.1f}% to
  {spike_rates[0]:.1f}% (Aug 21–27) and {spike_rates[1]:.1f}% (Aug 28–Sep 3) —
  a {spike_rates[1]/baseline_rate:.1f}× increase. The rate partially recovered but remained
  above baseline through the end of the observation period. Root cause is investigated in section 5.7.
</div>

<h3>By document type</h3>
<div class="chart-row">
  <div class="chart-box">{img_tag(CHART_DOC_TYPE)}</div>
  <div>
    <p>Passports achieve the highest pass rate (<strong>96.4%</strong>) followed by Visas (95.8%).
    ID Cards (92.6%) and Driving Licenses (89.5%) perform below the overall average.</p>
    <p>Despite the lower pass rate, ID Cards account for
    <strong>{(df['data_type']=='ID_CARD').sum():,} attempts ({(df['data_type']=='ID_CARD').sum()/total*100:.0f}%)</strong>
    of all attempts — making them the most impactful document type to optimise.</p>
    <p>Within ID Cards, Mexico's Electoral IDs (95.8%) outperform National IDs (89.3%) by
    6.5 percentage points. Whether pipeline blockages explain the ID card gap is analysed
    in section 5.7.</p>
  </div>
</div>
<div class="chart-box">{img_tag(CHART_SUBTYPE)}</div>

<h3>By country</h3>
<div class="chart-row">
  <div class="chart-box">{img_tag(CHART_COUNTRY)}</div>
  <div>
    <p>There is a <strong>10.6 percentage-point gap</strong> in pass rates between Mexico
    ({mex_total:,} attempts, {mex_total/total*100:.0f}%) and Argentina ({arg_total:,} attempts,
    {arg_total/total*100:.0f}%).</p>
    <p>Mexico's lower rate is partly driven by document mix — a higher share of National IDs
    (89.3%) vs Electoral IDs (95.8%). RESIDENT_PERMIT_ID in Mexico achieves 96.0%, showing
    the quality bar is reachable. Argentina's weakest performer is Driving Licenses (87.4%).</p>
    <p>Whether pipeline blockages explain the MEX–ARG gap is analysed in section 5.7.</p>
  </div>
</div>
</div>
""")

# ─── 5.6 Rejection Causes ────────────────────────────────────────────────────
h(f"""<div class="page">
<h2 id="rejection-causes">5.6 Rejection Causes</h2>
<div class="section-intro">
  Rejections are attributed to the first check that blocked the pipeline, then drilled into
  the specific detail label returned by each check.
</div>

<h3>Root cause of rejections</h3>
<div class="chart-box">{img_tag(CHART_FAIL_CHECK)}</div>
<div class="finding red no-break">
  <strong>Pipeline blockages — {n_pipeline_blocked:,} rejections ({n_pipeline_blocked/n_rejected*100:.1f}% of all rejections)</strong>
  These users were not rejected because a check explicitly failed — the pipeline itself stalled.
  <ul style="margin:8px 0 0 18px;font-size:13px;">
    <li><strong>Extraction blocked ({n_extraction_blocked:,}):</strong> Usability passed but Extraction never ran, halting Image Checks, Data Checks, and Watchlist Screening.</li>
    <li><strong>Usability WARNING cascaded ({n_usability_warn:,}):</strong> A usability warning was treated as a hard blocker for Extraction.</li>
    <li><strong>Usability not executed ({n_usability_noexec:,}):</strong> The root check itself did not run.</li>
  </ul>
</div>
<div class="finding red no-break">
  <strong>Similarity failures — {n_similarity:,} rejections ({n_similarity/n_rejected*100:.1f}%)</strong>
  Selfie does not match the document photo. Similarity runs independently of the document chain.
</div>
<div class="finding amber no-break">
  <strong>Liveness failures — {n_liveness:,} rejections ({n_liveness/n_rejected*100:.1f}%)</strong>
  System cannot confirm the user is live. Mostly UNDETERMINED (UX/connectivity) rather than
  hard spoofing signals.
</div>
<div class="finding amber no-break">
  <strong>Image check failures — {n_image:,} rejections ({n_image/n_rejected*100:.1f}%)</strong>
  Documents flagged as manipulated or digital copies.
</div>
<div class="finding amber no-break">
  <strong>Usability hard rejections — {n_usability:,} rejections ({n_usability/n_rejected*100:.1f}%)</strong>
  Document image could not be processed; blocks the entire document chain.
</div>

<h3>Failure reasons by check</h3>
<div class="chart-row">
  <div class="chart-box">
    <h3>Usability Failures</h3>
    {img_tag(CHART_USABILITY)}
    <p style="font-size:12.5px;color:#6B7280;margin-top:8px;">
      REJECTED: MISSING_MANDATORY_DATAPOINTS ({usability_rejected_reasons.get('MISSING_MANDATORY_DATAPOINTS',0):,})
      and image quality issues (BLURRED, GLARE, MISSING_PAGE) — addressable with better in-app
      capture guidance.
      WARNING: UNSUPPORTED_DOCUMENT_TYPE ({usability_warning_reasons.get('UNSUPPORTED_DOCUMENT_TYPE',0):,}) dominates
      — users submitting document types not supported by the workflow. Catchable earlier with
      a document selector.
    </p>
  </div>
  <div class="chart-box">
    <h3>Image Check Failures</h3>
    {img_tag(CHART_IMAGE)}
    <p style="font-size:12.5px;color:#6B7280;margin-top:8px;">
      MANIPULATED_DOCUMENT ({image_reasons.get('MANIPULATED_DOCUMENT',0):,}) is the dominant
      failure reason — genuine fraud signals that should be escalated for manual review.
      DIGITAL_COPY ({image_reasons.get('DIGITAL_COPY',0):,}) may indicate users photographing
      a screen instead of a physical document.
    </p>
  </div>
</div>
<div class="chart-row">
  <div class="chart-box">
    <h3>Liveness Failures</h3>
    {img_tag(CHART_LIVENESS)}
    <p style="font-size:12.5px;color:#6B7280;margin-top:8px;">
      <code>LIVENESS_UNDETERMINED</code> ({liveness_reasons.get('liveness_UNDETERMINED',0):,} cases)
      accounts for the vast majority. Per Jumio docs this means the system could not reach a
      confident verdict — almost always a UX or connectivity issue, not spoofing.
      A guided retry flow would recover most of these users.
    </p>
  </div>
  <div class="chart-box">
    <h3>Similarity Failures</h3>
    {img_tag(CHART_SIMILARITY)}
    <p style="font-size:12.5px;color:#6B7280;margin-top:8px;">
      NO_MATCH ({similarity_reasons.get('NO_MATCH',0):,}) — selfie and document photo could
      not be matched (hard rejection). NOT_POSSIBLE ({similarity_reasons.get('NOT_POSSIBLE',0):,})
      — comparison cannot be determined (WARNING per docs). These {similarity_reasons.get('NOT_POSSIBLE',0):,}
      users pass overall without a confirmed face match — a potential compliance gap.
    </p>
  </div>
</div>
</div>
""")

# ─── 5.7 Anomaly Investigation ────────────────────────────────────────────────
h(f"""<div class="page">
<h2 id="anomaly">5.7 Anomaly Investigation</h2>
<div class="section-intro">
  Three anomalies were identified in the pass rate analysis: a rejection spike in late August,
  a lower pass rate in Mexico compared to Argentina, and a lower pass rate of ID Cards compared
  to Passports. This section investigates whether pipeline blockages explain each one.
</div>

<h3>Q1 — Does the August rejection spike correlate with pipeline blockages?</h3>
<div class="chart-box">{img_tag(CHART_ANOM_WEEKLY)}</div>
<div class="finding {'amber' if abs(spike_blocked_pct - baseline_blocked_pct) < 5 else 'red'} no-break">
  <strong>Pipeline blockages {'do not explain' if abs(spike_blocked_pct - baseline_blocked_pct) < 5 else 'partially explain'} the August spike</strong>
  During the spike weeks (Aug 21 – Sep 3), pipeline blockages accounted for
  <strong>{spike_blocked_pct:.1f}%</strong> of rejections, compared to
  <strong>{baseline_blocked_pct:.1f}%</strong> during the baseline weeks — a
  {'negligible' if abs(spike_blocked_pct - baseline_blocked_pct) < 5 else 'notable'}
  {'difference' if abs(spike_blocked_pct - baseline_blocked_pct) < 5 else f'{abs(spike_blocked_pct - baseline_blocked_pct):.1f}pp shift'}.
  {'The composition of rejections remained essentially unchanged: the spike was driven by a higher volume of <em>both</em> hard failures and pipeline blockages, not by a shift in their mix. This rules out a targeted pipeline degradation. More likely causes: a new user acquisition batch, increased fraud volume, or an app change affecting all check types.' if abs(spike_blocked_pct - baseline_blocked_pct) < 5 else 'The increase in pipeline blockages during the spike suggests a vendor-side or infrastructure issue may have contributed to the elevated rejection rate.'}
</div>

<h3>Q2 — Do pipeline blockages explain Mexico's lower pass rate vs Argentina?</h3>
<div class="chart-box">{img_tag(CHART_ANOM_SEGMENTS)}</div>
<div class="finding {'red' if mex_blocked_pct - arg_blocked_pct > 3 else 'amber'} no-break">
  <strong>Pipeline blockages {'are' if mex_blocked_pct - arg_blocked_pct > 3 else 'are not'} a primary driver of the MEX–ARG gap</strong>
  In Mexico, {mex_blocked_pct:.1f}% of total attempts end as pipeline blockages, vs
  {arg_blocked_pct:.1f}% in Argentina — a {mex_blocked_pct - arg_blocked_pct:.1f}pp difference.
  {'This gap is material and contributes meaningfully to the overall pass rate differential. Fixing MEX pipeline blockages would directly close part of the 10.6pp gap.' if mex_blocked_pct - arg_blocked_pct > 3 else 'The gap is small, suggesting pipeline blockages are not the primary driver of the MEX–ARG pass rate difference. The gap is more likely driven by document mix (National vs Electoral ID) and user/device quality differences.'}
</div>

<h3>Q3 — Do pipeline blockages explain why ID Cards underperform Passports?</h3>
<div class="finding {'red' if idcard_blocked_pct - passport_blocked_pct > 2 else 'amber'} no-break">
  <strong>Pipeline blockages {'significantly contribute to' if idcard_blocked_pct - passport_blocked_pct > 2 else 'partially explain'} the ID Card–Passport gap</strong>
  For ID Cards, {idcard_blocked_pct:.1f}% of total attempts end as pipeline blockages, vs
  {passport_blocked_pct:.1f}% for Passports — a {idcard_blocked_pct - passport_blocked_pct:.1f}pp difference.
  ID Cards are structurally more susceptible to pipeline blockages: they require
  front-and-back capture (increasing upload failure risk), have stricter field extraction requirements
  across many more regional variants, and are more likely to fail usability checks due to wear and
  regional printing differences. A share of the pass rate gap between ID Cards and Passports is
  therefore attributable to pipeline architecture, not document quality alone.
</div>
</div>
""")

h("""</body>
</html>
""")

# ── Write output ──────────────────────────────────────────────────────────────
html_content = "\n".join(html_parts)
OUTPUT_HTML.write_text(html_content, encoding="utf-8")
print(f"Report written to: {OUTPUT_HTML}")
print(f"File size: {OUTPUT_HTML.stat().st_size / 1024:.0f} KB")
