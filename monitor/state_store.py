import threading
from copy import deepcopy
from typing import Dict, List, Optional, Tuple


class StateStore:
    def __init__(self):
        self._services: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def _build_service_state(self, service_id: str) -> dict:
        return {
            "service_id": service_id,
            "status": "UNKNOWN",
            "last_heartbeat": 0.0,
            "last_status_change": 0.0,
            "heartbeat_count": 0,
            "message_count": 0,
            "missed_checks": 0,
            "last_ping_id": None,
            "ping_sent_at": 0.0,
            "pending_ping": False,
            "rtt_ms": None,
            "network": {
                "ip": "?",
                "port": "?",
            },
            "metadata": {},
        }

    def _ensure_service(self, service_id: str) -> dict:
        if service_id not in self._services:
            self._services[service_id] = self._build_service_state(service_id)
        return self._services[service_id]

    def get_or_create(self, service_id: str) -> Tuple[dict, bool]:
        with self._lock:
            created = service_id not in self._services
            service = self._ensure_service(service_id)
            return service, created

    def set_status(self, service_id: str, new_status: str, now_ts: float) -> bool:
        with self._lock:
            service = self._ensure_service(service_id)
            if service.get("status") != new_status:
                service["status"] = new_status
                service["last_status_change"] = now_ts
                return True
            return False

    def apply_metadata(self, service_id: str, payload: dict, now_ts: float) -> None:
        with self._lock:
            service = self._ensure_service(service_id)
            service["message_count"] += 1
            service["metadata"] = payload
            network = payload.get("network", {})
            service["network"]["ip"] = network.get("ip", service["network"]["ip"])
            service["network"]["port"] = network.get("port", service["network"]["port"])
            service["last_heartbeat"] = now_ts
            service["missed_checks"] = 0

    def apply_heartbeat(self, service_id: str, now_ts: float) -> None:
        with self._lock:
            service = self._ensure_service(service_id)
            service["message_count"] += 1
            service["heartbeat_count"] += 1
            service["last_heartbeat"] = now_ts
            service["missed_checks"] = 0

    def apply_pong(self, service_id: str, ping_id: str, sent_at: float, now_ts: float) -> Optional[float]:
        with self._lock:
            service = self._ensure_service(service_id)
            service["message_count"] += 1
            if ping_id != service.get("last_ping_id"):
                return None

            rtt = (now_ts - float(sent_at)) * 1000
            if not 0 <= rtt < 60000:
                return None

            rtt_ms = round(rtt, 2)
            service["rtt_ms"] = rtt_ms
            service["pending_ping"] = False
            return rtt_ms

    def get_snapshot(self) -> Dict[str, dict]:
        with self._lock:
            return deepcopy(self._services)

    def get_service_copy(self, service_id: str) -> Optional[dict]:
        with self._lock:
            data = self._services.get(service_id)
            if data is None:
                return None
            return deepcopy(data)

    def get_ping_targets(self) -> List[str]:
        with self._lock:
            return [
                service_id
                for service_id, data in self._services.items()
                if data.get("status") == "UP" and not data.get("pending_ping")
            ]

    def mark_ping_sent(self, service_id: str, ping_id: str, sent_at: float) -> None:
        with self._lock:
            service = self._ensure_service(service_id)
            service["last_ping_id"] = ping_id
            service["ping_sent_at"] = sent_at
            service["pending_ping"] = True

    def expire_pending_pings(self, now_ts: float, response_timeout: float) -> List[str]:
        expired: List[str] = []
        with self._lock:
            for service_id, data in self._services.items():
                ping_sent_at = data.get("ping_sent_at", 0.0)
                if data.get("pending_ping") and ping_sent_at and now_ts - ping_sent_at > response_timeout:
                    data["pending_ping"] = False
                    expired.append(service_id)
        return expired

    def check_timeouts(self, now_ts: float, timeout_seconds: int, max_missed_checks: int) -> List[dict]:
        transitions: List[dict] = []
        with self._lock:
            for service_id, data in self._services.items():
                last = data.get("last_heartbeat", 0)
                if not last:
                    continue

                elapsed = now_ts - last
                if elapsed > timeout_seconds:
                    data["missed_checks"] = data.get("missed_checks", 0) + 1
                    if data["missed_checks"] >= max_missed_checks and data["status"] != "DOWN":
                        data["status"] = "DOWN"
                        data["last_status_change"] = now_ts
                        transitions.append({
                            "service_id": service_id,
                            "missed_checks": data["missed_checks"],
                            "elapsed": elapsed,
                        })

        return transitions
