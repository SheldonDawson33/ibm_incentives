"""app.py – IBM × CBRE Incentive Finder (REV‑I‑patch2)
================================================================
* Silences regex capture warning by switching to a **non‑capturing** group `(?: … )`.
* Everything else unchanged from patch1 (stable KPI scalars).
"""

import re
from pathlib import Path
from io import BytesIO

import pandas as pd
import streamlit as st
from streamlit_tags import st_tags

# ------------------------------------------------------------------
# Config & constants
# ------------------------------------------------------------------
WORKBOOK = "ny_incentives_3.xlsx"
assert Path(WORKBOOK).exists(), f"{WORKBOOK} not found in repo"

FRIENDLY_NAMES = {
    0: "Empire State Development Incentives",
    1: "Municipal IDA Projects",
}
DEFAULT_TERMS = ["IBM", "International Business Machines"]

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_sheets(path: str) -> dict[str, pd.DataFrame]:
    xls = pd.ExcelFile(path, engine="openpyxl")
    return {name: pd.read_excel(xls, sheet_name=name, dtype=str) for name in xls.sheet_names}


def filter_terms(df: pd.DataFrame, terms: list[str]) -> pd.DataFrame:
    if not terms:
        return df.iloc[0:0]
    obj_cols = df.select_dtypes(include="object").columns
    # non‑capturing group avoids pandas warning
    pattern = r"\b(?:" + "|".join(re.escape(t) for t in terms) + r")\b"
    contains = df[obj_cols].apply(lambda col: col.str.contains(pattern, case=False, na=False, regex=True))
    return df[contains.any(axis=1)]


def to_numeric_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series([0])
    return pd.to_numeric(df[col].str.replace(",", ""), errors="coerce").fillna(0)


def kpi_totals(df: pd.DataFrame) -> dict[str, float]:
    """Compute KPI metrics with duplicate‑safe dollar / job sums.

    ▸ **approvals** – raw row count (no dedup).
    ▸ **state/local/capex/jobs** – summed *once per project* using the first
      ID‑like column found. If no ID column exists, fall back to raw sums.
    """

    # -------------------------------------------------------------
    # 1. Find a project‑ID column
    id_candidates = [
        "Project ID", "Project ID #", "Project Code", "Project Identifier",
        "Record ID", "ProjectNumber", "Project Number",
    ]
    id_col = next((c for c in id_candidates if c in df.columns), None)

    # 2. Build dedup view (drop duplicate IDs, keep first)
    dedup_df = (
        df.drop_duplicates(subset=id_col, keep="first") if id_col else df.copy()
    )

    # 3. Helper: numeric sum from dedup_df
    def _sum(col_name: str) -> float:
        if col_name not in dedup_df.columns:
            return 0.0
        col = pd.to_numeric(
            dedup_df[col_name].str.replace(",", "", regex=False), errors="coerce"
        )
        return col.fillna(0).sum()

    # 4. KPI calculations
    approvals = float(len(df))  # raw rows

    state_val = _sum("Assistance Amount")  # primary state incentive column

    local_val = 0.0
    if {
        "Total Exemptions",
        "State Sales Tax Exemption Amount",
    }.issubset(dedup_df.columns):
        local_series = (
            pd.to_numeric(
                dedup_df["Total Exemptions"].str.replace(",", "", regex=False),
                errors="coerce",
            )
            - pd.to_numeric(
                dedup_df["State Sales Tax Exemption Amount"].str.replace(",", "", regex=False),
                errors="coerce",
            )
        ).fillna(0)
        local_val = local_series.sum()

    capex = _sum("Total Public-Private Investment") + _sum("Total Project Amount")

    jobs = _sum("Job Creation Commitments (FTEs)") + _sum(
        "Original Estimate Of Jobs To Be Created"
    )

    return {
        "approvals": approvals,
        "state_val": state_val,
        "local_val": local_val,
        "capex": capex,
        "jobs": jobs,
    }


def fmt_dollar(x: float) -> str:
    return f"US$ {x:,.0f}" if x else "—"

# ------------------------------------------------------------------
# UI
# ------------------------------------------------------------------
st.set_page_config(page_title="IBM × CBRE Incentive Finder", layout="wide", page_icon="💵")

# Hero banner --------------------------------------------------------------
hero_html = """
<style>
.hero {background:linear-gradient(90deg,#0023ff 0%,#007a3e 100%);padding:32px;border-radius:6px;color:white;text-align:left;}
.hero h1{margin:0;font-family:IBM Plex Sans, sans-serif;font-weight:600;font-size:32px;}
.hero p{margin:0;font-size:14px;opacity:.9;}
</style>
<div class="hero">
  <h1>IBM × CBRE Incentive Finder</h1>
  <p>Real‑time lens on every New York incentive powering IBM’s growth.</p>
</div>
"""
st.markdown(hero_html, unsafe_allow_html=True)

# Search terms -------------------------------------------------------------
st.markdown("### Search Terms")
terms_chips = st_tags(label="", text="Press enter to add", value=DEFAULT_TERMS, maxtags=10, key="terms")

# Load data -----------------------------------------------------------------
with st.spinner("Loading workbook …"):
    DATA = load_sheets(WORKBOOK)

RAW_NAMES = list(DATA.keys())[:2]
DISPLAY_OPTS = [FRIENDLY_NAMES.get(i, n) for i, n in enumerate(RAW_NAMES)] + ["State & Local Combined"]

# Sidebar filters -----------------------------------------------------------


sheet_display = st.sidebar.radio("Choose data view", DISPLAY_OPTS, index=len(DISPLAY_OPTS)-1)
if sheet_display == "All Sheets":
    current_df = pd.concat(DATA.values(), keys=RAW_NAMES, names=["Source_Sheet"]).reset_index(level=0)
else:
    raw_name = RAW_NAMES[DISPLAY_OPTS.index(sheet_display)]
    current_df = DATA[raw_name].copy()

# Filter by terms -----------------------------------------------------------
filtered_df = filter_terms(current_df, terms_chips)

# KPIs ----------------------------------------------------------------------
kpi = kpi_totals(filtered_df)
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("# Incentive Approvals", f"{kpi['approvals']:,.0f}")
col2.metric("Total State Value", fmt_dollar(kpi['state_val']))
col3.metric("Total Local Value", fmt_dollar(kpi['local_val']))
col4.metric("CapEx", fmt_dollar(kpi['capex']))
col5.metric("New Jobs / FTEs", f"{kpi['jobs']:,.0f}")

st.divider()

# Data table ---------------------------------------------------------------
st.dataframe(filtered_df, use_container_width=True, hide_index=True)

# Download -----------------------------------------------------------------

def _to_excel_bytes(df: pd.DataFrame) -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="IBM_Matches", index=False)
    return bio.getvalue()

st.download_button(
    "Download current view (Excel)",
    _to_excel_bytes(filtered_df),
    "IBM_Matches.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

st.caption("A pilot project from Logan's HUGE Brain · Phase‑0 UI")
