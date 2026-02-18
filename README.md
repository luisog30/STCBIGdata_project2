# STCBIGdata Project 2: End-to-End NBA Analytics Pipeline

This repository contains a complete Big Data engineering solution for analyzing NBA shot data. The system ingests data in real-time, processes it via a message broker, stores it in a Data Lake, trains a Machine Learning model, and visualizes the results via an interactive Dashboard.

## 1. System Architecture

The project is structured into four distinct phases, orchestrated via Docker Compose:

### Phase 1: Ingestion & Messaging (MQTT)
- **Ingest Service:** Connects to the Hugging Face dataset (`Vladislav/nba_dataset`), simulates a real-time data stream, and publishes raw JSON events to the MQTT topic `shots/raw`.
- **Message Broker:** Eclipse Mosquitto manages the message queues using QoS 1 to ensure delivery.
- **Preprocess Service:** Subscribes to `shots/raw`, performs data cleaning and standardization, and republishes enriched data to `shots/clean`.

### Phase 2: Storage & ETL (MinIO)
- **Data Lake:** MinIO provides local S3-compatible object storage.
- **Bridge Script:** A local Python script subscribes to `shots/clean` and persists individual events as JSON files into the MinIO bucket `nba-data`.
- **ETL Process:** A batch Python process extracts the JSON files, transforms the data (calculating metrics like clutch time and shot zones), and loads the consolidated dataset as a partitioned Parquet file (`processed/clean_data.parquet`).

### Phase 3: Machine Learning (Scikit-Learn)
- **Training Service:** A Dockerized container reads the Parquet file from MinIO.
- **Model:** It trains a Logistic Regression model to calculate "Expected Points" (xP) based on shot distance and court coordinates.
- **Artifact:** The trained model is serialized (`.pkl`) and saved back to MinIO for deployment.

### Phase 4: Serving & Visualization
- **Backend API:** A FastAPI service exposes endpoints for player metrics and shot predictions. It utilizes **Redis** to cache heavy aggregation queries.
- **Dashboard:** A Streamlit application consumes the API to render interactive shot charts and efficiency comparisons.

---

## 2. Repository Structure

.
├── docker-compose.yml          # Orchestration configuration for all services
├── requirements.txt            # Python dependencies for local ETL scripts
├── services/
│   ├── ingest/                 # Data ingestion logic (Hugging Face -> MQTT)
│   ├── preprocess/             # Real-time cleaning logic (MQTT -> MQTT)
│   ├── mqtt/                   # Mosquitto broker configuration
│   ├── etl/                    # ETL scripts (MQTT -> MinIO -> Parquet)
│   ├── xpoints_model/          # ML Training logic
│   ├── api_backend/            # FastAPI Backend
│   └── dashboard/              # Streamlit Frontend
└── minio_data/                 # Local persistence for MinIO (Git ignored)

## 3. Prerequisites

Ensure the following are installed on your local machine:

* **Docker Desktop** (Running Linux containers)
* **Python 3.9+** (For executing local ETL scripts)
* **Git**

---

## 4. Execution Guide

Follow these steps in order to stand up the full pipeline.

### Step 1: Start Base Infrastructure
Initialize the core services: MinIO, MQTT Broker, Redis, Preprocess, API, and Dashboard.

docker compose up -d --build

### Step 2: Data Ingestion
Run the ingestion job to populate the system with data. By default, this sends 5,000 events.

docker compose run --rm ingest

### Step 3: ETL Execution (Local)
This step bridges the gap between the real-time stream and the analytical model using a containerized ETL process.

#### Run the Bridge (MQTT to MinIO):
   `docker compose --profile etl run etl_job python bridge.py`

#### Install dependencies:
`pip install -r requirements.txt`

#### Run the Bridge (MQTT to MinIO):
This script listens for MQTT messages and saves them as JSON.

`python services/etl/bridge.py`

Keep this running while Ingestion (Step 2) is active. Once data is saved, verify files in MinIO and stop with Ctrl+C.

#### Run the ETL Processor:
This script converts the JSON files into a clean Parquet file.

`python services/etl/etl_process.py`

Expected Output: "EXIT: Data processed and saved to processed/clean_data.parquet"

### Step 4: Model Training
Train the Machine Learning model using the Parquet file generated in Step 3.

`docker compose --profile train up xpoints_train`

Note: This container will exit automatically once the model (xpoints_model.pkl) is saved to MinIO.

### Step 5: Access Applications
The system is now fully operational. Access the services via your browser:

Dashboard (Streamlit): `http://localhost:8501`
MinIO Console: `http://localhost:9001`
  Credentials: `minioadmin / minioadmin`

API Documentation: `http://localhost:8000/docs`

## 5. Configuration Reference
The system behavior is controlled via environment variables in docker-compose.yml.

### Ingestion Settings
MAX_EVENTS: Number of shots to process (Default: 5000). Increase this for a larger dataset.

SLEEP_MS: Artificial delay between messages (milliseconds). Set to >0 to visualize real-time flow.

HF_STREAMING: Set to "1" to stream data without downloading the full dataset locally.

### MQTT Settings
TOPIC_RAW: Topic for initial data (shots/raw).

TOPIC_CLEAN: Topic for processed data (shots/clean).

MQTT_QOS: Quality of Service level (Default: 1).

### API & Cache Settings
CACHE_TTL_SECONDS: Duration to hold player metrics in Redis (Default: 600s).

MODEL_PATH: Location of the model file within the bucket.

## 6. Data Schema
### Clean Topic (shots/clean)
The Preprocess service normalizes data into the following schema:

Identifiers: `event_id`, `gameId`, `personId`, `playerName`.

Temporal: `YEAR`, `period`, `clock`, `timeActual`.

Spatial: `x`, `y` (Court coordinates), `shotDistance`, `area`, `zone`.

Context: `shotResult` (Made/Missed), `shot_value` (2/3), `is_clutch`, `scoreMargin`.

### Parquet Output (processed/clean_data.parquet)
The ETL process creates a columnar file optimized for ML, renaming specific columns to match the training script requirements:

locationX (Mapped from x)

locationY (Mapped from y)

distance (Mapped from shotDistance)

isScore (Binary target variable derived from shotResult)

## 7. Troubleshooting

### Issue: Dashboard shows empty charts.

Cause: The ML model or data file is missing.

Solution: Ensure you successfully ran python services/etl/etl_process.py (Step 3) and the xpoints_train container (Step 4). Check MinIO to confirm clean_data.parquet and xpoints_model.pkl exist in the nba-data bucket.

### Issue: Connection Refused on Port 1883 or 5432.

Cause: You have a local instance of Mosquitto or Postgres/Redis running.

Solution: Stop local services or modify the port mapping in docker-compose.yml.

### Issue: Ingestion stops immediately.

Cause: MAX_EVENTS might be set too low.

Solution: Check the docker-compose.yml file and ensure MAX_EVENTS is set to at least 1000.

### Issue: "MinIO bucket does not exist".

Solution: The bridge.py script usually creates the bucket automatically. If it fails, log in to the MinIO console (localhost:9001) and create a bucket named nba-data manually.
