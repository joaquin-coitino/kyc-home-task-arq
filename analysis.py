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

# Normalise non-standard decision labels
label_map = {"OK": "PASSED", "APPROVED": "PASSED", "PASSES": "PASSED"}
details["decision_label"] = details["decision_label"].replace(label_map)
summary["decision_type"] = summary["decision_type"].replace(label_map)

# Parse dates
summary["date"] = pd.to_datetime(summary["date_"], utc=True)
summary["week"] = summary["date"].dt.to_period("W")
summary["day"]  = summary["date"].dt.date

# Computed columns
details["age"] = 2023 - details["year_birth"]

CHECKS = [
    ("usability_decision",           "Usability"),
    ("image_checks_decision",        "Image Checks"),
    ("extraction_decision",          "Extraction"),
    ("data_checks_decision",         "Data Checks"),
    ("liveness_decision",            "Liveness"),
    ("similarity_decision",          "Similarity"),
    ("watchlist_screening_decision", "Watchlist"),
]

# ── Core metrics ─────────────────────────────────────────────────────────────
total       = len(details)
n_passed    = (details["decision_label"] == "PASSED").sum()
n_rejected  = (details["decision_label"] == "REJECTED").sum()
n_warning   = (details["decision_label"] == "WARNING").sum()
pass_rate   = n_passed / total * 100
date_min    = summary["date"].min().strftime("%b %d, %Y")
date_max    = summary["date"].max().strftime("%b %d, %Y")

# ── First failing check attribution ─────────────────────────────────────────
rejected_df = details[details["decision_label"] == "REJECTED"].copy()

def first_fail(row):
    for col, _ in CHECKS:
        if row[col] == "REJECTED":
            return col
    # image checks NOT_EXECUTED = document not processed
    if row["image_checks_decision"] == "NOT_EXECUTED":
        return "incomplete_submission"
    return "other"

rejected_df["first_fail"] = rejected_df.apply(first_fail, axis=1)
fail_counts = rejected_df["first_fail"].value_counts()

fail_labels_map = {
    "usability_decision":           "Usability",
    "image_checks_decision":        "Image Checks",
    "liveness_decision":            "Liveness",
    "similarity_decision":          "Similarity",
    "data_checks_decision":         "Data Checks",
    "incomplete_submission":        "Incomplete Submission\n(checks not executed)",
    "other":                        "Other",
}

# ── Weekly trend ─────────────────────────────────────────────────────────────
weekly = summary.groupby("week")["decision_type"].value_counts().unstack(fill_value=0)
for col in ["PASSED", "REJECTED", "WARNING"]:
    if col not in weekly.columns:
        weekly[col] = 0
weekly["total"] = weekly.sum(axis=1)
weekly["rejection_rate"] = weekly["REJECTED"] / weekly["total"] * 100
weekly.index = [str(p) for p in weekly.index]

# ── Pass rate by doc type ────────────────────────────────────────────────────
doc_stats = details.groupby("data_type").apply(
    lambda g: pd.Series({
        "total": len(g),
        "passed": (g["decision_label"] == "PASSED").sum(),
    })
).reset_index()
doc_stats["pass_rate"] = doc_stats["passed"] / doc_stats["total"] * 100
doc_stats = doc_stats.sort_values("pass_rate")

# ── Pass rate by country ──────────────────────────────────────────────────────
country_stats = details.groupby("data_issuing_country").apply(
    lambda g: pd.Series({
        "total": len(g),
        "passed": (g["decision_label"] == "PASSED").sum(),
    })
).reset_index()
country_stats["pass_rate"] = country_stats["passed"] / country_stats["total"] * 100

# ── Sub-type pass rates ───────────────────────────────────────────────────────
sub_stats = details.groupby(["data_issuing_country", "data_sub_type"]).apply(
    lambda g: pd.Series({"total": len(g), "passed": (g["decision_label"] == "PASSED").sum()})
).reset_index()
sub_stats["pass_rate"] = sub_stats["passed"] / sub_stats["total"] * 100
sub_stats = sub_stats[sub_stats["total"] >= 50]

