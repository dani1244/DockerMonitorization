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
                    module TEXT,
                    department TEXT,
                    service_type TEXT,
                    version TEXT,
                    registered INTEGER DEFAULT 0,
                    registered_at REAL,
                    last_unregister REAL,
                    ip TEXT,
                    port TEXT,
                    last_heartbeat REAL,
                    last_status_change REAL,
                    heartbeat_count INTEGER,
                    message_count INTEGER,
                    rtt_ms REAL,
                    service_status_json TEXT,
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

                CREATE TABLE IF NOT EXISTS status_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_id TEXT NOT NULL,
                    sample_ts REAL NOT NULL,
                    payload TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_status_service_ts
                ON status_samples(service_id, sample_ts DESC);
                """
            )
            self._ensure_columns()
            self._conn.commit()

    def _ensure_columns(self) -> None:
        existing = {
            row[1]
            for row in self._conn.execute("PRAGMA table_info(services)").fetchall()
        }

        missing_columns = [
            ("module", "TEXT"),
            ("department", "TEXT"),
            ("service_type", "TEXT"),
            ("version", "TEXT"),
            ("registered", "INTEGER DEFAULT 0"),
            ("registered_at", "REAL"),
            ("last_unregister", "REAL"),
            ("service_status_json", "TEXT"),
        ]

        for column_name, column_type in missing_columns:
            if column_name not in existing:
                self._conn.execute(f"ALTER TABLE services ADD COLUMN {column_name} {column_type}")

    def upsert_service(self, service: dict, now_ts: Optional[float] = None) -> None:
        ts = now_ts if now_ts is not None else time.time()
        network = service.get("network", {})

        with self._lock:
            self._conn.execute(
                """
                INSERT INTO services (
                    service_id, status, module, department, service_type, version,
                    registered, registered_at, last_unregister,
                    ip, port, last_heartbeat, last_status_change,
                    heartbeat_count, message_count, rtt_ms, service_status_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(service_id) DO UPDATE SET
                    status=excluded.status,
                    module=excluded.module,
                    department=excluded.department,
                    service_type=excluded.service_type,
                    version=excluded.version,
                    registered=excluded.registered,
                    registered_at=excluded.registered_at,
                    last_unregister=excluded.last_unregister,
                    ip=excluded.ip,
                    port=excluded.port,
                    last_heartbeat=excluded.last_heartbeat,
                    last_status_change=excluded.last_status_change,
                    heartbeat_count=excluded.heartbeat_count,
                    message_count=excluded.message_count,
                    rtt_ms=excluded.rtt_ms,
                    service_status_json=excluded.service_status_json,
                    updated_at=excluded.updated_at
                """,
                (
                    service.get("service_id"),
                    service.get("status"),
                    str(service.get("module", "unknown")),
                    str(service.get("department", "unknown")),
                    str(service.get("service_type", "unknown")),
                    str(service.get("version", "unknown")),
                    1 if service.get("registered") else 0,
                    float(service.get("registered_at", 0.0) or 0.0),
                    float(service.get("last_unregister", 0.0) or 0.0),
                    str(network.get("ip", "?")),
                    str(network.get("port", "?")),
                    float(service.get("last_heartbeat", 0.0) or 0.0),
                    float(service.get("last_status_change", 0.0) or 0.0),
                    int(service.get("heartbeat_count", 0) or 0),
                    int(service.get("message_count", 0) or 0),
                    service.get("rtt_ms"),
                    json.dumps(service.get("service_status", {}), ensure_ascii=True),
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

    def record_status(self, service_id: str, sample_ts: float, payload: dict) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO status_samples(service_id, sample_ts, payload) VALUES (?, ?, ?)",
                (service_id, sample_ts, json.dumps(payload, ensure_ascii=True)),
            )
            self._conn.commit()

    def get_history_overview(self) -> dict:
        with self._lock:
            events_count = self._conn.execute("SELECT COUNT(*) FROM service_events").fetchone()[0]
            rtt_count = self._conn.execute("SELECT COUNT(*) FROM rtt_samples").fetchone()[0]
            services_count = self._conn.execute("SELECT COUNT(*) FROM services").fetchone()[0]
            status_count = self._conn.execute("SELECT COUNT(*) FROM status_samples").fetchone()[0]

            last_write = self._conn.execute(
                """
                SELECT MAX(ts) FROM (
                    SELECT MAX(event_ts) AS ts FROM service_events
                    UNION ALL
                    SELECT MAX(received_at) AS ts FROM rtt_samples
                    UNION ALL
                    SELECT MAX(sample_ts) AS ts FROM status_samples
                    UNION ALL
                    SELECT MAX(updated_at) AS ts FROM services
                )
                """
            ).fetchone()[0]

        return {
            "events_stored": int(events_count or 0),
            "rtt_samples": int(rtt_count or 0),
            "services_registered": int(services_count or 0),
            "status_samples": int(status_count or 0),
            "last_write": float(last_write or 0.0),
        }

    def get_observability_stats(self, hours: int = 24) -> dict:
        now_ts = time.time()
        since_ts = now_ts - (max(1, int(hours)) * 3600)
        with self._lock:
            avg_rtt_row = self._conn.execute(
                "SELECT AVG(rtt_ms), MAX(rtt_ms) FROM rtt_samples WHERE received_at >= ?",
                (since_ts,),
            ).fetchone()

            highest_latency_row = self._conn.execute(
                """
                SELECT service_id, AVG(rtt_ms) AS avg_rtt
                FROM rtt_samples
                WHERE received_at >= ?
                GROUP BY service_id
                ORDER BY avg_rtt DESC
                LIMIT 1
                """,
                (since_ts,),
            ).fetchone()

            events_by_type = {
                row[0]: int(row[1])
                for row in self._conn.execute(
                    "SELECT event_type, COUNT(*) FROM service_events WHERE event_ts >= ? GROUP BY event_type",
                    (since_ts,),
                ).fetchall()
            }

            events_by_service = {
                row[0]: int(row[1])
                for row in self._conn.execute(
                    "SELECT service_id, COUNT(*) FROM service_events WHERE event_ts >= ? GROUP BY service_id",
                    (since_ts,),
                ).fetchall()
            }

            downtime_rows = self._conn.execute(
                """
                SELECT service_id,
                       SUM(CASE WHEN event_type = 'service_down' THEN 1 ELSE 0 END) AS down_events,
                       SUM(CASE WHEN event_type IN ('service_up', 'service_registered') THEN 1 ELSE 0 END) AS up_events
                FROM service_events
                WHERE event_ts >= ?
                GROUP BY service_id
                """,
                (since_ts,),
            ).fetchall()

        service_availability = {}
        downtime_scores = {}
        for row in downtime_rows:
            service_id = str(row[0])
            down_events = int(row[1] or 0)
            up_events = int(row[2] or 0)
            total = down_events + up_events
            availability = 100.0 if total == 0 else round((up_events / total) * 100.0, 2)
            service_availability[service_id] = availability
            downtime_scores[service_id] = down_events

        worst_downtime_service = "-"
        if downtime_scores:
            worst_downtime_service = max(downtime_scores.items(), key=lambda item: item[1])[0]

        return {
            "window_hours": int(hours),
            "avg_rtt_24h": round(float(avg_rtt_row[0] or 0.0), 2),
            "max_rtt_24h": round(float(avg_rtt_row[1] or 0.0), 2),
            "highest_latency_service": highest_latency_row[0] if highest_latency_row else "-",
            "highest_latency_avg_rtt": round(float(highest_latency_row[1] or 0.0), 2) if highest_latency_row else 0.0,
            "worst_downtime_service": worst_downtime_service,
            "events_by_type": events_by_type,
            "events_by_service": events_by_service,
            "availability_by_service": service_availability,
        }

    def close(self) -> None:
        with self._lock:
            self._conn.close()
