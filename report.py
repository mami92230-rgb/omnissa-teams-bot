#!/usr/bin/env python3
"""Omnissa Intelligence > Teams : distribution iOS iPads - version compacte."""

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
    """Tri par numero de version decroissant (26.x avant 18.x)."""
    try:
        return tuple(int(x) for x in v.split("."))
    except (ValueError, AttributeError):
        return (0,)


def build_chart_url(sorted_v, total):
    top = sorted_v[:8]
    others = sum(c for _, c in sorted_v[8:])
    if others > 0:
        top.append(("Autres", others))
    labels = [f"{v} ({round(c/total*100,1)}%)" for v, c in top]
    chart_config = {
        "type": "doughnut",
        "data": {"labels": labels, "datasets": [{"data": [c for _, c in top],
            "backgroundColor": ["#0078D4","#00BCF2","#FFB900","#E74856","#744DA9","#10893E","#FF8C00","#E3008C","#B4B4B4"],
            "borderWidth": 2, "borderColor": "#fff"}]},
        "options": {"plugins": {
            "legend": {"position": "right", "labels": {"font": {"size": 14}, "padding": 14, "usePointStyle": True}},
            "datalabels": {"display": True, "color": "#fff", "font": {"size": 14, "weight": "bold"},
                "formatter": "(val, ctx) => (val / ctx.chart.getDatasetMeta(0).total * 100).toFixed(1) + '%'"}
        }}
    }
    resp = http("https://quickchart.io/chart/create", "POST",
        {"Content-Type": "application/json"},
        json.dumps({"chart": chart_config, "width": 800, "height": 400, "backgroundColor": "white", "format": "png", "devicePixelRatio": 2}))
    return resp.get("url", "")


def build_card(chart_url, sorted_v, total):
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    # Top 5 versions (triees par version desc = 26.x en premier)
    top5_lines = []
    for i, (v, c) in enumerate(sorted_v[:5]):
        top5_lines.append(f"{i+1}. **{v}** — {c} ({round(c/total*100,1)}%)")
    top5_text = "\n\n".join(top5_lines)

    others_count = sum(c for _, c in sorted_v[5:])
    others_nb = len(sorted_v) - 5
    summary = f"+ {others_nb} autres : {others_count} iPads ({round(others_count/total*100,1)}%)"

    body = [
        {"type": "TextBlock", "text": f"**iPads - Distribution iOS** | {total} iPads | {now}", "wrap": True, "size": "Medium"},
    ]
    if chart_url:
        body.append({"type": "Image", "url": chart_url, "size": "Stretch"})
    body.append({"type": "TextBlock", "text": top5_text, "wrap": True, "size": "Small", "spacing": "Small"})
    body.append({"type": "TextBlock", "text": summary, "isSubtle": True, "size": "Small", "spacing": "None"})

    return {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "contentUrl": None,
        "content": {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard", "version": "1.5", "body": body}}]}


def main():
    token = get_token()
    versions = get_versions(token)
    # Tri par version decroissante (26.x en premier)
    sorted_v = sorted(versions.items(), key=lambda x: version_key(x[0]), reverse=True)
    total = sum(versions.values())
    print(f"[OK] {total} iPads, {len(versions)} versions")
    chart_url = build_chart_url(sorted_v, total)
    card = build_card(chart_url, sorted_v, total)
    http(TEAMS_WEBHOOK, "POST", {"Content-Type": "application/json"}, json.dumps(card))
    print("[DONE] Envoye sur Teams")


if __name__ == "__main__":
    main()
