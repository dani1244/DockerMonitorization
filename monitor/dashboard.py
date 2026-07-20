import os
import time
from datetime import datetime
from typing import Dict, List, Tuple


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def format_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds/60:.0f}m"
    return f"{seconds/3600:.1f}h"


def format_timestamp(timestamp: float) -> str:
    if not timestamp:
        return "-"
    return datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")


def _module_label(value: str) -> str:
    if not value:
        return "UNKNOWN"
    return str(value).strip().upper()


def _group_by_module(services_snapshot: Dict[str, dict]) -> Dict[str, List[Tuple[str, dict]]]:
    grouped: Dict[str, List[Tuple[str, dict]]] = {}
    for service_id, data in services_snapshot.items():
        module = _module_label(data.get("module") or data.get("service_type") or "unknown")
        grouped.setdefault(module, []).append((service_id, data))
    return grouped


def _filter_modules(grouped: Dict[str, List[Tuple[str, dict]]], module_filter: str) -> Dict[str, List[Tuple[str, dict]]]:
    value = str(module_filter or "ALL").strip().upper()
    if value in {"", "ALL", "*"}:
        return grouped
    return {value: grouped.get(value, [])}


def _status_colored(status: str, green: str, red: str, yellow: str, reset: str) -> str:
    if status == "UP":
        return green + "UP" + reset
    if status == "DOWN":
        return red + "DOWN" + reset
    return yellow + status + reset


def _preview_payload(payload: dict) -> str:
    if not payload:
        return "-"
    keys = sorted(payload.keys())
    preview = ", ".join(f"{k}={payload[k]}" for k in keys[:2])
    return preview or "-"


def _rooms_metric(payload: dict) -> str:
    free_rooms = payload.get("free_rooms")
    occupied_rooms = payload.get("occupied_rooms")
    if free_rooms is None and occupied_rooms is None:
        return ""
    return f"free={free_rooms if free_rooms is not None else '-'} occ={occupied_rooms if occupied_rooms is not None else '-'}"


def _printing_metric(payload: dict) -> str:
    jobs = payload.get("jobs")
    queue_size = payload.get("queue_size")
    if jobs is None and queue_size is None:
        return ""
    return f"jobs={jobs if jobs is not None else '-'} queue={queue_size if queue_size is not None else '-'}"


def _parking_metric(payload: dict) -> str:
    free_spots = payload.get("free_spots", payload.get("free"))
    if free_spots is None:
        return ""
    return f"free={free_spots}"


def _transport_metric(payload: dict) -> str:
    stop = payload.get("current_stop")
    eta = payload.get("eta")
    if stop is None and eta is None:
        return ""
    return f"stop={stop if stop is not None else '-'} eta={eta if eta is not None else '-'}"


def _canteen_metric(payload: dict) -> str:
    queue_avg = payload.get("avg_queue")
    if queue_avg is None:
        return ""
    return f"avg_queue={queue_avg}"


def _extract_module_metric(module: str, service_data: dict) -> str:
    status_payload = service_data.get("service_status", {})
    if not isinstance(status_payload, dict):
        return "-"

    module_key = module.lower()
    groups = [
        ({"rooms", "room", "sala", "salas"}, _rooms_metric),
        ({"printing", "printers", "printer", "impressao", "impressora"}, _printing_metric),
        ({"parking", "estacionamento"}, _parking_metric),
        ({"transport", "transports", "shuttle", "bus"}, _transport_metric),
        ({"canteen", "cantina"}, _canteen_metric),
    ]

    for aliases, metric_builder in groups:
        if module_key in aliases:
            value = metric_builder(status_payload)
            return value or _preview_payload(status_payload)

    return _preview_payload(status_payload)


def _render_module_rows(module: str, services: List[Tuple[str, dict]], now: float, colors: Tuple[str, str, str, str]) -> None:
    green, red, yellow, reset = colors
    for service_id, data in sorted(services, key=lambda item: item[0]):
        status_str = _status_colored(str(data.get("status", "UNKNOWN")), green, red, yellow, reset)
        registered = "YES" if data.get("registered") else "NO"

        last = data.get("last_heartbeat", 0)
        last_str = format_time(now - last) if last else "-"

        rtt = data.get("rtt_ms")
        rtt_str = f"{rtt}ms" if rtt is not None else "-"

        metric = _extract_module_metric(module, data)
        department = str(data.get("department", "unknown"))

        print(
            f"{service_id:<24} {department:<18} {status_str:<8} {registered:<6} "
            f"{last_str:<8} {rtt_str:<10} {metric:<30}"
        )


def _render_domain_events(events: List[dict]) -> None:
    print("EVENTOS DE DOMINIO (ultimos)")
    print(f"{'TIME':<10} {'PRODUCER':<26} {'EVENT':<34} {'TOPIC':<34}")
    for item in events[:8]:
        ts = float(item.get("timestamp", 0) or 0)
        ts_str = format_timestamp(ts)
        producer = str(item.get("producer_service", "-"))
        event_type = str(item.get("event_type", "-"))
        topic = str(item.get("topic", "-"))
        print(f"{ts_str:<10} {producer:<26} {event_type:<34} {topic:<34}")
    if not events:
        print("-")
    print("-" * 80)


def render_dashboard(
    services_snapshot: Dict[str, dict],
    timeout_seconds: int,
    log_file: str,
    domain_events: List[dict] | None = None,
    module_filter: str = "ALL",
) -> None:
    clear_screen()

    green = "\033[92m"
    red = "\033[91m"
    yellow = "\033[93m"
    reset = "\033[0m"
    bold = "\033[1m"

    print(bold + "=" * 80 + reset)
    print(bold + "SMART CAMPUS SERVICE PLATFORM" + reset)
    print(bold + "=" * 80 + reset)

    print(f"Atualizado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Timeout: {timeout_seconds}s")
    print(f"Log: {log_file}")
    print("-" * 80)

    if not services_snapshot:
        print("Nenhum servico ativo ainda...")
        return

    grouped = _group_by_module(services_snapshot)
    grouped = _filter_modules(grouped, module_filter)
    print(bold + "SERVICOS / MODULOS" + reset)
    modules = sorted(grouped.keys())
    print(f"Filtro de modulo: {str(module_filter or 'ALL').upper()}")
    for module in modules:
        print(f"- {module} ({len(grouped[module])})")
    print("-" * 80)

    now = time.time()
    colors = (green, red, yellow, reset)
    for module in modules:
        print(bold + f"[{module}]" + reset)
        print(
            f"{'SERVICE':<24} {'DEPARTMENT':<18} {'STATUS':<8} {'REG':<6} "
            f"{'LAST HB':<8} {'RTT':<10} {'METRIC':<30}"
        )

        _render_module_rows(module, grouped[module], now, colors)

        print("-" * 80)

    _render_domain_events(domain_events or [])
