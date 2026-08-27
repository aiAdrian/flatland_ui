"""Lightweight HTML/SVG visual components rendered inside Streamlit.

Everything returns an HTML string so it can be dropped into ``st.markdown(...,
unsafe_allow_html=True)``. No external drawing libraries are required.
"""

from __future__ import annotations

from typing import Any

from strategies import strategy_name

# Colour palette (matches the light dashboard style requested).
COLOR_CONFLICT = "#e5484d"      # red
COLOR_PROTECTED = "#30a46c"     # green
COLOR_TRAIN = "#0091ff"         # blue
COLOR_NORMAL = "#8b8d98"        # grey
COLOR_RISK = "#f76b15"          # orange
COLOR_BG = "#f7f9fc"


def _pressure_ratio(pressure: str) -> float:
    return {"LOW": 0.25, "MEDIUM": 0.5, "HIGH": 0.75, "STRESS": 1.0}.get(
        (pressure or "LOW").upper(), 0.25
    )


def pressure_gauge(pressure: str) -> str:
    """A small horizontal bar gauge for operational pressure."""
    ratio = _pressure_ratio(pressure)
    color = {
        "LOW": COLOR_PROTECTED,
        "MEDIUM": COLOR_TRAIN,
        "HIGH": COLOR_RISK,
        "STRESS": COLOR_CONFLICT,
    }.get((pressure or "LOW").upper(), COLOR_NORMAL)
    return f"""
    <div style="font-size:12px;color:#555;margin-bottom:2px;">Operational Pressure</div>
    <div style="background:#e6e8ee;border-radius:6px;height:14px;width:180px;overflow:hidden;">
      <div style="background:{color};height:14px;width:{ratio * 100:.0f}%;"></div>
    </div>
    <div style="font-size:12px;font-weight:600;color:{color};margin-top:2px;">{pressure}</div>
    """


def kpi_badge(label: str, value: str, color: str = COLOR_TRAIN) -> str:
    return f"""
    <span style="display:inline-block;background:{COLOR_BG};border:1px solid #e0e3ea;
      border-radius:8px;padding:6px 10px;margin:3px;">
      <span style="font-size:11px;color:#666;">{label}</span><br>
      <span style="font-size:15px;font-weight:700;color:{color};">{value}</span>
    </span>
    """


