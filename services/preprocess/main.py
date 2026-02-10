import os, json, uuid, re
import paho.mqtt.client as mqtt
import math

def present(v):
    if v is None:
        return False
    if isinstance(v, float) and math.isnan(v):
        return False
    if isinstance(v, str) and v.strip().lower() in ("", "nan", "none", "null"):
        return False
    return True


MQTT_HOST = os.getenv("MQTT_HOST", "mqtt")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
TOPIC_RAW = os.getenv("TOPIC_RAW", "shots/raw")
TOPIC_CLEAN = os.getenv("TOPIC_CLEAN", "shots/clean")

CLOCK_RE = re.compile(r"PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?")

def clock_to_seconds(clock_str):
    if not clock_str:
        return None
    m = CLOCK_RE.match(str(clock_str))
    if not m:
        return None
    minutes = float(m.group(1) or 0)
    seconds = float(m.group(2) or 0)
    return minutes * 60 + seconds

def derive(ev: dict) -> dict:
    # 1) Derivar is_assisted / is_blocked
    is_assisted = 1 if (present(ev.get("assistPersonId")) or present(ev.get("assistPlayerNameInitial"))) else 0
    is_blocked  = 1 if (present(ev.get("blockPersonId")) or present(ev.get("blockPlayerName"))) else 0
    


    made = 1 if ev.get("shotResult") == "Made" else 0

    # extras útiles
    margin_home = None
    try:
        if ev.get("scoreHome") is not None and ev.get("scoreAway") is not None:
            margin_home = int(ev["scoreHome"]) - int(ev["scoreAway"])
    except Exception:
        margin_home = None

    out = dict(ev)
    out["is_assisted"] = is_assisted
    out["is_blocked"] = is_blocked
    out["made"] = made
    out["time_remaining_sec"] = clock_to_seconds(ev.get("clock"))
    out["margin_home"] = margin_home
    zone_val = ev.get("areaDetail") if present(ev.get("areaDetail")) else ev.get("area")
    out["zone"] = zone_val if present(zone_val) else "unknown"


    # normaliza value -> shot_value
    out["shot_value"] = out.get("value")
    out.pop("value", None)

    # 2) borrar columnas amarillas (foto)
    for k in ["assistPersonId", "assistPlayerNameInitial", "blockPlayerName", "blockPersonId"]:
        out.pop(k, None)

    return out

def on_connect(client, userdata, flags, rc):
    print("[preprocess] connected rc=", rc)
    client.subscribe(TOPIC_RAW, qos=1)

def on_message(client, userdata, msg):
    try:
        ev = json.loads(msg.payload.decode("utf-8"))
        clean = derive(ev)
        client.publish(TOPIC_CLEAN, json.dumps(clean, default=str), qos=1)
    except Exception as e:
        print("[preprocess] error:", e)

def main():
    c = mqtt.Client(client_id=f"preprocess-{uuid.uuid4()}")
    c.on_connect = on_connect
    c.on_message = on_message
    c.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    c.loop_forever()

if __name__ == "__main__":
    main()
