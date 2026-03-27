#!/usr/bin/env python3
"""Omnissa Intelligence > Teams : camembert distribution iOS iPads."""

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
    """Essaie trend d'abord, fallback sur preview."""
    if TREND_ID:
        try:
            return get_versions_trend(token)
        except Exception as e:
            print(f"[WARN] Trend echoue ({e}), fallback preview...")
    return get_versions_preview(token)


# -- Camembert via QuickChart.io --
def build_chart_url(versions):
    sorted_v = sorted(versions.items(), key=lambda x: -x[1])
    total = sum(versions.values())

    top = sorted_v[:10]
    others = sum(c for _, c in sorted_v[10:])
    if others > 0:
        top.append(("Autres", others))

    labels = [v for v, _ in top]
    data = [c for _, c in top]

    chart_config = {
        "type": "doughnut",
        "data": {
            "labels": labels,
            "datasets": [{
                "data": data,
                "backgroundColor": [
                    "#FF6384", "#36A2EB", "#FFCE56", "#4BC0C0",
                    "#9966FF", "#FF9F40", "#E7E9ED", "#7BC67E",
                    "#C9CBCF", "#F7464A", "#949FB1"
                ]
            }]
        },
        "options": {
            "plugins": {
                "title": {
                    "display": True,
                    "text": f"Distribution iOS - {total} iPads",
                    "font": {"size": 18}
                },
                "datalabels": {
                    "display": True,
                    "color": "#fff",
                    "font": {"size": 11, "weight": "bold"}
                }
            }
        }
    }

    chart_json = json.dumps(chart_config)
    chart_url = f"https://quickchart.io/chart?c={urllib.parse.quote(chart_json)}&w=600&h=400&bkg=white&f=png"
    print(f"[OK] Chart URL generee ({len(chart_url)} chars)")
    return chart_url, sorted_v, total


# -- Adaptive Card avec image camembert --
def build_card(chart_url, versions, total):
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    rows = []
    for version, count in versions[:10]:
        pct = round(count / total * 100, 1)
        rows.append(f"**{version}** : {count} ({pct}%)")

    others = sum(c for _, c in versions[10:])
    if others > 0:
        rows.append(f"**Autres** : {others} ({round(others/total*100, 1)}%)")

    summary_text = " | ".join(rows[:6])
    if len(rows) > 6:
        summary_text += f" | +{len(rows)-6} autres..."

    card = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "contentUrl": None,
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.4",
                "body": [
                    {
                        "type": "TextBlock",
                        "text": "iPads - Mises a jour iOS",
                        "weight": "Bolder",
                        "size": "Large",
                        "style": "heading"
                    },
                    {
                        "type": "TextBlock",
                        "text": f"{now} | {total} iPads | {len(versions)} versions",
                        "isSubtle": True,
                        "spacing": "None"
                    },
                    {
                        "type": "Image",
                        "url": chart_url,
                        "size": "Large",
                        "altText": "Camembert distribution iOS"
                    },
                    {
                        "type": "TextBlock",
                        "text": summary_text,
                        "wrap": True,
                        "size": "Small",
                        "spacing": "Medium"
                    }
                ]
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
    print("Omnissa Intelligence > Teams Report (camembert)")
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
    print("\n[DONE] Camembert envoye sur Teams !")


if __name__ == "__main__":
    main()
