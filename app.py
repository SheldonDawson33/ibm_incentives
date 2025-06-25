# app.py – IBM Incentive Finder (REV‑F, syntax‑checked)
# -----------------------------------------------------------
# Streamlit dashboard that consolidates 5 NY incentive sheets,
# cleans headers, computes totals, and lets users filter IBM‑
# related records. Export matches on‑screen view.
# Author: Data‑Wrangler‑GPT | 2025‑06‑24

"""
CHANGELOG (rev‑F)
-----------------
✓ Places *all* imports at top (prevents NameError on type hints)
✓ Adds missing closing parentheses (SyntaxError fixed)
✓ Ensures every function is fully closed
✓ Adds `curate()` helper to present only curated columns
✓ Excel export writes to named sheet and freezes header
"""

# --------------------------- Imports ---------------------------------------
import re
from io import BytesIO

import pandas as pd
import streamlit as st

# --------------------------- Page config -----------------------------------
st.set_page_config(page_title="IBM Incentive Finder", layout="wide")

# --------------------------- Constants -------------------------------------
WORKBOOK = "ny_incentives_full.xlsx"
DEFAULT_TERMS = ["IBM", "International Business Machines"]

# --------------------------- Header mapping --------------------------------
HEADER_MAP: dict[str, list[str]] = {
    # identity
    "Project_ID": ["Project ID", "Record ID", "Project Identifier", "Report Record ID"],
    "Related_Project_ID": [
        "Parent Project ID",
        "Prior Project #",
        "Related Project Number",
        "Multi-Phase Project ID",
    ],
    "Authority_Name": ["Lead Agency Name", "Authority Name"],
    "Program_Name": ["Program through which the funding was awarded"],
    "Project_Name": ["Project Title", "Name of Project", "Project"],
    "Industry": ["Industry"],
    "Municipality": ["City/Town", "Municipality", "Project City", "Recipient City"],
    "County": ["County", "Project County", "Recipient County"],
    "State": ["State"],
    "Postal_Code": ["Zip", "Zip Code", "Postal Code"],
    # dollars – exemptions & PILOT (jurisdiction‑level)
    "Exemption_School": ["School District Exemption", "School Tax Abated"],
    "Exemption_County": ["County Exemption", "County Tax Abated"],
    "Exemption_City": ["City/Town Exemption", "City Tax Abated"],
    "PILOT_School": ["School PILOT Payments Scheduled", "School PILOT"],
    "PILOT_County": ["County PILOT Payments Scheduled", "County PILOT"],
    "PILOT_City": ["City PILOT Payments Scheduled", "City PILOT"],
    # state awards (ESD credits / grants)
    "State_Award": [
        "Assistance Amount",
        "Tax Credit Amount",
        "Grant Award",
        "Capital Grant Amount",
        "Empire State Jobs Retention Credit",
    ],
    # jobs
    "Jobs_Plan_Total": ["Jobs Planned", "Jobs to be Created", "Employment Target"],
    "Jobs_Plan_FTE": ["FTE Planned", "Projected FTEs"],
    "Jobs_Created_ToDate": ["Jobs Created", "FTEs Reported"],
    "Construction_Jobs": ["Construction Jobs", "Const Jobs"],
    "Average_Salary": ["Average Salary", "Avg Annual Wage"],
    # dates
    "Board_Approval_Date": ["Board Approval Date", "Date Approved"],
    "Agreement_Execution_Date": ["Agreement Execution Date"],
    "Project_Start_Date": ["Project Start Date", "Construction Start"],
    "Project_Completion_Date": ["Project Completion Date", "Construction Completion"],
    "Benefit_End_Date": ["Benefit End Date", "Exemption End Date"],
    "Measurement_Year": ["Fiscal Year", "Reporting Year"],
}

