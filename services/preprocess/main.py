import os
import json
import uuid
import math
import re
from typing import Any, Dict, Optional, Union, List

import paho.mqtt.client as mqtt


MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
TOPIC_RAW = os.getenv("TOPIC_RAW", "shots/raw")
TOPIC_CLEAN = os.getenv("TOPIC_CLEAN", "shots/clean")
MQTT_QOS = int(os.getenv("MQTT_QOS", "1"))


def parse_iso_duration_to_seconds(iso: Optional[str]) -> Optional[float]:
    """
    Convierte 'PT11M22.00S' -> 682.0
    """
    if not iso or not isinstance(iso, str):
        return None
    m = re.match(r"PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", iso)
    if not m:
        return None
    minutes = float(m.group(1)) if m.group(1) else 0.0
    seconds = float(m.group(2)) if m.group(2) else 0.0
    return minutes * 60.0 + seconds


def to_int(x: Any) -> Optional[int]:
    if x is None:
        return None
    try:
        if isinstance(x, bool):
            return int(x)
        if isinstance(x, float) and math.isnan(x):
            return None
        return int(float(x))
    except Exception:
        return None


def to_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        if isinstance(x, float) and math.isnan(x):
            return None
        return float(x)
    except Exception:
        return None


def is_truthy(v: Any) -> bool:
    return str(v).lower() in ("1", "true", "t", "yes", "y")


def clean_event(ev: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    # 0) asegurar que es tiro
    if not is_truthy(ev.get("isFieldGoal")):
        return None

    shot_result = ev.get("shotResult")
    made = 1 if str(shot_result).lower() == "made".lower() else 0

    assist_person = ev.get("assistPersonId")
    block_person = ev.get("blockPersonId")
    block_name = ev.get("blockPlayerName")

    # Según el criterio del grupo (foto): derivar y borrar columnas auxiliares
    is_assisted = 1 if assist_person is not None else 0

    # “Blocked” tiene sentido si es Missed y existe blockPersonId/Name
    is_blocked = 1 if (str(shot_result).lower() == "missed" and (block_person is not None or block_name is not None)) else 0

    score_home = to_int(ev.get("scoreHome"))
    score_away = to_int(ev.get("scoreAway"))
    margin_home = (score_home - score_away) if (score_home is not None and score_away is not None) else None

    clock = ev.get("clock")
    time_remaining_sec = parse_iso_duration_to_seconds(clock)

    # Zona: preferimos areaDetail, fallback area
    area = ev.get("area")
    area_detail = ev.get("areaDetail")
    zone = area_detail or area or "unknown"

    # Valor del tiro (2/3): preferimos 'value', fallback actionType
    shot_value = to_int(ev.get("value"))
    if shot_value is None:
        at = str(ev.get("actionType", "")).lower()
        if "3" in at:
            shot_value = 3
        elif "2" in at:
            shot_value = 2

    out = {
        "schema_version": "1.0",
        "event_id": ev.get("event_id"),
        "gameId": ev.get("gameId"),
        "YEAR": to_int(ev.get("YEAR")),

        "period": to_int(ev.get("period")),
        "clock": clock,
        "timeActual": ev.get("timeActual"),
        "time_remaining_sec": time_remaining_sec,

        "teamTricode": ev.get("teamTricode"),
        "playerName": ev.get("playerName"),
        "personId": to_int(ev.get("personId")),

        "x": to_float(ev.get("x")),
        "y": to_float(ev.get("y")),

        "actionType": ev.get("actionType"),
        "subType": ev.get("subType"),

        "shotResult": shot_result,
        "made": made,
        "shotDistance": to_float(ev.get("shotDistance")),
        "shot_value": shot_value,

        "scoreHome": score_home,
        "scoreAway": score_away,
        "margin_home": margin_home,

        "area": area,
        "areaDetail": area_detail,
        "zone": zone,

        "is_assisted": is_assisted,
        "is_blocked": is_blocked,
    }

    return out


def on_connect(client, userdata, flags, rc):
    print(f"[preprocess] connected rc={rc}, subscribing to {TOPIC_RAW}")
    client.subscribe(TOPIC_RAW, qos=MQTT_QOS)


def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode("utf-8", errors="replace")
        data = json.loads(payload)

        # admite dict o lista
        events: List[Dict[str, Any]]
        if isinstance(data, list):
            events = data
        else:
            events = [data]

        published = 0
        for ev in events:
            if not isinstance(ev, dict):
                continue

            clean = clean_event(ev)
            if clean is None:
                continue

            out_payload = json.dumps(clean, ensure_ascii=False, allow_nan=False)
            info = client.publish(TOPIC_CLEAN, out_payload, qos=MQTT_QOS, retain=False)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                print(f"[preprocess] publish error rc={info.rc}")
            else:
                published += 1

        if published > 0:
            print(f"[preprocess] published {published} clean events to {TOPIC_CLEAN}")

    except Exception as e:
        print(f"[preprocess] ERROR processing message: {e}")


def main():
    client = mqtt.Client(client_id=f"preprocess-{uuid.uuid4()}")
    client.on_connect = on_connect
    client.on_message = on_message

    print(f"[preprocess] MQTT={MQTT_HOST}:{MQTT_PORT} raw={TOPIC_RAW} clean={TOPIC_CLEAN} qos={MQTT_QOS}")
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_forever()


if __name__ == "__main__":
    main()