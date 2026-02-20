FROM python:3.9-slim

WORKDIR /app

RUN pip install --no-cache-dir pandas minio paho-mqtt pyarrow fastparquet scikit-learn

COPY bridge.py .
COPY etl_process.py .

CMD ["python", "etl_process.py"]