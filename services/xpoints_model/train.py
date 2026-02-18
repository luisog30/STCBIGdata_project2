import io
import logging
import os
import pickle
from typing import Optional

import pandas as pd
from sklearn.linear_model import LogisticRegression


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
LOGGER = logging.getLogger("xpoints-train")


# Hauria de posar 'http://minio:9000' com a valor per defecte, NO 'localhost'
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


def prepare_training_frame(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    required_columns = set(FEATURE_COLUMNS + [TARGET_COLUMN])
    missing = required_columns.difference(df.columns)
    if missing:
        LOGGER.error("Missing required columns in training data: %s", sorted(missing))
        return None

    training_frame = df[FEATURE_COLUMNS + [TARGET_COLUMN]].copy()
    training_frame = training_frame.dropna()
    if training_frame.empty:
        LOGGER.error("Training frame is empty after dropping null values")
        return None

    return training_frame


def main() -> None:
    LOGGER.info("Reading training parquet from %s", parquet_uri())
    df = pd.read_parquet(parquet_uri(), storage_options=s3_storage_options())

    training_frame = prepare_training_frame(df)
    if training_frame is None:
        raise SystemExit(1)

    X = training_frame[FEATURE_COLUMNS]
    y = training_frame[TARGET_COLUMN]

    model = LogisticRegression(max_iter=500)
    model.fit(X, y)

    artifact = {
        "model": model,
        "features": FEATURE_COLUMNS,
        "target": TARGET_COLUMN,
    }

    buffer = io.BytesIO()
    pickle.dump(artifact, buffer)
    buffer.seek(0)

    LOGGER.info("Writing model artifact to %s", model_uri())
    # Write the model artifact with fsspec so the same code works for MinIO/S3.
    import fsspec  # local import to keep startup dependency minimal

    fs, _, paths = fsspec.get_fs_token_paths(model_uri(), storage_options=s3_storage_options())
    with fs.open(paths[0], "wb") as output_file:
        output_file.write(buffer.read())

    LOGGER.info("Training complete")


if __name__ == "__main__":
    main()
