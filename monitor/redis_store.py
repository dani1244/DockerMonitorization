import json
import time
from typing import Dict, List, Optional

import redis


REDIS_KEY_EVENTS_DOMAIN_RECENT = "events:domain:recent"
REDIS_KEY_EVENTS_PLATFORM_RECENT = "events:platform:recent"
REDIS_KEY_ALERTS_ACTIVE = "alerts:active"
REDIS_KEY_ALERTS_RECENT = "alerts:recent"
REDIS_KEY_SERVICES_REGISTERED = "services:registered"
REDIS_KEY_SERVICES_ALL = "services:all"
REDIS_KEY_COUNTER_EVENTS_TOTAL = "counters:events_total"
REDIS_KEY_COUNTER_EVENTS_BY_TYPE = "counters:events_by_type"
REDIS_KEY_COUNTER_EVENTS_BY_SERVICE = "counters:events_by_service"


class RedisRealtimeStore:
    def __init__(self, host: str, port: int, alert_cooldown_seconds: int = 30):
        self._client = redis.Redis(
            host=host,
            port=port,
            decode_responses=True,
            socket_timeout=2,
            socket_connect_timeout=2,
        )
        self._client.ping()
        self._alert_cooldown_seconds = max(0, int(alert_cooldown_seconds))

    @property
    def client(self):
        return self._client

    def close(self) -> None:
        self._client.close()

    def _decode_bool(self, value: Optional[str]) -> bool:
        return str(value) == "1"

    def _decode_float(self, value: Optional[str]) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _decode_int(self, value: Optional[str]) -> int:
        try:
            return int(float(value or 0))
        except (TypeError, ValueError):
            return 0

    def get_service_snapshot(self, service_id: str) -> Optional[dict]:
        data = self._client.hgetall(f"service:{service_id}:current")
        if not data:
            return None

        status_payload = {}
        try:
            status_payload = json.loads(data.get("last_status_payload", "{}"))
        except json.JSONDecodeError:
            status_payload = {}

        return {
            "service_id": service_id,
            "status": data.get("status", "UNKNOWN"),
            "module": data.get("module", "unknown"),
            "department": data.get("department", "unknown"),
            "service_type": data.get("service_type", "unknown"),
            "version": data.get("version", "unknown"),
            "registered": self._decode_bool(data.get("registered")),
            "registered_at": self._decode_float(data.get("registered_at")),
            "last_unregister": self._decode_float(data.get("last_unregister")),
            "last_heartbeat": self._decode_float(data.get("last_heartbeat")),
            "last_status_change": self._decode_float(data.get("last_status_change")),
            "heartbeat_count": self._decode_int(data.get("heartbeat_count")),
            "message_count": self._decode_int(data.get("message_count")),
            "missed_checks": self._decode_int(data.get("missed_checks")),
            "last_ping_id": data.get("last_ping_id") or None,
            "ping_sent_at": self._decode_float(data.get("ping_sent_at")),
            "pending_ping": self._decode_bool(data.get("pending_ping")),
            "rtt_ms": None if not data.get("rtt_ms") else self._decode_float(data.get("rtt_ms")),
            "network": {
                "ip": data.get("ip", "?"),
                "port": data.get("port", "?"),
            },
            "metadata": {},
            "service_status": status_payload,
            "health_score": self._decode_int(data.get("health_score")),
            "updated_at": self._decode_float(data.get("updated_at")),
        }

    def get_snapshot(self) -> Dict[str, dict]:
        service_ids: List[str] = sorted(self._client.smembers(REDIS_KEY_SERVICES_ALL))
        snapshot: Dict[str, dict] = {}
        for service_id in service_ids:
            service_snapshot = self.get_service_snapshot(service_id)
            if service_snapshot is not None:
                snapshot[service_id] = service_snapshot
        return snapshot

    def record_domain_event(self, event_doc: dict, max_items: int = 80) -> None:
        payload = json.dumps(event_doc, ensure_ascii=True)
        self._client.lpush(REDIS_KEY_EVENTS_DOMAIN_RECENT, payload)
        self._client.ltrim(REDIS_KEY_EVENTS_DOMAIN_RECENT, 0, max_items - 1)

    def record_platform_event(self, event_doc: dict, max_items: int = 120) -> None:
        payload = json.dumps(event_doc, ensure_ascii=True)
        self._client.lpush(REDIS_KEY_EVENTS_PLATFORM_RECENT, payload)
        self._client.ltrim(REDIS_KEY_EVENTS_PLATFORM_RECENT, 0, max_items - 1)

    def get_recent_domain_events(self, limit: int = 20) -> List[dict]:
        rows = self._client.lrange(REDIS_KEY_EVENTS_DOMAIN_RECENT, 0, max(0, limit - 1))
        events: List[dict] = []
        for row in rows:
            try:
                parsed = json.loads(row)
                if isinstance(parsed, dict):
                    events.append(parsed)
            except json.JSONDecodeError:
                continue
        return events

    def get_recent_platform_events(self, limit: int = 40) -> List[dict]:
        rows = self._client.lrange(REDIS_KEY_EVENTS_PLATFORM_RECENT, 0, max(0, limit - 1))
        events: List[dict] = []
        for row in rows:
            try:
                parsed = json.loads(row)
                if isinstance(parsed, dict):
                    events.append(parsed)
            except json.JSONDecodeError:
                continue
        return events

    def get_runtime_panel(self) -> dict:
        return {
            "connected": True,
            "keys": self._client.dbsize(),
            "services": self._client.scard(REDIS_KEY_SERVICES_ALL),
            "registered": self._client.scard(REDIS_KEY_SERVICES_REGISTERED),
            "active_alerts": self._client.scard(REDIS_KEY_ALERTS_ACTIVE),
            "counters_active": len(self._client.hkeys(REDIS_KEY_COUNTER_EVENTS_BY_TYPE)),
        }

    def get_event_counters(self) -> dict:
        by_type = self._client.hgetall(REDIS_KEY_COUNTER_EVENTS_BY_TYPE)
        by_service = self._client.hgetall(REDIS_KEY_COUNTER_EVENTS_BY_SERVICE)

        platform_total = 0
        domain_total = 0
        for key, value in by_type.items():
            count = self._decode_int(value)
            if str(key).startswith("domain_"):
                domain_total += count
            else:
                platform_total += count

        return {
            "events_total": self._decode_int(self._client.get(REDIS_KEY_COUNTER_EVENTS_TOTAL)),
            "platform_events_total": platform_total,
            "domain_events_total": domain_total,
            "events_by_type": by_type,
            "events_by_service": by_service,
        }

    def get_mqtt_panel(self) -> dict:
        counters = self.get_event_counters()
        return {
            "broker_online": True,
            "monitor_connected": True,
            "subscriptions": 7,
            "messages_received": counters["events_total"],
            "messages_published_estimate": counters["events_total"],
        }

    def get_recent_alerts(self, limit: int = 25) -> List[dict]:
        rows = self._client.lrange(REDIS_KEY_ALERTS_RECENT, 0, max(0, limit - 1))
        items: List[dict] = []
        for row in rows:
            try:
                parsed = json.loads(row)
                if isinstance(parsed, dict):
                    items.append(parsed)
            except json.JSONDecodeError:
                continue
        return items

    def _maybe_emit_alert_history(self, alert_doc: dict) -> None:
        service_id = str(alert_doc.get("service_id", ""))
        reason = str(alert_doc.get("reason", ""))
        if not service_id or not reason:
            return

        key = f"alert:last:{service_id}:{reason}"
        last = self._decode_float(self._client.get(key))
        now_ts = self._decode_float(alert_doc.get("updated_at"))
        if now_ts - last < float(self._alert_cooldown_seconds):
            return

        self._client.set(key, str(now_ts))
        self._client.lpush(REDIS_KEY_ALERTS_RECENT, json.dumps(alert_doc, ensure_ascii=True))
        self._client.ltrim(REDIS_KEY_ALERTS_RECENT, 0, 79)

    def get_dashboard_summary(self) -> dict:
        snapshot = self.get_snapshot()
        total = len(snapshot)
        up = 0
        down = 0
        rtts: List[float] = []

        for data in snapshot.values():
            status = str(data.get("status", "UNKNOWN"))
            if status == "UP":
                up += 1
            elif status == "DOWN":
                down += 1

            rtt = data.get("rtt_ms")
            if isinstance(rtt, (int, float)):
                rtts.append(float(rtt))

        avg_rtt = round(sum(rtts) / len(rtts), 2) if rtts else 0.0
        max_rtt = round(max(rtts), 2) if rtts else 0.0

        active_alerts = sorted(self._client.smembers(REDIS_KEY_ALERTS_ACTIVE))
        counters = self.get_event_counters()

        return {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "totals": {
                "total": total,
                "up": up,
                "down": down,
                "avg_rtt": avg_rtt,
                "max_rtt": max_rtt,
                "registered": self._client.scard(REDIS_KEY_SERVICES_REGISTERED),
                "active_alerts": len(active_alerts),
            },
            "alerts": [self._client.hgetall(f"alert:{service_id}") for service_id in active_alerts],
            "alerts_recent": self.get_recent_alerts(limit=25),
            "services": snapshot,
            "domain_events": self.get_recent_domain_events(limit=20),
            "platform_events": self.get_recent_platform_events(limit=40),
            "event_counters": counters,
            "runtime": self.get_runtime_panel(),
            "mqtt": self.get_mqtt_panel(),
        }

    def increment_event_counters(self, service_id: str, msg_type: str) -> None:
        self._client.incr(REDIS_KEY_COUNTER_EVENTS_TOTAL)
        self._client.hincrby(REDIS_KEY_COUNTER_EVENTS_BY_TYPE, str(msg_type), 1)
        self._client.hincrby(REDIS_KEY_COUNTER_EVENTS_BY_SERVICE, str(service_id), 1)

    def _compute_health_score(self, service: dict) -> int:
        status = str(service.get("status", "UNKNOWN"))
        if status == "DOWN":
            return 0

        score = 100

        if not service.get("registered"):
            score -= 20

        missed_checks = int(service.get("missed_checks", 0) or 0)
        score -= min(missed_checks * 10, 40)

        if service.get("pending_ping"):
            score -= 5

        rtt_val = service.get("rtt_ms")
        if isinstance(rtt_val, (int, float)):
            rtt = float(rtt_val)
            if rtt > 200:
                score -= 40
            elif rtt > 100:
                score -= 25
            elif rtt > 50:
                score -= 10

        return max(0, min(100, score))

    def upsert_service_realtime(self, service: dict, now_ts: Optional[float] = None) -> None:
        ts = now_ts if now_ts is not None else time.time()
        service_id = str(service.get("service_id", ""))
        if not service_id:
            return

        network = service.get("network", {})
        status_payload = service.get("service_status", {})
        health_score = self._compute_health_score(service)

        doc = {
            "service_id": service_id,
            "status": str(service.get("status", "UNKNOWN")),
            "module": str(service.get("module", "unknown")),
            "department": str(service.get("department", "unknown")),
            "service_type": str(service.get("service_type", "unknown")),
            "version": str(service.get("version", "unknown")),
            "registered": "1" if service.get("registered") else "0",
            "registered_at": str(float(service.get("registered_at", 0.0) or 0.0)),
            "last_unregister": str(float(service.get("last_unregister", 0.0) or 0.0)),
            "last_heartbeat": str(float(service.get("last_heartbeat", 0.0) or 0.0)),
            "last_status_change": str(float(service.get("last_status_change", 0.0) or 0.0)),
            "heartbeat_count": str(int(service.get("heartbeat_count", 0) or 0)),
            "message_count": str(int(service.get("message_count", 0) or 0)),
            "missed_checks": str(int(service.get("missed_checks", 0) or 0)),
            "rtt_ms": "" if service.get("rtt_ms") is None else str(service.get("rtt_ms")),
            "last_ping_id": str(service.get("last_ping_id") or ""),
            "ping_sent_at": str(float(service.get("ping_sent_at", 0.0) or 0.0)),
            "pending_ping": "1" if service.get("pending_ping") else "0",
            "ip": str(network.get("ip", "?")),
            "port": str(network.get("port", "?")),
            "last_status_payload": json.dumps(status_payload, ensure_ascii=True),
            "health_score": str(health_score),
            "updated_at": str(ts),
        }

        key = f"service:{service_id}:current"
        self._client.hset(key, mapping=doc)
        self._client.sadd(REDIS_KEY_SERVICES_ALL, service_id)

        if service.get("registered"):
            self._client.sadd(REDIS_KEY_SERVICES_REGISTERED, service_id)
        else:
            self._client.srem(REDIS_KEY_SERVICES_REGISTERED, service_id)

        status = str(service.get("status", "UNKNOWN"))
        if status == "UP" and health_score >= 50:
            self._client.srem(REDIS_KEY_ALERTS_ACTIVE, service_id)
            self._client.delete(f"alert:{service_id}")
        else:
            self._client.sadd(REDIS_KEY_ALERTS_ACTIVE, service_id)
            reason = "status_down" if status == "DOWN" else "low_health_score"
            severity = "CRITICAL" if status == "DOWN" or health_score < 30 else "WARN"
            self._client.hset(
                f"alert:{service_id}",
                mapping={
                    "service_id": service_id,
                    "reason": reason,
                    "health_score": str(health_score),
                    "status": status,
                    "severity": severity,
                    "updated_at": str(ts),
                },
            )
            self._maybe_emit_alert_history(
                {
                    "timestamp": str(ts),
                    "service_id": service_id,
                    "severity": severity,
                    "reason": reason,
                }
            )
