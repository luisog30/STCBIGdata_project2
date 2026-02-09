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
    'personId': 'object',
    'area': 'object',          # <--- Aquesta és la que t'ha donat l'error
    'areaDetail': 'object',
    'shotResult': 'object',
    'actionType': 'object',
    'subType': 'object',
    'teamTricode': 'object',
    'playerName': 'object',
    'YEAR': 'object'
}

# Llegim amb Dask aplicant els tipus de ftixers
df = dd.read_csv(input_file, 
                 sep=';',            # Important: CSV separat per comes (UTF-8)
                 encoding='utf-8',
                 dtype=dtype_fix,
                 decimal=',') # Forcem que l'ID sigui text

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

df['scoreMargin'] = df['scoreHome'] - df['scoreAway']
condition_clutch = (df['period'] >= 4) & (df['scoreMargin'].abs() <= 5)
df['is_clutch'] = condition_clutch.astype('int8')

if 'area' in df.columns:
    df['area'] = df['area'].str.upper()

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
        write_index=False,
        partition_on=['YEAR']
    )
    print("ÈXIT! Dades processades i guardades a MinIO correctament.")
except Exception as e:
    print(f"ERROR al guardar a MinIO: {e}")
    print("   Comprova que el contenidor Docker estigui engegat (docker ps)")

# 4. CAPA GOLD (Agregacions per a l'Analista)
# Exemple: Percentatge d'encert per Jugador i Zona
# Agrupem per Nom i Zona, i calculem:
# - Total de tirs (count)
# - Punts totals (sum)
# - Mitjana d'encert (mean de isFieldGoal si fos 1/0, o shotResult)

# Truc: Primer convertim shotResult (que és text "Made"/"Missed") a número (1/0)
df['shot_made_flag'] = (df['shotResult'] == 'Made').astype('int8')

# Creem la taula resum
df_player_stats = df.groupby(['playerName', 'teamTricode', 'area'])[['shot_made_flag', 'is_clutch']].agg(
    {'shot_made_flag': ['count', 'sum', 'mean'], # Tirs intentats, anotats, % encert
     'is_clutch': 'sum'}                         # Tirs fets en moment clutch
)

# Aplanem les columnes perquè quedi bonic (opcional però recomanat en Dask)
df_player_stats.columns = ['total_shots', 'made_shots', 'accuracy', 'clutch_shots_attempted']

# Guardem aquesta taula resum en una carpeta separada 'gold'
target_path_gold = "s3://shots-data/gold/player_stats_zone/"

df_player_stats.to_parquet(
    target_path_gold,
    storage_options=minio_options,
    engine="pyarrow",
    compression="snappy"
)