def network_svg(
    network: dict[str, Any],
    width: int = 1160,
    height: int = 360,
    animate: bool = True,
    display_height: int = 240,
) -> str:
    """Render a wide corridor map with trains gliding over a long distance.

    Motion is inline SVG SMIL, so trains move smoothly in the browser without
    any Streamlit reruns. Trains travel a long way along the corridor toward the
    conflict node and back; the conflict node pulses. ``display_height`` fixes
    the rendered height (content fit with preserveAspectRatio, never clipped).
    """
    if not network:
        return "<div style='color:#888;'>No network data for this decision.</div>"

    nodes = {n["id"]: n for n in network.get("nodes", [])}
    edges = network.get("edges", [])
    conflict_node = network.get("conflict_node")
    critical_connection = network.get("critical_connection", [])
    trains = network.get("trains", [])
    conflict = nodes.get(conflict_node)

    svg = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{display_height}" '
        f'preserveAspectRatio="xMidYMid meet" '
        f'style="background:{COLOR_BG};border:1px solid #e0e3ea;border-radius:12px;">'
    ]

    # edges: a grey "rail bed" underlay first, then the coloured status overlay
    for edge in edges:
        a = nodes.get(edge.get("from"))
        b = nodes.get(edge.get("to"))
        if not a or not b:
            continue
        svg.append(
            f'<line x1="{a["x"]}" y1="{a["y"]}" x2="{b["x"]}" y2="{b["y"]}" '
            f'stroke="#cdd2dc" stroke-width="9" stroke-linecap="round"/>'
        )
    for edge in edges:
        a = nodes.get(edge.get("from"))
        b = nodes.get(edge.get("to"))
        if not a or not b:
            continue
        color, w, dash = COLOR_NORMAL, 4, ""
        status = edge.get("status")
        if status == "conflict":
            color, w = COLOR_CONFLICT, 8
        elif status == "protected":
            color, w = COLOR_PROTECTED, 8
        elif status == "risk":
            color, w, dash = COLOR_TRAIN, 6, 'stroke-dasharray="10 7"'
        svg.append(
            f'<line x1="{a["x"]}" y1="{a["y"]}" x2="{b["x"]}" y2="{b["y"]}" '
            f'stroke="{color}" stroke-width="{w}" stroke-linecap="round" {dash}/>'
        )

    # nodes (stations / junctions)
    for node in nodes.values():
        is_conflict = node["id"] == conflict_node
        color = COLOR_CONFLICT if is_conflict else "#6b7280"
        r = 16 if is_conflict else 11
        if is_conflict and animate:
            svg.append(
                f'<circle cx="{node["x"]}" cy="{node["y"]}" r="{r}" '
                f'fill="{COLOR_CONFLICT}" opacity="0.3">'
                f'<animate attributeName="r" values="{r};{r + 22};{r}" '
                f'dur="1.6s" repeatCount="indefinite"/>'
                f'<animate attributeName="opacity" values="0.4;0;0.4" '
                f'dur="1.6s" repeatCount="indefinite"/></circle>'
            )
        svg.append(
            f'<circle cx="{node["x"]}" cy="{node["y"]}" r="{r}" fill="{color}" '
            f'stroke="#fff" stroke-width="3"/>'
        )
        label = node.get("label", node["id"])
        svg.append(
            f'<text x="{node["x"]}" y="{node["y"] - 22}" font-size="17" '
            f'font-weight="600" text-anchor="middle" fill="#333">{label}</text>'
        )
        if is_conflict:
            svg.append(
                f'<text x="{node["x"]}" y="{node["y"] + 34}" font-size="14" '
                f'text-anchor="middle" fill="{COLOR_CONFLICT}" '
                f'font-weight="700">⚠ Conflict</text>'
            )

    # trains: flow in ONE direction toward the problem (no left-right jitter).
    # A fade at the loop boundary hides the reset so motion reads as forward travel.
    for i, train in enumerate(trains):
        tid = train.get("id", "")
        color = COLOR_TRAIN
        if train.get("broken"):
            color = COLOR_CONFLICT
        elif tid in critical_connection:
            color = COLOR_PROTECTED
        elif train.get("risk"):
            color = COLOR_RISK
        x, y = train.get("x", 0), train.get("y", 0)

        if conflict:
            dx = (conflict["x"] - x) * 0.75
            dy = (conflict["y"] - y) * 0.75
        else:
            dx, dy = 180, 0
        dist = max(1.0, (dx ** 2 + dy ** 2) ** 0.5)
        dur = max(3.5, min(9.0, dist / 22.0)) + (i % 3) * 0.5

        anim = ""
        if animate:
            anim = (
                f'<animateTransform attributeName="transform" type="translate" '
                f'values="0 0; {dx:.0f} {dy:.0f}" dur="{dur:.1f}s" '
                f'calcMode="spline" keyTimes="0;1" keySplines="0.3 0 0.7 1" '
                f'repeatCount="indefinite"/>'
                f'<animate attributeName="opacity" values="0;1;1;0" '
                f'keyTimes="0;0.12;0.82;1" dur="{dur:.1f}s" repeatCount="indefinite"/>'
            )
        label = train.get("label", tid)
        status_txt = train.get("status", "")
        svg.append(
            f'<g>{anim}'
            f'<rect x="{x - 17}" y="{y - 12}" width="34" height="24" rx="6" '
            f'fill="{color}" stroke="#fff" stroke-width="2"/>'
            f'<text x="{x}" y="{y + 5}" font-size="13" font-weight="700" '
            f'text-anchor="middle" fill="#fff">{label}</text>'
            + (
                f'<text x="{x}" y="{y + 30}" font-size="12" text-anchor="middle" '
                f'fill="#666">{status_txt}</text>'
                if status_txt
                else ""
            )
            + "</g>"
        )

    # projected follow-up conflicts (from a what-if strategy preview)
    for pc in network.get("projected_conflicts", []):
        node = nodes.get(pc)
        if not node:
            continue
        svg.append(
            f'<circle cx="{node["x"]}" cy="{node["y"]}" r="14" fill="none" '
            f'stroke="{COLOR_RISK}" stroke-width="3" stroke-dasharray="4 3">'
            f'<animate attributeName="r" values="14;24;14" dur="1.4s" '
            f'repeatCount="indefinite"/></circle>'
            f'<text x="{node["x"]}" y="{node["y"] + 48}" font-size="12" '
            f'text-anchor="middle" fill="{COLOR_RISK}" font-weight="600">'
            f'⚠ projected follow-up</text>'
        )

    # legend (mockup wording)
    legend = [
        (COLOR_CONFLICT, "Conflict", False),
        (COLOR_PROTECTED, "Protected connection", False),
        (COLOR_TRAIN, "Limited delay propagation", True),
        (COLOR_NORMAL, "Normal operation", False),
    ]
    lx = 18
    ly = height - 14
    for color, text, dashed in legend:
        if dashed:
            svg.append(
                f'<line x1="{lx}" y1="{ly - 5}" x2="{lx + 22}" y2="{ly - 5}" '
                f'stroke="{color}" stroke-width="4" stroke-dasharray="7 5"/>'
            )
        else:
            svg.append(
                f'<rect x="{lx}" y="{ly - 12}" width="18" height="11" rx="2" '
                f'fill="{color}"/>'
            )
        svg.append(
            f'<text x="{lx + 28}" y="{ly - 2}" font-size="14" fill="#555">{text}</text>'
        )
        lx += 58 + len(text) * 7.6

    svg.append("</svg>")
    return "".join(svg)


