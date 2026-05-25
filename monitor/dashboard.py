import os
import time
from datetime import datetime
from typing import Dict


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


def render_dashboard(services_snapshot: Dict[str, dict], timeout_seconds: int, log_file: str) -> None:
    clear_screen()

    green = "\033[92m"
    red = "\033[91m"
    yellow = "\033[93m"
    reset = "\033[0m"
    bold = "\033[1m"

    print(bold + "=" * 80 + reset)
    print(bold + "DOCKER MONITOR" + reset)
    print(bold + "=" * 80 + reset)

    print(f"Atualizado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Timeout: {timeout_seconds}s")
    print(f"Log: {log_file}")
    print("-" * 80)

    print(
        f"{'SERVICE':<20} {'IP':<16} {'PORT':<8} {'STATUS':<8} "
        f"{'LAST HB':<10} {'LAST CHG':<10} {'RTT':<10} {'PING':<8}"
    )

    if not services_snapshot:
        print("Nenhum servico ativo ainda...")
        return

    now = time.time()
    for service_id, data in services_snapshot.items():
        net = data.get("network", {})
        ip = net.get("ip", "?")
        port = net.get("port", "?")

        status = data.get("status", "UNKNOWN")
        if status == "UP":
            status_str = green + "UP" + reset
        elif status == "DOWN":
            status_str = red + "DOWN" + reset
        else:
            status_str = yellow + status + reset

        last = data.get("last_heartbeat", 0)
        last_str = format_time(now - last) if last else "-"
        last_change = format_timestamp(data.get("last_status_change", 0))

        rtt = data.get("rtt_ms")
        rtt_str = f"{rtt}ms" if rtt is not None else "-"
        ping_status = "WAIT" if data.get("pending_ping") else "-"

        print(
            f"{service_id:<20} {ip:<16} {port:<8} {status_str:<8} "
            f"{last_str:<10} {last_change:<10} {rtt_str:<10} {ping_status:<8}"
        )
