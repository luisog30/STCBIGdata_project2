import io
import logging
import os
import pickle
from typing import Optional

import fsspec
import pandas as pd
from sklearn.linear_model import LogisticRegression


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
LOGGER = logging.getLogger("xpoints-train")

S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://minio:9000")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "minioadmin")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "minioadmin")
S3_BUCKET = os.getenv("S3_BUCKET", "nba-data")
TRAIN_DATA_PATH = os.getenv("TRAIN_DATA_PATH", "processed/clean_data.parquet")
MODEL_OUTPUT_PATH = os.getenv("MODEL_OUTPUT_PATH", "models/xpoints_model.pkl")

FEATURE_COLUMNS = ["locationX", "locationY", "distance"]
TARGET_COLUMN = "isScore"


def parquet_uri() -> str:
    return f"s3://{S3_BUCKET}/{TRAIN_DATA_PATH}"


def model_uri() -> str:
    return f"s3://{S3_BUCKET}/{MODEL_OUTPUT_PATH}"


def s3_storage_options() -> dict:
    return {
        "key": S3_ACCESS_KEY,
        "secret": S3_SECRET_KEY,
        "client_kwargs": {"endpoint_url": S3_ENDPOINT},
    }


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()

    alias_map = {
        "locationX": ["locationX", "x"],
        "locationY": ["locationY", "y"],
        "distance": ["distance", "shotDistance"],
        "isScore": ["isScore"],
    }

    for canonical, options in alias_map.items():
        if canonical in normalized.columns:
            continue
        for option in options:
            if option in normalized.columns:
                normalized[canonical] = normalized[option]
                break

    if "isScore" not in normalized.columns and "shotResult" in normalized.columns:
        normalized["isScore"] = (normalized["shotResult"].astype(str).str.lower() == "made").astype("int8")

    return normalized


def prepare_training_frame(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    normalized = normalize_columns(df)
    required_columns = set(FEATURE_COLUMNS + [TARGET_COLUMN])
    missing = required_columns.difference(normalized.columns)
    if missing:
        LOGGER.error("Missing required columns in training data: %s", sorted(missing))
        return None

    frame = normalized[FEATURE_COLUMNS + [TARGET_COLUMN]].dropna().copy()
    if frame.empty:
        LOGGER.error("Training frame is empty after dropping null values")
        return None

    return frame


def main() -> None:
    LOGGER.info("Reading training parquet from %s", parquet_uri())
    df = pd.read_parquet(parquet_uri(), storage_options=s3_storage_options())

    frame = prepare_training_frame(df)
    if frame is None:
        raise SystemExit(1)

    model = LogisticRegression(max_iter=500)
    model.fit(frame[FEATURE_COLUMNS], frame[TARGET_COLUMN])

    artifact = {
        "model": model,
        "features": FEATURE_COLUMNS,
        "target": TARGET_COLUMN,
        "meta": {"rows": int(len(frame)), "source": parquet_uri()},
    }

    buffer = io.BytesIO()
    pickle.dump(artifact, buffer)
    buffer.seek(0)

    LOGGER.info("Writing model artifact to %s", model_uri())
    fs, _, paths = fsspec.get_fs_token_paths(model_uri(), storage_options=s3_storage_options())
    with fs.open(paths[0], "wb") as output_file:
        output_file.write(buffer.read())

    LOGGER.info("Training complete. rows=%s", len(frame))


if __name__ == "__main__":
    main()
