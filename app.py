"""app.py – IBM Incentive Finder (Phase‑0 UI Refresh)
====================================================
*Hero banner  + KPI cards  + Filter chips*

Assumes workbook `ny_incentives_2.xlsx` with sheets `ESD Data Export …` and
`IDA Data Export …` is present in the repo.
"""

import streamlit as st
import pandas as pd
from io import BytesIO
from pathlib import Path

# ----------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------
WORKBOOK = "ny_incentives_2.xlsx"  # replace if the filename changes
DEFAULT_TERMS = ["IBM", "International Business Machines"]

# Brand colours
IBM_BLUE = "#0033FF"
CBRE_GREEN = "#007A3E"
BG_GRADIENT = "linear-gradient(90deg, rgba(0,51,255,0.35) 0%, rgba(0,122,62,0.35) 100%)"

st.set_page_config(page_title="IBM × CBRE | NY Incentives", layout="wide")

# Inject lightweight CSS for hero + chips -------------------------------------------------
st.markdown(
    f"""
    <style>
    /* hero */
    .hero {{
        background: {BG_GRADIENT};
        padding: 1.5rem 2rem;
        border-radius: 8px;
        display: flex;
        align-items: center;
        gap: 1.2rem;
        margin-bottom: 1.2rem;
        color: white;
    }}
    .hero img {{ height: 40px; }}
    /* chip */
    .stMultiSelect [data-baseweb="tag"] {{
        background:{IBM_BLUE}22;
        border: 1px solid {IBM_BLUE}66;
        color: white;
    }}
    .stMultiSelect [data-baseweb="tag"]:hover {{ background:{IBM_BLUE}44; }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------------
# Data utilities
# ----------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_workbook(path: str) -> dict[str, pd.DataFrame]:
    """Return dict of sheet_name -> DataFrame (all cols as text)"""
    xls = pd.ExcelFile(path, engine="openpyxl")
    return {s: pd.read_excel(xls, sheet_name=s, dtype=str) for s in xls.sheet_names}

def filter_rows(df: pd.DataFrame, terms: list[str], regex: bool = False) -> pd.DataFrame:
    if not terms:
        return df.iloc[0:0]
    obj_cols = df.select_dtypes(include="object").columns
    if regex:
        pat = "|".join(terms)
        mask = df[obj_cols].apply(lambda s: s.str.contains(pat, case=False, na=False, regex=True)).any(axis=1)
    else:
        terms_lower = [t.lower() for t in terms]
        mask = df[obj_cols].apply(lambda s: s.str.lower().fillna("").apply(lambda x: any(t in x for t in terms_lower))).any(axis=1)
    return df[mask]

def sum_numeric(df: pd.DataFrame) -> float:
    num = df.select_dtypes(include="number")
    if num.empty:
        return 0.0
    return float(num.sum(axis=1).sum())

def to_excel_bytes(df: pd.DataFrame, sheet_name: str = "Matches") -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        writer.book.worksheets[0].freeze_panes = "A2"
    return bio.getvalue()

# ----------------------------------------------------------------------------
# Load data once
# ----------------------------------------------------------------------------
if not Path(WORKBOOK).exists():
    st.error(f"Workbook '{WORKBOOK}' not found in repo.")
    st.stop()

data_dict = load_workbook(WORKBOOK)

# ----------------------------------------------------------------------------
# Sidebar – search + sheet toggle + chip filters
# ----------------------------------------------------------------------------
st.sidebar.header("Search Controls")
terms = st.sidebar.multiselect("Synonyms / Code‑names", DEFAULT_TERMS, default=DEFAULT_TERMS)
new_term = st.sidebar.text_input("Add term").strip()
if new_term:
    terms.append(new_term)
regex_mode = st.sidebar.checkbox("Regex mode (advanced)")

sheet_choice = st.sidebar.selectbox("Choose view", list(data_dict) + ["All Sheets"], index=len(data_dict))

# Determine working DataFrame
if sheet_choice == "All Sheets":
    df = pd.concat([d.assign(Source_Sheet=s) for s, d in data_dict.items()], ignore_index=True)
else:
    df = data_dict[sheet_choice].copy()

# Chip filters (dynamically populate options) ---------------------------------
with st.sidebar.expander("Optional filters"):
    # Authority filter
    if "Authority_Name" in df.columns:
        auth_opts = sorted(df["Authority_Name"].dropna().unique())
        sel_auth = st.multiselect("Authority", auth_opts)
        if sel_auth:
            df = df[df["Authority_Name"].isin(sel_auth)]

    # Assistance Type (if column exists)
    if "Assistance_Type" in df.columns:
        aid_opts = sorted(df["Assistance_Type"].dropna().unique())
        sel_aid = st.multiselect("Assistance Type", aid_opts)
        if sel_aid:
            df = df[df["Assistance_Type"].isin(sel_aid)]

    # County
    if "County" in df.columns:
        county_opts = sorted(df["County"].dropna().unique())
        sel_county = st.multiselect("County", county_opts)
        if sel_county:
            df = df[df["County"].isin(sel_county)]

    # Fiscal / Measurement Year
    if "Measurement_Year" in df.columns:
        year_opts = sorted(df["Measurement_Year"].dropna().unique())
        sel_year = st.multiselect("Fiscal Year", year_opts)
        if sel_year:
            df = df[df["Measurement_Year"].isin(sel_year)]

# Apply search term filter last so KPIs reflect chip filters too
filtered = filter_rows(df, terms, regex_mode)

# ----------------------------------------------------------------------------
# Hero banner (IBM × CBRE lock‑up)
# ----------------------------------------------------------------------------
hero_html = f"""
<div class='hero'>
  <img src='https://static.wikia.nocookie.net/logopedia/images/3/3e/IBM_logo.svg' alt='IBM logo'>
  <img src='https://upload.wikimedia.org/wikipedia/commons/4/4b/CBRE_logo.svg' alt='CBRE logo'>
  <h2>NY Incentive Intelligence Dashboard</h2>
</div>
"""
st.markdown(hero_html, unsafe_allow_html=True)

# ----------------------------------------------------------------------------
# KPI cards
# ----------------------------------------------------------------------------
col_left, col_right = st.columns(2)
col_left.metric("Matched rows", len(filtered))

net_benefit = sum_numeric(filtered)
col_right.metric("Net Benefit (Σ)", f"US$ {net_benefit:,.0f}")

# ----------------------------------------------------------------------------
# Data table (native columns)
# ----------------------------------------------------------------------------
# If the dataset is huge, limit the default rows shown (scroll remains)
st.dataframe(filtered, use_container_width=True, height=520)

# ----------------------------------------------------------------------------
# Download current view
# ----------------------------------------------------------------------------
file_name = (
    f"IBM_{sheet_choice.replace(' ', '_')}_matches.xlsx" if sheet_choice != "All Sheets" else "IBM_AllSheets_matches.xlsx"
)
st.download_button(
    "Download filtered rows (Excel)",
    data=to_excel_bytes(filtered),
    file_name=file_name,
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

# Footer
st.markdown("""<hr style='margin-top:2rem'>
<small>IBM × CBRE Incentives Dashboard · Phase‑0 prototype</small>""", unsafe_allow_html=True)
