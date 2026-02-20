# Persona 3: ML API + Dashboard

This setup adds an isolated machine-learning/API/dashboard stack on top of the existing MinIO service.

## What is included
- `services/xpoints_model`: train `xPoints` logistic model from cleaned parquet in MinIO and save model artifact to MinIO.
- `services/api_backend`: FastAPI service with:
  - `GET /health`
  - `POST /predict`
  - `GET /players/{player_id}/metrics` (cached in Redis)
- `services/dashboard`: Streamlit UI consuming API data (KPI + compare + shot-chart placeholder).
- `docker-compose.yml`: incluye `redis`, `api_backend`, `dashboard` y el perfil opcional `xpoints_train`.

## Prerequisites
- Docker + Docker Compose plugin.
- Existing parquet data available in MinIO bucket path:
  - `shots-data/processed/YEAR=2020/part.0.parquet`

## 1) Start base infrastructure
```bash
docker compose up -d minio
```

## 2) Train model artifact (optional profile)
This writes `shots-data/models/xpoints_model.pkl` to MinIO.

```bash
docker compose --profile train up --build xpoints_train
```

## 3) Start API + Dashboard + Redis
```bash
docker compose up --build -d redis api_backend dashboard
```

## 4) Test endpoints
```bash
curl http://localhost:8000/health

curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"locationX": 10, "locationY": 120, "distance": 15}'

curl http://localhost:8000/players/2544/metrics
```

## 5) Open dashboard
- URL: http://localhost:8501

## Notes
- API and trainer both read/write using MinIO S3-compatible access.
- Redis is used only as cache for heavy `player metrics` aggregation responses.
- Dashboard auto-resolves API host for both Docker (`api_backend`) and host (`localhost`) modes, with retries and fallback endpoint support.
- If `/predict` fails, run training step first to generate the model artifact.
