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
sub_stats = df[df["data_type"] == "ID_CARD"].groupby(["data_issuing_country", "data_sub_type"]).apply(
    lambda g: pd.Series({"total": len(g), "passed": (g["decision_type"] == "PASSED").sum()})
).reset_index()
sub_stats["pass_rate"] = sub_stats["passed"] / sub_stats["total"] * 100
sub_stats = sub_stats[sub_stats["total"] >= 50]

# ── Pass rate by age group ────────────────────────────────────────────────────
AGE_BINS   = [0, 17, 24, 34, 44, 54, 64, 120]
AGE_LABELS = ["<18", "18–24", "25–34", "35–44", "45–54", "55–64", "65+"]
df["age_group"] = pd.cut(df["age"], bins=AGE_BINS, labels=AGE_LABELS)
age_stats = df.groupby("age_group", observed=False).apply(
    lambda g: pd.Series({"total": len(g), "passed": (g["decision_type"] == "PASSED").sum()})
).reset_index()
age_stats["pass_rate"] = age_stats["passed"] / age_stats["total"] * 100
# Append Unknown (no year_birth) as an explicit row
_unk        = df[df["age_group"].isna()]
_unk_total  = len(_unk)
_unk_passed = (_unk["decision_type"] == "PASSED").sum()
age_stats = pd.concat([age_stats, pd.DataFrame([{
    "age_group": "Unknown",
    "total":     _unk_total,
    "passed":    _unk_passed,
    "pass_rate": _unk_passed / _unk_total * 100,
}])], ignore_index=True)

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

def _box_crossings(p0, p1, cx, cy, hw=0.9, hh=0.275):
    """t values where line P(t)=p0+t*(p1-p0) crosses box [cx±hw, cy±hh], t in (eps, 1-eps)."""
    dx = p1[0] - p0[0]; dy = p1[1] - p0[1]
    eps = 1e-9
    ts = []
    if abs(dx) > eps:
        for ex in [cx - hw, cx + hw]:
            t = (ex - p0[0]) / dx
            if eps < t < 1 - eps:
                y = p0[1] + t * dy
                if cy - hh - eps <= y <= cy + hh + eps:
                    ts.append(t)
    if abs(dy) > eps:
        for ey in [cy - hh, cy + hh]:
            t = (ey - p0[1]) / dy
            if eps < t < 1 - eps:
                x = p0[0] + t * dx
                if cx - hw - eps <= x <= cx + hw + eps:
                    ts.append(t)
    return ts

def _pt(p0, p1, t):
    return (p0[0] + t*(p1[0]-p0[0]), p0[1] + t*(p1[1]-p0[1]))

def arrow(ax, src, dst, color="#9CA3AF"):
    """Draw arrow from src box edge to dst box edge, computed geometrically."""
    src_ts = _box_crossings(src, dst, src[0], src[1])
    dst_ts = _box_crossings(src, dst, dst[0], dst[1])
    src_pt = _pt(src, dst, min(src_ts)) if src_ts else src
    dst_pt = _pt(src, dst, min(dst_ts)) if dst_ts else dst
    ax.annotate("", xy=dst_pt, xytext=src_pt,
                arrowprops=dict(arrowstyle="-|>", color=color, lw=1.4))

# Node positions — left column: document chain; right column: selfie/identity (stacked)
nodes = {
    "Usability":            (4.5, 5.0),
    "Extraction":           (3.0, 3.8),
    "Image Checks":         (3.0, 2.6),
    "Data Checks":          (1.8, 1.4),
    "Watchlist\nScreening": (4.2, 1.4),
    "Liveness":             (7.0, 3.8),
    "Similarity":           (7.0, 2.6),
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
    "Extraction":           BRAND_DARK,
    "Image Checks":         BRAND_DARK,
    "Data Checks":          BRAND_DARK,
    "Watchlist\nScreening": BRAND_DARK,
    "Liveness":             BRAND_DARK,
    "Similarity":           BRAND_DARK,
}

fig, ax = plt.subplots(figsize=(10, 5))
ax.set_xlim(0.5, 8.5)
ax.set_ylim(0.6, 5.8)
ax.axis("off")
ax.set_facecolor("#FAFAFA")
fig.patch.set_facecolor("#FAFAFA")

# Draw edges first (behind boxes)
for src, dst, etype in edges:
    arrow(ax, nodes[src], nodes[dst])

