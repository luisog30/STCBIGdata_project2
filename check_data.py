import pandas as pd

# Configuració per connectar a MinIO
minio_options = {
    "key": "minioadmin",
    "secret": "minioadmin",
    "client_kwargs": {"endpoint_url": "http://localhost:9000"}
}

print("🕵️‍♂️  INSPECCIONANT DADES...")
print("-" * 30)

# 1. Comprovem la Capa SILVER (Dades enriquides)
print("1️⃣  Llegint fitxer SILVER (Processed)...")
try:
    df_silver = pd.read_parquet("s3://shots-data/processed/", storage_options=minio_options)
    
    # Mostrem columnes noves interessants
    cols_to_show = ['gameId', 'period', 'scoreHome', 'scoreAway', 'scoreMargin', 'is_clutch']
    # Si les columnes existeixen, les mostrem
    available_cols = [c for c in cols_to_show if c in df_silver.columns]
    print(df_silver[available_cols].head(5))
    
    print(f"\n   ✅ Total files: {len(df_silver)}")
    print(f"   ✅ Columnes totals: {len(df_silver.columns)}")
except Exception as e:
    print(f"   ❌ Error llegint Silver: {e}")

print("-" * 30)

# 2. Comprovem la Capa GOLD (Agregacions)
print("2️⃣  Llegint fitxer GOLD (Estadístiques per Jugador)...")
try:
    df_gold = pd.read_parquet("s3://shots-data/gold/player_stats_zone/", storage_options=minio_options)
    
    print(df_gold.head(5))
    print(f"\n   ✅ Total files (resumides): {len(df_gold)}")
except Exception as e:
    print(f"   ❌ Error llegint Gold: {e}")