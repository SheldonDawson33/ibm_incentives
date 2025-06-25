"""app.py – IBM Incentive Finder (REV‑H2)
=================================================
Phase‑0 polish + dynamic sheet names for ny_incentives_3.xlsx.

This version auto‑detects the first two sheets in whatever workbook is present
and shows them as "ESD State Incentives" and "Municipal IDA Projects" in the
sidebar, while keeping the raw names internally.

Requires:
    pip install streamlit streamlit-tags openpyxl pandas
"""

import re
from pathlib import Path
from io import BytesIO

import pandas as pd
import streamlit as st
from streamlit_tags import st_tags

# ---------------------------------------------------------------------
# Page & brand setup
# ---------------------------------------------------------------------
st.set_page_config(page_title="IBM×CBRE Incentive Finder", layout="wide")
BRAND_BLUE = "#0033FF"
BRAND_GREEN = "#007A3E"

HERO_SVG = f"""
<svg width='0' height='0'>
  <defs>
    <pattern id='circuit' width='120' height='120' patternUnits='userSpaceOnUse'>
      <path d='M0 60 H120 M60 0 V120' stroke='{BRAND_GREEN}' stroke-width='0.3'/>
    </pattern>
  </defs>
</svg>
<div style='position:relative;width:100%;padding:32px 0;background:linear-gradient(135deg,{BRAND_BLUE} 0%,#0D0D3B 100%);'>
  <div style='position:absolute;inset:0;opacity:0.12;background:url("#circuit");'></div>
  <h1 style='position:relative;color:white;font-family:"IBM Plex Sans",sans-serif;font-size:2rem;margin:0 0 4px 32px;'>IBM × CBRE Incentive Finder</h1>
  <p style='position:relative;color:#E0E0E0;margin:0 0 0 32px;'>Real‑time lens on every New York incentive powering IBM’s growth.</p>
</div>"""

st.components.v1.html(HERO_SVG, height=140)

# ---------------------------------------------------------------------
# Load workbook (cached)
# ---------------------------------------------------------------------
WORKBOOK = "ny_incentives_3.xlsx"

@st.cache_data(show_spinner=False)
def load_sheets(path: str):
    xls = pd.ExcelFile(path, engine="openpyxl")
    return {s: pd.read_excel(xls, sheet_name=s, dtype=str) for s in xls.sheet_names}

data_dict = load_sheets(WORKBOOK)

# Map raw names ➜ friendly labels for the first two sheets
RAW_NAMES = list(data_dict.keys())[:2]
DISPLAY_MAP = {
    RAW_NAMES[0]: "ESD State Incentives",
    RAW_NAMES[1]: "Municipal IDA Projects",
}

display_options = [DISPLAY_MAP[r] for r in RAW_NAMES] + ["All Sheets"]

sheet_display = st.sidebar.radio("Choose data view", display_options, index=len(display_options)-1)

sheet_choice = (
    "All Sheets" if sheet_display == "All Sheets" else RAW_NAMES[display_options.index(sheet_display)]
)

# ---------------------------------------------------------------------
# Sidebar – chips for synonyms
# ---------------------------------------------------------------------
st.sidebar.subheader("Search Synonyms / Code‑names")
DEFAULT_TERMS = ["IBM", "International Business Machines"]
terms_chips = st_tags(
    label="Add or remove terms",
    text="Press enter to add",
    value=DEFAULT_TERMS,
    suggestions=["Project Chess", "Endicott"],
)

# ---------------------------------------------------------------------
# Prep dataframe based on choice
# ---------------------------------------------------------------------
if sheet_choice == "All Sheets":
    frames = []
    for s, df in data_dict.items():
        temp = df.copy()
        temp["Source_Sheet"] = s
        frames.append(temp)
    current_df = pd.concat(frames, ignore_index=True)
else:
    current_df = data_dict[sheet_choice]

# ---------------------------------------------------------------------
# Helper: word‑boundary search (avoids 'kibm')
# ---------------------------------------------------------------------

def filter_terms(df: pd.DataFrame, terms: list[str]):
    if not terms:
        return df.iloc[0:0]
    pattern = r"\\b(" + "|".join(map(re.escape, terms)) + r")\\b"
    obj_cols = df.select_dtypes("object").columns
    mask = df[obj_cols].apply(lambda s: s.str.contains(pattern, case=False, na=False, regex=True)).any(1)
    return df[mask]

filtered_df = filter_terms(current_df, terms_chips)

# ---------------------------------------------------------------------
# KPI calculations (sheet‑aware)
# ---------------------------------------------------------------------

def to_num(series):
    return pd.to_numeric(series, errors="coerce").fillna(0)

authority = (
    "ESD" if "ESD" in sheet_choice else "IDA" if "IDA" in sheet_choice else "All"
)

# Approvals
kpi_approvals = len(filtered_df)

# State Value
state_val = 0.0
if authority in ("ESD", "All") and "Total NYS Investment" in filtered_df.columns:
    state_val += to_num(filtered_df["Total NYS Investment"]).sum()
if authority in ("IDA", "All") and "State Sales Tax Exemption Amount" in filtered_df.columns:
    state_val += to_num(filtered_df["State Sales Tax Exemption Amount"]).sum()

# Local Value
local_val = 0.0
if authority in ("IDA", "All") and {
    "Total Exemptions",
    "State Sales Tax Exemption Amount",
}.issubset(filtered_df.columns):
    local_val = (
        to_num(filtered_df["Total Exemptions"]) - to_num(filtered_df["State Sales Tax Exemption Amount"])
    ).sum()

# CapEx
capex_val = 0.0
if authority in ("ESD", "All") and "Total Public-Private Investment" in filtered_df.columns:
    capex_val += to_num(filtered_df["Total Public-Private Investment"]).sum()
if authority in ("IDA", "All") and "Total Project Amount" in filtered_df.columns:
    capex_val += to_num(filtered_df["Total Project Amount"]).sum()

# Jobs
jobs_val = 0.0
if authority in ("ESD", "All") and "Job Creation Commitments (FTEs)" in filtered_df.columns:
    jobs_val += to_num(filtered_df["Job Creation Commitments (FTEs)"]).sum()
if authority in ("IDA", "All") and "Original Estimate Of Jobs To Be Created" in filtered_df.columns:
    jobs_val += to_num(filtered_df["Original Estimate Of Jobs To Be Created"]).sum()

# KPI card row
kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
kpi1.metric("# Incentive Approvals", f"{kpi_approvals}")
kpi2.metric("Total State Value ($)", f"{state_val:,.0f}")
kpi3.metric("Total Local Value ($)", f"{local_val:,.0f}")
kpi4.metric("CapEx ($)", f"{capex_val:,.0f}")
kpi5.metric("New Jobs / FTEs", f"{jobs_val:,.0f}")

st.markdown("---")

# ---------------------------------------------------------------------
# Data table in native column order
# ---------------------------------------------------------------------
st.dataframe(filtered_df, use_container_width=True)

# ---------------------------------------------------------------------
# Download current view
# ---------------------------------------------------------------------

def df_to_excel_bytes(df: pd.DataFrame) -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="IBM_Matches", index=False)
        writer.book.worksheets[0].freeze_panes = "A2"
    return bio.getvalue()

st.download_button(
    label="Download current view (Excel)",
    data=df_to_excel_bytes(filtered_df),
    file_name="IBM_Incentives_filtered.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

# Footer
st.markdown(
    """<small>Phase‑0 preview • powered by Streamlit • © 2025 CBRE & IBM</small>""",
    unsafe_allow_html=True,
)
