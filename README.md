# STCBIGdata_project2 — Pipeline NBA (MQTT + Ingest + Preprocess + MinIO)

Aquest repositori aixeca un **pipeline local amb Docker** per processar esdeveniments de tirs NBA (o dades dummy) amb arquitectura *event-driven*:

- **MQTT (Mosquitto)** com a bus de missatges
- **Ingest**: llegeix un CSV i publica esdeveniments a `shots/raw`
- **Preprocess**: consumeix `shots/raw`, transforma i publica a `shots/clean`
- **MinIO**: S3 local (preparat per persistència quan s’activi)

✅ La validació principal és veure missatges a `shots/raw` i `shots/clean`.

---

## Requisits

- Docker Desktop (Engine running)
- Ports lliures:
  - MQTT: `1883`
  - MinIO: `9000` (API) i `9001` (consola)

---

## Estructura del repo

```
Data/
  dummy_data.csv
services/
  mqtt/mosquitto.conf
  ingest/{Dockerfile,requirements.txt,main.py}
  preprocess/{Dockerfile,requirements.txt,main.py}
docker-compose.yml
minio_data/          (volum local MinIO — NO versionar)
```

---

## 1) Arrencar el pipeline (pas a pas)

Des de l’arrel del repo:

### 1.1 Aixecar MinIO + MQTT + Preprocess
```bash
docker compose up -d --build minio mqtt preprocess
```

### 1.2 Comprovar que estan en marxa
```bash
docker ps
```

Hauries de veure `nba_minio`, `nba_mqtt`, `nba_preprocess` en estat **Up**.

### 1.3 Llançar ingest
> Ingest sol enviar events i acabar (Exited). És normal.

```bash
docker compose up --build ingest
```

Als logs hauries de veure:
- `[ingest] sent=XX events to shots/raw`

---

## 2) Validar que funciona (RAW → CLEAN)

La manera més fàcil és escoltar MQTT des del contenidor `nba_mqtt`.

### 2.1 Escoltar tots els topics `shots/#`
```bash
docker exec -it nba_mqtt mosquitto_sub -t "shots/#" -v
```

Si tot està bé, veuràs missatges que comencen amb:
- `shots/raw ...`
- `shots/clean ...`

Per sortir: **CTRL+C**

### 2.2 Escoltar només CLEAN
```bash
docker exec -it nba_mqtt mosquitto_sub -t "shots/clean" -v
```

---

## 3) Test manual (publicar RAW i veure CLEAN)

Obre 2 terminals.

### Terminal A: subscripció a CLEAN
```bash
docker exec -it nba_mqtt mosquitto_sub -t "shots/clean" -v
```

### Terminal B: publicar events RAW (tests)

**Test 1: sense assistència ni bloqueig**
```bash
docker exec -it nba_mqtt mosquitto_pub -t shots/raw -m "{\"event_id\":\"test-noassist\",\"shotResult\":\"Missed\",\"value\":2,\"assistPersonId\":null,\"assistPlayerNameInitial\":null,\"blockPersonId\":null,\"blockPlayerName\":null}"
```

**Test 2: amb assistència**
```bash
docker exec -it nba_mqtt mosquitto_pub -t shots/raw -m "{\"event_id\":\"test-assist\",\"shotResult\":\"Made\",\"value\":3,\"assistPersonId\":123,\"assistPlayerNameInitial\":\"K. Durant\",\"blockPersonId\":null,\"blockPlayerName\":null}"
```

**Test 3: amb bloqueig**
```bash
docker exec -it nba_mqtt mosquitto_pub -t shots/raw -m "{\"event_id\":\"test-block\",\"shotResult\":\"Missed\",\"value\":2,\"assistPersonId\":null,\"assistPlayerNameInitial\":null,\"blockPersonId\":555,\"blockPlayerName\":\"Gobert\"}"
```

✅ Esperat a `shots/clean`:
- `is_assisted` i `is_blocked` calculats correctament (0/1)

---

## 4) Regles de preprocess (resum)

- Filtra files per `isFieldGoal == True` (si la columna existeix al dataset)
- Crea:
  - `is_assisted = 1` si `assistPersonId` o `assistPlayerNameInitial` existeixen (no buits), si no `0`
  - `is_blocked = 1` si `blockPersonId` o `blockPlayerName` existeixen (no buits), si no `0`
- Publica l’event transformat a `shots/clean`

---

## 5) MinIO (S3 local)

### 5.1 Accés a consola
- URL: http://localhost:9001
- User: `minioadmin`
- Pass: `minioadmin`

Encara que no s’estigui escrivint Parquet en aquesta fase, això valida que MinIO funciona.

---

## 6) Aturar i netejar

### 6.1 Aturar contenidors
```bash
docker compose down
```

### 6.2 Aturar i eliminar volums (⚠️ esborra dades persistents de MinIO)
```bash
docker compose down -v
```

---

## 7) Troubleshooting ràpid

### 7.1 CSV `ParserError: Expected X fields...`
El CSV pot tenir separador diferent o línies mal formades. Solució típica (ja aplicada al codi d’ingest):
- `sep=None`, `engine="python"`, `on_bad_lines="skip"`, `encoding_errors="replace"`

### 7.2 No veig `shots/clean`
Checklist:
1) `docker ps` → `nba_mqtt` i `nba_preprocess` en **Up**
2) Logs:
```bash
docker logs nba_preprocess --tail 80
docker logs nba_ingest --tail 120
```
3) Prova el **Test manual** (secció 3)

---

## 8) Git: fitxers que NO s’han de pujar

No versionar:
- `.venv/` / `venv/`
- `__pycache__/`
- `minio_data/.minio.sys/` (fitxers interns runtime de MinIO)
- datasets grans dins `Data/` (segons acord d’equip)

⚠️ Nota important: `.gitignore` ha d’estar en **UTF-8** (no UTF-16), si no, Git pot no aplicar les regles.

---



# Part Mariona

## Com arrencar el projecte
1. **Infraestructura:** `docker-compose up -d`
2. **Entorn:** `pip install -r requirements.txt`
3. **Processament:** `python etl_process.py`

## Estructura de Dades
- **Raw:** Dades originals en CSV.
- **Processed (MinIO):** Dades netes en Parquet, filtrades per `isFieldGoal == 1`.
