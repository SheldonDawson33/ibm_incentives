# app.py
# Streamlit interface to locate IBM‑related incentive records (clean, canonical headers)
# Author: Data‑Wrangler‑GPT | 2025‑06‑24 → refreshed 2025‑06‑24 (night)

import streamlit as st
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="IBM Incentive Finder", layout="wide")

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------
WORKBOOK = "ny_incentives_full.xlsx"  # keep the original filename here
DEFAULT_TERMS = [
    "IBM",
    "International Business Machines",
]

# -----------------------------------------------------------------------------
# Canonical header → variants map  (extend lists as you spot new labels)
# -----------------------------------------------------------------------------
HEADER_MAP = {
    # ---- identity ----
    "Recipient_Name": ["Recipient", "Company", "Company Name", "Applicant Name"],
    "Project_Name":   ["Project Title", "Name of Project", "Project"],
    "Industry":       ["Industry"],  # identical across sheets
    "Municipality":   ["City/Town", "Municipality", "Project City", "Recipient City"],
    "County":         ["County", "Project County", "Recipient County"],
    "Postal_Code":    ["Zip", "Zip Code", "Postal Code"],

    # ---- authority/program ----
    "Authority_Name": ["Lead Agency Name", "Authority Name"],
    "Program_Name":   ["Program through which the funding was awarded"],

    # ---- project IDs ----
    "Project_ID": ["Project ID", "Record ID", "Project Identifier", "Report Record ID"],
    "Related_Project_ID": [
        "Parent Project ID", "Prior Project #", "Related Project Number",
        "Multi-Phase Project ID"
    ],

    # ---- money: local exemptions ----
    "Exemption_School": ["School District Exemption", "School Tax Abated"],
    "Exemption_County": ["County Exemption", "County Tax Abated"],
    "Exemption_City":   ["City/Town Exemption", "City Tax Abated"],

    # ---- PILOT payments ----
    "PILOT_School": ["School PILOT Payments Scheduled", "School PILOT"],
    "PILOT_County": ["County PILOT Payments Scheduled", "County PILOT"],
    "PILOT_City":   ["City PILOT Payments Scheduled", "City PILOT"],

    # ---- state‑level credits / grants ----
    "State_Award": [
        "Assistance Amount", "Tax Credit Amount", "Grant Award",
        "Capital Grant Amount", "Empire State Jobs Retention Credit",
    ],

    # ---- employment ----
    "Jobs_Plan_Total":   ["Jobs Planned", "Jobs to be Created", "Employment Target"],
    "Jobs_Plan_FTE":     ["FTE Planned", "Projected FTEs"],
    "Jobs_Created_ToDate": ["Jobs Created", "FTEs Reported"],
    "Construction_Jobs": ["Construction Jobs", "Const Jobs"],
    "Average_Salary":    ["Average Salary", "Avg Annual Wage"],

    # ---- dates ----
    "Board_Approval_Date":       ["Board Approval Date", "Date Approved"],
    "Agreement_Execution_Date":  ["Agreement Execution Date"],
    "Project_Start_Date":        ["Project Start Date", "Construction Start"],
    "Project_Completion_Date":   ["Project Completion Date", "Construction Completion"],
    "Benefit_End_Date":          ["Benefit End Date", "Exemption End Date"],
    "Measurement_Year":          ["Fiscal Year", "Reporting Year"],
}

# -----------------------------------------------------------------------------
# Helper – harmonise headers & derive totals
# -----------------------------------------------------------------------------

