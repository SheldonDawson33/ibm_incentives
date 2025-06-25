import os
import pydeck as pdk
import pandas as pd
import streamlit as st
from core import load_data

st.set_page_config(page_title="IBM Incentives · Map", layout="wide")

# ─── Mapbox token -----------------------------------------------------------
TOKEN = os.getenv("MAPBOX_TOKEN")
if not TOKEN or not TOKEN.startswith("pk."):
    st.error("Mapbox token missing or malformed. Add it under Settings → Secrets like\nMAPBOX_TOKEN = \"pk....\"")
    st.stop()

pdk.settings.mapbox_api_key = TOKEN

# Choose a light basemap so bubbles pop
MAP_STYLE = "mapbox://styles/mapbox/light-v11"

# ─── Load data --------------------------------------------------------------
DATA = load_data()
RAW_NAMES = list(DATA.keys())[:2]  # first two sheets only
FRIENDLY = [
    "Empire State Development Incentives",
    "Municipal IDA Incentives",
    "State & Local Combined",
]

sheet_display = st.sidebar.radio("Select sheet", FRIENDLY, index=2)
if sheet_display == FRIENDLY[0]:
    df = DATA[RAW_NAMES[0]].copy()
elif sheet_display == FRIENDLY[1]:
    df = DATA[RAW_NAMES[1]].copy()
else:
    df = pd.concat(DATA.values(), keys=RAW_NAMES, names=["Source_Sheet"]).reset_index(drop=True)

# ─── County filter (optional) ----------------------------------------------
if "County" in df.columns:
    county_opts = sorted(df["County"].dropna().unique())
    sel = st.sidebar.multiselect("County", county_opts, default=county_opts)
    df = df[df["County"].isin(sel)]

# ─── Numeric $ --------------------------------------------------------------
num_col = (
    "Total NYS Investment" if "Total NYS Investment" in df.columns else "Total Exemptions"
)
if num_col not in df.columns:
    st.warning("No numeric $ column found in this sheet.")
    st.stop()

df["$"] = pd.to_numeric(df[num_col], errors="coerce").fillna(0)
# Radius for bubbles (sqrt scaling so big $ don't dominate)
df["_radius"] = (df["$"] ** 0.5).clip(lower=3) * 2000  # metres

# ─── Geocode ---------------------------------------------------------------
zip_candidates = ["Project Postal Code", "Postal Code", "ZIP", "Zip Code", "Zip"]
zip_col = next((c for c in zip_candidates if c in df.columns), None)

if zip_col:
    lut = {
        "10001": (40.7506, -73.9972),  # NYC
        "14604": (43.1566, -77.6088),  # Rochester
        "12207": (42.6512, -73.7540),  # Albany
    }
    coords = df[zip_col].str.zfill(5).map(lut)
    df["lat"] = coords.str[0]
    df["lon"] = coords.str[1]
else:
    county_lut = {
        "Albany": (42.6526, -73.7562),
        "Dutchess": (41.7784, -73.7471),
        "Westchester": (41.1220, -73.7949),
    }
    coords = df["County"].map(county_lut)
    df["lat"] = coords.str[0]
    df["lon"] = coords.str[1]

df = df.dropna(subset=["lat", "lon"])
if df.empty:
    st.warning("No geodata available for the selected sheet/filter.")
    st.stop()

# ─── View state -------------------------------------------------------------
view_state = pdk.ViewState(latitude=df["lat"].mean(), longitude=df["lon"].mean(), zoom=5)

# ─── Layers -----------------------------------------------------------------
layer = pdk.Layer(
    "ScatterplotLayer",
    data=df,
    get_position="[lon, lat]",
    get_radius="_radius",
    radius_scale=1,
    get_fill_color=[0, 122, 62, 160],  # CBRE green
    pickable=True,
)

tooltip = {"html": "<b>{Project Name}</b><br/>US$ {${0:,.0f}}".format("$")}

st.header("Incentive Map 📍")
st.pydeck_chart(
    pdk.Deck(
        map_style=MAP_STYLE,
        layers=[layer],
        initial_view_state=view_state,
        tooltip=tooltip,
    )
)

st.caption("Bubble radius ∝ √incentive $. Use sidebar filters above.")
