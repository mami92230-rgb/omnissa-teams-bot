#!/usr/bin/env python3
"""Omnissa Intelligence > Teams : distribution iOS iPads."""

import os, json, urllib.request, urllib.parse, base64
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
    data = http(TOKEN_URL, "POST",
        {"Content-Type": "application/x-www-form-urlencoded",
         "Authorization": f"Basic {creds}"},
        "grant_type=client_credentials")
    print("[OK] Token obtenu")
    return data["access_token"]


# -- Methode 1 : Trend endpoint (1 seul appel, donnees agregees) --
def get_versions_trend(token):
    if not TREND_ID:
        raise Exception("TREND_ID non configure")
    url = f"{API_BASE}/v2/async/query/trend/{TREND_ID}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    resp = http(url, "GET", headers)
    data = resp.get("data", resp)
    first_key = list(data.keys())[0]
    trend_results = data[first_key]["trend"]["trend_results"]
    versions = {}
    for r in trend_results:
        version = r["bucketing_attributes"][0]["value"]
        count = r["counters"][0]["result"]["value"]
        versions[version] = count
    print(f"[OK] Trend: {len(versions)} versions, {sum(versions.values())} iPads")
    return versions


# -- Methode 2 : Preview pagine (fallback) --
def get_versions_preview(token):
    import time
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    versions = {}
    offset = 0
    total = None
    while True:
        url = f"{API_BASE}/v2/reports/{REPORT_ID}/preview?page_size=100&offset={offset}"
        resp = http(url, "GET", headers)
        data = resp.get("data", resp)
        results = data.get("results", [])
        if total is None:
            total = data.get("total_count", 0)
            print(f"[OK] Preview: {total} devices a paginer")
        for d in results:
            v = d.get("airwatch.device.device_os_version", "Inconnu")
            versions[v] = versions.get(v, 0) + 1
        offset += 100
        if offset >= total or not results:
            break
        time.sleep(0.15)
    print(f"[OK] Preview: {len(versions)} versions, {sum(versions.values())} iPads")
    return versions


def get_versions(token):
    if TREND_ID:
        try:
            return get_versions_trend(token)
        except Exception as e:
            print(f"[WARN] Trend echoue ({e}), fallback preview...")
    return get_versions_preview(token)


