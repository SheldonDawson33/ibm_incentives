import os
import pydeck as pdk
import pandas as pd
import streamlit as st
from core import load_data

st.set_page_config(page_title="IBM Incentives · Map", layout="wide")

# ─── Mapbox token -----------------------------------------------------------
TOKEN = os.getenv("MAPBOX_TOKEN")
if not TOKEN or not TOKEN.startswith("pk."):
    st.error("Mapbox token missing or malformed. Add it under Settings → Secrets like\nMAPBOX_TOKEN = \"pk.XXXXXXXXXXXXXXXX\"")
    st.stop()

pdk.settings.mapbox_api_key = TOKEN

# ─── Load data --------------------------------------------------------------
DATA = load_data()
RAW_NAMES = list(DATA.keys())[:2]
DISPLAY = ["Empire State Development Incentives", "Municipal IDA Incentives", "State & Local Combined"]

sheet_display = st.sidebar.radio("Select sheet", DISPLAY, index=2)

if sheet_display == "State & Local Combined":
    df = pd.concat(DATA.values(), keys=RAW_NAMES, names=["Source_Sheet"]).reset_index(drop=True)
else:
    idx = 0 if sheet_display.startswith("Empire") else 1
    df = DATA[RAW_NAMES[idx]].copy()

# ─── County filter (only if column present) ---------------------------------
if "County" in df.columns:
    counties = sorted(df["County"].dropna().unique())
    chosen = st.sidebar.multiselect("County", counties, default=counties)
    df = df[df["County"].isin(chosen)]

# ─── Numeric $ and radius ----------------------------------------------------
num_col = "Total NYS Investment" if "Total NYS Investment" in df.columns else "Total Exemptions"
df["$"] = pd.to_numeric(df[num_col], errors="coerce").fillna(0)
df["_radius"] = df["$"] .clip(lower=1) * 2

# ─── Geo‑prep: ZIP or County centroid ---------------------------------------
zip_candidates = ["Project Postal Code", "Postal Code", "ZIP", "Zip Code", "Zip"]
zip_col = next((c for c in zip_candidates if c in df.columns), None)

if zip_col is not None:
    lut = {
        "10001": (40.7506, -73.9972),  # NYC
        "14604": (43.1566, -77.6088),  # Rochester
    }
    coords = df[zip_col].map(lut)
else:
    county_lut = {
        "Albany": (42.6526, -73.7562),
        "Monroe": (43.1610, -77.6109),
    }
    coords = df["County"].map(county_lut) if "County" in df.columns else pd.Series()

df["lat"] = coords.str[0]
df["lon"] = coords.str[1]

df = df.dropna(subset=["lat", "lon"])
if df.empty:
    st.warning("No geodata available for the selected filter.")
    st.stop()

# ─── Tooltip: pick a safe project-name header --------------------------------
proj_candidates = [
    "Project Name", "Project", "Project Title", "Company", "Recipient",
]
proj_col = next((c for c in proj_candidates if c in df.columns), df.columns[0])

tooltip = {
    "html": f"<b>{{{{{proj_col}}}}}</b><br/>US$ {{{{${'$'}:,.0f}}}}"
}

# ─── Deck layers -------------------------------------------------------------
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

view = pdk.ViewState(latitude=float(df["lat"].mean()), longitude=float(df["lon"].mean()), zoom=5.5)

st.header("Incentive Map 📍")
st.pydeck_chart(
    pdk.Deck(
        layers=[layer],
        initial_view_state=view,
        map_style="mapbox://styles/mapbox/light-v11",
        tooltip=tooltip,
    )
)

st.caption("Bubble radius ∝ incentive $. Use sidebar to change sheet or county.")
