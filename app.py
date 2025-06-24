
# app.py
# Streamlit interface to locate IBM-related incentive records
# Author: Data-Wrangler-GPT | 2025‑06‑24

import streamlit as st
import pandas as pd
import openpyxl
import re
from io import BytesIO

st.set_page_config(page_title="IBM Incentive Finder", layout="wide")

# --- Constants ---
WORKBOOK = "ny_incentives_full.xlsx"
DEFAULT_TERMS = ["IBM", "International Business Machines"]

# --- Helpers ---
@st.cache_data(show_spinner=False)
def load_data(path: str) -> pd.DataFrame:
    xls = pd.ExcelFile(path)
    frames = []
    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet, dtype=str)  # read as text; keeps IDs intact
        df["Source_Sheet"] = sheet
        frames.append(df)
    return pd.concat(frames, ignore_index=True)

def search_records(df: pd.DataFrame, terms: list[str], regex: bool = False) -> pd.DataFrame:
    """Return rows where ANY text column contains ANY term (case‑insensitive)."""
    if not terms:
        return df.iloc[0:0]
    obj_cols = df.select_dtypes(include="object").columns
    if regex:
        pattern = "|".join(terms)
        mask = df[obj_cols].apply(lambda s: s.str.contains(pattern, case=False, na=False, regex=True)).any(axis=1)
    else:
        terms_lower = [t.lower() for t in terms]
        mask = df[obj_cols].apply(
            lambda s: s.str.lower().fillna("").apply(lambda cell: any(t in cell for t in terms_lower))
        ).any(axis=1)
    return df[mask]

def incentive_sum(df: pd.DataFrame) -> float:
    num = df.select_dtypes(include="number")
    if num.empty:
        return 0.0
    return float(num.sum(axis=1).sum())

def to_excel_bytes(df: pd.DataFrame) -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="IBM_Matches", index=False)
        writer.book.worksheets[0].freeze_panes = "A2"
    return bio.getvalue()

# --- Load & cache data ---
with st.spinner("Loading workbook..."):
    data = load_data(WORKBOOK)

# --- Sidebar ---
st.sidebar.header("Search Controls")
terms = st.sidebar.multiselect("Synonyms / Code‑names", DEFAULT_TERMS, default=DEFAULT_TERMS)
new_term = st.sidebar.text_input("Add term").strip()
if new_term:
    terms.append(new_term)
regex_mode = st.sidebar.checkbox("Regex mode (advanced)", value=False)

# --- Search ---
filtered = search_records(data, terms, regex_mode)

# --- Metrics ---
col_a, col_b = st.columns(2)
col_a.metric("Matched rows", len(filtered))
col_b.metric("Σ Incentives (all numeric cols)", f"US$ {incentive_sum(filtered):,.0f}")

# --- Data table ---
st.dataframe(filtered, use_container_width=True)

# --- Download ---
st.download_button(
    "Download filtered rows (Excel)",
    data=to_excel_bytes(filtered),
    file_name="IBM_Assistance.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

# --- Footer ---
st.markdown(
    """---  
    **Instructions**  
    1. Use the sidebar to refine search terms (add or remove).  
    2. Regex mode interprets each term as a regular expression.  
    3. Download your current view via the button above.  
    """
)
