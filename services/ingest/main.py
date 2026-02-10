import os, json, time, uuid
import pandas as pd
import paho.mqtt.client as mqtt
import csv

MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
TOPIC_RAW  = os.getenv("TOPIC_RAW", "shots/raw")

DATA_PATH  = os.getenv("DATA_PATH", "/data")
MAX_EVENTS = int(os.getenv("MAX_EVENTS", "5000"))
SLEEP_MS   = int(os.getenv("SLEEP_MS", "0"))

CSV_FILE = os.path.join(DATA_PATH, "dummy_data.csv")

# Verdes + Amarillas
KEEP_COLS = [
    "gameId", "YEAR", "period", "clock", "timeActual",
    "teamId", "teamTricode", "playerName", "personId",
    "actionType", "subType", "qualifiers",
    "shotResult", "pointsTotal", "shotDistance", "value",
    "x", "y", "area", "areaDetail",
    "scoreHome", "scoreAway",
    # amarillas para derivar luego
    "assistPlayerNameInitial", "assistPersonId",
    "blockPlayerName", "blockPersonId",
    # filtro
    "isFieldGoal",
    # opcional
    "actionNumber"
]

def connect_mqtt():
    c = mqtt.Client(client_id=f"ingest-{uuid.uuid4()}")
    c.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    return c

def main():
    if not os.path.exists(CSV_FILE):
        raise RuntimeError(f"No encuentro {CSV_FILE}. Pon el CSV en ./Data/dummy_data.csv")

    # Lee CSV detectando separador automáticamente y saltando líneas corruptas
    df = pd.read_csv(
    CSV_FILE,
    sep=None,              # autodetecta separador
    engine="python",       # necesario para sep=None
    on_bad_lines="skip",   # ignora filas rotas en dummy_data
    encoding="utf-8",
    encoding_errors="replace"
)

    # Limpia nombres de columnas (por si hay espacios raros)
    df.columns = df.columns.str.strip()

    if "isFieldGoal" not in df.columns:
     raise RuntimeError("El CSV no tiene columna isFieldGoal. Para probar, añádela o usa dataset real.")

    # Convierte isFieldGoal a booleano robusto
    df["isFieldGoal"] = df["isFieldGoal"].astype(str).str.lower().isin(["1", "true", "t", "yes", "y"])

    # 1) FILTRAR FILAS PRIMERO
    df = df[df["isFieldGoal"]]

    # 2) QUEDARSE SOLO CON COLUMNAS (si existen)
    cols = [c for c in KEEP_COLS if c in df.columns]
    df = df[cols]

    client = connect_mqtt()

    sent = 0
    for _, r in df.iterrows():
        if sent >= MAX_EVENTS:
            break

        row = r.to_dict()

        # event_id estable si existen gameId + actionNumber
        game_id = row.get("gameId")
        action_num = row.get("actionNumber")
        event_id = f"{game_id}-{action_num}" if pd.notna(game_id) and pd.notna(action_num) else str(uuid.uuid4())

        # no hace falta publicar isFieldGoal (ya filtrado)
        row.pop("isFieldGoal", None)

        payload = {"event_id": event_id, **row}
        client.publish(TOPIC_RAW, json.dumps(payload, default=str), qos=1)
        sent += 1

        if SLEEP_MS > 0:
            time.sleep(SLEEP_MS / 1000)

    print(f"[ingest] sent={sent} events to {TOPIC_RAW}")

if __name__ == "__main__":
    main()
