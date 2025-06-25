"""app.py – IBM × CBRE Incentive Finder (REV‑I, **stable**)
================================================================
• Two‑sheet workbook (`ny_incentives_3.xlsx`) – ESD + IDA only
• Hero banner, chip filters (`streamlit_tags`), KPI cards.
• No harmonisation: table shows native columns, so no KeyErrors.
• Word‑boundary search fixes “kibm”.
• Guards for missing columns in KPI math.
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
possible_workbook_path = Path(WORKBOOK)
assert possible_workbook_path.exists(), f"{WORKBOOK} not found in repo"

FRIENDLY_NAMES = {
    0: "ESD State Incentives",
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
    pattern = r"\\b(" + "|".join(re.escape(t) for t in terms) + r")\\b"
    contains = df[obj_cols].apply(lambda col: col.str.contains(pattern, case=False, na=False, regex=True))
    mask = contains.any(axis=1)
    return df[mask]


def to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.str.replace(",", ""), errors="coerce").fillna(0)


def kpi_totals(df: pd.DataFrame) -> dict[str, float]:
    res = {}
    res["approvals"] = len(df)

    # State value
    state_cols = [
        "Total NYS Investment",  # ESD
        "State Sales Tax Exemption Amount",  # IDA
    ]
    res["state_val"] = sum(to_numeric(df[c]) for c in state_cols if c in df.columns)

    # Local value (IDA only)
    if {"Total Exemptions", "State Sales Tax Exemption Amount"}.issubset(df.columns):
        res["local_val"] = (to_numeric(df["Total Exemptions"]) - to_numeric(df["State Sales Tax Exemption Amount"]) ).sum()
    else:
        res["local_val"] = 0

    # CapEx
    capex_cols = [
        "Total Public-Private Investment",  # ESD
        "Total Project Amount",  # IDA
    ]
    res["capex"] = sum(to_numeric(df[c]) for c in capex_cols if c in df.columns)

    # New jobs / FTEs
    job_cols = [
        "Job Creation Commitments (FTEs)",  # ESD
        "Original Estimate Of Jobs To Be Created",  # IDA
    ]
    res["jobs"] = sum(to_numeric(df[c]) for c in job_cols if c in df.columns)
    return res


def fmt_dollar(x: float) -> str:
    return f"US$ {x:,.0f}" if x else "—"

# ------------------------------------------------------------------
# UI
# ------------------------------------------------------------------
st.set_page_config(page_title="IBM × CBRE Incentive Finder", layout="wide", page_icon="💵")

# Hero banner ----------------------------------------------------------------
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

# Load data -------------------------------------------------------------------
with st.spinner("Loading workbook …"):
    DATA = load_sheets(WORKBOOK)

RAW_NAMES = list(DATA.keys())[:2]
display_options = [FRIENDLY_NAMES.get(i, n) for i, n in enumerate(RAW_NAMES)] + ["All Sheets"]

# Sidebar filters -------------------------------------------------------------
st.sidebar.subheader("Add or remove terms")
terms_chips = st_tags(label="", text="Press enter to add", value=DEFAULT_TERMS, suggestions=[], maxtags=10)

sheet_display = st.sidebar.radio("Choose data view", display_options, index=len(display_options)-1)
if sheet_display == "All Sheets":
    current_df = pd.concat(DATA.values(), keys=RAW_NAMES, names=["Source_Sheet"]).reset_index(level=0)
else:
    raw_name = RAW_NAMES[display_options.index(sheet_display)]
    current_df = DATA[raw_name].copy()

# Filter by terms -------------------------------------------------------------
filtered_df = filter_terms(current_df, terms_chips)

# KPIs ------------------------------------------------------------------------
kpi = kpi_totals(filtered_df)
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("# Incentive Approvals", f"{kpi['approvals']:,.0f}")
col2.metric("Total State Value", fmt_dollar(kpi['state_val']))
col3.metric("Total Local Value", fmt_dollar(kpi['local_val']))
col4.metric("CapEx", fmt_dollar(kpi['capex']))
col5.metric("New Jobs / FTEs", f"{kpi['jobs']:,.0f}")

st.divider()

# Data table ------------------------------------------------------------------
st.dataframe(filtered_df, use_container_width=True, hide_index=True)

# Download --------------------------------------------------------------------
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
