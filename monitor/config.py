import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    broker_host: str = os.getenv("BROKER_HOST", "localhost")
    broker_port: int = int(os.getenv("BROKER_PORT", 1883))
    timeout_seconds: int = int(os.getenv("DOWN_TIMEOUT", os.getenv("TIMEOUT_SECONDS", 15)))
    max_missed_checks: int = int(os.getenv("MAX_MISSED_CHECKS", 2))
    ping_interval_seconds: float = float(os.getenv("PING_INTERVAL_SECONDS", 5.0))
    ping_response_timeout: float = float(os.getenv("PING_RESPONSE_TIMEOUT", 2.0))
    dashboard_refresh_seconds: float = float(os.getenv("DASHBOARD_REFRESH_SECONDS", 2.0))
    log_file: str = os.getenv("LOG_FILE", "monitor.log")
    mqtt_username: str = os.getenv("MQTT_USERNAME", "")
    mqtt_password: str = os.getenv("MQTT_PASSWORD", "")
