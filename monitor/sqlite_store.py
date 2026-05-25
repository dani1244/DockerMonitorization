import json
import sqlite3
import threading
import time
from typing import Optional


class SQLiteStore:
    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS services (
                    service_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    ip TEXT,
                    port TEXT,
                    last_heartbeat REAL,
                    last_status_change REAL,
                    heartbeat_count INTEGER,
                    message_count INTEGER,
                    rtt_ms REAL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS service_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_ts REAL NOT NULL,
                    payload TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_events_service_ts
                ON service_events(service_id, event_ts DESC);

                CREATE TABLE IF NOT EXISTS rtt_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_id TEXT NOT NULL,
                    ping_id TEXT,
                    rtt_ms REAL NOT NULL,
                    sent_at REAL,
                    received_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_rtt_service_ts
                ON rtt_samples(service_id, received_at DESC);
                """
            )
            self._conn.commit()

    def upsert_service(self, service: dict, now_ts: Optional[float] = None) -> None:
        ts = now_ts if now_ts is not None else time.time()
        network = service.get("network", {})

        with self._lock:
            self._conn.execute(
                """
                INSERT INTO services (
                    service_id, status, ip, port, last_heartbeat, last_status_change,
                    heartbeat_count, message_count, rtt_ms, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(service_id) DO UPDATE SET
                    status=excluded.status,
                    ip=excluded.ip,
                    port=excluded.port,
                    last_heartbeat=excluded.last_heartbeat,
                    last_status_change=excluded.last_status_change,
                    heartbeat_count=excluded.heartbeat_count,
                    message_count=excluded.message_count,
                    rtt_ms=excluded.rtt_ms,
                    updated_at=excluded.updated_at
                """,
                (
                    service.get("service_id"),
                    service.get("status"),
                    str(network.get("ip", "?")),
                    str(network.get("port", "?")),
                    float(service.get("last_heartbeat", 0.0) or 0.0),
                    float(service.get("last_status_change", 0.0) or 0.0),
                    int(service.get("heartbeat_count", 0) or 0),
                    int(service.get("message_count", 0) or 0),
                    service.get("rtt_ms"),
                    ts,
                ),
            )
            self._conn.commit()

    def record_event(self, service_id: str, event_type: str, event_ts: float, payload: Optional[dict] = None) -> None:
        payload_json = json.dumps(payload or {}, ensure_ascii=True)
        with self._lock:
            self._conn.execute(
                "INSERT INTO service_events(service_id, event_type, event_ts, payload) VALUES (?, ?, ?, ?)",
                (service_id, event_type, event_ts, payload_json),
            )
            self._conn.commit()

    def record_rtt(self, service_id: str, ping_id: str, rtt_ms: float, sent_at: float, received_at: float) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO rtt_samples(service_id, ping_id, rtt_ms, sent_at, received_at) VALUES (?, ?, ?, ?, ?)",
                (service_id, ping_id, rtt_ms, sent_at, received_at),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