def forecast_table(forecast: dict[str, Any]) -> str:
    """Render the 'Strategy Impact Forecast' table with coloured state chips."""
    columns = forecast.get("columns", [])
    rows = forecast.get("rows", [])
    conf_color = {"high": COLOR_PROTECTED, "medium": COLOR_RISK, "lower": COLOR_TRAIN,
                  "unknown": COLOR_NORMAL}

    head = "<th style='text-align:left;padding:6px 8px;'></th>"
    for col in columns:
        c = conf_color.get(col.get("confidence"), COLOR_NORMAL)
        sub = f"<div style='font-size:10px;color:#888;'>{col.get('sub','')}</div>" if col.get("sub") else ""
        head += (
            f"<th style='padding:6px 8px;text-align:center;color:{c};font-size:12px;'>"
            f"{col['label']}{sub}</th>"
        )

    body = ""
    for row in rows:
        cells = (
            f"<td style='padding:6px 8px;font-size:12px;color:#333;'>"
            f"{row.get('icon','')} {row['label']}</td>"
        )
        for cell in row["cells"]:
            cells += (
                f"<td style='padding:6px 8px;text-align:center;'>"
                f"<span style='background:{cell['color']}22;color:{cell['color']};"
                f"border-radius:6px;padding:2px 8px;font-size:12px;font-weight:600;'>"
                f"{cell['text']}</span></td>"
            )
        body += f"<tr>{cells}</tr>"
        # the derivation behind this row -- answers "why this value"
        if row.get("driver"):
            body += (
                f"<tr><td colspan='{len(columns) + 1}' style='padding:0 8px 6px 20px;"
                f"font-size:11px;color:#777;border-bottom:1px solid #f0f1f4;'>"
                f"↳ {row['driver']}</td></tr>"
            )

    open_problems = forecast.get("open_problems", 0)
    horizon = forecast.get("horizon_min", 30)
    if horizon >= 30:
        horizon_txt = (f"🔮 Forecast reliable to +{horizon} min · "
                       f"{open_problems} open problem(s) — the future is predictable, "
                       f"good time to stabilise.")
        horizon_color = COLOR_PROTECTED
    else:
        horizon_txt = (f"🔮 Forecast reliable only to "
                       f"{'now' if horizon == 0 else f'+{horizon} min'} · "
                       f"{open_problems} open problem(s) — the future is getting "
                       f"uncertain. Stabilising decisions widen this horizon again.")
        horizon_color = COLOR_RISK if horizon > 0 else COLOR_CONFLICT
    assumptions = forecast.get("assumptions") or []
    assumptions_html = (
        "<div style='font-size:11px;color:#888;margin-top:4px;'>Model: "
        + " · ".join(assumptions)
        + "</div>"
        if assumptions
        else ""
    )
    legend = (
        f"<div style='font-size:12px;color:{horizon_color};font-weight:600;"
        f"margin-top:6px;'>{horizon_txt}</div>"
        f"{assumptions_html}"
        f"<div style='font-size:11px;color:#777;'>Confidence: "
        f"<span style='color:{COLOR_PROTECTED};'>■ High</span> "
        f"<span style='color:{COLOR_RISK};'>■ Medium</span> "
        f"<span style='color:{COLOR_TRAIN};'>▪ Lower</span> "
        f"<span style='color:{COLOR_NORMAL};'>▪ Unknown</span></div>"
    )
    return (
        "<table style='width:100%;border-collapse:collapse;background:#fff;"
        "border:1px solid #e0e3ea;border-radius:8px;'>"
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>{legend}"
    )


