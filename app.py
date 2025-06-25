"""IBM Incentive Finder – simplified two‑sheet edition
====================================================
Streamlit dashboard that lets IBM reviewers filter and download incentive
records from *exactly* the two source sheets now present in
`ny_incentives_2.xlsx`.

• No header harmonisation – each view shows columns exactly as they appear
  in the sheet (avoids mapping errors).
• Sidebar allows: synonym search, sheet toggle (ESD, IDA, All).
• KPI cards sum the **first numeric column** found in each sheet (typically
  the assistance $ field); if a sheet has no numerics, the KPI hides.
• Download button exports the *currently visible* table to Excel with
  filters applied; “All Sheets” adds a `Source_Sheet` column.

Author: Data‑Wrangler‑GPT | 2025‑06‑25
"""

import streamlit as st
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="IBM Incentive Finder (Two‑Sheet)", layout="wide")

# -----------------------------------------------------------------------------
# Constants                                                                      
# -----------------------------------------------------------------------------
WORKBOOK = "ny_incentives_2.xlsx"  # <- make sure this filename matches repo
DEFAULT_TERMS = ["IBM", "International Business Machines"]

# -----------------------------------------------------------------------------
# Data loading – cached so the workbook is read only once                        
# -----------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_sheets(path: str) -> dict[str, pd.DataFrame]:
    xls = pd.ExcelFile(path, engine="openpyxl")
    return {s: pd.read_excel(xls, sheet_name=s, dtype=str) for s in xls.sheet_names}

DATA = load_sheets(WORKBOOK)
SHEET_NAMES = list(DATA)  # keeps original order

# -----------------------------------------------------------------------------
# Sidebar – search + sheet selector                                             
# -----------------------------------------------------------------------------
st.sidebar.header("Search Controls")
terms = st.sidebar.multiselect("Synonyms / Code‑names", DEFAULT_TERMS, default=DEFAULT_TERMS)
new_term = st.sidebar.text_input("Add term").strip()
if new_term:
    terms.append(new_term)
regex_mode = st.sidebar.checkbox("Regex mode (advanced)", value=False)

sheet_choice = st.sidebar.radio("View", SHEET_NAMES + ["All Sheets"], index=0)

# -----------------------------------------------------------------------------
# Helper – filter rows                                                          
# -----------------------------------------------------------------------------

def row_filter(df: pd.DataFrame) -> pd.DataFrame:
    if not terms:
        return df.iloc[0:0]
    obj_cols = df.select_dtypes("object").columns
    if regex_mode:
        pattern = "|".join(terms)
        mask = df[obj_cols].apply(lambda s: s.str.contains(pattern, case=False, na=False, regex=True)).any(axis=1)
    else:
        t_low = [t.lower() for t in terms]
        mask = df[obj_cols].apply(lambda s: s.str.lower().fillna("").apply(lambda cell: any(t in cell for t in t_low))).any(axis=1)
    return df[mask]

# -----------------------------------------------------------------------------
# Get current DataFrame (single or concatenated)                                
# -----------------------------------------------------------------------------
if sheet_choice == "All Sheets":
    frames = []
    for s, df in DATA.items():
        tmp = df.copy()
        tmp["Source_Sheet"] = s
        frames.append(tmp)
    current_df = pd.concat(frames, ignore_index=True)
else:
    current_df = DATA[sheet_choice]

filtered = row_filter(current_df)

# -----------------------------------------------------------------------------
# KPI cards                                                                     
# -----------------------------------------------------------------------------
num_cols = filtered.select_dtypes("number").columns
col_left, col_right = st.columns(2)
col_left.metric("Matched rows", len(filtered))
if num_cols.any():
    col_right.metric("Σ of first numeric column", f"US$ {filtered[num_cols[0]].sum():,.0f}")
else:
    col_right.metric("Σ of numeric column", "—")

# -----------------------------------------------------------------------------
# Data table                                                                    
# -----------------------------------------------------------------------------
st.dataframe(filtered, use_container_width=True)

# -----------------------------------------------------------------------------
# Download                                                                      
# -----------------------------------------------------------------------------

def to_excel_bytes(df: pd.DataFrame) -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="IBM_Records", index=False)
        writer.book.worksheets[0].freeze_panes = "A2"
    return bio.getvalue()

st.download_button(
    "Download current view (Excel)",
    data=to_excel_bytes(filtered),
    file_name="IBM_Incentives_filtered.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

# -----------------------------------------------------------------------------
# Footer                                                                        
# -----------------------------------------------------------------------------
st.markdown(
    """---  \nUse the sidebar to switch between ESD and IDA sheets or see all rows together.\nRegex mode lets you write full regular expressions (e.g., `(?i)ibm|project chess`).""")
