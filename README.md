# STCBIGdata Project 2 — Team 2  
## Shot Selection & Efficiency Insights (Data Engineer / MQTT Pipeline)

This repository contains the **data acquisition + preprocessing** pipeline for the NBA/WNBA play-by-play + shot-detail dataset from Hugging Face (**Vladislav/nba_dataset**).  
It publishes:
- **Raw events** as JSON to MQTT topic: `shots/raw`
- **Clean/enriched events** as JSON to MQTT topic: `shots/clean`

> **Design choice (final project):**
> - ✅ **Ingest = batch job** (sends N events and exits)  
> - ✅ **Preprocess = continuous service** (keeps listening + publishing clean events)  
> This avoids infinite re-reading + duplicate data on the Hugging Face dataset.

---

## 1) Architecture (end-to-end)

1. **Ingest service** (batch)
   - Reads dataset from Hugging Face (`HF_STREAMING=1`)
   - Publishes raw JSON messages to `shots/raw` (QoS configurable)
   - Stops after `MAX_EVENTS` (default 5000)

2. **Preprocess service** (continuous)
   - Subscribes to `shots/raw`
   - Filters + cleans + enriches
   - Publishes to `shots/clean`
   - Keeps running

3. **MQTT Broker (Mosquitto)**
   - Runs in Docker
   - Exposes port `1883`

4. **(Optional) MinIO**
   - S3-like local storage (for later Parquet exports / sharing)
   - Exposes `9000` (API) and `9001` (console)

---

## 2) Requirements (local machine)

- Docker Desktop (Windows/macOS/Linux)
- Git
- Recommended: Visual Studio Code

> No local Python is required to run the pipeline (everything runs in Docker containers).

---

## 3) Repository structure

```
.
├── docker-compose.yml
├── services
│   ├── mqtt
│   │   └── mosquitto.conf
│   ├── ingest
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── main.py
│   └── preprocess
│       ├── Dockerfile
│       ├── requirements.txt
│       └── main.py
└── minio_data/                # local MinIO persistence (should be gitignored)
```

---

## 4) docker-compose.yml (reference)

Use this compose file as the baseline configuration (already in the repo):

```yaml
version: '3.8'

services:
  minio:
    image: minio/minio
    container_name: nba_minio
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      MINIO_ROOT_USER: "minioadmin"
      MINIO_ROOT_PASSWORD: "minioadmin"
    volumes:
      - ./minio_data:/data
    command: server /data --console-address ":9001"
    networks:
      - nba_network

  mqtt:
    image: eclipse-mosquitto:2
    container_name: nba_mqtt
    ports:
      - "1883:1883"
    volumes:
      - ./services/mqtt/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro
    networks:
      - nba_network

  preprocess:
    build: ./services/preprocess
    container_name: nba_preprocess
    environment:
      MQTT_HOST: mqtt
      MQTT_PORT: 1883
      TOPIC_RAW: shots/raw
      TOPIC_CLEAN: shots/clean
      MQTT_QOS: 1
    depends_on:
      - mqtt
    restart: unless-stopped
    networks:
      - nba_network

  ingest:
    build: ./services/ingest
    container_name: nba_ingest
    environment:
      MQTT_HOST: mqtt
      MQTT_PORT: 1883
      TOPIC_RAW: shots/raw
      MQTT_QOS: 1

      HF_DATASET: Vladislav/nba_dataset
      HF_SPLIT: train
      HF_STREAMING: "1"

      MAX_EVENTS: 5000
      SLEEP_MS: 0

      # Optional year filter:
      # YEAR_MIN: "2020"
      # YEAR_MAX: "2020"
    depends_on:
      - mqtt
      - preprocess
    networks:
      - nba_network

networks:
  nba_network:
    driver: bridge
```

> Note: Docker Compose v2 shows a warning that `version:` is obsolete. It’s safe to remove, but it does not break anything.

---

## 5) Quickstart (run the full pipeline)

### 5.1 Clone the repo & checkout the working branch

```bash
git clone https://github.com/victorceballosfouces/STCBIGdata_project2.git
cd STCBIGdata_project2
git checkout feature/mqtt-ingest-preprocess
```

### 5.2 Start base services (MQTT + Preprocess + MinIO)

```bash
docker compose up -d --build minio mqtt preprocess
```

Check containers:

```bash
docker ps
```

You should see:
- `nba_mqtt` (running)
- `nba_preprocess` (running)
- `nba_minio` (running)

### 5.3 Run ingest (batch job)

Run ingest as a one-time job (it will exit when done):

```bash
docker compose up --build --force-recreate ingest
```

Expected behavior:
- `nba_ingest` prints progress like `sent=5000 events...`
- Then exits with `code 0`

To run ingest again later (recommended command):

```bash
docker compose run --rm ingest
```

---

## 6) Step 3 — “Definitive test”: verify MQTT topics end-to-end

You can run these commands in **either**:
- **Docker Desktop** → click container `nba_mqtt` → tab **Exec** → run the commands  
**or**
- Your terminal using `docker exec`

### 6.1 Subscribe to all topics

```bash
docker exec -it nba_mqtt sh
```

Inside the container:

```sh
mosquitto_sub -t 'shots/#' -v
```

If everything is correct you will see messages like:
- `shots/raw {...}`
- `shots/clean {...}`

### 6.2 Subscribe only to clean messages

```sh
mosquitto_sub -t 'shots/clean' -v
```

### 6.3 Publish a small manual test message (optional)

In the same `nba_mqtt` shell:

