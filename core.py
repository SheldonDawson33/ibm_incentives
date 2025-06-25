import pandas as pd
import streamlit as st

WORKBOOK = "ny_incentives_3.xlsx"

@st.cache_data(ttl=86400, show_spinner=False)
def load_data() -> dict[str, pd.DataFrame]:
    """Return {sheet_name: DataFrame} with every column read as text."""
    xls = pd.ExcelFile(WORKBOOK, engine="openpyxl")
    return {s: pd.read_excel(xls, sheet_name=s, dtype=str) for s in xls.sheet_names}