# -- Camembert via QuickChart POST (haute resolution) --
def build_chart_url(versions):
    sorted_v = sorted(versions.items(), key=lambda x: -x[1])
    total = sum(versions.values())

    top = sorted_v[:8]
    others = sum(c for _, c in sorted_v[8:])
    if others > 0:
        top.append(("Autres", others))

    labels = []
    for v, c in top:
        pct = round(c / total * 100, 1)
        labels.append(f"{v} ({pct}%)")
    data = [c for _, c in top]

    chart_config = {
        "type": "doughnut",
        "data": {
            "labels": labels,
            "datasets": [{
                "data": data,
                "backgroundColor": [
                    "#0078D4", "#00BCF2", "#FFB900", "#E74856",
                    "#744DA9", "#10893E", "#FF8C00", "#E3008C", "#B4B4B4"
                ],
                "borderWidth": 2,
                "borderColor": "#fff"
            }]
        },
        "options": {
            "plugins": {
                "legend": {
                    "position": "right",
                    "labels": {"font": {"size": 13}, "padding": 12, "usePointStyle": True}
                },
                "datalabels": {
                    "display": True,
                    "color": "#fff",
                    "font": {"size": 13, "weight": "bold"},
                    "formatter": "(val, ctx) => { return (val / ctx.chart.getDatasetMeta(0).total * 100).toFixed(1) + '%'; }"
                }
            }
        }
    }

    chart_payload = json.dumps({
        "chart": chart_config,
        "width": 800,
        "height": 450,
        "backgroundColor": "white",
        "format": "png",
        "devicePixelRatio": 2
    })

    req = urllib.request.Request(
        "https://quickchart.io/chart/create",
        method="POST",
        headers={"Content-Type": "application/json"},
        data=chart_payload.encode()
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.loads(r.read())

    chart_url = resp.get("url", "")
    print(f"[OK] Chart URL: {chart_url}")
    return chart_url, sorted_v, total


# -- Adaptive Card --
def build_card(chart_url, versions, total):
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    body = [
        {
            "type": "ColumnSet",
            "columns": [
                {"type": "Column", "width": "auto", "items": [
                    {"type": "TextBlock", "text": "\U0001F4F1", "size": "Large"}
                ]},
                {"type": "Column", "width": "stretch", "items": [
                    {"type": "TextBlock", "text": "iPads - Distribution iOS", "weight": "Bolder", "size": "Large", "wrap": True},
                    {"type": "TextBlock", "text": f"{now}", "isSubtle": True, "spacing": "None", "size": "Small"}
                ]}
            ]
        },
        {"type": "TextBlock", "text": " ", "spacing": "Small"},
    ]

    body.append({
        "type": "ColumnSet",
        "columns": [
            {"type": "Column", "width": "1", "items": [
                {"type": "TextBlock", "text": str(total), "weight": "Bolder", "size": "ExtraLarge", "horizontalAlignment": "Center", "color": "Accent"},
                {"type": "TextBlock", "text": "iPads", "horizontalAlignment": "Center", "isSubtle": True, "spacing": "None", "size": "Small"}
            ]},
            {"type": "Column", "width": "1", "items": [
                {"type": "TextBlock", "text": str(len(versions)), "weight": "Bolder", "size": "ExtraLarge", "horizontalAlignment": "Center", "color": "Accent"},
                {"type": "TextBlock", "text": "versions", "horizontalAlignment": "Center", "isSubtle": True, "spacing": "None", "size": "Small"}
            ]},
            {"type": "Column", "width": "1", "items": [
                {"type": "TextBlock", "text": versions[0][0] if versions else "-", "weight": "Bolder", "size": "ExtraLarge", "horizontalAlignment": "Center", "color": "Good"},
                {"type": "TextBlock", "text": "top version", "horizontalAlignment": "Center", "isSubtle": True, "spacing": "None", "size": "Small"}
            ]}
        ]
    })

    if chart_url:
        body.append({"type": "Image", "url": chart_url, "size": "Stretch", "spacing": "Medium"})

    body.append({"type": "TextBlock", "text": "**Top 10 versions**", "spacing": "Medium", "separator": True})

    # En-tete tableau
    body.append({
        "type": "ColumnSet",
        "spacing": "Small",
        "columns": [
            {"type": "Column", "width": "stretch", "items": [
                {"type": "TextBlock", "text": "Version", "weight": "Bolder", "size": "Small", "isSubtle": True}
            ]},
            {"type": "Column", "width": "auto", "items": [
                {"type": "TextBlock", "text": "Nombre", "weight": "Bolder", "size": "Small", "isSubtle": True, "horizontalAlignment": "Right"}
            ]},
            {"type": "Column", "width": "60px", "items": [
                {"type": "TextBlock", "text": "%", "weight": "Bolder", "size": "Small", "isSubtle": True, "horizontalAlignment": "Right"}
            ]}
        ]
    })

    top10 = versions[:10]
    for i, (version, count) in enumerate(top10):
        pct = round(count / total * 100, 1)
        body.append({
            "type": "ColumnSet",
            "spacing": "None",
            "columns": [
                {"type": "Column", "width": "stretch", "items": [
                    {"type": "TextBlock", "text": f"{i+1}. **{version}**", "size": "Small"}
                ]},
                {"type": "Column", "width": "auto", "items": [
                    {"type": "TextBlock", "text": f"**{count}**", "size": "Small", "horizontalAlignment": "Right"}
                ]},
                {"type": "Column", "width": "60px", "items": [
                    {"type": "TextBlock", "text": f"{pct}%", "size": "Small", "horizontalAlignment": "Right", "isSubtle": True}
                ]}
            ]
        })

    others_count = sum(c for _, c in versions[10:])
    if others_count > 0:
        others_pct = round(others_count / total * 100, 1)
        nb_others = len(versions) - 10
        body.append({
            "type": "TextBlock",
            "text": f"*+ {nb_others} autres versions : {others_count} iPads ({others_pct}%)*",
            "isSubtle": True,
            "size": "Small",
            "spacing": "Small"
        })

    card = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "contentUrl": None,
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.5",
                "body": body
            }
        }]
    }
    return card


def post_teams(card):
    http(TEAMS_WEBHOOK, "POST",
         {"Content-Type": "application/json"},
         json.dumps(card))
    print("[OK] Message envoye sur Teams")


def main():
    print("=" * 50)
    print("Omnissa Intelligence > Teams Report")
    print("=" * 50)

    token = get_token()
    versions = get_versions(token)

    sorted_v = sorted(versions.items(), key=lambda x: -x[1])
    total = sum(versions.values())

    print(f"\n--- Distribution iOS ({total} iPads, {len(versions)} versions) ---")
    for v, c in sorted_v[:15]:
        print(f"  {v}: {c} ({round(c/total*100, 1)}%)")

    chart_url, sorted_v, total = build_chart_url(versions)
    card = build_card(chart_url, sorted_v, total)
    post_teams(card)
    print("\n[DONE] Rapport envoye sur Teams !")


if __name__ == "__main__":
    main()