# Edge labels
edge_label_positions = {
    ("Usability", "Liveness"):   (6.1, 4.7, "selfie\nusability"),
    ("Usability", "Similarity"): (6.1, 4.0, "face\ndetectability"),
    ("Usability", "Extraction"): (3.0, 4.5, ""),
}
for (src, dst), (lx, ly, lbl) in edge_label_positions.items():
    if lbl:
        ax.text(lx, ly, lbl, ha="center", va="center", fontsize=7.5,
                color="#6B7280", style="italic")

# Draw node boxes
for name, (x, y) in nodes.items():
    draw_box(ax, (x, y), name, node_colors[name])

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
ax.set_xlim(0, 115)
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
ax.set_ylim(0, 105)
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
    ax.set_xlim(0, 120)
    for bar, (_, row) in zip(bars, sub.iterrows()):
        ax.text(bar.get_width() + 0.2, bar.get_y() + bar.get_height()/2,
                f"{row['pass_rate']:.1f}%  n={row['total']:,}",
                va="center", fontsize=8.5, color=GRAY)
    ax.set_xlabel("Pass rate (%)")
    ax.set_title(f"{country} — ID Card Pass Rate by Subtype")
plt.tight_layout()
CHART_SUBTYPE = fig_to_b64(fig)


# ════════════════════════════════════════════════════════════════════════════
# CHART 8 — Pass rate by age group
# ════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(figsize=(9, 3.5))
def _age_bar_color(label, rate):
    if label in ("<18", "Unknown"):
        return "#9CA3AF"   # neutral grey — not a true pass-rate cohort
    return PASS_GREEN if rate >= 92 else WARN_AMBER if rate >= 88 else FAIL_RED
bar_colors = [_age_bar_color(str(row["age_group"]), row["pass_rate"])
              for _, row in age_stats.iterrows()]
bars = ax.bar(age_stats["age_group"].astype(str), age_stats["pass_rate"],
              color=bar_colors, edgecolor="none", width=0.6)
ax.set_ylim(0, 105)
for i, (_, row) in enumerate(age_stats.iterrows()):
    rate = row["pass_rate"]
    ax.text(i, rate + 1.5,
            f"{rate:.1f}%\n(n={row['total']:,})",
            ha="center", va="bottom", fontsize=8.5, color=GRAY)
ax.set_xlabel("Age group")
ax.set_ylabel("Pass rate (%)")
ax.set_title("Pass Rate by Age Group")
plt.tight_layout()
CHART_AGE = fig_to_b64(fig)


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
fig, ax = plt.subplots(figsize=(6, 3.5))
cats = country_rj_comp.index.tolist()
w = 0.35
xs = range(len(cats))
ax.bar([i - w/2 for i in xs], country_rj_comp["hard_rate"],    width=w, label="Hard rejection", color=FAIL_RED,   edgecolor="none")
ax.bar([i + w/2 for i in xs], country_rj_comp["blocked_rate"], width=w, label="Pipeline blocked", color=WARN_AMBER, edgecolor="none")
for i, cat in enumerate(cats):
    ax.text(i - w/2, country_rj_comp.loc[cat, "hard_rate"]    + 0.2, f"{country_rj_comp.loc[cat, 'hard_rate']:.1f}%",    ha="center", fontsize=8.5, color=GRAY)
    ax.text(i + w/2, country_rj_comp.loc[cat, "blocked_rate"] + 0.2, f"{country_rj_comp.loc[cat, 'blocked_rate']:.1f}%", ha="center", fontsize=8.5, color=GRAY)
ax.set_xticks(list(xs))
ax.set_xticklabels(cats)
ax.set_ylabel("% of total attempts")
ax.set_title("MEX vs ARG — Rejection Composition\n(% of total attempts per country)", fontsize=10)
ax.legend(fontsize=8.5)
plt.tight_layout()
CHART_ANOM_SEGMENTS = fig_to_b64(fig)


