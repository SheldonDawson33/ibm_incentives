# app.py – cleaned & curated version\n# Streamlit dashboard to locate IBM‑related incentive records\n# Author: Data‑Wrangler‑GPT | 2025‑06‑24 (rev‑B)\n\nimport streamlit as st\nimport pandas as pd\nfrom io import BytesIO\n\nst.set_page_config(page_title="IBM Incentive Finder", layout="wide")\n\n# ----------------------------------------------------------------------------\n# Constants\n# ----------------------------------------------------------------------------\nWORKBOOK = "ny_incentives_full.xlsx"  # change here only if the file name changes\nDEFAULT_TERMS = ["IBM", "International Business Machines"]\n\n# ----------------------------------------------------------------------------\n# Canonical header map – add variants as you discover them\n# ----------------------------------------------------------------------------\nHEADER_MAP = {\n    # — Identity —\n    "Recipient_Name": ["Recipient", "Company Name", "Applicant Name"],\n    "Project_Name":   ["Project", "Project Title", "Name of Project"],\n    "Municipality":   ["City/Town", "Municipality", "Project City", "Recipient City"],\n    "County":         ["County", "Project County", "Recipient County"],\n    "Postal_Code":    ["Zip", "Zip Code", "Postal Code"],\n\n    # — IDs & linkage —\n    "Project_ID": ["Project ID", "Record ID", "Project Identifier", "Report Record ID"],\n    "Related_Project_ID": ["Parent Project ID", "Prior Project #", "Related Project Number",\n                            "Multi-Phase Project ID"],\n\n    # — Dollars: exemptions & PILOTs —\n    "Exemption_School": ["School District Exemption", "School Tax Abated"],\n    "Exemption_County": ["County Exemption", "County Tax Abated"],\n    "Exemption_City":   ["City/Town Exemption", "City Tax Abated"],\n    "PILOT_School":     ["School PILOT Payments Scheduled", "School PILOT"],\n    "PILOT_County":     ["County PILOT Payments Scheduled", "County PILOT"],\n    "PILOT_City":       ["City PILOT Payments Scheduled", "City PILOT"],\n\n    # — State‑level awards —\n    "State_Award": ["Assistance Amount", "Tax Credit Amount", "Grant Award",\n                     "Capital Grant Amount", "Empire State Jobs Retention Credit"],\n\n    # — Jobs —\n    "Jobs_Plan_Total":        ["Jobs Planned", "Jobs to be Created", "Employment Target"],\n    "Jobs_Created_ToDate":    ["Jobs Created", "FTEs Reported"],\n    "Average_Salary":         ["Average Salary", "Avg Annual Wage"],\n\n    # — Dates —\n    "Board_Approval_Date":    ["Board Approval Date", "Date Approved"],\n    "Project_Start_Date":     ["Project Start Date", "Construction Start"],\n    "Project_Completion_Date": ["Project Completion Date", "Construction Completion"],\n}\n\n# ----------------------------------------------------------------------------\n# Helper: harmonise & tidy each sheet\n# ----------------------------------------------------------------------------\n\ndef harmonise_columns(df: pd.DataFrame) -> pd.DataFrame:\n    df.columns = df.columns.str.strip()\n\n    # 1) rename & co‑fill variants into canonical columns\n    for canon, variants in HEADER_MAP.items():\n        for v in variants:\n            if v in df.columns:\n                if canon not in df.columns:\n                    df.rename(columns={v: canon}, inplace=True)\n                else:  # co‑fill blanks\n                    df[canon] = df[canon].fillna(df[v])\n                    df.drop(columns=v, inplace=True)\n\n    # 2) ensure key numeric buckets exist even if blank in this sheet\n    for col in ["Exemption_School", "Exemption_County", "Exemption_City",\n                 "PILOT_School", "PILOT_County", "PILOT_City",\n                 "State_Award"]:\n        if col not in df.columns:\n            df[col] = pd.NA\n\n    # 3) derive totals & flags\n    df["Exemption_Total"] = df[["Exemption_School", "Exemption_County", "Exemption_City"]]\n        .apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)\n    df["PILOT_Total"] = df[["PILOT_School", "PILOT_County", "PILOT_City"]]\n        .apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)\n    df["State_Award_Total"] = pd.to_numeric(df["State_Award"], errors="coerce").fillna(0)\n    df["Total_Incentive"] = df["Exemption_Total"] + df["State_Award_Total"] - df["PILOT_Total"]\n    df["Is_MultiPhase"] = df["Related_Project_ID"].notna()\n\n    # 4) drop fully blank columns & duplicates\n    df.dropna(axis=1, how="all", inplace=True)\n    df = df.loc[:, ~df.columns.duplicated()].copy()\n    return df\n\n# ----------------------------------------------------------------------------\n# Data loader (cached)\n# ----------------------------------------------------------------------------\n@st.cache_data(show_spinner=False)
def load_data(path: str) -> pd.DataFrame:  # noqa: D401
    """Read all sheets, tidy, and concatenate."""
    xls = pd.ExcelFile(path, engine="openpyxl")
    all_frames = []
    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet, dtype=str)
        df["Source_Sheet"] = sheet
        all_frames.append(harmonise_columns(df))
    return pd.concat(all_frames, ignore_index=True)

