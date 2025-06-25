import os
import pydeck as pdk
import pandas as pd
import streamlit as st
from core import load_data

st.set_page_config(page_title="IBM Incentives · Map", layout="wide")

# ─── Mapbox token -----------------------------------------------------------
TOKEN = os.getenv("MAPBOX_TOKEN")
if not TOKEN:
    st.error("⚠️ Set the MAPBOX_TOKEN environment variable in Streamlit Cloud.")
    st.stop()
pdk.settings.mapbox_api_key = TOKEN

# ─── Load data --------------------------------------------------------------
DATA = load_data()
RAW_NAMES = list(DATA.keys())[:2]  # assume first two sheets
DISPLAY = {
    "ESD": "Empire State Development Incentives",
    "IDA": "Municipal IDA Incentives",
}

sheet_display = st.sidebar.radio(
    "Select sheet",
    [DISPLAY.get("ESD"), DISPLAY.get("IDA"), "State & Local Combined"],
    index=2,
)

# translate to DataFrame
if sheet_display == "State & Local Combined":
    df = pd.concat(DATA.values(), keys=RAW_NAMES, names=["Source_Sheet"])
else:
    idx = 0 if sheet_display.startswith("Empire") else 1
    df = DATA[RAW_NAMES[idx]].copy()

# ─── sidebar county filter --------------------------------------------------
if "County" in df.columns:
    counties = sorted(df["County"].dropna().unique())
    chosen = st.sidebar.multiselect("County", counties, default=counties)
    df = df[df["County"].isin(chosen)]

# ─── numeric $ column + radius ---------------------------------------------
num_col = (
    "Total NYS Investment"
    if "Total NYS Investment" in df.columns
    else "Total Exemptions"
)

df["$"] = pd.to_numeric(df[num_col], errors="coerce").fillna(0)
df["_radius"] = df["$"] .clip(lower=1) * 2  # ensure visible bubbles

# ─── Geo‑prep: ZIP first, then County centroids -----------------------------
zip_col = None
for cand in [
    "Postal Code",
    "Project Postal Code",  # newly added header variant
    "ZIP",
    "Zip Code",
    "Zip",
]:
    if cand in df.columns:
        zip_col = cand
        break

if zip_col is not None:
    # tiny hard‑coded demo lookup
    lut = {
        "10001": (40.7506, -73.9972),
        "14604": (43.1566, -77.6088),
    }
    coords = df[zip_col].map(lut)
    df["lat"] = coords.str[0]
    df["lon"] = coords.str[1]
elif "County" in df.columns:
    county_lut = {
        "Albany": (42.6526, -73.7562),
        "Monroe": (43.1610, -77.6109),
    }
    coords = df["County"].map(county_lut)
    df["lat"] = coords.str[0]
    df["lon"] = coords.str[1]
else:
    st.warning("No ZIP or County column to geocode.")
    st.stop()

# Drop rows without coords
df = df.dropna(subset=["lat", "lon"])
if df.empty:
    st.warning("No geodata available for the selected sheet/filter.")
    st.stop()

# ─── Build map --------------------------------------------------------------
layer = pdk.Layer(
    "ScatterplotLayer",
    data=df,
    get_position="[lon, lat]",
    get_radius="_radius",
    radius_scale=20,
    radius_min_pixels=4,
    get_fill_color=[0, 122, 62, 160],
    pickable=True,
)
view = pdk.ViewState(latitude=42.8, longitude=-75.5, zoom=5.3)

st.header("Incentive Map 📍")
st.pydeck_chart(
    pdk.Deck(
        layers=[layer],
        initial_view_state=view,
        tooltip={"text": "{Project Name}\nUS$ {$:,.0f}"},
    )
)

st.caption("Bubble radius ∝ incentive $.  Use sidebar to change sheet or county.")
