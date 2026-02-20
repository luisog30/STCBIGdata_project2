import pandas as pd
from minio import Minio
import io
import sys

# 1. CONFIGURACIO DE CONNEXIÓ
minio_client = Minio(
    "minio:9000",
    access_key="minioadmin",
    secret_key="minioadmin",
    secure=False
)

INPUT_BUCKET = "nba-data"  # On estan els JSONs (origen)
OUTPUT_BUCKET = "nba-data" # On guardarem els Parquet (destí)

# 2. DEFINICIÓ DE L'ESQUEMA (Exactament el teu codi anterior)
COLUMNS_TO_KEEP = [
    'gameId', 'YEAR', 'teamTricode', 'playerName', 'personId',
    'x', 'y', 'shotDistance', 'area', 'areaDetail',
    'actionType', 'subType', 'shotResult', 'value',
    'period', 'clock', 'scoreHome', 'scoreAway',
    'isFieldGoal', 'assistPersonId', 'blockPersonId'
]

# Columnes que han de ser text sí o sí (per evitar errors de format)
TEXT_COLUMNS = [
    'gameId', 'blockPersonId', 'blockPlayerName', 'jumpBallRecoverdPersonId',
    'orderNumber', 'stealPersonId', 'stealPlayerName', 'assistPersonId',
    'personId', 'area', 'areaDetail', 'shotResult', 'actionType',
    'subType', 'teamTricode', 'playerName', 'YEAR'
]

print("Iniciant el procés ETL...")

# 3. INGESTA: Llegir JSONs des de MinIO (Substitueix la lectura del CSV)
try:
    # Comprovem si el bucket existeix
    if not minio_client.bucket_exists(INPUT_BUCKET):
        print(f"ERROR: El bucket {INPUT_BUCKET} no existeix.")
        sys.exit(1)
        
    objectes = minio_client.list_objects(INPUT_BUCKET, recursive=True)
except Exception as e:
    print(f"ERROR: No s'ha pogut connectar al MinIO: {e}")
    sys.exit(1)

dades_llista = []
count_files = 0

print("Llegint fitxers JSON del MinIO...")

for obj in objectes:
    # Només processem fitxers JSON (ignorem carpetes o parquets)
    if obj.object_name.endswith('.json'):
        try:
            response = minio_client.get_object(INPUT_BUCKET, obj.object_name)
            file_content = response.read()
            
            # Llegim el JSON
            df_temp = pd.read_json(io.BytesIO(file_content), lines=True)
            
            # Normalitzem si arriba com a serie
            if isinstance(df_temp, pd.Series): 
                df_temp = df_temp.to_frame().T
            
            dades_llista.append(df_temp)
            count_files += 1
            
        except Exception as e:
            print(f"AVIS: Error llegint fitxer {obj.object_name}: {e}")
        finally:
            response.close()
            response.release_conn()

if not dades_llista:
    print("ERROR: No s'han trobat dades JSON. Assegura't d'haver executat l'ingest i el pont.")
    sys.exit(1)

# Unificació en un sol DataFrame
df = pd.concat(dades_llista, ignore_index=True)
print(f"Total fitxers llegits: {count_files}")
print(f"Total files carregades: {len(df)}")

# 4. TRANSFORMACIÓ (La teva lògica original preservada)
print("Aplicant neteja i transformacions...")

# A. Filtrar columnes (Només ens quedem amb les de COLUMNS_TO_KEEP que existeixin)
cols_existents = [c for c in COLUMNS_TO_KEEP if c in df.columns]
df = df[cols_existents]

# B. Aplicar tipus de dades (dtype_fix adaptat)
for col in TEXT_COLUMNS:
    if col in df.columns:
        df[col] = df[col].astype(str)

# Assegurar que les columnes numèriques ho són
numeric_cols = ['scoreHome', 'scoreAway', 'period', 'x', 'y', 'shotDistance']
for col in numeric_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

# C. Filtre de files: Només Tirs de Camp (isFieldGoal == 1)
if 'isFieldGoal' in df.columns:
    # Convertim a numèric per si de cas ve com string del JSON
    df['isFieldGoal'] = pd.to_numeric(df['isFieldGoal'], errors='coerce')
    df = df[df['isFieldGoal'] == 1]
    df = df.drop('isFieldGoal', axis=1) # Ja no la necessitem

