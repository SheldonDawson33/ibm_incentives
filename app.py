"""IBM Incentives Dashboard (clean schema)
=================================================
A Streamlit application that consolidates five NY‑state incentive source
sheets into a single, tidy DataFrame tailored for IBM executives.

Key features
------------
• Canonical 4‑layer schema (financials, compliance, geography, metadata)
• Exhaustive header mapping → co‑fills variants into a single column
• Derived totals (Exemption$, PILOT$, State Award$, Net Benefit$)
• Project identifiers + multi‑phase flag
• Compact on‑screen view; Excel/CSV export matches the view

Author: Data‑Wrangler‑GPT  |  Rev‑G 2025‑06‑24
"""

# ------------------------------------------------------------------
# Imports & config
# ------------------------------------------------------------------
import streamlit as st
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="IBM Incentives Dashboard", layout="wide")

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------
WORKBOOK = "ny_incentives_full.xlsx"  # uploaded in repo
DEFAULT_TERMS = ["IBM", "International Business Machines"]

# Primary display order (40 columns)
PREFERRED_ORDER = [
    # Layer 1 · Financials
    "Assistance_Type", "Exemption_School", "Exemption_County", "Exemption_City",
    "Exemption_Total", "PILOT_School", "PILOT_County", "PILOT_City", "PILOT_Total",
    "State_Award_Total", "Net_Benefit",
    # Layer 2 · Compliance & Jobs
    "Jobs_Plan_Total", "Jobs_Created_ToDate", "Average_Salary", "Measurement_Year",
    # Layer 3 · Geography
    "Municipality", "County", "State", "Postal_Code",
    # Layer 4 · Metadata / IDs
    "Source_Sheet", "Authority_Name", "Program_Name", "Project_ID",
    "Related_Project_ID", "Is_MultiPhase", "Project_Name", "Industry",
    "Board_Approval_Date", "Agreement_Execution_Date", "Project_Start_Date",
    "Project_Completion_Date", "Benefit_End_Date", "Project_Description", "Notes",
]

# Exhaustive header map (variant → canonical)
HEADER_MAP = {
    # IDs & meta
    "Project_ID": ["Project ID", "Record ID", "Project Identifier", "Report Record ID"],
    "Related_Project_ID": ["Parent Project ID", "Prior Project #", "Related Project Number", "Multi-Phase Project ID"],
    "Authority_Name": ["Lead Agency Name", "Authority Name"],
    "Program_Name": ["Program through which the funding was awarded"],
    # Geography
    "Municipality": ["City/Town", "Municipality", "Project City", "Recipient City"],
    "County": ["County", "Project County", "Recipient County"],
    "Postal_Code": ["Zip", "Zip Code", "Postal Code"],
    "State": ["State"],
    # Financials – exemptions & PILOTs
    "Exemption_School": ["School District Exemption", "School Tax Abated"],
    "Exemption_County": ["County Exemption", "County Tax Abated"],
    "Exemption_City": ["City/Town Exemption", "City Tax Abated"],
    "PILOT_School": ["School PILOT Payments Scheduled", "School PILOT"],
    "PILOT_County": ["County PILOT Payments Scheduled", "County PILOT"],
    "PILOT_City": ["City PILOT Payments Scheduled", "City PILOT"],
    "State_Award": [
        "Assistance Amount", "Tax Credit Amount", "Grant Award", "Capital Grant Amount",
        "Empire State Jobs Retention Credit",
    ],
    # Jobs & salary
    "Jobs_Plan_Total": ["Jobs Planned", "Jobs to be Created", "Employment Target"],
    "Jobs_Created_ToDate": ["Jobs Created", "FTEs Reported"],
    "Average_Salary": ["Average Salary", "Avg Annual Wage"],
    # Dates
    "Board_Approval_Date": ["Board Approval Date", "Date Approved"],
    "Agreement_Execution_Date": ["Agreement Execution Date"],
    "Project_Start_Date": ["Project Start Date", "Construction Start"],
    "Project_Completion_Date": ["Project Completion Date", "Construction Completion"],
    "Benefit_End_Date": ["Benefit End Date", "Exemption End Date"],
    "Measurement_Year": ["Fiscal Year", "Reporting Year"],
    # Narrative
    "Project_Name": ["Project Title", "Name of Project", "Project"],
    "Industry": ["Industry"],
    "Project_Description": ["Project Description", "Description"],
    "Notes": ["Notes", "Comments"],
}