```sh
mosquitto_pub -t shots/raw -m '{"event_id":"test-1","shotResult":"Made","actionType":"2pt","value":2,"assistPersonId":123,"blockPersonId":null}'
```

You should see `shots/clean` output shortly after (preprocess transforms + enriches).

To exit the container shell:

```sh
exit
```

---

## 7) What “finished” looks like (expected Docker behavior)

✅ `nba_preprocess` keeps running and logging publishes like:

```bash
docker logs -f nba_preprocess
```

✅ `nba_ingest` exits after sending `MAX_EVENTS` (this is correct):

```bash
docker logs nba_ingest
```

In Docker Desktop you’ll see:
- `nba_ingest` = **Exited (0)** (expected)
- `nba_preprocess` = **Running** (expected)
- `nba_mqtt` = **Running** (expected)

---

## 8) Configuration (how Integrator 2 should control data volume)

All controls are via environment variables in `docker-compose.yml`:

### Ingest
- `HF_DATASET` (default `Vladislav/nba_dataset`)
- `HF_SPLIT` (default `train`)
- `HF_STREAMING` (`"1"` recommended)
- `MAX_EVENTS` (default `5000`)  
  - Increase to process more data (e.g. `50000`)
- `SLEEP_MS` (default `0`)  
  - Add a delay between messages if needed
- `YEAR_MIN` / `YEAR_MAX` (optional)  
  - Example: only 2020 season

### Preprocess
- `TOPIC_RAW` (default `shots/raw`)
- `TOPIC_CLEAN` (default `shots/clean`)
- `MQTT_QOS` (default `1`)

---

## 9) Output message formats (important for Integrator 2)

### 9.1 Raw topic: `shots/raw`

- Messages are **JSON**.
- Fields are close to dataset rows (some may be missing/null depending on source row).

Minimum you can assume exists:
- `event_id` (or equivalent unique identifier)
- shot/action descriptors (like `actionType`, `subType`, `shotResult`)
- coordinates (`x`, `y`) may be null in some rows

### 9.2 Clean topic: `shots/clean` (recommended schema for analytics)

Preprocess publishes a normalized message with these core fields:

- `schema_version` (e.g. `"1.0"`)
- `event_id` (string)
- `gameId` (int/string)
- `YEAR` (int)
- `period` (int)
- `clock` (string, dataset format)
- `timeActual` (string timestamp)
- `teamTricode` (string)

- `playerName` (string)
- `personId` (int)

- `actionType` (string: `2pt` / `3pt`)
- `subType` (string)
- `shotResult` (string: `Made` / `Missed`)
- `made` (0/1)
- `shotDistance` (float)

- `x` (float)
- `y` (float)

- `scoreHome` (int)
- `scoreAway` (int)
- `margin_home` (int = scoreHome - scoreAway)

- `area` (string or null)
- `areaDetail` (string or null)
- `zone` (string: if unknown → `"unknown"`)

- `shot_value` (2 or 3)
- `is_assisted` (0/1)
- `is_blocked` (0/1)

> Some fields can legitimately be `null`. Integrator 2 should handle nulls safely.

---

## 10) How Integrator 2 can consume `shots/clean` (example subscriber)

Below is a minimal Python subscriber (outside Docker, optional) that prints clean messages:

```python
import json
import paho.mqtt.client as mqtt

BROKER = "localhost"
PORT = 1883
TOPIC = "shots/clean"

def on_message(client, userdata, msg):
    payload = json.loads(msg.payload.decode("utf-8", errors="replace"))
    print("CLEAN:", payload)

client = mqtt.Client(client_id="integrator2-consumer")
client.connect(BROKER, PORT, keepalive=60)
client.subscribe(TOPIC, qos=1)
client.on_message = on_message

print("Listening on", TOPIC)
client.loop_forever()
```

If Integrator 2 prefers staying inside Docker-only, they can always test via:

```bash
docker exec -it nba_mqtt sh -c "mosquitto_sub -t 'shots/clean' -v"
```

---

## 11) Stop / reset the environment

Stop services:

```bash
docker compose down
```

Full reset (removes volumes):

```bash
docker compose down -v
```

If MinIO persistence causes problems, delete local folder:

```bash
rm -rf minio_data
```

(Windows PowerShell)

```powershell
Remove-Item -Recurse -Force .\minio_data
```

---

## 12) Troubleshooting

### Port already in use (1883 / 9000 / 9001)
- Another MQTT/MinIO is running locally
- Fix: stop it or change ports in `docker-compose.yml`

### Ingest exits quickly
- This is expected when `MAX_EVENTS` is set
- Increase `MAX_EVENTS` to send more data

### “No messages on shots/clean”
Check:
1. `nba_preprocess` is running  
   ```bash
   docker logs -f nba_preprocess
   ```
2. You are subscribing to the right topic (`shots/clean`)
3. `preprocess` depends on the fields it computes (if you publish manual minimal JSON, some fields may become `unknown`)

### Git shows MinIO runtime files
MinIO creates internal state under `minio_data/` and `.minio.sys/`.
These should be **ignored** via `.gitignore` and never committed.

---

## 13) Handoff checklist (Integrator 2)

To continue analytics work, Integrator 2 only needs:

- ✅ Run: `docker compose up -d --build minio mqtt preprocess`
- ✅ Run ingest job whenever they need new data:  
  `docker compose run --rm ingest`
- ✅ Consume clean stream from `shots/clean`
- ✅ Treat ingest as **batch**, preprocess as **continuous**

That’s it — the pipeline is ready for downstream aggregation, shot charts, and context efficiency metrics.