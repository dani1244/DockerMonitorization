from collections import defaultdict
from datetime import datetime
from flask import Flask, jsonify, render_template_string, request


HTML_TEMPLATE = """
<!doctype html>
<html lang="pt">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Smart Campus Observability Console</title>
  <style>
    :root {
      --bg: #f5f7f8;
      --card: #ffffff;
      --ink: #182025;
      --muted: #5b6772;
      --line: #d8dee4;
      --healthy: #177245;
      --degraded: #a26a00;
      --unhealthy: #c53d13;
      --offline: #6a7280;
      --accent: #1c6ea4;
      --critical: #b42318;
      --warn: #b54708;
      --info: #1d4ed8;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background:
        linear-gradient(125deg, #edf4f9 0%, #f5f7f8 40%),
        radial-gradient(circle at 85% 20%, #dbeef9 0%, transparent 35%);
      color: var(--ink);
      font-family: "Segoe UI", "Ubuntu", sans-serif;
    }
    .wrap { max-width: 1380px; margin: 0 auto; padding: 22px; }
    .hero {
      background: linear-gradient(95deg, #173b56 0%, #295f86 70%);
      color: #fff;
      border-radius: 16px;
      padding: 16px 18px;
      margin-bottom: 14px;
      box-shadow: 0 8px 22px rgba(16, 40, 60, 0.22);
    }
    h1 { margin: 0; font-size: 1.9rem; }
    h2 { margin: 0 0 10px; font-size: 1.15rem; }
    .sub { color: #d7e6f2; margin: 6px 0 2px; }
    .grid { display: grid; gap: 12px; }
    .kpis { grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); margin-bottom: 14px; }
    .two { grid-template-columns: 1.2fr 1fr; margin-bottom: 14px; }
    .three { grid-template-columns: repeat(3, minmax(0, 1fr)); margin-bottom: 14px; }
    .card {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
      box-shadow: 0 5px 16px rgba(20, 35, 45, 0.05);
    }
    .card:hover { box-shadow: 0 8px 22px rgba(20, 35, 45, 0.09); }
    .label { color: var(--muted); font-size: 0.86rem; text-transform: uppercase; letter-spacing: 0.4px; }
    .kpi { font-size: 1.7rem; font-weight: 700; line-height: 1.2; }
    .healthy { color: var(--healthy); }
    .degraded { color: var(--degraded); }
    .unhealthy { color: var(--unhealthy); }
    .offline { color: var(--offline); }
    .toolbar {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
      margin-bottom: 10px;
    }
    .toolbar strong { color: #28465e; }
    .toolbar a {
      text-decoration: none;
      color: var(--accent);
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 5px 10px;
      background: #fff;
      font-size: 0.86rem;
    }
    .toolbar a.active { background: #e8f2fa; font-weight: 700; border-color: #a8cae4; }
    .module-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 10px; }
    .module-title { font-weight: 700; font-size: 1.02rem; margin-bottom: 6px; }
    .module-row { display: flex; justify-content: space-between; font-size: 0.9rem; margin-top: 4px; }
    .section-caption { font-size: 0.86rem; color: var(--muted); margin: 0 0 8px; }
    .tag {
      display: inline-block;
      border-radius: 999px;
      padding: 2px 9px;
      font-size: 0.76rem;
      font-weight: 700;
      border: 1px solid transparent;
    }
    .tag.HEALTHY { color: var(--healthy); background: #d7f4e6; border-color: #9cdbbd; }
    .tag.DEGRADED { color: var(--degraded); background: #fff3d7; border-color: #ffd690; }
    .tag.UNHEALTHY { color: var(--unhealthy); background: #ffe2d6; border-color: #ffb79f; }
    .tag.OFFLINE { color: var(--offline); background: #eef0f3; border-color: #d5dae1; }
    .sev { font-weight: 700; }
    .sev.INFO { color: var(--info); }
    .sev.WARN { color: var(--warn); }
    .sev.CRITICAL { color: var(--critical); }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 8px 7px; border-bottom: 1px solid #edf0f2; font-size: 0.9rem; vertical-align: top; }
    th { color: #253645; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.35px; }
    .timeline { display: grid; gap: 8px; }
    .timeline-item {
      border-left: 3px solid #9dc1d9;
      padding: 6px 10px;
      background: #f8fbfd;
      border-radius: 6px;
      font-size: 0.9rem;
    }
    .flow-path { display: grid; gap: 8px; }
    .flow-step {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 0.9rem;
      padding: 6px 8px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fafcfd;
    }
    .arrow { color: #6b7784; }
    @media (max-width: 1050px) {
      .two, .three { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <h1>Smart Campus Observability Console</h1>
      <div class="sub">Atualizado em {{ timestamp }} | servicos monitorizados: {{ totals.total }} | modelo de health ativo</div>
    </section>

    <section class="grid kpis">
      <article class="card"><div class="label">Servicos UP</div><div class="kpi">{{ totals.up }}</div></article>
      <article class="card"><div class="label">Servicos DOWN</div><div class="kpi">{{ totals.down }}</div></article>
      <article class="card"><div class="label">Healthy</div><div class="kpi healthy">{{ health_counts.HEALTHY }}</div></article>
      <article class="card"><div class="label">Degraded</div><div class="kpi degraded">{{ health_counts.DEGRADED }}</div></article>
      <article class="card"><div class="label">Unhealthy</div><div class="kpi unhealthy">{{ health_counts.UNHEALTHY }}</div></article>
      <article class="card"><div class="label">Offline</div><div class="kpi offline">{{ health_counts.OFFLINE }}</div></article>
      <article class="card"><div class="label">RTT medio</div><div class="kpi">{{ totals.avg_rtt }} ms</div></article>
      <article class="card"><div class="label">RTT maximo</div><div class="kpi">{{ totals.max_rtt }} ms</div></article>
      <article class="card"><div class="label">Disponibilidade</div><div class="kpi">{{ totals.availability_pct }}%</div></article>
      <article class="card"><div class="label">Mensagens MQTT</div><div class="kpi">{{ event_counters.events_total }}</div></article>
      <article class="card"><div class="label">Eventos de dominio</div><div class="kpi">{{ event_counters.domain_events_total }}</div></article>
      <article class="card"><div class="label">Alertas ativos</div><div class="kpi">{{ totals.active_alerts }}</div></article>
    </section>

    <section class="card">
      <p class="section-caption">Vista agregada por modulo com estado operacional dominante.</p>
      <div class="toolbar">
        <strong>Filtro modulo:</strong>
        {% for item in available_modules %}
          <a href="/?module={{ item }}" class="{% if item == selected_module %}active{% endif %}">{{ item }}</a>
        {% endfor %}
      </div>
      <div class="module-cards">
        {% for card in module_cards %}
          <article class="card">
            <div class="module-title">{{ card.module }}</div>
            <div class="module-row"><span>Estado</span><span class="tag {{ card.health_label }}">{{ card.health_label }}</span></div>
            <div class="module-row"><span>RTT medio</span><span>{{ card.avg_rtt }} ms</span></div>
            <div class="module-row"><span>Ultimo heartbeat</span><span>{{ card.last_heartbeat }}</span></div>
            <div class="module-row"><span>Metrica</span><span>{{ card.metric }}</span></div>
          </article>
        {% endfor %}
      </div>
    </section>

    <section class="grid two">
      <article class="card">
        <h2>Painel de Alertas</h2>
        <p class="section-caption">Alertas com cooldown para reduzir repeticao e ruido.</p>
        <table>
          <thead><tr><th>Timestamp</th><th>Servico</th><th>Severidade</th><th>Motivo</th></tr></thead>
          <tbody>
          {% for alert in alerts_recent %}
            <tr>
              <td>{{ alert.time }}</td>
              <td>{{ alert.service_id }}</td>
              <td><span class="sev {{ alert.severity }}">{{ alert.severity }}</span></td>
              <td>{{ alert.reason }}</td>
            </tr>
          {% else %}
            <tr><td colspan="4">Sem alertas recentes.</td></tr>
          {% endfor %}
          </tbody>
        </table>
      </article>

      <article class="card">
        <h2>Timeline de Eventos de Dominio</h2>
        <p class="section-caption">Sequencia cronologica de colaboracoes entre servicos.</p>
        <div class="timeline">
          {% for ev in domain_events %}
            <div class="timeline-item">
              <strong>{{ ev.time }}</strong> | {{ ev.event_label }}<br/>
              <span>{{ ev.producer_service }}</span><br/>
              <span>{{ ev.data_summary }}</span>
            </div>
          {% else %}
            <div class="timeline-item">Sem eventos de dominio.</div>
          {% endfor %}
        </div>
      </article>
    </section>

    <section class="grid two">
      <article class="card">
        <h2>Fluxo de Eventos (colaboracao)</h2>
        <p class="section-caption">Cadeias origem -> evento -> destino inferidas dos eventos recentes.</p>
        <div class="flow-path">
          {% for step in event_flow %}
            <div class="flow-step">
              <span>{{ step.source }}</span>
              <span class="arrow">-></span>
              <span>{{ step.event }}</span>
              <span class="arrow">-></span>
              <span>{{ step.target }}</span>
            </div>
          {% else %}
            <div class="flow-step">Sem relacoes recentes com triggered_by.</div>
          {% endfor %}
        </div>
      </article>

      <article class="card">
        <h2>Plataforma vs Dominio</h2>
        <p class="section-caption">Separacao entre eventos tecnicos da plataforma e eventos funcionais do campus.</p>
        <div class="module-row"><span>Eventos plataforma</span><strong>{{ event_counters.platform_events_total }}</strong></div>
        <div class="module-row"><span>Eventos dominio</span><strong>{{ event_counters.domain_events_total }}</strong></div>
        <table style="margin-top:8px;">
          <thead><tr><th>Time</th><th>Evento plataforma</th><th>Servico</th></tr></thead>
          <tbody>
          {% for ev in platform_events %}
            <tr>
              <td>{{ ev.time }}</td><td>{{ ev.event_type }}</td><td>{{ ev.service_id }}</td>
            </tr>
          {% else %}
            <tr><td colspan="3">Sem eventos de plataforma recentes.</td></tr>
          {% endfor %}
          </tbody>
        </table>
      </article>
    </section>

    <section class="grid three">
      <article class="card">
        <h2>Redis (tempo real)</h2>
        <div class="module-row"><span>Connected</span><strong>{{ 'YES' if runtime.connected else 'NO' }}</strong></div>
        <div class="module-row"><span>Keys</span><strong>{{ runtime.keys }}</strong></div>
        <div class="module-row"><span>Counters ativos</span><strong>{{ runtime.counters_active }}</strong></div>
        <div class="module-row"><span>Servicos registados</span><strong>{{ runtime.registered }}</strong></div>
      </article>

      <article class="card">
        <h2>SQLite (historico)</h2>
        <div class="module-row"><span>Eventos armazenados</span><strong>{{ sqlite.events_stored }}</strong></div>
        <div class="module-row"><span>RTT samples</span><strong>{{ sqlite.rtt_samples }}</strong></div>
        <div class="module-row"><span>Status samples</span><strong>{{ sqlite.status_samples }}</strong></div>
        <div class="module-row"><span>Ultima escrita</span><strong>{{ sqlite.last_write_label }}</strong></div>
      </article>

      <article class="card">
        <h2>MQTT Broker</h2>
        <div class="module-row"><span>Broker online</span><strong>{{ 'YES' if mqtt.broker_online else 'NO' }}</strong></div>
        <div class="module-row"><span>Monitor ligado</span><strong>{{ 'YES' if mqtt.monitor_connected else 'NO' }}</strong></div>
        <div class="module-row"><span>Subscricoes</span><strong>{{ mqtt.subscriptions }}</strong></div>
        <div class="module-row"><span>Msgs recebidas</span><strong>{{ mqtt.messages_received }}</strong></div>
        <div class="module-row"><span>Msgs publicadas</span><strong>{{ mqtt.messages_published_estimate }}</strong></div>
      </article>
    </section>

    <section class="card">
      <h2>Estatisticas Historicas (24h)</h2>
      <div class="grid three" style="margin-bottom:6px;">
        <div class="module-row"><span>RTT medio 24h</span><strong>{{ historical.avg_rtt_24h }} ms</strong></div>
        <div class="module-row"><span>Maior latencia</span><strong>{{ historical.highest_latency_service }} ({{ historical.highest_latency_avg_rtt }} ms)</strong></div>
        <div class="module-row"><span>Maior downtime</span><strong>{{ historical.worst_downtime_service }}</strong></div>
      </div>
      <table>
        <thead><tr><th>Servico</th><th>Disponibilidade (%)</th><th>Eventos</th></tr></thead>
        <tbody>
          {% for row in service_stats_rows %}
          <tr><td>{{ row.service_id }}</td><td>{{ row.availability }}</td><td>{{ row.events }}</td></tr>
          {% else %}
          <tr><td colspan="3">Sem dados historicos ainda.</td></tr>
          {% endfor %}
        </tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""


def _module_alias(value: str) -> str:
    key = (value or "").strip().lower()
    if key in {"parking", "estacionamento"}:
        return "PARKING"
    if key in {"rooms", "room", "sala", "salas"}:
        return "ROOMS"
    if key in {"printers", "printer", "printing", "impressora", "impressao"}:
        return "PRINTERS"
    return key.upper() or "UNKNOWN"


def _format_metric(module_name: str, payload: dict) -> str:
  if not isinstance(payload, dict) or not payload:
    return "-"

  if module_name == "PARKING":
    free = payload.get("free_spots", payload.get("free"))
    occ = payload.get("occupied_spots")
    if free is not None or occ is not None:
      return f"free={free if free is not None else '-'} occ={occ if occ is not None else '-'}"
  if module_name == "ROOMS":
    free = payload.get("free_rooms")
    occ = payload.get("occupied_rooms")
    if free is not None or occ is not None:
      return f"free={free if free is not None else '-'} occ={occ if occ is not None else '-'}"
  if module_name == "PRINTERS":
    jobs = payload.get("jobs")
    queue = payload.get("queue_size")
    if jobs is not None or queue is not None:
      return f"jobs={jobs if jobs is not None else '-'} queue={queue if queue is not None else '-'}"
  if module_name == "TRANSPORT":
    stop = payload.get("current_stop")
    eta = payload.get("eta")
    if stop is not None or eta is not None:
      return f"stop={stop if stop is not None else '-'} eta={eta if eta is not None else '-'}"
  if module_name == "CANTEEN":
    queue_avg = payload.get("avg_queue")
    meals = payload.get("available_meals")
    if queue_avg is not None or meals is not None:
      return f"queue={queue_avg if queue_avg is not None else '-'} meals={meals if meals is not None else '-'}"

  keys = sorted(payload.keys())
  return ", ".join(f"{k}={payload[k]}" for k in keys[:2]) or "-"


def _to_float(value, default=0.0) -> float:
  try:
    return float(value)
  except (TypeError, ValueError):
    return default


def _health_label(data: dict) -> str:
  status = str(data.get("status", "UNKNOWN"))
  if status == "DOWN" or not data.get("registered"):
    return "OFFLINE"

  health_score = int(data.get("health_score", 0) or 0)
  rtt = _to_float(data.get("rtt_ms"), default=0.0)
  payload = data.get("service_status", {}) if isinstance(data.get("service_status"), dict) else {}

  functional_penalty = False
  if "queue_size" in payload and _to_float(payload.get("queue_size")) > 15:
    functional_penalty = True
  if "avg_queue" in payload and _to_float(payload.get("avg_queue")) > 30:
    functional_penalty = True
  if "free_spots" in payload and _to_float(payload.get("free_spots")) <= 5:
    functional_penalty = True
  if "free_rooms" in payload and _to_float(payload.get("free_rooms")) <= 0:
    functional_penalty = True

  if health_score < 35 or rtt > 180:
    return "UNHEALTHY"
  if health_score < 70 or rtt > 90 or functional_penalty:
    return "DEGRADED"
  return "HEALTHY"


def _format_domain_event_row(event: dict) -> dict:
  ts = event.get("timestamp", 0)
  try:
    ts_value = float(ts)
    time_label = datetime.fromtimestamp(ts_value).strftime("%H:%M:%S")
  except (TypeError, ValueError):
    time_label = "-"

  payload = event.get("payload", {})
  payload_data = payload.get("data", {}) if isinstance(payload, dict) else {}
  summary = "-"
  if isinstance(payload_data, dict) and payload_data:
    keys = sorted(payload_data.keys())
    preview = ", ".join(f"{k}={payload_data[k]}" for k in keys[:3])
    summary = preview if len(keys) <= 3 else f"{preview}, ..."

  event_type = str(event.get("event_type", "-")).replace("domain_", "")

  return {
    "time": time_label,
    "producer_service": str(event.get("producer_service", "-")),
    "event_type": str(event.get("event_type", "-")),
    "event_label": event_type.replace("_", " ").title(),
    "topic": str(event.get("topic", "-")),
    "data_summary": summary,
  }


def _format_platform_event_row(event: dict) -> dict:
  ts = _to_float(event.get("timestamp"), default=0.0)
  time_label = datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else "-"
  return {
    "time": time_label,
    "event_type": str(event.get("event_type", "-")).upper(),
    "service_id": str(event.get("service_id", "-")),
  }


def _format_alert_row(alert: dict) -> dict:
  ts = _to_float(alert.get("timestamp"), default=0.0)
  time_label = datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else "-"
  return {
    "time": time_label,
    "service_id": str(alert.get("service_id", "-")),
    "severity": str(alert.get("severity", "WARN")),
    "reason": str(alert.get("reason", "-")),
  }


def _build_event_flow(domain_events: list) -> list:
  steps = []
  for item in domain_events:
    payload = item.get("payload", {}) if isinstance(item, dict) else {}
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    source = str(data.get("triggered_by", ""))
    target = str(item.get("producer_service", ""))
    if not source or not target:
      continue
    steps.append(
      {
        "source": source,
        "event": str(item.get("event_type", "-")).replace("domain_", ""),
        "target": target,
      }
    )
  return steps[:12]


def _compute_module_cards(modules: dict) -> list:
  cards = []
  for module, rows in sorted(modules.items()):
    if not rows:
      continue

    rtts = []
    health_counts = {"HEALTHY": 0, "DEGRADED": 0, "UNHEALTHY": 0, "OFFLINE": 0}
    heartbeat_times = []
    metric = "-"

    for row in rows:
      data = row.get("raw", {})
      label = _health_label(data)
      health_counts[label] += 1
      if isinstance(data.get("rtt_ms"), (int, float)):
        rtts.append(float(data.get("rtt_ms")))
      heartbeat_times.append(_to_float(data.get("last_heartbeat"), default=0.0))
      if metric == "-" and row.get("metric"):
        metric = row.get("metric")

    dominant = max(health_counts.items(), key=lambda x: x[1])[0]
    cards.append(
      {
        "module": module,
        "health_label": dominant,
        "avg_rtt": round(sum(rtts) / len(rtts), 2) if rtts else 0.0,
        "last_heartbeat": datetime.fromtimestamp(max(heartbeat_times)).strftime("%H:%M:%S") if max(heartbeat_times) > 0 else "-",
        "metric": metric,
      }
    )
  return cards


def build_dashboard_snapshot(
    snapshot: dict,
    alerts: list | None = None,
    alerts_recent: list | None = None,
    domain_events: list | None = None,
    platform_events: list | None = None,
    event_counters: dict | None = None,
    runtime: dict | None = None,
    mqtt: dict | None = None,
    sqlite_overview: dict | None = None,
    historical: dict | None = None,
) -> dict:
    totals = {
        "total": len(snapshot),
        "up": 0,
        "down": 0,
        "avg_rtt": 0.0,
        "max_rtt": 0.0,
        "registered": sum(1 for data in snapshot.values() if data.get("registered")),
        "active_alerts": len(alerts or []),
        "availability_pct": 0.0,
    }

    health_counts = {"HEALTHY": 0, "DEGRADED": 0, "UNHEALTHY": 0, "OFFLINE": 0}
    modules = defaultdict(list)
    rtts = []

    for service_id, data in snapshot.items():
        status = str(data.get("status", "UNKNOWN"))
        if status == "UP":
            totals["up"] += 1
        elif status == "DOWN":
            totals["down"] += 1

        label = _health_label(data)
        health_counts[label] += 1

        rtt = data.get("rtt_ms")
        if isinstance(rtt, (int, float)):
            rtts.append(float(rtt))

        module_name = _module_alias(data.get("module") or data.get("service_type") or "unknown")
        metric = _format_metric(module_name, data.get("service_status", {}))
        modules[module_name].append(
            {
                "service_id": service_id,
                "department": str(data.get("department", "unknown")),
                "status": status,
                "health_score": data.get("health_score", 0),
                "health_label": label,
                "rtt": f"{rtt} ms" if rtt is not None else "-",
                "metric": metric,
                "raw": data,
            }
        )

    if rtts:
        totals["avg_rtt"] = round(sum(rtts) / len(rtts), 2)
        totals["max_rtt"] = round(max(rtts), 2)

    if totals["total"] > 0:
        totals["availability_pct"] = round((totals["up"] / totals["total"]) * 100.0, 2)

    for key in modules:
        modules[key] = sorted(modules[key], key=lambda item: item["service_id"])

    formatted_domain = [_format_domain_event_row(item) for item in (domain_events or [])]
    formatted_platform = [_format_platform_event_row(item) for item in (platform_events or [])]
    alert_rows = [_format_alert_row(item) for item in (alerts_recent or [])]
    event_flow = _build_event_flow(domain_events or [])

    sqlite_info = sqlite_overview or {}
    last_write = _to_float(sqlite_info.get("last_write"), default=0.0)
    sqlite_info["last_write_label"] = datetime.fromtimestamp(last_write).strftime("%H:%M:%S") if last_write else "-"

    hist = historical or {}
    events_by_service = hist.get("events_by_service", {})
    availability_by_service = hist.get("availability_by_service", {})
    service_rows = []
    for service_id in sorted(set(list(events_by_service.keys()) + list(availability_by_service.keys()))):
        service_rows.append(
            {
                "service_id": service_id,
                "events": int(events_by_service.get(service_id, 0)),
                "availability": round(float(availability_by_service.get(service_id, 0.0)), 2),
            }
        )

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "totals": totals,
        "modules": dict(modules),
        "module_cards": _compute_module_cards(dict(modules)),
        "alerts": alerts or [],
        "alerts_recent": alert_rows,
        "domain_events": formatted_domain,
        "platform_events": formatted_platform[:20],
        "event_flow": event_flow,
        "event_counters": event_counters or {
            "events_total": 0,
            "platform_events_total": 0,
            "domain_events_total": 0,
            "events_by_type": {},
            "events_by_service": {},
        },
        "runtime": runtime or {"connected": False, "keys": 0, "counters_active": 0, "registered": 0},
        "mqtt": mqtt
        or {
            "broker_online": False,
            "monitor_connected": False,
            "subscriptions": 0,
            "messages_received": 0,
            "messages_published_estimate": 0,
        },
        "sqlite": sqlite_info,
        "historical": {
            "avg_rtt_24h": round(float(hist.get("avg_rtt_24h", 0.0)), 2),
            "highest_latency_service": hist.get("highest_latency_service", "-"),
            "highest_latency_avg_rtt": round(float(hist.get("highest_latency_avg_rtt", 0.0)), 2),
            "worst_downtime_service": hist.get("worst_downtime_service", "-"),
        },
        "service_stats_rows": service_rows,
        "health_counts": health_counts,
    }


def _select_modules(context_modules: dict, selected_module: str) -> list:
    selected = str(selected_module or "ALL").strip().upper()
    module_names = sorted(context_modules.keys())
    if selected in {"", "ALL"}:
        return module_names
    return [selected] if selected in context_modules else []


def _filter_module_cards(module_cards: list, selected_module: str) -> list:
  selected = str(selected_module or "ALL").strip().upper()
  if selected in {"", "ALL"}:
    return module_cards
  return [card for card in module_cards if str(card.get("module", "")).upper() == selected]


def create_app(store, sqlite_store=None):
    app = Flask(__name__)

    @app.get("/")
    def index():
        selected_module = str(request.args.get("module", "ALL")).strip().upper()
        if hasattr(store, "get_dashboard_summary"):
            summary = store.get_dashboard_summary()
            sqlite_overview = sqlite_store.get_history_overview() if sqlite_store is not None else {}
            historical_stats = sqlite_store.get_observability_stats(hours=24) if sqlite_store is not None else {}
            context = build_dashboard_snapshot(
                summary.get("services", {}),
                summary.get("alerts", []),
                summary.get("alerts_recent", []),
                summary.get("domain_events", []),
                summary.get("platform_events", []),
                summary.get("event_counters", {}),
                summary.get("runtime", {}),
                summary.get("mqtt", {}),
                sqlite_overview,
                historical_stats,
            )
        else:
            context = build_dashboard_snapshot(store.get_snapshot(), [], [], [], [], {}, {}, {}, {}, {})

        context["available_modules"] = ["ALL"] + sorted(context["modules"].keys())
        context["selected_module"] = selected_module
        context["selected_modules"] = _select_modules(context["modules"], selected_module)
        context["module_cards"] = _filter_module_cards(context.get("module_cards", []), selected_module)
        return render_template_string(HTML_TEMPLATE, **context)

    @app.get("/api/summary")
    def api_summary():
        selected_module = str(request.args.get("module", "ALL")).strip().upper()
        if hasattr(store, "get_dashboard_summary"):
            summary = store.get_dashboard_summary()
            sqlite_overview = sqlite_store.get_history_overview() if sqlite_store is not None else {}
            historical_stats = sqlite_store.get_observability_stats(hours=24) if sqlite_store is not None else {}
            context = build_dashboard_snapshot(
                summary.get("services", {}),
                summary.get("alerts", []),
                summary.get("alerts_recent", []),
                summary.get("domain_events", []),
                summary.get("platform_events", []),
                summary.get("event_counters", {}),
                summary.get("runtime", {}),
                summary.get("mqtt", {}),
                sqlite_overview,
                historical_stats,
            )
        else:
            context = build_dashboard_snapshot(store.get_snapshot(), [], [], [], [], {}, {}, {}, {}, {})

        context["selected_module"] = selected_module
        context["selected_modules"] = _select_modules(context["modules"], selected_module)
        context["module_cards"] = _filter_module_cards(context.get("module_cards", []), selected_module)
        return jsonify(context)

    return app


def start_web_dashboard(store, sqlite_store, host: str, port: int, logger):
    app = create_app(store, sqlite_store=sqlite_store)
    logger.info(f"Web dashboard disponivel em http://{host}:{port}")
    app.run(host=host, port=port, debug=False, use_reloader=False)
