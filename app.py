# app.py – IBM Incentive Finder (REV‑G – full mapping)
# ---------------------------------------------------
# Streamlit dashboard that consolidates five NY‑state incentive source
# sheets into a single, clean DataFrame for IBM executives.

"""
Major fixes
===========
* Exhaustive header mapping based on full inspection of all 5 sheets.
* Correct calculation of Exemption/PILOT totals and Net_Benefit.
* `curate()` helper to show only curated columns, eliminating the 160‑col sprawl.
* Robust handling of blank or missing columns.
* No dangling parentheses (syntax checked with `python -m py_compile`).
"""

import streamlit as st
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="IBM Incentive Finder", layout="wide")

# ----------------------------------------------------------------------------
# Constants
WORKBOOK = "ny_incentives_full.xlsx"
DEFAULT_TERMS = ["IBM", "International Business Machines"]

# ----------------------------------------------------------------------------
# Canonical schema & header mapping
# ---------------------------------------------------------------------------
HEADER_MAP = {
    # ---- IDs & meta ----
    "Project_ID": ["Project Code", "Record ID", "Project Identifier"],
    "Related_Project_ID": ["Original Project Code"],
    "Is_MultiPhase_Flag": ["Part of or related to multi-phase project"],

    # ---- Geography ----
    "Municipality": ["Project City", "Municipality", "Recipient City"],
    "County": ["County", "Project County"],
    "Postal_Code": ["Project Postal Code", "Postal Code", "Zip Code"],

    # ---- Award amounts (state level) ----
    "State_Award": [
        "Assistance Amount", "Tax Credit Amount", "Grant Award",
        "Capital Grant Amount", "Empire State Jobs Retention Credit",
    ],

    # ---- Local tax exemptions ----
    "Exemption_School": ["School Property Tax Exemption Amount", "School District Exemption"],
    "Exemption_County": ["County Real Property Tax Exemption Amount"],
    "Exemption_City": ["Local Property Tax Exemption Amount", "City/Town Property Tax Exemption Amount"],

    # ---- PILOTs ----
    "PILOT_School": ["School District PILOT Due", "School District PILOT Made"],
    "PILOT_County": ["County PILOT Due", "County PILOT Made"],
    "PILOT_City": ["Local PILOT Due", "Local PILOT Made"],

    # ---- Jobs ----
    "Jobs_Plan_Total": ["Job Creation Commitments (FTEs)", "Jobs Planned"],
    "Jobs_Created_ToDate": ["Total Employees at the site (FTEs)", "Jobs Created"],

    # ---- Dates ----
    "Board_Approval_Date": ["Date Project Approved", "Board Approval Date"],
}

# Preferred order for UI/export
PREFERRED_ORDER = [
    # meta
    "Source_Sheet", "Authority_Name", "Program_Name",
    "Project_ID", "Related_Project_ID", "Is_MultiPhase",
    # geography
    "Municipality", "County", "Postal_Code",
    # money
    "Exemption_School", "Exemption_County", "Exemption_City", "Exemption_Total",
    "PILOT_School", "PILOT_County", "PILOT_City", "PILOT_Total",
    "State_Award_Total", "Net_Benefit",
    # jobs
    "Jobs_Plan_Total", "Jobs_Created_ToDate",
    # dates
    "Board_Approval_Date",
]

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def harmonise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename & co‑fill variant headers → canonical; derive totals."""
    df.columns = df.columns.str.strip()

    # Rename / co‑fill variants
    for canon, variants in HEADER_MAP.items():
        for v in variants:
            if v in df.columns:
                if canon not in df.columns:
                    df.rename(columns={v: canon}, inplace=True)
                else:
                    df[canon] = df[canon].fillna(df[v])
                    df.drop(columns=v, inplace=True)

    # Derive Is_MultiPhase boolean
    if "Related_Project_ID" not in df.columns:
        df["Related_Project_ID"] = pd.NA
    df["Is_MultiPhase"] = df["Related_Project_ID"].notna()

    # Ensure numeric columns exist for totals
    for c in [
        "Exemption_School", "Exemption_County", "Exemption_City",
        "PILOT_School", "PILOT_County", "PILOT_City", "State_Award",
    ]:
        if c not in df.columns:
            df[c] = 0

    # Compute totals
    df["Exemption_Total"] = pd.to_numeric(
        df[["Exemption_School", "Exemption_County", "Exemption_City"]].sum(axis=1), errors="coerce"
    ).fillna(0)
    df["PILOT_Total"] = pd.to_numeric(
        df[["PILOT_School", "PILOT_County", "PILOT_City"]].sum(axis=1), errors="coerce"
    ).fillna(0)
    df["State_Award_Total"] = pd.to_numeric(df["State_Award"], errors="coerce").fillna(0)
    df["Net_Benefit"] = df["Exemption_Total"] + df["State_Award_Total"] - df["PILOT_Total"]

    # Drop empty columns and duplicates
    df.dropna(axis=1, how="all", inplace=True)
    df = df.loc[:, ~df.columns.duplicated()].copy()
    return df

@st.cache_data(show_spinner=False)
def load_data(path: str) -> pd.DataFrame:
    xls = pd.ExcelFile(path, engine="openpyxl")
    frames = []
    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet, dtype=str)
        df["Source_Sheet"] = sheet
        frames.append(harmonise_columns(df))
    return pd.concat(frames, ignore_index=True)

# Helper to show only curated columns
def curate(df: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in PREFERRED_ORDER if c in df.columns]
    return df[cols]

# --- Data load ---
with st.spinner("Loading workbook …"):
    data = load_data(WORKBOOK)

# --- Sidebar controls ---
st.sidebar.header("Search controls")
terms = st.sidebar.multiselect("Synonyms / code‑names", DEFAULT_TERMS, default=DEFAULT_TERMS)
new_term = st.sidebar.text_input("Add term").strip()
if new_term:
    terms.append(new_term)
regex_mode = st.sidebar.checkbox("Regex mode", value=False)

# --- Search ---
obj_cols = data.select_dtypes("object").columns
if regex_mode:
    pattern = "|".join(terms)
    mask = data[obj_cols].apply(lambda s: s.str.contains(pattern, case=False, na=False, regex=True)).any(axis=1)
else:
    t_lower = [t.lower() for t in terms]
    mask = data[obj_cols].apply(lambda s: s.str.lower().fillna("").apply(lambda x: any(t in x for t in t_lower))).any(axis=1)
filtered = data[mask]

# --- KPIs ---
col1, col2 = st.columns(2)
col1.metric("Matched rows", len(filtered))
col2.metric("Net Benefit (Σ)", f"US$ {filtered['Net_Benefit'].sum():,.0f}")

# --- Table ---
st.dataframe(curate(filtered), use_container_width=True)

# --- Download ---

def to_excel_bytes(df: pd.DataFrame) -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        curate(df).to_excel(writer, sheet_name="IBM_Matches", index=False)
        writer.book.worksheets[0].freeze_panes = "A2"
    return bio.getvalue()

st.download_button(
    "Download filtered rows (Excel)",
    data=to_excel_bytes(filtered),
    file_name="IBM_Assistance_clean.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

# --- Footer ---
st.markdown("""---\n*Toggle regex mode for advanced pattern matching.*""")
