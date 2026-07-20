import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    broker_host: str = os.getenv("BROKER_HOST", "localhost")
    broker_port: int = int(os.getenv("BROKER_PORT", 1883))
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", 6379))
    timeout_seconds: int = int(os.getenv("DOWN_TIMEOUT", os.getenv("TIMEOUT_SECONDS", 15)))
    max_missed_checks: int = int(os.getenv("MAX_MISSED_CHECKS", 2))
    ping_interval_seconds: float = float(os.getenv("PING_INTERVAL_SECONDS", 5.0))
    ping_response_timeout: float = float(os.getenv("PING_RESPONSE_TIMEOUT", 2.0))
    dashboard_refresh_seconds: float = float(os.getenv("DASHBOARD_REFRESH_SECONDS", 2.0))
    log_file: str = os.getenv("LOG_FILE", "monitor.log")
    db_path: str = os.getenv("MONITOR_DB_PATH", "monitor_data.db")
    mqtt_username: str = os.getenv("MQTT_USERNAME", "")
    mqtt_password: str = os.getenv("MQTT_PASSWORD", "")
    web_dashboard_host: str = os.getenv("WEB_DASHBOARD_HOST", "0.0.0.0")
    web_dashboard_port: int = int(os.getenv("WEB_DASHBOARD_PORT", 5000))
    terminal_dashboard_enabled: bool = _env_bool("TERMINAL_DASHBOARD_ENABLED", True)
    dashboard_module_filter: str = os.getenv("DASHBOARD_MODULE_FILTER", "ALL")
    alert_cooldown_seconds: int = int(os.getenv("ALERT_COOLDOWN_SECONDS", 30))
