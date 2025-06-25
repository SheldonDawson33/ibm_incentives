# app.py – cleaned & curated version (rev‑D)
# Streamlit dashboard to locate IBM‑related incentive records
# Author: Data‑Wrangler‑GPT | 2025‑06‑24

"""
Key fixes in this revision
-------------------------
✓ `import pandas as pd` now appears *before* type‑hints that reference ``pd``
✓ Makes sure **Related_Project_ID** column exists before flagging multi‑phase
✓ Uses explicit `engine="openpyxl"` when opening the workbook (solves pandas
  ValueError on format detection)
✓ Curates the on‑screen/export column set – no more 100+ blank columns
"""

import streamlit as st
import pandas as pd
from io import BytesIO

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(page_title="IBM Incentive Finder", layout="wide")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
WORKBOOK = "ny_incentives_full.xlsx"  # change only if the filename changes
DEFAULT_TERMS = ["IBM", "International Business Machines"]

# ---------------------------------------------------------------------------
# Canonical header map  (add variants as you discover them)
# ---------------------------------------------------------------------------
HEADER_MAP: dict[str, list[str]] = {
    # — Identity —
    "Recipient_Name": ["Recipient", "Company Name", "Applicant Name"],
    "Project_Name":   ["Project", "Project Title", "Name of Project"],
    "Municipality":   ["City/Town", "Municipality", "Project City", "Recipient City"],
    "County":         ["County", "Project County", "Recipient County"],
    "Postal_Code":    ["Zip", "Zip Code", "Postal Code"],

    # — IDs & linkage —
    "Project_ID": ["Project ID", "Record ID", "Project Identifier", "Report Record ID"],
    "Related_Project_ID": [
        "Parent Project ID", "Prior Project #", "Related Project Number", "Multi-Phase Project ID"
    ],

    # — Dollars: exemptions & PILOTs —
    "Exemption_School": ["School District Exemption", "School Tax Abated"],
    "Exemption_County": ["County Exemption", "County Tax Abated"],
    "Exemption_City":   ["City/Town Exemption", "City Tax Abated"],
    "PILOT_School":     ["School PILOT Payments Scheduled", "School PILOT"],
    "PILOT_County":     ["County PILOT Payments Scheduled", "County PILOT"],
    "PILOT_City":       ["City PILOT Payments Scheduled", "City PILOT"],

    # — State‑level awards —
    "State_Award": [
        "Assistance Amount", "Tax Credit Amount", "Grant Award",
        "Capital Grant Amount", "Empire State Jobs Retention Credit",
    ],

    # — Jobs —
    "Jobs_Plan_Total":     ["Jobs Planned", "Jobs to be Created", "Employment Target"],
    "Jobs_Created_ToDate": ["Jobs Created", "FTEs Reported"],
    "Average_Salary":      ["Average Salary", "Avg Annual Wage"],

    # — Dates —
    "Board_Approval_Date":    ["Board Approval Date", "Date Approved"],
    "Project_Start_Date":     ["Project Start Date", "Construction Start"],
    "Project_Completion_Date": ["Project Completion Date", "Construction Completion"],
}

# ---------------------------------------------------------------------------
# Helper: harmonise & tidy each sheet
# ---------------------------------------------------------------------------

def harmonise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename variants → canonical, derive totals, drop blanks."""
    df.columns = df.columns.str.strip()

    # 1) rename & co‑fill
    for canon, variants in HEADER_MAP.items():
        for v in variants:
            if v in df.columns:
                if canon not in df.columns:
                    df.rename(columns={v: canon}, inplace=True)
                else:
                    df[canon] = df[canon].fillna(df[v])
                    df.drop(columns=v, inplace=True)

    # 2) make sure all numeric buckets exist
    numeric_buckets = [
        "Exemption_School", "Exemption_County", "Exemption_City",
        "PILOT_School", "PILOT_County", "PILOT_City",
        "State_Award",
    ]
    for col in numeric_buckets + ["Related_Project_ID"]:
        if col not in df.columns:
            df[col] = pd.NA

    # 3) derive totals & flags
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
    df["State_Award_Total"] = pd.to_numeric(df["State_Award"], errors="coerce").fillna(0)
    df["Total_Incentive"] = df["Exemption_Total"] + df["State_Award_Total"] - df["PILOT_Total"]
    df["Is_MultiPhase"] = df["Related_Project_ID"].notna()

    # 4) drop blank columns & duplicates
    df.dropna(axis=1, how="all", inplace=True)
    df = df.loc[:, ~df.columns.duplicated()].copy()
    return df

# ---------------------------------------------------------------------------
# Data loader (cached)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def load_data(path: str) -> pd.DataFrame:  # noqa: D401
    """Read all sheets, tidy each, concatenate."""
    xls = pd.ExcelFile(path, engine="openpyxl")
    frames = []
    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet, dtype=str)
        df["Source_Sheet"] = sheet
        frames.append(harmonise_columns(df))
    return pd.concat(frames, ignore_index=True)

# ---------------------------------------------------------------------------
# Search helper
# ---------------------------------------------------------------------------

def search_records(df: pd.DataFrame, terms: list[str], regex: bool = False) -> pd.DataFrame:
    if not terms:
        return df.iloc[0:0]
    obj_cols = df.select_dtypes("object").columns
    if regex:
        pat = "|".join(terms)
        mask = df[obj_cols].apply(lambda s: s.str.contains(pat, case=False, na=False, regex=True)).any(axis=1)
    else:
        lower = [t.lower() for t in terms]
        mask = df[obj_cols].apply(lambda s: s.str.lower().fillna("").apply(lambda x: any(t in x for t in lower))).any(axis=1)
    return df[mask]

# ---------------------------------------------------------------------------
# Column order helper
# ---------------------------------------------------------------------------

PREFERRED_ORDER = [
    # identity / linkage
    "Source_Sheet", "Project_ID", "Related_Project_ID", "Is_MultiPhase",
    "Project_Name", "Recipient_Name", "Municipality", "County", "State", "Postal_Code",

    # money buckets
    "Exemption_School", "Exemption_County", "Exemption_City", "Exemption_Total",
    "PILOT_School", "PILOT_County", "PILOT_City", "PILOT_Total",
    "State_Award_Total", "Total_Incentive",

    # jobs
    "Jobs_Plan_Total", "Jobs_Created_ToDate", "Average_Salary",

    # dates
    "Board_Approval_Date", "Project_Start_Date", "Project_Completion_Date",
]


def curate(df: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in PREFERRED_ORDER if c in df.columns]
    return df[cols + [c for c in df.columns if c not in cols]]


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        curate(df).to_excel(writer, sheet_name="IBM_Matches", index=False)
        writer.book.worksheets[0].freeze_panes = "A2"
    return bio.getvalue()

# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

with st.spinner("Loading workbook …"):
    DATA = load_data(WORKBOOK)

st.sidebar.header("Search Controls")
terms = st.sidebar.multiselect("Synonyms / Code‑names", DEFAULT_TERMS, default=DEFAULT_TERMS)
new_term = st.sidebar.text_input("Add term").strip()
if new_term:
    terms.append(new_term)
regex_mode = st.sidebar.checkbox("Regex mode (advanced)")

RESULTS = search_records(DATA, terms, regex_mode)

left, right = st.columns(2)
left.metric("Matched rows", len(RESULTS))
right.metric(
    "Total Incentive (Σ)",
    f"US$ {pd.to_numeric(RESULTS['Total_Incentive'], errors='coerce').fillna(0).sum():,.0f}",
)

st.dataframe(curate(
