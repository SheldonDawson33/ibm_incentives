import os, pydeck as pdk, pandas as pd, streamlit as st
from core import load_data

st.set_page_config(page_title="IBM Incentives · Map", layout="wide")

TOKEN = os.getenv("MAPBOX_TOKEN")
if not TOKEN:
    st.error("⚠️ Set the MAPBOX_TOKEN environment variable in Streamlit Cloud.")
    st.stop()
pdk.settings.mapbox_api_key = TOKEN

DATA = load_data()
RAW_NAMES = list(DATA.keys())[:2]          # first two sheets only
DISPLAY = {"ESD": "Empire State Development Incentives",
           "IDA": "Municipal IDA Incentives"}

sheet_display = st.sidebar.radio(
    "Select sheet",
    [DISPLAY.get("ESD"), DISPLAY.get("IDA"), "State & Local Combined"],
    index=2
)
# translate
if sheet_display == "State & Local Combined":
    df = pd.concat(DATA.values(), keys=RAW_NAMES, names=["Source_Sheet"])
else:
    idx = 0 if sheet_display.startswith("Empire") else 1
    df = DATA[RAW_NAMES[idx]].copy()

# optional county filter
if "County" in df.columns:
    county_opts = sorted(df["County"].dropna().unique())
    chosen = st.sidebar.multiselect("County", county_opts, default=county_opts)
    df = df[df["County"].isin(chosen)]

# numeric $ column guess
num_col = ("Total NYS Investment" if "Total NYS Investment" in df.columns
           else "Total Exemptions")
# numeric $ column
df["$"] = pd.to_numeric(df[num_col], errors="coerce").fillna(0)

# radius column for bubbles (min 1, double for visibility)
df["_radius"] = df["$"].clip(lower=1) * 2


# tiny ZIP→lat/lon lookup just for demo
lut = {"10001": (40.7506, -73.9972), "14604": (43.1566, -77.6088)}
coords = df["Postal Code"].map(lut)
df["lat"] = coords.str[0]; df["lon"] = coords.str[1]
df = df.dropna(subset=["lat", "lon"])

layer = pdk.Layer(
    "ScatterplotLayer",
    data=df,
    get_position="[lon, lat]",
    get_radius="_radius",
    radius_scale=20,
    radius_min_pixels=4,
    get_fill_color=[0,122,62,160],
    pickable=True,
)
view = pdk.ViewState(latitude=42.8, longitude=-75.5, zoom=5.3)

st.header("Incentive Map 📍")
st.pydeck_chart(pdk.Deck(
    layers=[layer],
    initial_view_state=view,
    tooltip={"text": "{Project Name}\\nUS$ {$:,.0f}"}
))
st.caption("Bubble radius ∝ incentive $.  Use sidebar to change sheet or county.")