def harmonise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Standardise headers, co‑fill variants, compute totals, derive flags."""
    df.columns = df.columns.str.strip()

    # 1) Rename or co‑fill variant headers into canonical names
    for canon, variants in HEADER_MAP.items():
        for v in variants:
            if v in df.columns:
                if canon not in df.columns:
                    df.rename(columns={v: canon}, inplace=True)
                else:
                    df[canon] = df[canon].fillna(df[v])
                    df.drop(columns=v, inplace=True)

    # 2) Ensure key numeric columns exist even if blank
    money_cols = [
        "Exemption_School", "Exemption_County", "Exemption_City",
        "PILOT_School", "PILOT_County", "PILOT_City",
        "State_Award",
    ]
    for c in money_cols:
        if c not in df.columns:
            df[c] = pd.NA

    # 3) Derive totals & net incentive
    df["Exemption_Total"] = (
        df[["Exemption_School", "Exemption_County", "Exemption_City"]]
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0)
        .sum(axis=1)
    )

    df["PILOT_Total"] = (
        df[["PILOT_School", "PILOT_County", "PILOT_City"]]
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0)
        .sum(axis=1)
    )

    df["State_Award_Total"] = (
        pd.to_numeric(df["State_Award"], errors="coerce").fillna(0)
    )

    df["Total_Incentive"] = df["Exemption_Total"] + df["State_Award_Total"] - df["PILOT_Total"]

    # 4) Multi‑phase flag
    if "Related_Project_ID" not in df.columns:
        df["Related_Project_ID"] = pd.NA
    df["Is_MultiPhase"] = df["Related_Project_ID"].notna()

    # 5) Drop completely empty columns & duplicates
    df.dropna(axis=1, how="all", inplace=True)
    df = df.loc[:, ~df.columns.duplicated()].copy()

    return df

# -----------------------------------------------------------------------------
# Data loader (cached)
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# Search helper
# -----------------------------------------------------------------------------

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

# -----------------------------------------------------------------------------
# Excel export helper
# -----------------------------------------------------------------------------

def to_excel_bytes(df: pd.DataFrame) -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="IBM_Matches", index=False)
        writer.book.worksheets[0].freeze_panes = "A2"
    return bio.getvalue()

# -----------------------------------------------------------------------------
# Display configuration – preferred column order
# -----------------------------------------------------------------------------
PREFERRED_ORDER = [
    # identity & IDs
    "Source_Sheet", "Authority_Name", "Program_Name",
    "Project_ID", "Related_Project_ID", "Is_MultiPhase",
    "Project_Name", "Industry", "Municipality", "County", "Postal_Code",

    # money buckets
    "Exemption_School", "Exemption_County", "Exemption_City", "Exemption_Total",
    "PILOT_School", "PILOT_County", "PILOT_City", "PILOT_Total",
    "State_Award_Total", "Total_Incentive",

    # employment
    "Jobs_Plan_Total", "Jobs_Plan_FTE", "Jobs_Created_ToDate",
    "Construction_Jobs", "Average_Salary",

    # dates
    "Board_Approval_Date", "Agreement_Execution_Date", "Project_Start_Date",
    "Project_Completion_Date", "Benefit_End_Date", "Measurement_Year",
]

# -----------------------------------------------------------------------------
# Load data (cached)
# -----------------------------------------------------------------------------
with st.spinner("Loading workbook… this may take 10–20 s on first load"):
    DATA = load_data(WORKBOOK)

# -----------------------------------------------------------------------------
# Sidebar – search controls
# -----------------------------------------------------------------------------
st.sidebar.header("Search Controls")
terms = st.sidebar.multiselect("Synonyms / Code‑names", DEFAULT_TERMS, default=DEFAULT_TERMS)
new_term = st.sidebar.text_input("Add term").strip()
if new_term:
    terms.append(new_term)
regex_mode = st.sidebar.checkbox("Regex mode (advanced)", value=False)

# -----------------------------------------------------------------------------
# Filter records
# -----------------------------------------------------------------------------
filtered = search_records(DATA, terms, regex_mode)

# -----------------------------------------------------------------------------
# Metrics – simple row count & total incentive
# -----------------------------------------------------------------------------
col_a, col_b = st.columns(2)
col_a.metric("Matched rows", len(filtered))
col_b.metric("Total Incentive (US$)", f"{filtered['Total_Incentive'].sum():,.0f}")

# -----------------------------------------------------------------------------
# Reorder columns for display
# -----------------------------------------------------------------------------
ordered_cols = [c for c in PREFERRED_ORDER if c in filtered.columns] + [
    c for c in filtered.columns if c not in PREFERRED_ORDER
]

st.dataframe(filtered[ordered_cols], use_container_width=True)

# -----------------------------------------------------------------------------
# Download button
# -----------------------------------------------------------------------------
st.download_button(
    "Download filtered rows (Excel)",
    data=to_excel_bytes(filtered[ordered_cols]),
    file_name="IBM_Assistance_clean.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

# -----------------------------------------------------------------------------
# Footer
# -----------------------------------------------------------------------------
st.markdown(
    """---  
    **Instructions**  
    1. Use the sidebar to refine search terms (add or remove).  
    2. Regex mode interprets each term as a regular expression.  
    3. Download the current view via the button above.  
    """
)
