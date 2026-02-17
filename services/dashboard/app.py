import os

import pandas as pd
import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://api_backend:8000")

st.set_page_config(page_title="Persona 3 Dashboard", layout="wide")
st.title("Persona 3 - xPoints Dashboard")

with st.sidebar:
    st.header("Controls")
    player_a = st.number_input("Player A ID", min_value=1, value=2544, step=1)
    player_b = st.number_input("Player B ID", min_value=1, value=201939, step=1)


def get_player_metrics(player_id: int) -> dict:
    response = requests.get(f"{API_BASE_URL}/players/{player_id}/metrics", timeout=15)
    response.raise_for_status()
    return response.json()


def show_player_card(player_id: int, column) -> None:
    with column:
        st.subheader(f"Player {player_id}")
        try:
            metrics = get_player_metrics(player_id)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Failed to load player metrics: {exc}")
            return

        c1, c2, c3 = st.columns(3)
        c1.metric("Total shots", metrics.get("total_shots", 0))
        c2.metric("FG%", f"{metrics.get('fg_pct', 0.0) * 100:.1f}%")
        c3.metric("Avg distance", f"{metrics.get('avg_distance', 0.0):.2f}")

        shot_points = metrics.get("shot_points", [])
        if shot_points:
            st.caption("Basic shot chart placeholder")
            shot_df = pd.DataFrame(shot_points)
            st.scatter_chart(shot_df[["locationX", "locationY"]], x="locationX", y="locationY")
        else:
            st.info("No x/y shot data available for this player.")


col_a, col_b = st.columns(2)
show_player_card(int(player_a), col_a)
show_player_card(int(player_b), col_b)

st.divider()
st.subheader("Quick prediction")
px = st.slider("locationX", min_value=-250, max_value=250, value=0)
py = st.slider("locationY", min_value=-50, max_value=500, value=120)
pdist = st.slider("distance", min_value=0, max_value=40, value=12)

if st.button("Predict make probability"):
    try:
        result = requests.post(
            f"{API_BASE_URL}/predict",
            json={"locationX": px, "locationY": py, "distance": pdist},
            timeout=15,
        )
        result.raise_for_status()
        st.success(f"Predicted probability: {result.json()['probability']:.3f}")
    except Exception as exc:  # noqa: BLE001
        st.error(f"Prediction failed: {exc}")