def pattern_bars(pattern: dict[str, Any], selected_strategy: str | None = None) -> str:
    """Render the 'YOUR DECISION PATTERN' bar chart."""
    counts = pattern.get("counts", {})
    total = sum(counts.values())
    if total == 0:
        return "<div style='color:#888;'>Not enough history for a pattern yet.</div>"

    rows = []
    for strat, count in sorted(counts.items(), key=lambda kv: kv[1], reverse=True):
        pct = count / total * 100
        filled = int(round(pct / 100 * 20))
        bar = "█" * filled + "░" * (20 - filled)
        highlight = "font-weight:700;" if strat == selected_strategy else ""
        rows.append(
            f'<div style="font-family:monospace;font-size:13px;{highlight}">'
            f'{strategy_name(strat):<28}<span style="color:{COLOR_TRAIN};">{bar}</span>'
            f' {pct:.0f}%</div>'
        )
    return (
        "<div style='font-size:12px;color:#666;margin-bottom:4px;'>"
        f"Based on {total} similar situation(s)</div>" + "".join(rows)
    )


def timeline(moments: list[dict[str, Any]]) -> str:
    """Render a compact session timeline of reflection moments."""
    if not moments:
        return "<div style='color:#888;'>No moments to show.</div>"

    label_map = {
        "pattern_deviation": ("Pattern deviation", COLOR_RISK),
        "pattern_confirmation": ("Pattern confirmed", COLOR_PROTECTED),
        "unexpected_outcome": ("Unexpected outcome", COLOR_CONFLICT),
        "learning_adjusted": ("Learning-adjusted", COLOR_TRAIN),
        "override": ("Override", COLOR_RISK),
        "quick_accept_pattern": ("Quick accepts", COLOR_NORMAL),
    }
    items = []
    for m in moments:
        ep = m["episode"]
        ctx = ep.get("context", {})
        time_label = ctx.get("time_label", "")
        strat = strategy_name(ep.get("user_decision", {}).get("selected_strategy"))
        tag, color = label_map.get(m["case_type"], (m["case_type"], COLOR_NORMAL))
        # why this moment was picked -- the selector already scores this, so show it
        reasons = m.get("reasons") or []
        reason_txt = " · ".join(reasons) if reasons else ""
        sample = (m.get("pattern") or {}).get("sample_size", 0)
        basis_txt = (
            f" — compared against {sample} similar earlier decision(s)"
            if sample
            else " — no comparable earlier decision yet"
        )
        items.append(
            f'<div style="display:flex;align-items:flex-start;margin:6px 0;">'
            f'<div style="width:52px;font-weight:600;color:#333;">{time_label}</div>'
            f'<div style="flex:1;padding-left:10px;border-left:3px solid {color};">'
            f'<div style="font-weight:600;">{strat}</div>'
            f'<div style="font-size:12px;color:{color};">{tag}</div>'
            f'<div style="font-size:11px;color:#777;">Selected because: '
            f'{reason_txt}{basis_txt}</div></div></div>'
        )
    return "".join(items)


def preference_panel(preferences: list, sample_size: int) -> str:
    """Render the persistent 'How I see you' belief panel with confidence bars."""
    if not preferences:
        return (
            "<div style='color:#888;font-size:13px;'>No decisions yet — I don't have "
            "a picture of your preferences.</div>"
        )
    rows = []
    for strat, weight, count in preferences:
        pct = weight * 100
        # NOTE: keep this HTML on single lines — leading indentation makes
        # Streamlit's markdown treat it as a code block and show raw tags.
        rows.append(
            f"<div style='margin:5px 0;'>"
            f"<div style='font-size:12px;display:flex;justify-content:space-between;'>"
            f"<span>{strategy_name(strat)}</span><span>{pct:.0f}%</span></div>"
            f"<div style='background:#e6e8ee;border-radius:5px;height:9px;'>"
            f"<div style='background:{COLOR_TRAIN};height:9px;border-radius:5px;"
            f"width:{pct:.0f}%;'></div></div></div>"
        )
    return (
        f"<div style='font-size:11px;color:#666;margin-bottom:4px;'>"
        f"Based on {sample_size} decision(s) this session</div>" + "".join(rows)
    )


