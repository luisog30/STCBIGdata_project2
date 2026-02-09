# Projecte NBA - Big Data

## Com arrencar el projecte
1. **Infraestructura:** `docker-compose up -d`
2. **Entorn:** `pip install -r requirements.txt`
3. **Processament:** `python etl_process.py`

## Estructura de Dades
- **Raw:** Dades originals en CSV.
- **Processed (MinIO):** Dades netes en Parquet, filtrades per `isFieldGoal == 1`.