# preferred UI order
PREFERRED_ORDER = [
    # identity & IDs
    "Source_Sheet",
    "Authority_Name",
    "Program_Name",
    "Project_ID",
    "Related_Project_ID",
    "Is_MultiPhase",
    "Project_Name",
    "Industry",
    "Municipality",
    "County",
    "State",
    "Postal_Code",
    # dollars
    "Exemption_School",
    "Exemption_County",
    "Exemption_City",
    "Exemption_Total",
    "PILOT_School",
    "PILOT_County",
    "PILOT_City",
    "PILOT_Total",
    "State_Award_Total",
    "Total_Incentive",
    # jobs
    "Jobs_Plan_Total",
    "Jobs_Plan_FTE",
    "Jobs_Created_ToDate",
    "Construction_Jobs",
    "Average_Salary",
    # dates
    "Board_Approval_Date",
    "Agreement_Execution_Date",
    "Project_Start_Date",
    "Project_Completion_Date",
    "Benefit_End_Date",
    "Measurement_Year",
]

# --------------------------- Helpers ---------------------------------------

def harmonise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename variants, merge duplicates, derive totals and flags."""
    df.columns = df.columns.str.strip()

    # rename / co‑fill
    for canon, variants in HEADER_MAP.items():
        for v in variants:
            if v in df.columns:
                if canon not in df.columns:
                    df.rename(columns={v: canon}, inplace=True)
                else:
                    df[canon] = df[canon].fillna(df[v])
                    df.drop(columns=v, inplace=True)

    # totals & nets
    tax_cols = ["Exemption_School", "Exemption_County", "Exemption_City"]
    pilot_cols = ["PILOT_School", "PILOT_County", "PILOT_City"]
    state_cols = ["State_Award"]

    for lst in (tax_cols, pilot_cols, state_cols):
        for c in lst:
            if c not in df.columns:
                df[c] = pd.NA

    df["Exemption_Total"] = (
        df[tax_cols].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
    )
    df["PILOT_Total"] = (
        df[pilot_cols].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
    )
    df["State_Award_Total"] = (
        df[state_cols].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
    )
    df["Total_Incentive"] = (
        df["Exemption_Total"] + df["State_Award_Total"] - df["PILOT_Total"]
    )

    # multiphase flag
    if "Related_Project_ID" not in df.columns:
        df["Related_Project_ID"] = pd.NA
    df["Is_MultiPhase"] = df["Related_Project_ID"].notna()

    # drop empty columns & duplicates
    df.dropna(axis=1, how="all", inplace=True)
    df = df.loc[:, ~df.columns.duplicated()].copy()

    return df


def curate(df: pd.DataFrame) -> pd.DataFrame:
    """Return df with curated column order; others appended right."""
    ordered = [c for c in PREFERRED_ORDER if c in df.columns] + [
        c for c in df.columns if c not in PREFERRED_ORDER
    ]
    return df[ordered]


@st.cache_data(show_spinner=False)
def load_data(path: str) -> pd.DataFrame:
    xls = pd.ExcelFile(path, engine="openpyxl")
    frames = []
    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet, dtype=str)
        df["Source_Sheet"] = sheet
        df = harmonise_columns(df)
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def search_records(df: pd.DataFrame, terms: list[str], regex: bool = False) -> pd.DataFrame:
    """Return rows where any text column contains any term."""
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


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        curate(df).to_excel(writer, sheet_name="IBM_Matches", index=False)
        # freeze header row
        writer.book.worksheets[0].freeze_panes = "A2"
    return bio.getvalue()

# --------------------------- UI -------------------------------------------
with st.spinner("Loading workbook…"):
    data = load_data(WORKBOOK)

st.sidebar.header("Search Controls")
terms = st.sidebar.multiselect("Synonyms / Code‑names", DEFAULT_TERMS, default=DEFAULT_TERMS)
new_term = st.sidebar.text_input("Add term").strip()
if new_term:
    terms.append(new_term)
regex_mode = st.sidebar.checkbox("Regex mode (advanced)", value=False)

filtered = search_records(data, terms, regex_mode)

col_a, col_b = st.columns(2)
col_a.metric("Matched rows", len(filtered))
col_b.metric(
    "Σ Total Incentive", f"US$ {pd.to_numeric(filtered['Total_Incentive'], errors='coerce').fillna(0).sum():,.0f}"
)

st.dataframe(curate(filtered), use_container_width=True)

st.download_button(
    "Download filtered rows (Excel)",
    data=to_excel_bytes(filtered),
    file_name="IBM_Assistance_clean.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

st.markdown(
    """---  
    **Instructions**  
    1. Use the sidebar to refine search terms (add or remove).  
    2. Toggle regex mode for advanced pattern matching.  
    3. Download the current view via the button above.  
    """
)