def prediction_card(predicted_name: str, confidence: float, basis: str) -> str:
    """Render the AI's pre-decision bet on what the operator will choose."""
    basis_txt = {
        "similar_context": "based on similar situations you've handled",
        "overall_preference": "based on your overall tendency so far",
        "cold_start": "",
    }.get(basis, "")
    conf_pct = f"{int(confidence * 100)}%" if confidence else ""
    return f"""
    <div style="border:1px dashed {COLOR_TRAIN};border-radius:10px;padding:10px 12px;
         background:#eef6ff;margin-bottom:8px;">
      <span style="font-size:13px;color:#555;">🔮 My prediction</span><br>
      <span style="font-size:16px;font-weight:700;color:{COLOR_TRAIN};">
        I think you'll choose: {predicted_name}</span>
      <span style="font-size:12px;color:#666;"> &nbsp;{conf_pct} confidence</span>
      <div style="font-size:12px;color:#777;margin-top:2px;">{basis_txt}</div>
    </div>
    """


def prediction_reveal(predicted_name: str, actual_name: str, correct: bool) -> str:
    """Render the hit/miss reveal after a decision is committed."""
    if predicted_name in (None, "-", ""):
        return ""
    if correct:
        return (
            f"<div style='color:{COLOR_PROTECTED};font-weight:700;margin:6px 0;'>"
            f"🔮 I predicted <b>{predicted_name}</b> — and you did. "
            f"I'm getting to know you.</div>"
        )
    return (
        f"<div style='color:{COLOR_RISK};font-weight:700;margin:6px 0;'>"
        f"🔮 I predicted <b>{predicted_name}</b>, but you chose "
        f"<b>{actual_name}</b>. Noted — I'll update my picture of you.</div>"
    )


def fmt_passengers(n: int) -> str:
    """Passenger counts are estimates from typical train loads — show them as
    rounded approximations, never false-precise exact figures."""
    n = int(n or 0)
    if n == 0:
        return "~0"
    rounded = int(round(n / 10.0)) * 10
    return f"~{rounded}"


def kpi_strip(kpis: dict[str, Any]) -> str:
    """Continuously-accumulating shift KPIs shown during live mode."""
    net = str(kpis.get("network_state", "stable")).lower()
    net_color = {"stable": COLOR_PROTECTED, "strained": COLOR_RISK,
                 "unstable": COLOR_CONFLICT}.get(net, COLOR_NORMAL)
    open_problems = kpis.get("open_problems", 0)
    op_color = COLOR_PROTECTED if open_problems <= 1 else (
        COLOR_RISK if open_problems == 2 else COLOR_CONFLICT)
    items = [
        ("Open problems", str(open_problems), op_color),
        ("Added delay", f"{kpis.get('added_delay_min', 0)} min", COLOR_RISK),
        ("Connections kept", str(kpis.get("connections_kept", 0)), COLOR_PROTECTED),
        ("Connections lost", str(kpis.get("connections_lost", 0)), COLOR_CONFLICT),
        ("Passengers (est.)", fmt_passengers(kpis.get("passengers_affected", 0)),
         COLOR_CONFLICT),
        ("Follow-up conflicts", str(kpis.get("follow_up_conflicts", 0)), COLOR_RISK),
        ("Network", net.capitalize(), net_color),
        ("Deferred to AI", str(kpis.get("deferrals", 0)), COLOR_TRAIN),
    ]
    cells = "".join(
        f"<div style='flex:1;text-align:center;'>"
        f"<div style='font-size:11px;color:#888;'>{label}</div>"
        f"<div style='font-size:18px;font-weight:800;color:{color};'>{value}</div>"
        f"</div>"
        for label, value, color in items
    )
    return (
        f"<div style='display:flex;gap:6px;background:#fff;border:1px solid #e0e3ea;"
        f"border-radius:10px;padding:8px 10px;'>{cells}</div>"
    )