# ════════════════════════════════════════════════════════════════════════════
# DATA QUALITY summary table
# ════════════════════════════════════════════════════════════════════════════
dq_issues = [
    ("Incorrect label casing",
     "1,243 rows use <code>liveness_UNDETERMINED</code> (lowercase prefix) in "
     "<code>liveness_decision_details</code>. Per Jumio docs the correct label is "
     "<code>LIVENESS_UNDETERMINED</code> (all caps).",
     "We have assumed the correct value is LIVENESS_UNDETERMINED."),
    ("Liveness value misrouted to usability",
     "278 rows have <code>liveness_UNDETERMINED</code> in <code>usability_decision_details</code> "
     "and in <code>liveness_decision_details</code>. The value from the latter seems to have been "
     "copied by mistake to the former.",
     "We have assumed the usability check was passed and the failure occurred in the liveness check."),
    ("PASSED with usability not executed",
     "201 users have <code>usability_decision=NOT_EXECUTED</code> with detail <code>NOT_UPLOADED</code>, "
     "yet all downstream checks (Extraction, Image Checks, Liveness, Similarity) passed.",
     "We have assumed the usability check was passed instead of being not executed."),
     ("Non-standard top-level decision labels",
     "12 rows use <code>OK</code> (8) or <code>APPROVED</code> (4) in <code>decision_label</code> "
     "instead of <code>PASSED</code>; 1 row has <code>PASSED</code> in "
     "<code>usability_decision_details</code> instead of <code>OK</code>.",
     "We have assumed <code>OK</code>, <code>APPROVED</code> and <code>PASSED</code> to be " 
     "equivalent to each other."),
    ("Typo in check decisions",
     "3 rows use <code>PASSES</code> in <code>image_checks_decision</code>, <code>extraction_decision</code>, "
     "<code>data_checks_decision</code>.",
     "We have assumed <code>PASSES</code> to be equal to <code>PASSED</code>."),
    ("decision_type vs decision_label mismatch",
     "1 user has <code>decision_type=PASSED</code> in KYC_Summary but <code>decision_label=REJECTED</code> "
     "in KYC_Details — the two datasets are inconsistent for this record. ",
     "We have assumed the user passed (insignificant impact anyway)."),
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
  background: #FFFFFF;
  color: #111827;
  padding: 64px 72px;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  border-left: 6px solid #111827;
}
.cover h1 { font-size: 52px; font-weight: 800; color: #111827; margin-bottom: 14px; line-height: 1.1; }
.cover .subtitle { font-size: 21px; color: #374151; margin-bottom: 0; }
.cover .meta { font-size: 14px; color: #6B7280; border-top: 1px solid #E5E7EB; padding-top: 20px; margin-top: 0; }
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
ARQ_LOGO = """<svg width="200" height="68" viewBox="0 0 112 38" fill="none" xmlns="http://www.w3.org/2000/svg">
<path d="M36.303 13.1098V19.3799H0V13.1098C0 5.86928 5.89444 0 13.166 0H23.1357C30.4073 0 36.3017 5.86928 36.3017 13.1098H36.303ZM0 38H36.303V20.7106H0V38ZM72.699 13.1098V24.8889C72.699 32.1295 78.5934 37.9987 85.865 37.9987H91.4919V0H85.865C78.5934 0 72.699 5.86928 72.699 13.1098ZM37.6368 0V38L75.7972 37.9975L37.6368 0ZM71.7932 13.1098C71.7932 5.86928 65.8988 0 58.6272 0H39.5273L64.4873 24.8534C68.8186 22.7071 71.7945 18.2548 71.7945 13.1111L71.7932 13.1098ZM111.625 38L106.346 33.2394C109.551 30.8483 111.625 27.0352 111.625 22.7401V13.1098C111.625 5.86928 105.731 0 98.459 0H92.8283V38H111.625Z" fill="#111827"/>
</svg>"""

h(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>KYC Process Analysis — ARQ</title>
<style>{CSS}</style>
</head>
<body>
<div class="cover">
  <div>{ARQ_LOGO}</div>
  <div style="flex:1;display:flex;flex-direction:column;justify-content:center;padding:48px 0;">
    <div style="width:56px;height:4px;background:#111827;margin-bottom:36px;"></div>
    <h1>KYC Process Analysis</h1>
    <div class="subtitle">Identifying Inefficiencies &amp; Actionable Recommendations</div>
    <p style="font-size:15px;color:#6B7280;margin-top:28px;line-height:1.8;">
      Analysis of {total:,} KYC attempts across two markets (MEX &amp; ARG)<br>
      Period: {date_min} – {date_max}
    </p>
  </div>
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
  <a href="#limitations">4. Limitations</a>
  <a href="#analysis">5. Analysis</a>
  <a href="#overview" class="toc-sub">5.1 Dataset Overview</a>
  <a href="#jumio-docs" class="toc-sub">5.2 Jumio Documentation</a>
  <a href="#qualitative" class="toc-sub">5.3 Qualitative Review of Jumio</a>
  <a href="#data-quality" class="toc-sub">5.4 Data Cleaning</a>
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
  <p>Each finding is paired with a specific recommendation. Findings are ordered by estimated
  business impact.</p>

<div class="fr-pair no-break">
  <div class="fr-finding">
    <span class="fr-label">Finding 1 — Conversion</span>
    <strong>Pipeline blockages account for {n_pipeline_blocked/n_rejected*100:.0f}% of all rejections</strong>
    <p>{pct(n_pipeline_blocked, n_rejected)} of rejections occurred because the Extraction check never ran,
    stalling all downstream document checks. These are not genuine verification failures but rather
    infrastructure problems.</p>
  </div>
  <div class="fr-rec">
    <span class="fr-label">Recommendation</span>
    <strong>Diagnose and fix pipeline blockages</strong>
    <p>Investigate vendor API timeouts, upload failures, and whether Usability WARNINGs for unsupported docs should
    truly block Extraction. Implement retry logic and pre-submission image quality checks in-app.</p>
  </div>
</div>

<div class="fr-pair no-break">
  <div class="fr-finding">
    <span class="fr-label">Finding 2 — Conversion</span>
    <strong>Some document types are dealing to more failures</strong>
    <p>MEX National ID have an 89.3% pass rate vs. Electoral ID at 95.8%. 
    7.5% of failures are attributed to users uploading an unsupported document. 
    Document photo issues such as glare, blurr, data is hard to read, etc. represent over 10% of failures.   
    </p>
  </div>
  <div class="fr-rec">
    <span class="fr-label">Recommendation</span>
    <strong>Guide users during document upload</strong>
    <p>Add in-app guidance recommending Electoral ID as the preferred document for Mexican users.
    Make it clear for users what documents are not supported. Provide better guidance on how to 
    take a photo of the document.</p>
  </div>
</div>

<div class="fr-pair no-break">
  <div class="fr-finding">
    <span class="fr-label">Finding 3 — Conversion</span>
    <strong>{liveness_reasons.get('liveness_UNDETERMINED',0):,} liveness rejections are non-conclusive</strong>
    <p>Of {(df['liveness_decision']=='REJECTED').sum():,} liveness rejections, {liveness_reasons.get('liveness_UNDETERMINED',0):,}
    are <code>LIVENESS_UNDETERMINED</code>. Per Jumio docs this means the system could not reach a
    confident verdict, not that the user failed. These are mostly caused by poor lighting,
    glasses, movements not done as expected, or partial face visibility rather than spoofing attempts.</p>
  </div>
  <div class="fr-rec">
    <span class="fr-label">Recommendation</span>
    <strong>Introduce a guided retry flow for LIVENESS_UNDETERMINED</strong>
    <p>Instead of hard-rejecting these users, prompt them to retry with specific guidance
    (better lighting, remove glasses, move head in certain direction, ensure full face is visible). This distinction
    between UNDETERMINED and hard fraud signals (e.g. ID_USED_AS_SELFIE) should
    drive different user flows. This might require a discussion with Jumio or considering a different vendor.</p>
  </div>
</div>

<div class="fr-pair no-break">
  <div class="fr-finding">
    <span class="fr-label">Finding 4 — Operations</span>
    <strong>Rejection rate nearly doubled during Aug 21 – Sep 3</strong>
    <p>The weekly rejection rate spiked from a baseline of ~{baseline_rate:.1f}% to
    {max(spike_rates):.1f}% during this two-week window, then partially recovered
    but remained above baseline through the end of the observation period.</p>
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
    <span class="fr-label">Finding 5 — Data Quality</span>
    <strong>Multiple data quality issues indicate gaps in pipeline validation</strong>
    <p>Typos, inconsistent casing, misrouting of data to the wrong column, etc. suggest the data pipeline lacks schema validation and
    output contracts with the vendor and internal services.</p>
  </div>
  <div class="fr-rec">
    <span class="fr-label">Recommendation</span>
    <strong>Enforce data quality at the pipeline level</strong>
    <p>Add schema validation to reject non-standard label values in real time.
    Define and enforce a data contract with Jumio and internal services covering all expected field
    values, ensuring analytics remain reliable as the API evolves.</p>
  </div>
</div>

</div>
""")

# ─── Methodology ──────────────────────────────────────────────────────────────
h("""<div class="page">
<h2 id="methodology">3. Methodology</h2>
<p>This document and supporting analysis was primarily done on Python and HTML using Claude Code. 
  The repository with the code and changes is available in 
  <a href="https://github.com/joaquin-coitino/kyc-home-task-arq">Github<a>.</p>
<p>The process to solve the problem was "greedy". We did not start with any hypothesis or predetermined workflow.
  We started by providing Claude Code with the description of the task and datasets and requested it to output a solution.
  We then recursively reviewed the output and, as soon as we identified the first material mistake (or suboptimal part), we requested 
  Claude Code to fix and update the analysis (or parts of it). In order to ensure each new version Claude Code generated was better
  than the previous we provided the missing context (e.g.: Jumio docs, my own observations, summary of interview with a subject matter 
  expert). To prevent regressions, some context ia stored in the repo itself so Claude Code can refer to it and each change 
  is reviewed before committing and pushing. </p>
</div>
""")

# ─── Limitations ────────────────────────────────────────────────
h("""<div class="page">
<h2 id="limitations">4. Limitations</h2>
  <p>The following limitations were identified during the analysis.
  They do not invalidate the findings but should be considered when acting on recommendations.</p>
<table>
  <tr><th>Area</th><th>Limitations</th></tr>
  <tr><td><strong>Unclear retry behaviour</strong></td><td>The dataset contains one row per user with no retry history. It is unknown if some users re-attempted KYC and ultimately passed. Retry success rates would materially change the conversion impact estimates.</td></tr>
  <tr><td><strong>Data quality issues</strong></td><td>Multiple instances have been found of data that seems incorrect. However, we are unable to confirm if they are actually errors and what the correct value should be.</td></tr>
  <tr><td><strong>API version changes</strong></td><td>The dataset is from 2023; the Jumio documentation used reflects the current API (2026). Some label names or decision behaviours may have changed. This introduces a risk of the data being misinterpreted.</td></tr>
  <tr><td><strong>Short time period</strong></td><td>The analysis covers ~2 months (Jul–Sep 2023). Seasonal patterns, long-term trends, and year-on-year comparisons are not possible with this data.</td></tr>
  <tr><td><strong>No Colombian users</strong></td><td>According to ARQ's website in July 2023, ARQ (DolarApp) was live in Colombia (this can be seen using Wayback Machine). However, it is not known why there are no records of Colombian users in the data set.</td></tr>
  <tr><td><strong>Narrow scope of data</strong></td><td>The dataset only gives a small view of ARQ's KYC flows. No access has been provided to logs, Jumio support, codebase, etc.. However, those elements are key to diagnosing and solving the problem.</td></tr>
</table>
</div>
""")

# ─── Analysis wrapper ──────────────────────────────────────────────────────────
h("""<div class="page">
<h2 id="analysis">5. Analysis</h2>
  <p>Chain of reasoning that led to the findings and recommendations.</p>
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
    Data Checks, Liveness, Similarity, Watchlist Screening.</p>
    
  </div>
</div>
  <div class="finding blue no-break">
  <strong>Priorities for Analysis</strong>
  <ul style="margin:0 0 0 18px;line-height:1.8;">
      <li>Warnings are only ~1% of total attempts so we will be focusing on the larger problem of rejections.</li>
      <li>Analysing both Mexico and Argentina is important as they have roughly similar volumes.</li>
      <li>We will only look at ID cards and passports as they represent 98% of documents used by users.</li>
  </ul>
</div>
      
</div>
""")

# ─── 5.2 Jumio Documentation ──────────────────────────────────────────────────
h(f"""<div class="page">
<h2 id="jumio-docs">5.2 Jumio Documentation</h2>
  <p>Jumio's documentation explains the different checks that are part of the KYC pipeline.</p>

<h3>Check Overview</h3>
<table>
  <tr><th>Check</th><th>What it tests</th><th>Possible decisions</th></tr>
  <tr>
    <td><strong>Usability</strong></td>
    <td>Whether uploaded images (ID and selfie) are of sufficient quality to process</td>
    <td>PASSED, REJECTED, WARNING, NOT_EXECUTED</td>
  </tr>
  <tr>
    <td><strong>Extraction</strong></td>
    <td>Whether mandatory fields can be extracted from the ID</td>
    <td>PASSED, NOT_EXECUTED</td>
  </tr>
  <tr>
    <td><strong>Image Checks</strong></td>
    <td>Whether the ID passes integrity tests</td>
    <td>PASSED, REJECTED, WARNING, NOT_EXECUTED</td>
  </tr>
  <tr>
    <td><strong>Data Checks</strong></td>
    <td>Whether extracted data is internally consistent and does not match known fraud patterns or prior rejected transactions</td>
    <td>PASSED, REJECTED, WARNING, NOT_EXECUTED</td>
  </tr>
  <tr>
    <td><strong>Watchlist Screening</strong></td>
    <td>Whether the user appears on global sanctions lists, PEP databases, or adverse media sources</td>
    <td>PASSED, WARNING (ALERT), NOT_EXECUTED</td>
  </tr>
  <tr>
    <td><strong>Liveness</strong></td>
    <td>Whether the selfie was captured from a live person (detects spoofing, printed photos, screen recordings)</td>
    <td>PASSED, REJECTED, WARNING, NOT_EXECUTED</td>
  </tr>
  <tr>
    <td><strong>Similarity</strong></td>
    <td>Whether the face in the selfie matches the face on the ID document</td>
    <td>PASSED (MATCH), REJECTED (NO_MATCH), WARNING (NOT_POSSIBLE), NOT_EXECUTED</td>
  </tr>
</table>

<h3>Check Dependency Graph</h3>
<p>Some checks can only run once another check has run.</p>
<div class="chart-box">{img_tag(CHART_DAG)}</div>
</div>
""")

# ─── 5.3 Qualitative Review of Jumio ─────────────────────────────────────────
h("""<div class="page">
<h2 id="qualitative">5.3 Qualitative Review of Jumio</h2>
  <p>To complement the quantitative data, a conversation was held with <strong>Agustín Pividori</strong>,
  FinCrime lead at Personal Pay (a LATAM fintech and <strong>active Jumio customer</strong>). The insights below
  reflect his direct experience operating Jumio in production. </p>

<h3>Key Points</h3>
<ul style="margin:0 0 0 18px;line-height:1.8;">
  <li>Personal Pay selected Jumio primarily on cost.</li>
  <li>FaceTec is the main competitor (widely used by Mercado Libre and major banks).</li>
  <li>National ID is the only universally required document type across LATAM financial institutions. Passports and driver's licenses are much less common (note: consistent with our dataset where ID Cards represent 86% of all attempts).</li>
  <li>Jumio's document capture is aggressive in rejecting images that do not meet its quality bar. This creates friction.</li>
  <li>False positives were a concern prior to SLA negotiations; once managed, they came within agreed limits.</li>
</ul>
  
<div class="finding blue no-break">
  <strong>Things to Keep an Eye On</strong>
<ul style="margin:0 0 0 18px;line-height:1.8;">
  <li> Although unlikely to be visible in the current data set, we will keep an eye during the analysis on false positives that might merit a discussion with Jumio. </li>
  <li> Verify if image quality rejections are excessive as this might indicate an issue with Jumio and warrant considering alternative vendors. </li>
</ul>
  </div>
</div>
""")

# ─── 5.4 Data Cleaning ────────────────────────────────────────────────────────
h("""<div class="page">
<h2 id="data-quality">5.4 Data Cleaning</h2>
  <p>Several data quality issues were identified in the dataset. They can
  affect downstream analytics and thus we had to make a decision on how to correct the data.</p>
<table>
  <tr>
    <th>Issue</th>
    <th>Description</th>
    <th>Treatment</th>
  </tr>
""")
for title, desc, fix in dq_issues:
    h(f"  <tr><td><strong>{title}</strong></td><td>{desc}</td><td>{fix}</td></tr>")
h("""</table>
  
<div class="finding blue no-break">
  <strong>Fixing Data Quality Issues</strong>
  The first 3 issues seem the result of pipeline problems that should be fixed at the source.
</div>
</div>
""")

# ─── 5.5 Pass Rates ───────────────────────────────────────────────────────────
mex_total = (df["data_issuing_country"] == "MEX").sum()
arg_total = (df["data_issuing_country"] == "ARG").sum()

h(f"""<div class="page">
<h2 id="pass-rates">5.5 Pass Rates</h2>
<p> Pass rates are analysed across four dimensions: time (weekly trend), country, document type, age.</p>

<h3>Trend Over Time</h3>
<div class="chart-box">{img_tag(CHART_WEEKLY)}</div>
<p>The rejection rate jumped from a baseline of ~{baseline_rate:.1f}% to
  {spike_rates[0]:.1f}% (Aug 21–27) and {spike_rates[1]:.1f}% (Aug 28–Sep 3), i.e.:
  a {spike_rates[1]/baseline_rate:.1f}× increase. The rate partially recovered but remained
  above baseline through the end of the observation period.</p>

<h3>By Country</h3>
<div class="chart-row">
  <div class="chart-box">{img_tag(CHART_COUNTRY)}</div>
  <div>
    <p>There is a <strong>10.6 percentage-point gap</strong> in pass rates between Mexico and Argentina.</p>
  </div>
</div>

<h3>By Document Type</h3>
<div class="chart-row">
  <div class="chart-box">{img_tag(CHART_DOC_TYPE)}</div>
  <div>
    <p>Passports achieve the higher pass rates (<strong>96.4%</strong>) compared to
    ID Cards (92.6%). This is understandable as passports are more standardised.</p>
    <p>Within ID Cards, Mexico's Electoral IDs (95.8%) outperform National IDs (89.3%) by
    6.5 percentage points.</p>
  </div>
</div>
<div class="chart-box"><p style="font-size:12px;color:#6B7280;margin-bottom:6px;">ID Cards only as they are by far the most common document type ({(df['data_type']=='ID_CARD').sum():,} attempts, {(df['data_type']=='ID_CARD').sum()/total*100:.0f}% of all attempts).</p>{img_tag(CHART_SUBTYPE)}</div>

<h3>By Age Group</h3>
<div class="chart-row">
  <div class="chart-box">{img_tag(CHART_AGE)}</div>
  <div>
    <p>Among adult cohorts, pass rates are <strong>broadly stable</strong>, ranging from
    <strong>{age_stats.loc[age_stats['age_group']=='65+','pass_rate'].values[0]:.1f}%</strong> (65+) to
    <strong>{age_stats.loc[age_stats['age_group']=='18–24','pass_rate'].values[0]:.1f}%</strong> (18–24), which is
    a spread of only {age_stats.loc[age_stats['age_group']=='18–24','pass_rate'].values[0] - age_stats.loc[age_stats['age_group']=='65+','pass_rate'].values[0]:.1f} percentage points.</p>
    <p><strong>&lt;18 ({age_stats.loc[age_stats['age_group']=='<18','total'].values[0]:,} users,
    {age_stats.loc[age_stats['age_group']=='<18','pass_rate'].values[0]:.1f}% pass rate):</strong>
    Best case and mostly likely scenario, this is a data quality issue. Worst case scenario minors are being onboarded.</p>
    <p><strong>Unknown ({age_stats.loc[age_stats['age_group']=='Unknown','total'].values[0]:,} users,
    {age_stats.loc[age_stats['age_group']=='Unknown','pass_rate'].values[0]:.1f}% pass rate):</strong>
    No <code>year_birth</code> recorded. It is concerning there are any passes without a year of birth.</p>
  </div>
</div>

<div class="finding blue no-break">
  <strong>Root Cause of Analysis </strong>
  <ul style="margin:0 0 0 18px;line-height:1.8;">
    <li> We will look at the cause of the August spike. </li>
    <li> We will look at the cause of the pass rate difference between Argentina and Mexico. </li>
  </ul>
  </div>
</div>
""")

# ─── 5.6 Rejection Causes ────────────────────────────────────────────────────
h(f"""<div class="page">
<h2 id="rejection-causes">5.6 Rejection Causes</h2>
<p>Rejections are attributed to the first check that blocked the pipeline.</p>
<div class="chart-box">{img_tag(CHART_FAIL_CHECK)}</div>
<div class="finding blue no-break">
  <strong>Pipeline blockages: {n_pipeline_blocked:,} rejections ({n_pipeline_blocked/n_rejected*100:.1f}% of all rejections)</strong>
  These users were not rejected because a check explicitly failed but instead because the pipeline itself stalled.
  <ul style="margin:8px 0 0 18px;font-size:13px;">
    <li><strong>Extraction blocked ({n_extraction_blocked:,}):</strong> Usability passed but Extraction never ran, halting Image Checks, Data Checks, and Watchlist Screening.</li>
    <li><strong>Usability WARNING cascaded ({n_usability_warn:,}):</strong> A usability warning was treated as a hard blocker for Extraction because document was unsupported.</li>
    <li><strong>Usability not executed ({n_usability_noexec:,}):</strong> The root check itself did not run. Could be that the user did not provide the document or that there is a bug preventing processing.</li>
  </ul>
</div>

<div class="chart-row">
  <div class="chart-box">
    <h3>Usability Failures</h3>
    {img_tag(CHART_USABILITY)}
    <p style="font-size:12.5px;color:#6B7280;margin-top:8px;">
      Usability failures are partially solvable with better UX.
    </p>
  </div>
  <div class="chart-box">
    <h3>Image Check Failures</h3>
    {img_tag(CHART_IMAGE)}
    <p style="font-size:12.5px;color:#6B7280;margin-top:8px;">
      Manipulation failures are likely fraud. It is a good thing they have failed.
      Digital copy failures could be legitimate and some of them can be addressed with better UX.
    </p>
  </div>
</div>
<div class="chart-row">
  <div class="chart-box">
    <h3>Liveness Failures</h3>
    {img_tag(CHART_LIVENESS)}
    <p style="font-size:12.5px;color:#6B7280;margin-top:8px;">
      Liveness undetermined failures are mostly due to UX.
    </p>
  </div>
  <div class="chart-box">
    <h3>Similarity Failures</h3>
    {img_tag(CHART_SIMILARITY)}
    <p style="font-size:12.5px;color:#6B7280;margin-top:8px;">
      No match failures are likely actual cases of fraud. Face matching tech is very mature so mistakes are rare.
    </p>
  </div>
</div>
</div>
""")

# ─── 5.7 Anomaly Investigation ────────────────────────────────────────────────
h(f"""<div class="page">
<h2 id="anomaly">5.7 Anomaly Investigation</h2>
  <p>We will review the impact of pipeline blockages vs hard rejections on the rejection spike in late August and
  a lower pass rate in Mexico compared to Argentina. </p>

<h3>August Rejection Spike</h3>
<div class="chart-box">{img_tag(CHART_ANOM_WEEKLY)}</div>
<div class="finding blue no-break">
  <strong>Pipeline blockages {'do not explain' if abs(spike_blocked_pct - baseline_blocked_pct) < 5 else 'partially explain'} the August spike</strong>
  During the spike weeks (Aug 21 – Sep 3), pipeline blockages accounted for <strong>{spike_blocked_pct:.1f}%</strong> of rejections, compared to <strong>{baseline_blocked_pct:.1f}%</strong> during the baseline weeks, a
  {'negligible' if abs(spike_blocked_pct - baseline_blocked_pct) < 5 else 'notable'}
  {'difference' if abs(spike_blocked_pct - baseline_blocked_pct) < 5 else f'{abs(spike_blocked_pct - baseline_blocked_pct):.1f}pp shift'}.
  {'The composition of rejections remained essentially unchanged: the spike was driven by a higher volume of <em>both</em> hard failures and pipeline blockages, not by a shift in their mix. This rules out a targeted pipeline degradation. More likely causes: a new user acquisition batch, increased fraud volume, or an app change affecting all check types.' if abs(spike_blocked_pct - baseline_blocked_pct) < 5 else 'The increase in pipeline blockages during the spike suggests a vendor-side or infrastructure issue may have contributed to the elevated rejection rate.'}
</div>

<h3>Mexico vs Argentina Pass Rate</h3>
<div class="chart-box">{img_tag(CHART_ANOM_SEGMENTS)}</div>
<div class="finding blue no-break">
  <strong>Pipeline blockages {'are' if mex_blocked_pct - arg_blocked_pct > 3 else 'are not'} a primary driver of the MEX–ARG gap</strong>
  In Mexico, {mex_blocked_pct:.1f}% of total attempts end as pipeline blockages, vs
  {arg_blocked_pct:.1f}% in Argentina — a {mex_blocked_pct - arg_blocked_pct:.1f}pp difference.
  {'This gap is material and contributes meaningfully to the overall pass rate differential. Fixing MEX pipeline blockages would directly close part of the 10.6pp gap.' if mex_blocked_pct - arg_blocked_pct > 3 else 'The gap is small, suggesting pipeline blockages are not the primary driver of the MEX–ARG pass rate difference. The gap is more likely driven by document mix (National vs Electoral ID) and user/device quality differences.'}
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
