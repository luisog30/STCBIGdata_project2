import io
import json
import os
import pickle
from functools import lru_cache
from typing import Any

import fsspec
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

app = FastAPI(title="Persona 3 API", version="0.2.0")


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
    return redis.Redis.from_url(REDIS_URL, decode_responses=True)


@lru_cache
def load_dataset() -> pd.DataFrame:
    return pd.read_parquet(data_uri(), storage_options=s3_storage_options())


@lru_cache
def load_model_artifact() -> dict[str, Any]:
    fs, _, paths = fsspec.get_fs_token_paths(model_uri(), storage_options=s3_storage_options())
    with fs.open(paths[0], "rb") as file_obj:
        buffer = io.BytesIO(file_obj.read())
    return pickle.load(buffer)


def _cache_get(cache_key: str) -> dict[str, Any] | None:
    try:
        cached = redis_client().get(cache_key)
        return json.loads(cached) if cached else None
    except redis.RedisError:
        return None


def _cache_set(cache_key: str, payload: dict[str, Any]) -> None:
    try:
        redis_client().setex(cache_key, CACHE_TTL_SECONDS, json.dumps(payload))
    except redis.RedisError:
        pass


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "persona3-api"}


@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest) -> PredictResponse:
    try:
        artifact = load_model_artifact()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Model artifact not found. Run training first.") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to load model: {exc}") from exc

    frame = pd.DataFrame(
        [{"locationX": request.locationX, "locationY": request.locationY, "distance": request.distance}]
    )
    prediction = artifact["model"].predict_proba(frame[artifact["features"]])[0][1]
    return PredictResponse(probability=float(prediction))


@app.get("/players/{player_id}/metrics")
def player_metrics(player_id: int) -> dict[str, Any]:
    cache_key = f"player_metrics:{player_id}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        df = load_dataset()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Could not load dataset: {exc}") from exc

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

    if {"locationX", "locationY", "isScore"}.issubset(player_df.columns):
        sample = player_df[["locationX", "locationY", "isScore"]].head(200).fillna(0)
        metrics["shot_points"] = sample.to_dict(orient="records")

    _cache_set(cache_key, metrics)
    return metrics