# Assistance‑type inference map (label → column list that triggers it)
ASSIST_TYPE_MAP = {
    "Grant": ["Grant Award", "Assistance Amount"],
    "Tax Credit": ["Tax Credit Amount", "Empire State Jobs Retention Credit"],
    "Exemption": ["Exemption_School", "Exemption_County", "Exemption_City"],
    "PILOT": ["PILOT_School", "PILOT_County", "PILOT_City"],
}

# ------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------

def harmonise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename variants, co‑fill into canonical cols, drop empties."""
    df.columns = df.columns.str.strip()
    # 1 Rename / co‑fill
    for canon, variants in HEADER_MAP.items():
        for v in variants:
            if v in df.columns:
                if canon not in df.columns:
                    df.rename(columns={v: canon}, inplace=True)
                else:
                    df[canon] = df[canon].fillna(df[v])
                    df.drop(columns=v, inplace=True)

    # 2 Ensure all canonical cols exist
    for c in HEADER_MAP.keys():
        if c not in df.columns:
            df[c] = pd.NA

    # 3 Totals & derived fields
    tax_cols = ["Exemption_School", "Exemption_County", "Exemption_City"]
    pilot_cols = ["PILOT_School", "PILOT_County", "PILOT_City"]

    df["Exemption_Total"] = df[tax_cols].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
    df["PILOT_Total"] = df[pilot_cols].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
    df["State_Award_Total"] = pd.to_numeric(df["State_Award"], errors="coerce").fillna(0)
    df["Net_Benefit"] = df["Exemption_Total"] + df["State_Award_Total"] - df["PILOT_Total"]

    # 4 Assistance type inference
    for label, cols in ASSIST_TYPE_MAP.items():
        for c in cols:
            if c in df.columns and df[c].notna().any():
                df.loc[df[c].notna(), "Assistance_Type"] = label

    # 5 Multi‑phase flag
    df["Is_MultiPhase"] = df["Related_Project_ID"].notna()

    # 6 Drop all‑blank cols & de‑dupe
    df.dropna(axis=1, how="all", inplace=True)
    df = df.loc[:, ~df.columns.duplicated()].copy()

    return df

@st.cache_data(show_spinner=False)
def load_data(path: str) -> pd.DataFrame:
    """Load every sheet in the workbook, harmonise, concat."""
    xls = pd.ExcelFile(path, engine="openpyxl")
    frames = []
    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet, dtype=str)
        df["Source_Sheet"] = sheet
        frames.append(harmonise_columns(df))
    return pd.concat(frames, ignore_index=True)

# Streamlit utils ----------------------------------------------------

def curate(df: pd.DataFrame) -> pd.DataFrame:
    ordered = [c for c in PREFERRED_ORDER if c in df.columns] + [c for c in df.columns if c not in PREFERRED_ORDER]
    return df[ordered]

def to_excel_bytes(df: pd.DataFrame) -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        curate(df).to_excel(writer, sheet_name="IBM_Matches", index=False)
        writer.book.worksheets[0].freeze_panes = "A2"
    return bio.getvalue()

# ------------------------------------------------------------------
# UI
# ------------------------------------------------------------------
with st.spinner("Loading workbook …"):
    DATA = load_data(WORKBOOK)

st.sidebar.header("Search Controls")
terms = st.sidebar.multiselect("Synonyms / Code‑names", DEFAULT_TERMS, default=DEFAULT_TERMS)
new_term = st.sidebar.text_input("Add term").strip()
if new_term:
    terms.append(new_term)
regex_mode = st.sidebar.checkbox("Regex mode (advanced)")

# -- Search
obj_cols = DATA.select_dtypes("object").columns
if regex_mode:
    pattern = "|".join(terms) if terms else "^$"
    mask = DATA[obj_cols].apply(lambda s: s.str.contains(pattern, case=False, na=False, regex=True)).any(axis=1)
else:
    lowered = [t.lower() for t in terms]
    mask = DATA[obj_cols].apply(lambda s: s.str.lower().fillna("").apply(lambda x: any(t in x for t in lowered))).any(axis=1)
filtered = DATA[mask]

# -- Metrics
col_a, col_b = st.columns(2)
col_a.metric("Matched rows", len(filtered))
col_b.metric("Net Benefit (Σ)", f"US$ {filtered['Net_Benefit'].fillna(0).sum():,.0f}")

# -- Data table
st.dataframe(curate(filtered), use_container_width=True)

# -- Download