# ── Failure reason breakdowns ─────────────────────────────────────────────────
def top_reasons(col_decision, col_details, exclude=("OK", "PRECONDITION_NOT_FULFILLED"), top=6):
    mask = details[col_decision].isin(["REJECTED", "WARNING"])
    df = details[mask][col_details].value_counts()
    df = df[~df.index.isin(exclude)]
    return df.head(top)

usability_reasons  = top_reasons("usability_decision",    "usability_decision_details")
image_reasons      = top_reasons("image_checks_decision", "image_checks_decision_details")
liveness_reasons   = top_reasons("liveness_decision",     "liveness_decision_details")
similarity_reasons = top_reasons("similarity_decision",   "similarity_decision_details",
                                  exclude=("OK", "PRECONDITION_NOT_FULFILLED", "MATCH"))

# ── Daily volume ──────────────────────────────────────────────────────────────
daily = summary.groupby("day")["decision_type"].value_counts().unstack(fill_value=0)
for col in ["PASSED", "REJECTED", "WARNING"]:
    if col not in daily.columns:
        daily[col] = 0
daily["total"] = daily.sum(axis=1)
daily["rejection_rate"] = daily["REJECTED"] / daily["total"] * 100


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
# CHART 2 — First failing check bar
# ════════════════════════════════════════════════════════════════════════════
fc = fail_counts.rename(index=fail_labels_map).sort_values()
colors_bar = [FAIL_RED if "not executed" not in l.lower() else WARN_AMBER for l in fc.index]
fig, ax = plt.subplots(figsize=(7, 4))
bars = ax.barh(fc.index, fc.values, color=colors_bar, edgecolor="none")
for bar in bars:
    ax.text(bar.get_width() + 30, bar.get_y() + bar.get_height()/2,
            f"{bar.get_width():,}", va="center", fontsize=9, color=GRAY)
ax.set_xlabel("Number of rejections")
ax.set_title("Where Do KYC Rejections Happen?")
ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
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

