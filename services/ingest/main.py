import os
import json
import time
import uuid
import math
import hashlib
from typing import Any, Dict, Optional

import paho.mqtt.client as mqtt
from datasets import load_dataset
from tqdm import tqdm


# -------------------------
# ENV / CONFIG
# -------------------------
MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
TOPIC_RAW = os.getenv("TOPIC_RAW", "shots/raw")
MQTT_QOS = int(os.getenv("MQTT_QOS", "1"))

HF_DATASET = os.getenv("HF_DATASET", "Vladislav/nba_dataset")
HF_SPLIT = os.getenv("HF_SPLIT", "train")
HF_STREAMING = os.getenv("HF_STREAMING", "1") == "1"

MAX_EVENTS = int(os.getenv("MAX_EVENTS", "5000"))  # para demo local (cambia si quieres)
SLEEP_MS = int(os.getenv("SLEEP_MS", "0"))

YEAR_MIN = os.getenv("YEAR_MIN")  # opcional
YEAR_MAX = os.getenv("YEAR_MAX")  # opcional

# Campos mínimos “raw” (incluye los necesarios para derivar is_assisted / is_blocked)
RAW_COLS = [
    "gameId", "YEAR",
    "period", "clock", "timeActual",
    "teamTricode",
    "playerName", "personId",
    "x", "y",
    "scoreHome", "scoreAway",
    "actionType", "subType",
    "shotResult", "shotDistance", "value",
    "area", "areaDetail",
    "assistPersonId", "assistPlayerNameInitial",
    "blockPersonId", "blockPlayerName",
    "isFieldGoal",
    "actionNumber"
]


# -------------------------
# Helpers
# -------------------------
def sanitize_value(v: Any) -> Any:
    """Convierte NaN -> None para JSON estricto."""
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def make_event_id(row: Dict[str, Any]) -> str:
    """
    ID estable para deduplicar:
    hash(gameId|YEAR|actionNumber|period|clock|personId)
    """
    parts = [
        str(row.get("gameId", "")),
        str(row.get("YEAR", "")),
        str(row.get("actionNumber", "")),
        str(row.get("period", "")),
        str(row.get("clock", "")),
        str(row.get("personId", "")),
    ]
    raw = "|".join(parts).encode("utf-8")
    return hashlib.md5(raw).hexdigest()


def connect_mqtt() -> mqtt.Client:
    client = mqtt.Client(client_id=f"ingest-{uuid.uuid4()}")
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()
    return client


def year_in_range(y: Any) -> bool:
    if y is None:
        return True
    try:
        y_int = int(y)
    except Exception:
        return True

    if YEAR_MIN is not None and y_int < int(YEAR_MIN):
        return False
    if YEAR_MAX is not None and y_int > int(YEAR_MAX):
        return False
    return True


def project_row(row: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for c in RAW_COLS:
        out[c] = sanitize_value(row.get(c))
    out["event_id"] = make_event_id(out)
    out["schema_version"] = "1.0"
    return out


# -------------------------
# Main
# -------------------------
def main():
    print(f"[ingest] HF_DATASET={HF_DATASET} split={HF_SPLIT} streaming={HF_STREAMING}")
    print(f"[ingest] MQTT={MQTT_HOST}:{MQTT_PORT} topic={TOPIC_RAW} qos={MQTT_QOS}")
    print(f"[ingest] MAX_EVENTS={MAX_EVENTS} YEAR_MIN={YEAR_MIN} YEAR_MAX={YEAR_MAX}")

    client = connect_mqtt()

    # Cargamos dataset real (streaming recomendado por tamaño)
    ds = load_dataset(HF_DATASET, split=HF_SPLIT, streaming=HF_STREAMING)

    sent = 0
    t0 = time.time()

    try:
        for row in tqdm(ds, desc="[ingest] streaming rows"):
            # 1) filtra rango de año (si está)
            if not year_in_range(row.get("YEAR")):
                continue

            # 2) filtra solo tiros (isFieldGoal=1)
            is_fg = row.get("isFieldGoal")
            if str(is_fg).lower() not in ("1", "true", "t", "yes", "y"):
                continue

            event = project_row(row)
            payload = json.dumps(event, ensure_ascii=False, allow_nan=False)

            info = client.publish(TOPIC_RAW, payload=payload, qos=MQTT_QOS, retain=False)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                print(f"[ingest] publish error rc={info.rc}")

            sent += 1
            if sent % 500 == 0:
                elapsed = time.time() - t0
                print(f"[ingest] sent={sent} events to {TOPIC_RAW} ({elapsed:.1f}s)")

            if SLEEP_MS > 0:
                time.sleep(SLEEP_MS / 1000.0)

            if sent >= MAX_EVENTS:
                break

    except KeyboardInterrupt:
        print("[ingest] interrupted by user")

    finally:
        client.loop_stop()
        client.disconnect()
        print(f"[ingest] done. sent={sent} events")

if __name__ == "__main__":
    main()