# D. Feature Engineering (Les teves noves columnes)
# is_assisted
if 'assistPersonId' in df.columns:
    # Considerem assistit si no és null i no és 'None' o 'nan' string
    df['is_assisted'] = df['assistPersonId'].notnull() & (df['assistPersonId'] != 'None') & (df['assistPersonId'] != 'nan')
    df['is_assisted'] = df['is_assisted'].astype('int8')
    df = df.drop('assistPersonId', axis=1)

# is_blocked
if 'blockPersonId' in df.columns:
    df['is_blocked'] = df['blockPersonId'].notnull() & (df['blockPersonId'] != 'None') & (df['blockPersonId'] != 'nan')
    df['is_blocked'] = df['is_blocked'].astype('int8')
    df = df.drop('blockPersonId', axis=1)

# Clutch logic
if 'period' in df.columns and 'scoreHome' in df.columns:
    df['scoreMargin'] = df['scoreHome'] - df['scoreAway']
    condition_clutch = (df['period'] >= 4) & (df['scoreMargin'].abs() <= 5)
    df['is_clutch'] = condition_clutch.astype('int8')

# Area upper
if 'area' in df.columns:
    df['area'] = df['area'].str.upper()

# 5. CÀRREGA PROCESSED (Guardar Parquet net)
# 5. CÀRREGA PROCESSED (Guardar Parquet net)
print("Guardant dades processades (Processed)...")

# --- MODIFICACIÓ PER COMPATIBILITAT AMB INTEGRANT 3 ---
# Fem una còpia per no trencar res
df_export = df.copy()

# Renombrem les columnes perquè coincideixin amb el seu 'train.py'
rename_map = {
    'x': 'locationX',
    'y': 'locationY',
    'shotDistance': 'distance',
    'shot_made_flag': 'isScore'
}
# Només renombren si les columnes existeixen
df_export = df_export.rename(columns=rename_map)

# Assegurem que 'isScore' existeix (si no s'ha creat abans)
if 'isScore' not in df_export.columns and 'shotResult' in df_export.columns:
     df_export['isScore'] = (df_export['shotResult'] == 'Made').astype('int8')
# -------------------------------------------------------

# Preparem el buffer
buffer_processed = io.BytesIO()
# Guardem el dataframe amb els noms canviats
df_export.to_parquet(buffer_processed, index=False, compression="snappy")
buffer_processed.seek(0)

processed_path = "processed/clean_data.parquet"

try:
    minio_client.put_object(
        OUTPUT_BUCKET,
        processed_path,
        data=buffer_processed,
        length=buffer_processed.getbuffer().nbytes,
        content_type="application/octet-stream"
    )
    print(f"EXIT: Dades processades (compatibles amb Persona 3) guardades a '{OUTPUT_BUCKET}/{processed_path}'")
    
    # AVÍS IMPORTANT PER AL COMPANY
    print("   AVÍS PER AL COMPANY (Persona 3):")
    print("    El fitxer està a: processed/clean_data.parquet")
    print("    Les columnes són: locationX, locationY, distance, isScore")
    
except Exception as e:
    print(f"ERROR guardant processed: {e}")

# 6. CAPA GOLD (La teva lògica d'agregació)
print("Generant Capa Gold...")

# Preparem shot_made_flag
if 'shotResult' in df.columns:
    df['shot_made_flag'] = (df['shotResult'] == 'Made').astype('int8')

# Creem la taula resum
cols_group = ['playerName', 'teamTricode', 'area']
# Verifiquem que tenim les columnes necessàries
cols_present_group = [c for c in cols_group if c in df.columns]

if cols_present_group:
    df_player_stats = df.groupby(cols_present_group).agg(
        total_shots=('shot_made_flag', 'count'),
        made_shots=('shot_made_flag', 'sum'),
        accuracy=('shot_made_flag', 'mean'),
        clutch_shots_attempted=('is_clutch', 'sum')
    ).reset_index()

    # Arrodonim
    df_player_stats['accuracy'] = df_player_stats['accuracy'].round(3)

    # Guardem Gold
    buffer_gold = io.BytesIO()
    df_player_stats.to_parquet(buffer_gold, index=False, compression="snappy")
    buffer_gold.seek(0)

    gold_path = "gold/player_stats_zone.parquet"

    try:
        minio_client.put_object(
            OUTPUT_BUCKET,
            gold_path,
            data=buffer_gold,
            length=buffer_gold.getbuffer().nbytes,
            content_type="application/octet-stream"
        )
        print(f"EXIT: Capa Gold guardada a '{OUTPUT_BUCKET}/{gold_path}'")
    except Exception as e:
        print(f"ERROR guardant gold: {e}")

else:
    print("AVIS: Falten columnes per generar la capa Gold.")