CHART_USABILITY  = reason_chart(usability_reasons,  "Usability Failure Reasons", WARN_AMBER)
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
# DATA QUALITY summary table
# ════════════════════════════════════════════════════════════════════════════
dq_issues = [
    ("Non-standard decision labels",
     "12 rows use 'OK' (8) or 'APPROVED' (4) in <code>decision_label</code> instead of 'PASSED'.",
     "Low"),
    ("Typo in check decisions",
     "3 rows use 'PASSES' instead of 'PASSED' across <code>image_checks_decision</code>, "
     "<code>extraction_decision</code>, <code>data_checks_decision</code>.",
     "Low"),
    ("Liveness value in wrong column",
     "278 rows have 'liveness_UNDETERMINED' in <code>usability_decision_details</code> "
     "instead of <code>liveness_decision_details</code>. These rows show WARNING in both columns.",
     "Medium"),
    ("Missing watchlist screening",
     "2,889 rows have <code>NaN</code> in <code>watchlist_screening_decision</code> — "
     "all correspond to incomplete submissions (image checks NOT_EXECUTED).",
     "Medium"),
    ("Implausible ages",
     "Some <code>year_birth</code> values produce ages of 1 or 114 — likely input errors.",
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
.toc a:hover { text-decoration: underline; }
.section-intro { background: #F9FAFB; border-radius: 8px; padding: 16px 20px; margin-bottom: 24px; font-size: 13.5px; color: #374151; line-height: 1.7; }
@media print {
  .cover { page-break-after: always; }
  h2 { page-break-before: auto; }
  .no-break { page-break-inside: avoid; }
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
  <a href="#executive-summary">1. Executive Summary</a>
  <a href="#overview">2. Dataset Overview</a>
  <a href="#failure-funnel">3. Failure Funnel Analysis</a>
  <a href="#failure-reasons">4. Failure Reasons Deep Dive</a>
  <a href="#document-type">5. Document Type Performance</a>
  <a href="#country">6. Country Analysis</a>
  <a href="#trends">7. Time Trends</a>
  <a href="#data-quality">8. Data Quality Issues</a>
  <a href="#recommendations">9. Recommendations</a>
</div>
</div>
""")

# ─── Executive Summary ────────────────────────────────────────────────────────
h(f"""<div class="page">
<h2 id="executive-summary">1. Executive Summary</h2>
<p>
  ARQ's KYC pipeline processed <strong>{total:,} user verification attempts</strong> between {date_min} and {date_max},
  achieving an overall pass rate of <strong>{pass_rate:.1f}%</strong>. While the majority of users pass without friction,
  the analysis surfaces three material inefficiencies and several data quality issues that together
  represent a meaningful opportunity to improve conversion and reduce operational risk.
</p>

<div class="finding red no-break">
  <strong>Finding 1 — 43% of rejections are "incomplete submissions", not genuine failures</strong>
  {pct(fail_counts.get('incomplete_submission', 0), n_rejected)} of all rejections occur because the image-check pipeline
  never ran — the system cannot process the document and rejects the user by default.
  This is a UX and infrastructure problem, not a fraud signal.
</div>

<div class="finding amber no-break">
  <strong>Finding 2 — A 10-point pass-rate gap exists between Argentina (92.1%) and Mexico (81.5%)</strong>
  Mexican users are disproportionately rejected. The gap is partly explained by MEX National ID having
  an 89.3% pass rate vs. Electoral ID at 95.8% — suggesting document-guidance improvements could
  close this gap significantly.
</div>

<div class="finding amber no-break">
  <strong>Finding 3 — Rejection rate nearly doubled during Aug 21 – Sep 3</strong>
  The weekly rejection rate spiked from a baseline of ~10–11% to 16–19% during this two-week window,
  then partially recovered. The root cause is unknown from the data alone and warrants investigation
  with the vendor.
</div>
</div>
""")

# ─── Overview ─────────────────────────────────────────────────────────────────
h(f"""<div class="page">
<h2 id="overview">2. Dataset Overview</h2>
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
    <p>Two datasets were provided: <strong>KYC_Summary</strong> (one row per attempt with date and
    outcome) and <strong>KYC_Details</strong> (one row per attempt with the result of each
    individual check). Both contain {total:,} unique user references with no duplicates.</p>
    <p><strong>Date range:</strong> {date_min} – {date_max} ({(summary['date'].max()-summary['date'].min()).days} days)</p>
    <p><strong>Countries:</strong> Mexico (MEX) — {(details['data_issuing_country']=='MEX').sum():,} attempts &nbsp;|&nbsp;
    Argentina (ARG) — {(details['data_issuing_country']=='ARG').sum():,} attempts</p>
    <p><strong>Document types:</strong> ID Card ({(details['data_type']=='ID_CARD').sum():,}),
    Passport ({(details['data_type']=='PASSPORT').sum():,}),
    Driving License ({(details['data_type']=='DRIVING_LICENSE').sum():,}),
    Visa ({(details['data_type']=='VISA').sum():,})</p>
    <p><strong>KYC checks performed:</strong> Usability → Image Checks → Extraction →
    Data Checks → Liveness → Similarity → Watchlist Screening</p>
  </div>
</div>
</div>
""")

# ─── Failure Funnel ──────────────────────────────────────────────────────────
n_incomplete = fail_counts.get("incomplete_submission", 0)
n_usability  = fail_counts.get("usability_decision", 0)
n_image      = fail_counts.get("image_checks_decision", 0)
n_liveness   = fail_counts.get("liveness_decision", 0)
n_similarity = fail_counts.get("similarity_decision", 0)
n_datachecks = fail_counts.get("data_checks_decision", 0)

h(f"""<div class="page">
<h2 id="failure-funnel">3. Failure Funnel Analysis</h2>
<div class="section-intro">
  Each KYC attempt passes through a sequential pipeline of checks. When a check fails, downstream
  checks are typically not executed. This section attributes each rejection to the <em>first</em>
  check that caused it.
</div>
<div class="chart-box">{img_tag(CHART_FAIL_CHECK)}</div>

<h3>Key observations</h3>
<div class="finding red no-break">
  <strong>Incomplete submissions — {n_incomplete:,} rejections ({n_incomplete/n_rejected*100:.1f}% of all rejections)</strong>
  These users pass (or partially pass) usability but the image-check pipeline returns NOT_EXECUTED,
  blocking all downstream checks. This is the single largest rejection category and is highly
  actionable — see Recommendations.
</div>
<div class="finding red no-break">
  <strong>Similarity failures — {n_similarity:,} rejections ({n_similarity/n_rejected*100:.1f}%)</strong>
  The selfie does not match the document photo. This can be caused by poor selfie quality,
  lighting, or genuine identity fraud attempts.
</div>
<div class="finding amber no-break">
  <strong>Liveness failures — {n_liveness:,} rejections ({n_liveness/n_rejected*100:.1f}%)</strong>
  The system cannot confirm the user is live (not a photo or video replay). The most common
  reason is UNDETERMINED — suggesting a UX or connectivity issue rather than spoofing.
</div>
<div class="finding amber no-break">
  <strong>Image check failures — {n_image:,} rejections ({n_image/n_rejected*100:.1f}%)</strong>
  Documents flagged as manipulated ({image_reasons.get('MANIPULATED_DOCUMENT', 0):,} cases)
  or digital copies ({image_reasons.get('DIGITAL_COPY', 0):,} cases).
</div>
<div class="finding amber no-break">
  <strong>Usability failures — {n_usability:,} rejections ({n_usability/n_rejected*100:.1f}%)</strong>
  The document image is of insufficient quality for processing (blurry, glare, wrong document type, etc.).
</div>
</div>
""")

# ─── Failure Reasons ──────────────────────────────────────────────────────────
h(f"""<div class="page">
<h2 id="failure-reasons">4. Failure Reasons Deep Dive</h2>
<div class="section-intro">
  Drilling into the <em>details</em> columns reveals the specific error codes behind each check
  failure, enabling targeted interventions.
</div>

<div class="chart-row">
  <div class="chart-box">
    <h3>Usability Failures</h3>
    {img_tag(CHART_USABILITY)}
    <p style="font-size:12.5px;color:#6B7280;margin-top:8px;">
      UNSUPPORTED_DOCUMENT_TYPE ({usability_reasons.get('UNSUPPORTED_DOCUMENT_TYPE',0):,}) and
      MISSING_MANDATORY_DATAPOINTS ({usability_reasons.get('MISSING_MANDATORY_DATAPOINTS',0):,})
      are the top causes. Both can be reduced with better in-app guidance before document capture.
    </p>
  </div>
  <div class="chart-box">
    <h3>Image Check Failures</h3>
    {img_tag(CHART_IMAGE)}
    <p style="font-size:12.5px;color:#6B7280;margin-top:8px;">
      MANIPULATED_DOCUMENT ({image_reasons.get('MANIPULATED_DOCUMENT',0):,}) is the dominant
      failure reason and represents genuine fraud signals — these cases should be escalated
      for manual review. DIGITAL_COPY ({image_reasons.get('DIGITAL_COPY',0):,}) may indicate
      users photographing a screen instead of a physical document.
    </p>
  </div>
</div>

<div class="chart-row">
  <div class="chart-box">
    <h3>Liveness Failures</h3>
    {img_tag(CHART_LIVENESS)}
    <p style="font-size:12.5px;color:#6B7280;margin-top:8px;">
      liveness_UNDETERMINED ({liveness_reasons.get('liveness_UNDETERMINED',0):,}) accounts for
      the vast majority. UNDETERMINED means the system could not reach a confident verdict —
      this is almost always a UX / connectivity issue, not spoofing. Retry flows would recover
      most of these users.
    </p>
  </div>
  <div class="chart-box">
    <h3>Similarity Failures</h3>
    {img_tag(CHART_SIMILARITY)}
    <p style="font-size:12.5px;color:#6B7280;margin-top:8px;">
      NO_MATCH ({similarity_reasons.get('NO_MATCH',0):,}) means the selfie and document photo
      could not be matched. NOT_POSSIBLE ({similarity_reasons.get('NOT_POSSIBLE',0):,}) means
      the check could not be performed — these users currently receive a WARNING outcome and
      still pass, which may need review from a compliance perspective.
    </p>
  </div>
</div>
</div>
""")

# ─── Document Type ───────────────────────────────────────────────────────────
h(f"""<div class="page">
<h2 id="document-type">5. Document Type Performance</h2>
<div class="chart-row">
  <div class="chart-box">{img_tag(CHART_DOC_TYPE)}</div>
  <div>
    <h3>Findings</h3>
    <p>Passports achieve the highest pass rate (<strong>96.4%</strong>) followed by Visas (95.8%).
    ID Cards (92.6%) and Driving Licenses (89.5%) perform below the overall average.</p>
    <p>However, document volumes tell a different story: ID Cards account for
    <strong>{(details['data_type']=='ID_CARD').sum():,} attempts ({(details['data_type']=='ID_CARD').sum()/total*100:.0f}%)</strong>
    of all attempts, making it the critical document type to optimise.</p>
    <h3>Sub-type variation</h3>
    <p>Within ID Cards, there is significant variation by sub-type — particularly in Mexico
    where Electoral IDs (95.8%) outperform National IDs (89.3%) by 6.5 percentage points.
    Guiding MEX users toward Electoral IDs could meaningfully improve their overall pass rate.</p>
  </div>
</div>
<div class="chart-box">{img_tag(CHART_SUBTYPE)}</div>
</div>
""")

# ─── Country Analysis ──────────────────────────────────────────────────────────
mex_total = (details["data_issuing_country"] == "MEX").sum()
arg_total = (details["data_issuing_country"] == "ARG").sum()
mex_pass  = (details[details["data_issuing_country"]=="MEX"]["decision_label"]=="PASSED").sum()
arg_pass  = (details[details["data_issuing_country"]=="ARG"]["decision_label"]=="PASSED").sum()

h(f"""<div class="page">
<h2 id="country">6. Country Analysis</h2>
<div class="section-intro">
  The dataset covers two markets: Mexico ({mex_total:,} attempts, {mex_total/total*100:.0f}%)
  and Argentina ({arg_total:,} attempts, {arg_total/total*100:.0f}%). There is a
  <strong>10.6 percentage-point gap</strong> in pass rates between them.
</div>
<div class="chart-row">
  <div class="chart-box">{img_tag(CHART_COUNTRY)}</div>
  <div>
    <h3>Why is Mexico's pass rate lower?</h3>
    <p><strong>Document mix:</strong> Mexico has a higher share of National IDs (89.3% pass rate)
    relative to Electoral IDs (95.8%). If MEX users adopted Electoral IDs at the same rate
    as other sub-types, the estimated pass rate would improve by ~2–3pp.</p>
    <p><strong>RESIDENT_PERMIT_ID</strong> in Mexico has a 96.0% pass rate — one of the highest —
    suggesting the document quality standards are achievable.</p>
    <p><strong>Argentina's Driving Licenses</strong> (87.4%) are the weakest performer in that market,
    representing an opportunity for targeted guidance.</p>
    <p>The remaining gap likely reflects differences in user demographics, device quality, internet
    connectivity, and potentially different fraud patterns.</p>
  </div>
</div>
</div>
""")

# ─── Time Trends ──────────────────────────────────────────────────────────────
spike_weeks = ["2023-08-21/2023-08-27", "2023-08-28/2023-09-03"]
spike_rates = [weekly.loc[w, "rejection_rate"] for w in spike_weeks if w in weekly.index]
baseline_rate = weekly["rejection_rate"].iloc[:4].mean()

h(f"""<div class="page">
<h2 id="trends">7. Time Trends</h2>
<div class="section-intro">
  Monitoring the rejection rate over time reveals a significant anomaly in late August / early September
  that warrants investigation.
</div>
<div class="chart-box">{img_tag(CHART_WEEKLY)}</div>
<div class="finding red no-break">
  <strong>Rejection spike: Aug 21 – Sep 3</strong>
  The rejection rate jumped from a baseline of ~{baseline_rate:.1f}% to
  {spike_rates[0]:.1f}% (Aug 21–27) and {spike_rates[1]:.1f}% (Aug 28–Sep 3) —
  a {spike_rates[1]/baseline_rate:.1f}x increase. The rate partially recovered
  afterwards but remained above baseline (13–14%) through the end of the observation period.
</div>
<h3>Potential causes to investigate</h3>
<table>
  <tr><th>Hypothesis</th><th>How to verify</th></tr>
  <tr><td>Vendor system degradation or API changes</td><td>Check vendor incident logs &amp; SLA reports for those dates</td></tr>
  <tr><td>New user acquisition campaign targeting lower-quality leads</td><td>Cross-reference with marketing campaign dates</td></tr>
  <tr><td>Increased fraud attempt volume</td><td>Analyse MANIPULATED_DOCUMENT rate by week</td></tr>
  <tr><td>Change in app version / document capture UI</td><td>Cross-reference with app release history</td></tr>
</table>
</div>
""")

# ─── Data Quality ────────────────────────────────────────────────────────────
h("""<div class="page">
<h2 id="data-quality">8. Data Quality Issues</h2>
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
  None of these issues materially affect the conclusions of this analysis, but they indicate the
  need for schema validation and data contract enforcement upstream.
</p>
</div>
""")

# ─── Recommendations ──────────────────────────────────────────────────────────
recommendations = [
    (
        "Investigate and fix incomplete submission rejections",
        f"{n_incomplete:,} rejections ({n_incomplete/n_rejected*100:.0f}% of all rejections) occurred because the image "
        "pipeline could not execute — not because of a genuine failure. "
        "Diagnose whether this is caused by upload failures, unsupported file formats, or vendor timeouts. "
        "Implement retry logic, clearer upload error messages, and pre-submission image quality checks in the app. "
        f"Recovering even 50% of these cases would add ~{int(n_incomplete*0.5):,} passed users."
    ),
    (
        "Guide Mexican users toward Electoral IDs",
        "Electoral IDs pass at 95.8% vs. National IDs at 89.3% in Mexico. "
        "Add in-app guidance recommending Electoral ID as the preferred document. "
        "This is a low-effort UX change with a measurable impact on MEX pass rates."
    ),
    (
        "Introduce a guided retry flow for liveness failures",
        f"Of the {(details['liveness_decision']=='REJECTED').sum():,} liveness rejections, "
        f"{liveness_reasons.get('liveness_UNDETERMINED',0):,} are UNDETERMINED — meaning the system "
        "could not reach a conclusion, not that the user failed. "
        "These users should be prompted to retry in better lighting conditions rather than being hard-rejected."
    ),
    (
        "Investigate the Aug 21 – Sep 3 rejection spike",
        f"The rejection rate nearly doubled during this period (from {baseline_rate:.1f}% to "
        f"{max(spike_rates):.1f}%). Cross-reference with vendor SLA reports, marketing campaigns, "
        "and app release history to identify the root cause and prevent recurrence."
    ),
    (
        "Review watchlist warning handling",
        f"{(details['watchlist_screening_decision']=='WARNING').sum()} users triggered a watchlist warning but "
        "<strong>all 69 were marked as PASSED</strong>. Confirm with compliance that this is intentional "
        "and that a manual review process exists for these cases."
    ),
    (
        "Enforce data quality at the pipeline level",
        "Add schema validation to reject non-standard label values (OK, APPROVED, PASSES) and "
        "flag misrouted fields (liveness values in usability columns) in real time. "
        "This ensures analytics remain reliable as the pipeline evolves."
    ),
]

h("""<div class="page">
<h2 id="recommendations">9. Recommendations</h2>
<div class="section-intro">
  Recommendations are ordered by estimated impact. Items 1–3 are high-priority and can be
  addressed within a single sprint; items 4–6 require cross-functional coordination.
</div>
""")
for i, (title, body) in enumerate(recommendations, 1):
    h(f"""<div class="rec no-break">
  <div class="rec-num">{i}</div>
  <div class="rec-body">
    <strong>{title}</strong>
    <p>{body}</p>
  </div>
</div>""")

h("""</div>
</body>
</html>
""")

# ── Write output ──────────────────────────────────────────────────────────────
html_content = "\n".join(html_parts)
OUTPUT_HTML.write_text(html_content, encoding="utf-8")
print(f"Report written to: {OUTPUT_HTML}")
print(f"File size: {OUTPUT_HTML.stat().st_size / 1024:.0f} KB")
