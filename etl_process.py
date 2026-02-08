import dask.dataframe as dd
import pandas as pd
import os

# Opcions de connexió al MinIO local
minio_options = {
    "key": "minioadmin",          # Usuari per defecte de MinIO
    "secret": "minioadmin",       # Contrasenya per defecte
    "client_kwargs": {
        "endpoint_url": "http://localhost:9000" # Adreça del contenidor Docker
    }
}

# Columnes que volem mantenir (Schema)
COLUMNS_TO_KEEP = [
    'gameId', 'YEAR', 'teamTricode', 'playerName', 'personId',
    'x', 'y', 'shotDistance', 'area', 'areaDetail',
    'actionType', 'subType', 'shotResult', 'value',
    'period', 'clock', 'scoreHome', 'scoreAway',
    'isFieldGoal', 'assistPersonId', 'blockPersonId'
]

# 1. INGESTA (Llegir dades)
print("Llegint dades de prova...")

# Llegim el fitxer CSV que has posat a la carpeta 'tests/data/'
# Nota: Assegura't que el fitxer es diu 'dummy_data.csv' i està a 'tests/data/'
input_file = 'data/dummy_data.csv'

# Comprovació de seguretat
if not os.path.exists(input_file):
    print(f" ERROR: No trobo el fitxer {input_file}")
    print("   Assegura't d'haver creat la carpeta 'tests/data' i posat el CSV a dins.")
    exit()

# Definim manualment que les columnes problemàtiques es llegeixin com a TEXT ('object')
# Així evitem que Dask peti intentant convertir "Jordan" o "201,599" a número.
dtype_fix = {
    'gameId': 'object',
    'blockPersonId': 'object',
    'blockPlayerName': 'object',
    'jumpBallRecoverdPersonId': 'object',
    'orderNumber': 'object',
    'stealPersonId': 'object',
    'stealPlayerName': 'object',
    'assistPersonId': 'object',
    'personId': 'object'
}

# Llegim amb Dask aplicant els tipus de ftixers
df = dd.read_csv(input_file, 
                 sep=';',            # Important: CSV separat per comes (UTF-8)
                 encoding='utf-8',
                 dtype=dtype_fix,
                 thousands = ',',
                 decimal = ',') # Forcem que l'ID sigui text

# 2. TRANSFORMACIÓ (Neteja i Enriquiment)
print("Netejant i transformant...")

# A. Filtrar columnes: Només ens quedem amb les que existeixen al CSV
cols_existents = [c for c in COLUMNS_TO_KEEP if c in df.columns]
df = df[cols_existents]

# B. Filtre de files: Només Tirs de Camp (isFieldGoal == 1)
if 'isFieldGoal' in df.columns:
    df = df[df['isFieldGoal'] == 1]
    df = df.drop('isFieldGoal', axis=1) # Ja no la necessitem

# C. Feature Engineering (Crear dades noves útils per ML)
# Convertim IDs d'assistència i tap en flags (0 o 1)
if 'assistPersonId' in df.columns:
    df['is_assisted'] = df['assistPersonId'].notnull().astype('int8')
    df = df.drop('assistPersonId', axis=1)

if 'blockPersonId' in df.columns:
    df['is_blocked'] = df['blockPersonId'].notnull().astype('int8')
    df = df.drop('blockPersonId', axis=1)

# 3. CÀRREGA (Guardar a MinIO en Parquet)
print("Guardant resultat a MinIO (Bucket: shots-data/processed)...")

# La ruta on es guardarà dins del "núvol" local
target_path = "s3://shots-data/processed/"

try:
    df.to_parquet(
        target_path,
        storage_options=minio_options,
        engine="pyarrow",
        compression="snappy", # Comprimeix per estalviar espai
        write_index=False
    )
    print("ÈXIT! Dades processades i guardades a MinIO correctament.")
except Exception as e:
    print(f"ERROR al guardar a MinIO: {e}")
    print("   Comprova que el contenidor Docker estigui engegat (docker ps)")