def countdown_bar(remaining_s: float, total_s: float, lead_min: float | None = None) -> str:
    """A shrinking, colour-shifting deadline bar for live decisions.

    ``lead_min`` is the diegetic lead time (simulated minutes until the train
    reaches the decision point) — the realistic quantity; the seconds are the
    compressed on-screen budget.
    """
    ratio = max(0.0, min(1.0, remaining_s / total_s)) if total_s else 0.0
    color = COLOR_PROTECTED if ratio > 0.5 else (COLOR_RISK if ratio > 0.25 else COLOR_CONFLICT)
    lead = (f"~{lead_min:.0f} min until the train reaches the decision point"
            if lead_min else "limited lead time")
    return (
        f"<div style='margin:4px 0;'>"
        f"<div style='display:flex;justify-content:space-between;font-size:12px;'>"
        f"<span style='color:{color};font-weight:700;'>⏳ {lead}</span>"
        f"<span style='color:#888;'>after that the AI acts by default "
        f"({remaining_s:.0f}s on screen)</span></div>"
        f"<div style='background:#e6e8ee;border-radius:6px;height:12px;overflow:hidden;'>"
        f"<div style='background:{color};height:12px;width:{ratio * 100:.0f}%;"
        f"transition:width 0.3s linear;'></div></div></div>"
    )


def event_banner(event: dict[str, Any] | None, big: bool = True) -> str:
    """A short trigger announcement (e.g. 'Track blocked', 'Train delayed')."""
    if not event:
        return ""
    kind = event.get("kind", "conflict")
    icon = event.get("icon", "⚠️")
    text = event.get("text", "")
    color = {
        "track_blocked": COLOR_CONFLICT,
        "disruption": COLOR_CONFLICT,
        "train_delayed": COLOR_RISK,
        "connection_risk": COLOR_PROTECTED,
        "conflict": COLOR_RISK,
    }.get(kind, COLOR_RISK)
    label = kind.replace("_", " ").upper()
    if big:
        return (
            f"<div style='display:flex;align-items:center;gap:10px;"
            f"background:{color}14;border-left:6px solid {color};border-radius:8px;"
            f"padding:8px 12px;margin-bottom:6px;'>"
            f"<span style='font-size:22px;'>{icon}</span>"
            f"<span><span style='color:{color};font-weight:800;font-size:12px;'>"
            f"{label}</span><br><span style='font-weight:600;'>{text}</span></span>"
            f"</div>"
        )
    return (
        f"<span style='color:{color};font-weight:600;'>{icon} {text}</span>"
    )


def attention_feed(feed: list[dict[str, Any]]) -> str:
    """A streaming log of what the AI handled autonomously vs. your decisions."""
    if not feed:
        return (
            "<div style='color:#888;font-size:12px;'>No activity yet — the AI is "
            "monitoring.</div>"
        )
    rows = []
    for item in feed:
        by = item.get("by", "AI")
        color = COLOR_TRAIN if by == "You" else (
            COLOR_RISK if "defer" in by.lower() else COLOR_NORMAL
        )
        mark = "🧑 You" if by == "You" else ("🤝 " + by if "defer" in by.lower()
                                             else "🤖 AI")
        rows.append(
            f"<div style='display:flex;gap:8px;font-size:12px;margin:3px 0;'>"
            f"<span style='color:#999;width:44px;'>{item.get('time_label','')}</span>"
            f"<span style='color:{color};font-weight:600;width:78px;'>{mark}</span>"
            f"<span style='flex:1;color:#444;'>{item.get('text','')} "
            f"<span style='color:#888;'>→ {item.get('strategy','')}</span></span></div>"
        )
    return (
        "<div style='border:1px solid #e0e3ea;border-radius:10px;padding:8px 10px;"
        "background:#fff;max-height:170px;overflow:auto;'>"
        "<div style='font-size:11px;color:#888;font-weight:700;margin-bottom:4px;'>"
        "ATTENTION FEED</div>" + "".join(rows) + "</div>"
    )


