import os
import pydeck as pdk
import pandas as pd
import streamlit as st
from core import load_data

st.set_page_config(page_title="IBM Incentives · Map", layout="wide")

# ─── Retrieve Mapbox token -------------------------------------------------
TOKEN = os.getenv("MAPBOX_TOKEN")
if not TOKEN or TOKEN.startswith("pk.") is False:
    st.error("Mapbox token missing or malformed. Add it under Settings → Secrets as\n``\nMAPBOX_TOKEN = \"pk.……\"\n``")
    st.stop()

pdk.settings.mapbox_api_key = TOKEN

# ─── Load data & sheet selector -------------------------------------------
DATA = load_data()
RAW = list(DATA.keys())[:2]  # first two sheets only
NICE = ["Empire State Development Incentives", "Municipal IDA Incentives"]
CHOICES = NICE + ["State & Local Combined"]
choice = st.sidebar.radio("Select sheet", CHOICES, index=2)

if choice == CHOICES[2]:
    df = pd.concat(DATA.values(), keys=RAW, names=["Source_Sheet"])
else:
    idx = NICE.index(choice)
    df = DATA[RAW[idx]].copy()

# ─── County filter ---------------------------------------------------------
if "County" in df.columns:
    opts = sorted(df["County"].dropna().unique())
    sel = st.sidebar.multiselect("County", opts, default=opts)
    df = df[df["County"].isin(sel)]

# ─── Incentive $ column ----------------------------------------------------
num_col = next((c for c in ["Total NYS Investment", "Total Exemptions"] if c in df.columns), None)
if num_col is None:
    st.warning("No dollar column found to size bubbles.")
    st.stop()

df["$"] = pd.to_numeric(df[num_col], errors="coerce").fillna(0)
df["_radius"] = df["$"].clip(lower=1).pow(0.5) * 40  # sqrt scaling, min radius ~40

# ─── Geocode: ZIP or County centroid --------------------------------------
zip_candidates = ["Project Postal Code", "Postal Code", "ZIP", "Zip Code"]
zip_col = next((c for c in zip_candidates if c in df.columns), None)

county_centroid = {
    "Albany": (42.6526, -73.7562),
    "Dutchess": (41.7789, -73.6773),
    "Monroe": (43.1610, -77.6109),
    # … extend as needed …
}

if zip_col:
    # Minimal demo ZIP→lat/lon (add more as required)
    lut = {"10001": (40.7506, -73.9972), "14604": (43.1566, -77.6088)}
    coords = df[zip_col].astype(str).str[:5].map(lut)
    df["lat"], df["lon"] = coords.str[0], coords.str[1]
else:
    coords = df["County"].map(county_centroid)
    df["lat"], df["lon"] = coords.str[0], coords.str[1]

# Drop rows without coords
geo_df = df.dropna(subset=["lat", "lon"])
if geo_df.empty:
    st.warning("No geodata available for the selected filter.")
    st.stop()

# ─── Build layers ----------------------------------------------------------
layer = pdk.Layer(
    "ScatterplotLayer",
    data=geo_df,
    get_position="[lon, lat]",
    get_radius="_radius",
    radius_scale=1,
    get_fill_color=[0, 122, 62, 160],  # CBRE green semi‑transparent
    pickable=True,
)
view = pdk.ViewState(latitude=42.8, longitude=-75.5, zoom=5.3)

st.header("Incentive Map 📍")

st.pydeck_chart(
    pdk.Deck(
        layers=[layer],
        initial_view_state=view,
        map_style="mapbox://styles/mapbox/dark-v11",  # ensures base‑map loads
        tooltip={"text": "{Project Name}\nUS$ {$.2s}"},
    )
)

st.caption("Bubble radius ∝ incentive $.  Use sidebar to change sheet or county.")
