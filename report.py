#!/usr/bin/env python3
"""Omnissa Intelligence > Teams : versions iPadOS 26 uniquement."""

import os, json, urllib.request, base64
from datetime import datetime, timezone

TOKEN_URL    = "https://auth.eu1.data.workspaceone.com/oauth/token"
API_BASE     = "https://api.eu1.data.workspaceone.com"
CLIENT_ID    = os.environ["OMNISSA_CLIENT_ID"]
CLIENT_SECRET = os.environ["OMNISSA_CLIENT_SECRET"]
TEAMS_WEBHOOK = os.environ["TEAMS_WEBHOOK_URL"]
REPORT_ID    = os.environ["OMNISSA_REPORT_ID"]
TREND_ID     = os.environ.get("OMNISSA_TREND_ID", "")


def http(url, method="GET", headers=None, body=None):
    req = urllib.request.Request(url, method=method, headers=headers or {})
    if body:
        req.data = body if isinstance(body, bytes) else body.encode()
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def get_token():
    creds = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    return http(TOKEN_URL, "POST",
        {"Content-Type": "application/x-www-form-urlencoded",
         "Authorization": f"Basic {creds}"},
        "grant_type=client_credentials")["access_token"]


def get_versions_trend(token):
    url = f"{API_BASE}/v2/async/query/trend/{TREND_ID}"
    resp = http(url, "GET", {"Authorization": f"Bearer {token}", "Accept": "application/json"})
    data = resp.get("data", resp)
    first_key = list(data.keys())[0]
    versions = {}
    for r in data[first_key]["trend"]["trend_results"]:
        versions[r["bucketing_attributes"][0]["value"]] = r["counters"][0]["result"]["value"]
    return versions


def get_versions_preview(token):
    import time
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    versions, offset, total = {}, 0, None
    while True:
        resp = http(f"{API_BASE}/v2/reports/{REPORT_ID}/preview?page_size=100&offset={offset}", "GET", headers)
        data = resp.get("data", resp)
        results = data.get("results", [])
        if total is None:
            total = data.get("total_count", 0)
        for d in results:
            v = d.get("airwatch.device.device_os_version", "?")
            versions[v] = versions.get(v, 0) + 1
        offset += 100
        if offset >= total or not results:
            break
        time.sleep(0.15)
    return versions


def get_versions(token):
    if TREND_ID:
        try:
            return get_versions_trend(token)
        except Exception:
            pass
    return get_versions_preview(token)


def version_key(v):
    try:
        return tuple(int(x) for x in v.split("."))
    except (ValueError, AttributeError):
        return (0,)


def build_chart_url(v26, total_fleet):
    """Bar chart horizontal des versions 26.x."""
    # Trier par version croissante pour le bar chart
    v26_sorted = sorted(v26, key=lambda x: version_key(x[0]))
    labels = [v for v, _ in v26_sorted]
    data = [c for _, c in v26_sorted]
    chart_config = {
        "type": "horizontalBar",
        "data": {"labels": labels, "datasets": [{"label": "iPads",
            "data": data,
            "backgroundColor": "#0078D4",
            "borderRadius": 4}]},
        "options": {
            "plugins": {
                "legend": {"display": False},
                "datalabels": {"display": True, "anchor": "end", "align": "right",
                    "font": {"size": 14, "weight": "bold"}, "color": "#333",
                    "formatter": "(val) => val"}
            },
            "scales": {
                "xAxes": [{"ticks": {"beginAtZero": True, "font": {"size": 13}}}],
                "yAxes": [{"ticks": {"font": {"size": 14}}}]
            }
        }
    }
    resp = http("https://quickchart.io/chart/create", "POST",
        {"Content-Type": "application/json"},
        json.dumps({"chart": chart_config, "width": 900, "height": 500, "backgroundColor": "white", "format": "png", "devicePixelRatio": 2}))
    return resp.get("url", "")


def build_card(chart_url, v26, total_fleet):
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    total_v26 = sum(c for _, c in v26)
    pct_v26 = round(total_v26 / total_fleet * 100, 1) if total_fleet else 0
    non_v26 = total_fleet - total_v26

    # Liste toutes les versions 26.x triees par version desc
    lines = []
    for v, c in sorted(v26, key=lambda x: version_key(x[0]), reverse=True):
        pct = round(c / total_fleet * 100, 1)
        lines.append(f"**{v}** : {c} iPads ({pct}%)")
    text_versions = "\n\n".join(lines)

    body = [
        {"type": "TextBlock", "text": f"**iPadOS 26 — Suivi deploiement** | {now}", "wrap": True, "size": "Medium"},
        {"type": "TextBlock", "text": f"**{total_v26}** iPads sur iPadOS 26 / {total_fleet} total ({pct_v26}%) — {non_v26} restants", "wrap": True, "size": "Small", "spacing": "Small"},
    ]
    if chart_url:
        body.append({"type": "Image", "url": chart_url, "size": "Stretch", "spacing": "Small"})
    body.append({"type": "TextBlock", "text": text_versions, "wrap": True, "size": "Small", "spacing": "Small"})

    return {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "contentUrl": None,
        "content": {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard", "version": "1.5", "body": body}}]}


def main():
    token = get_token()
    all_versions = get_versions(token)
    total_fleet = sum(all_versions.values())

    # Filtrer uniquement 26.x
    v26 = [(v, c) for v, c in all_versions.items() if v.startswith("26.")]
    v26.sort(key=lambda x: version_key(x[0]), reverse=True)

    print(f"[OK] Flotte: {total_fleet} iPads, {len(all_versions)} versions totales")
    print(f"[OK] Versions 26.x trouvees: {len(v26)}")
    for v, c in v26:
        print(f"  {v}: {c}")

    if not v26:
        print("[WARN] Aucune version 26.x trouvee!")
        return

    chart_url = build_chart_url(v26, total_fleet)
    card = build_card(chart_url, v26, total_fleet)
    http(TEAMS_WEBHOOK, "POST", {"Content-Type": "application/json"}, json.dumps(card))
    print("[DONE] Envoye sur Teams")


if __name__ == "__main__":
    main()