def projected_network(
    network: dict[str, Any],
    effects: dict[str, Any],
    expected: dict[str, Any],
) -> dict[str, Any]:
    """Return a copy of the network showing the projected consequences of a
    chosen strategy: connection protected/broken, delay propagation downstream,
    and any projected follow-up conflict node."""
    import copy

    net = {
        "nodes": network.get("nodes", []),
        "edges": [dict(e) for e in network.get("edges", [])],
        "trains": [dict(t) for t in network.get("trains", [])],
        "conflict_node": network.get("conflict_node"),
        "critical_connection": list(network.get("critical_connection", [])),
        "projected_conflicts": [],
    }
    nodes = {n["id"]: n for n in net["nodes"]}
    conflict = nodes.get(net["conflict_node"])
    conflict_x = conflict["x"] if conflict else 0

    conn = str(expected.get("connection", effects.get("connection_impact", ""))).lower()
    ripple = str(effects.get("ripple_risk", "")).lower()
    follow = int(expected.get("follow_up_conflicts", 0) or 0)
    protected = conn in ("protected", "kept", "excellent")
    broken = conn == "broken"

    # classify edges downstream of the conflict (toward the east / the problem)
    for e in net["edges"]:
        a, b = nodes.get(e["from"]), nodes.get(e["to"])
        if not a or not b:
            continue
        downstream = (a["x"] >= conflict_x - 1) and (b["x"] >= conflict_x - 1)
        touches_conflict = net["conflict_node"] in (e["from"], e["to"])
        if downstream or touches_conflict:
            if protected:
                e["status"] = "protected"
            elif broken:
                e["status"] = "conflict"
            elif ripple in ("medium", "high"):
                e["status"] = "risk"  # rendered as delay-propagation (blue dashed)

    # critical-connection trains reflect the connection outcome
    for t in net["trains"]:
        if t.get("id") in net["critical_connection"]:
            if broken:
                t["broken"] = True
    if broken:
        net["critical_connection"] = []

    # projected follow-up conflict: flag the easternmost downstream node
    if follow > 0:
        downstream_nodes = [n for n in net["nodes"] if n["x"] > conflict_x + 1]
        if downstream_nodes:
            target = max(downstream_nodes, key=lambda n: n["x"])
            net["projected_conflicts"].append(target["id"])

    return net


def relationship_panel(episodes: list[dict[str, Any]]) -> str:
    """Live operator–AI 'relationship' stats: how well the AI predicts you, and
    how deliberate your decisions are (over-reliance signal). Single-line HTML."""
    predicted = [
        e for e in episodes
        if e.get("user_decision", {}).get("interaction", {}).get("predicted_strategy")
    ]
    hits = sum(
        1 for e in predicted
        if e["user_decision"]["interaction"].get("prediction_correct")
    )
    deliberate = sum(
        1 for e in episodes
        if e.get("user_decision", {}).get("confirmation_mode")
        in ("reasoned_accept", "manual_override", "informed_accept")
    )
    passive = sum(
        1 for e in episodes
        if e.get("user_decision", {}).get("confirmation_mode")
        in ("quick_accept", "deferred_to_ai")
    )
    total_eng = deliberate + passive

    parts = []
    if predicted:
        rate = hits / len(predicted) * 100
        col = COLOR_PROTECTED if rate >= 60 else (COLOR_RISK if rate >= 30 else COLOR_CONFLICT)
        parts.append(
            f"<div style='font-size:12px;color:#555;margin-top:8px;'>How well I "
            f"predict you</div>"
            f"<div style='font-size:18px;font-weight:800;color:{col};'>{rate:.0f}% "
            f"<span style='font-size:11px;color:#888;'>({hits}/{len(predicted)})</span>"
            f"</div>"
        )
    if total_eng:
        dp_ = deliberate / total_eng * 100
        pp_ = passive / total_eng * 100
        parts.append(
            f"<div style='font-size:12px;color:#555;margin-top:6px;'>Engagement</div>"
            f"<div style='display:flex;height:16px;border-radius:5px;overflow:hidden;"
            f"border:1px solid #e0e3ea;'>"
            f"<div style='width:{dp_:.0f}%;background:{COLOR_PROTECTED};'></div>"
            f"<div style='width:{pp_:.0f}%;background:{COLOR_RISK};'></div></div>"
            f"<div style='font-size:11px;color:#888;'>{deliberate} deliberate · "
            f"{passive} passive</div>"
        )
    return "".join(parts)
