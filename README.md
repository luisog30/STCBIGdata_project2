# STCBIGdata Project 2 — End-to-End NBA Analytics Pipeline 🏀📈

![Docker](https://img.shields.io/badge/Docker-Compose-blue)
![Python](https://img.shields.io/badge/Python-3.9%2B-green)
![FastAPI](https://img.shields.io/badge/FastAPI-API-success)
![Streamlit](https://img.shields.io/badge/Streamlit-Dashboard-red)
![Redis](https://img.shields.io/badge/Redis-Cache-critical)
![MinIO](https://img.shields.io/badge/MinIO-S3%20Data%20Lake-orange)

An end-to-end Big Data pipeline for NBA shot analytics: **real-time ingestion → MQTT processing → S3 Data Lake (MinIO) → batch ETL (Parquet) → ML training → API + dashboard**.

> Nota: la parte API/dashboard puede funcionar con un parquet ya existente en `shots-data/processed/YEAR=2020/part.0.parquet` (configuración actual del compose) o con el parquet generado por el ETL (`nba-data/processed/clean_data.parquet`) ajustando variables de entorno.

---

## Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Repository Structure](#repository-structure)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Quickstart](#quickstart)
- [Services & URLs](#services--urls)
- [Outputs (MinIO)](#outputs-minio)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)

---

## Overview

This project processes NBA shot events and produces:
- A **clean analytical dataset** in **Parquet**
- A trained **Expected Points (xP)** model (**Logistic Regression**)
- A **FastAPI** backend with cached metrics (**Redis**)
- A **Streamlit** dashboard for interactive exploration

---

## Architecture

### Phase 1 — Ingestion & Messaging (MQTT)
- **ingest** reads `Vladislav/nba_dataset` and publishes raw events to `shots/raw`
- **mqtt** (Eclipse Mosquitto) handles messaging with **QoS 1**
- **preprocess** subscribes to `shots/raw`, cleans/enriches data, and republishes to `shots/clean`

### Phase 2 — Storage & ETL (MinIO)
- **MinIO** acts as a local S3 Data Lake
- **bridge** subscribes to `shots/clean` and stores each event as a JSON object in bucket `nba-data`
- **etl_process** reads JSON objects and produces a consolidated **Parquet** dataset

### Phase 3 — Machine Learning (Scikit-Learn)
- **xpoints_train** loads Parquet from MinIO, trains a Logistic Regression model (xP), and saves `models/xpoints_model.pkl`

### Phase 4 — Serving & Visualization
- **api_backend** serves metrics + predictions (with Redis caching)
- **dashboard** (Streamlit) visualizes shot charts and comparisons
- Endpoints principales del backend:
  - `GET /health`
  - `POST /predict`
  - `GET /players/{player_id}/metrics`

> Topics:
> - Raw: `shots/raw`
> - Clean: `shots/clean`

---

## Repository Structure

    .
    ├── docker-compose.yml
    ├── README.md
    ├── .gitignore
    └── services/
        ├── ingest/          # Hugging Face -> MQTT (shots/raw)
        ├── preprocess/      # MQTT -> MQTT cleaning (shots/clean)
        ├── mqtt/            # Mosquitto config
        ├── etl/             # bridge.py + etl_process.py
        ├── xpoints_model/   # model training
        ├── api_backend/     # FastAPI backend
        └── dashboard/       # Streamlit dashboard

> `minio_data/` is created locally to persist MinIO objects (git ignored).

---

## Tech Stack

- **Docker Compose** — orchestration
- **Eclipse Mosquitto (MQTT)** — message broker (QoS 1)
- **MinIO** — S3-compatible Data Lake
- **Pandas** — ETL processing
- **Parquet (pyarrow/fastparquet)** — analytics format
- **Scikit-Learn** — Expected Points model
- **FastAPI** — metrics & predictions API
- **Redis** — caching heavy aggregations
- **Streamlit** — interactive dashboard with API fallback/retry support

---

## Prerequisites

- **Docker Desktop** (Linux containers)
- **Python 3.9+** (only if you run the ETL locally)
- **Git**

---

## Quickstart

Run commands from the repository root.

### 1) Start core services

~~~bash
docker compose up -d --build
~~~

This starts: **MinIO, MQTT, Redis, preprocess, api_backend, dashboard**.

Si vas a usar la API/dashboard con el dataset de `shots-data`, asegúrate de que el objeto `processed/YEAR=2020/part.0.parquet` exista en MinIO.

### 2) Publish NBA events (ingestion)

~~~bash
docker compose run --rm ingest
~~~

By default, it publishes **5,000** events.

### 3) Persist clean events into MinIO + generate Parquet (ETL)

Choose one option:

#### Option A — Run ETL locally (recommended)

1) Install ETL dependencies:
~~~bash
pip install -r services/etl/requirements.txt
~~~

2) Run the bridge (MQTT → MinIO JSON):
~~~bash
python services/etl/bridge.py
~~~

Keep it running while Step 2 is active. Stop with `Ctrl + C` once enough JSON objects are stored.

3) Run the ETL processor (MinIO JSON → Parquet):
~~~bash
python services/etl/etl_process.py
~~~

Expected output includes:
- `EXIT: Data processed and saved to processed/clean_data.parquet`

#### Option B — Run the bridge inside Docker (profile: etl)

~~~bash
docker compose --profile etl run --rm etl_job python bridge.py
~~~

### 4) Train the xPoints model (profile: train)

~~~bash
docker compose --profile train up --build xpoints_train
~~~

The container exits automatically once the model is saved into MinIO.

---

## Services & URLs

| Service | URL | Notes |
|---|---|---|
| Streamlit Dashboard | http://localhost:8501 | UI for analytics |
| FastAPI Docs (Swagger) | http://localhost:8000/docs | Test endpoints |
| MinIO Console | http://localhost:9001 | S3 browser |
| MinIO S3 Endpoint | http://localhost:9000 | Used by services |
| MQTT Broker | localhost:1883 | Mosquitto |

MinIO credentials:
- **user:** `minioadmin`
- **password:** `minioadmin`

---

## Outputs (MinIO)

Depending on your flow, artifacts can be in different buckets:

- **ETL flow (bridge + etl_process):**
  - Bucket: `nba-data`
  - Outputs:
    - JSON events (bridge)
    - `processed/clean_data.parquet`

- **API/ML compose defaults (current `docker-compose.yml`):**
  - Bucket: `shots-data`
  - Inputs/outputs:
    - `processed/YEAR=2020/part.0.parquet`
    - `models/xpoints_model.pkl`

---

## Configuration

Configuration is defined in `docker-compose.yml` via environment variables.

### Ingestion (`ingest`)
- `HF_DATASET` (default: `Vladislav/nba_dataset`)
- `HF_SPLIT` (default: `train`)
- `HF_STREAMING` (default: `"1"`)
- `MAX_EVENTS` (default: `5000`)
- `SLEEP_MS` (default: `0`)
- `TOPIC_RAW` (default: `shots/raw`)
- `MQTT_QOS` (default: `1`)

### Preprocess (`preprocess`)
- `TOPIC_RAW` (default: `shots/raw`)
- `TOPIC_CLEAN` (default: `shots/clean`)
- `MQTT_QOS` (default: `1`)

### Training (`xpoints_train`)
- `S3_ENDPOINT` (default: `http://minio:9000`)
- `S3_BUCKET` (default: `shots-data`)
- `TRAIN_DATA_PATH` (default: `processed/YEAR=2020/part.0.parquet`)
- `MODEL_OUTPUT_PATH` (default: `models/xpoints_model.pkl`)

### API (`api_backend`)
- `S3_BUCKET` (default: `shots-data`)
- `DATA_PATH` (default: `processed/YEAR=2020/part.0.parquet`)
- `MODEL_PATH` (default: `models/xpoints_model.pkl`)
- `REDIS_URL` (default: `redis://redis:6379/0`)
- `CACHE_TTL_SECONDS` (default: `600`)

### Dashboard (`dashboard`)
- `API_BASE_URL` (default: `http://api_backend:8000`)
- `FALLBACK_API_BASE_URL` (default: auto-resolved to host endpoint)
- `API_REQUEST_RETRIES` (default in app: `3`, compose sets `5`)
- `API_REQUEST_RETRY_SLEEP` (default in app: `1`)

---

## Troubleshooting

### Dashboard is empty
- Make sure Parquet and model exist in the bucket used by API/training (`shots-data` by default in compose):
  - `processed/YEAR=2020/part.0.parquet`
  - `models/xpoints_model.pkl`
- If you generated parquet with ETL in `nba-data/processed/clean_data.parquet`, adjust `S3_BUCKET`/`DATA_PATH`/`TRAIN_DATA_PATH` accordingly in `docker-compose.yml`.
- Re-run training (Step 4) if `/predict` fails due to missing model artifact.

### Ingestion stops too early
- Increase `MAX_EVENTS` in `docker-compose.yml`.

### Port conflicts (1883, 6379, 8000, 8501, 9000, 9001)
- Stop local services using those ports or change mappings in `docker-compose.yml`.

### MinIO bucket does not exist
- Create the bucket you are using (`shots-data` for current API/training defaults, or `nba-data` for ETL flow) in MinIO console (http://localhost:9001).

---