# ----------------------------------------------------------------------------
# Search helpers
# ----------------------------------------------------------------------------

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

# ----------------------------------------------------------------------------
# Display & export helpers
# ----------------------------------------------------------------------------

PREFERRED_ORDER = [
    # identity / linkage
    "Source_Sheet", "Authority_Name", "Program_Name",
    "Project_ID", "Related_Project_ID", "Is_MultiPhase",
    "Project_Name", "Recipient_Name", "Industry",
    "Municipality", "County", "State", "Postal_Code",

    # money buckets
    "Exemption_School", "Exemption_County", "Exemption_City", "Exemption_Total",
    "PILOT_School", "PILOT_County", "PILOT_City", "PILOT_Total",
    "State_Award_Total", "Total_Incentive",

    # jobs
    "Jobs_Plan_Total", "Jobs_Created_ToDate", "Average_Salary",

    # dates
    "Board_Approval_Date", "Project_Start_Date", "Project_Completion_Date",
]


def subset_cols(df: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in PREFERRED_ORDER if c in df.columns]
    extras = [c for c in df.columns if c not in cols]
    return df[cols + extras]


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        subset_cols(df).to_excel(writer, sheet_name="IBM_Matches", index=False)
        writer.book.worksheets[0].freeze_panes = "A2"
    return bio.getvalue()

# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------
with st.spinner("Loading workbook …"):
    DATA = load_data(WORKBOOK)

st.sidebar.header("Search Controls")
terms = st.sidebar.multiselect("Synonyms / Code‑names", DEFAULT_TERMS, default=DEFAULT_TERMS)
new = st.sidebar.text_input("Add term").strip()
if new:
    terms.append(new)
regex_mode = st.sidebar.checkbox("Regex mode (advanced)")

RESULTS = search_records(DATA, terms, regex_mode)

left, right = st.columns(2)
left.metric("Matched rows", len(RESULTS))
right.metric("Total Incentive (Σ)", f"US$ {pd.to_numeric(RESULTS['Total_Incentive'], errors='coerce').fillna(0).sum():,.0f}")

st.dataframe(subset_cols(RESULTS), use_container_width=True)

st.download_button(
    "Download filtered rows (Excel)",
    data=to_excel_bytes(RESULTS),
    file_name="IBM_Assistance_clean.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

st.markdown("""---\n**Instructions**\n1. Use the sidebar to refine search terms.\n2. Regex mode treats each term as a regular expression.\n3. Click **Download** to export the current view.\n""")
