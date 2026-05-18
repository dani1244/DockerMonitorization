FROM python:3.12-slim

WORKDIR /app

RUN pip install paho-mqtt

COPY monitor.py .

CMD ["python", "monitor.py"]
