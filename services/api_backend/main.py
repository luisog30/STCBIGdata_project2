import io
import os
import pickle
from functools import lru_cache
from typing import Any

import pandas as pd
import redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://minio:9000")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minioadmin")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minioadmin")
S3_BUCKET = os.getenv("S3_BUCKET", "shots-data")
DATA_PATH = os.getenv("DATA_PATH", "processed/YEAR=2020/part.0.parquet")
MODEL_PATH = os.getenv("MODEL_PATH", "models/xpoints_model.pkl")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "600"))

app = FastAPI(title="Persona 3 API", version="0.1.0")


class PredictRequest(BaseModel):
    locationX: float
    locationY: float
    distance: float


class PredictResponse(BaseModel):
    probability: float


def s3_storage_options() -> dict[str, Any]:
    return {
        "key": S3_ACCESS_KEY,
        "secret": S3_SECRET_KEY,
        "client_kwargs": {"endpoint_url": S3_ENDPOINT},
    }


def data_uri() -> str:
    return f"s3://{S3_BUCKET}/{DATA_PATH}"


def model_uri() -> str:
    return f"s3://{S3_BUCKET}/{MODEL_PATH}"


@lru_cache
def redis_client() -> redis.Redis:
    return redis.Redis.from_url(REDIS_URL, decode_responses=False)


@lru_cache
def load_dataset() -> pd.DataFrame:
    return pd.read_parquet(data_uri(), storage_options=s3_storage_options())


@lru_cache
def load_model_artifact() -> dict[str, Any]:
    import fsspec

    fs, _, paths = fsspec.get_fs_token_paths(model_uri(), storage_options=s3_storage_options())
    with fs.open(paths[0], "rb") as file_obj:
        buffer = io.BytesIO(file_obj.read())
    return pickle.load(buffer)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest) -> PredictResponse:
    artifact = load_model_artifact()
    features = artifact["features"]
    model = artifact["model"]

    frame = pd.DataFrame([
        {
            "locationX": request.locationX,
            "locationY": request.locationY,
            "distance": request.distance,
        }
    ])
    prediction = model.predict_proba(frame[features])[0][1]
    return PredictResponse(probability=float(prediction))


@app.get("/players/{player_id}/metrics")
def player_metrics(player_id: int) -> dict[str, Any]:
    cache_key = f"player_metrics:{player_id}"
    cached = redis_client().get(cache_key)
    if cached:
        return pickle.loads(cached)

    df = load_dataset()
    if "playerId" not in df.columns:
        raise HTTPException(status_code=500, detail="Dataset does not contain playerId")

    player_df = df[df["playerId"] == player_id].copy()
    if player_df.empty:
        raise HTTPException(status_code=404, detail="Player not found")

    total_shots = int(len(player_df))
    made_shots = int(player_df["isScore"].sum()) if "isScore" in player_df.columns else 0
    fg_pct = float(made_shots / total_shots) if total_shots else 0.0
    avg_distance = float(player_df["distance"].mean()) if "distance" in player_df.columns else 0.0

    metrics: dict[str, Any] = {
        "player_id": player_id,
        "total_shots": total_shots,
        "made_shots": made_shots,
        "fg_pct": fg_pct,
        "avg_distance": avg_distance,
    }

    if {"locationX", "locationY"}.issubset(player_df.columns):
        sample = player_df[["locationX", "locationY", "isScore"]].head(200)
        metrics["shot_points"] = sample.fillna(0).to_dict(orient="records")

    redis_client().setex(cache_key, CACHE_TTL_SECONDS, pickle.dumps(metrics))
    return metrics
