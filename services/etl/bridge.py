import paho.mqtt.client as mqtt
from minio import Minio
import json
import io
import uuid
from datetime import datetime

# 1. Connectem amb el MinIO (La nevera on guardarem les coses)
client_minio = Minio(
    "minio:9000",
    access_key="minioadmin",
    secret_key="minioadmin",
    secure=False
)

bucket_name = "nba-data"
if not client_minio.bucket_exists(bucket_name):
    client_minio.make_bucket(bucket_name)

# 2. Què fem quan arriba una dada nova?
def on_message(client, userdata, msg):
    try:
        # Llegim el missatge
        dades = json.loads(msg.payload.decode())
        
        # Creem un nom de fitxer únic
        nom_fitxer = f"shot_{datetime.now().strftime('%H%M%S')}_{str(uuid.uuid4())[:4]}.json"
        
        # Guardem al MinIO
        dades_bytes = json.dumps(dades).encode('utf-8')
        client_minio.put_object(
            bucket_name,
            nom_fitxer,
            io.BytesIO(dades_bytes),
            len(dades_bytes),
            content_type="application/json"
        )
        print(f"✅ Guardat al MinIO: {nom_fitxer}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

# 3. Connectem a l'MQTT (L'orella que escolta)
client_mqtt = mqtt.Client()
client_mqtt.on_message = on_message

print("🎧 Esperant dades dels companys...")
client_mqtt.connect("localhost", 1883, 60)
client_mqtt.subscribe("shots/clean") # Escoltem només les dades netes
client_mqtt.loop_forever()