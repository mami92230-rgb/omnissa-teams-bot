#!/usr/bin/env python3
"""Omnissa Intelligence > Teams Webhook : rapport iPads iOS."""

import os, json, urllib.request, urllib.parse
from datetime import datetime, timezone

TOKEN_URL = "https://auth.eu1.data.workspaceone.com/oauth/token?grant_type=client_credentials"
API_BASE  = "https://eu1.data.workspaceone.com/v2"
CLIENT_ID = os.environ["OMNISSA_CLIENT_ID"]
CLIENT_SECRET = os.environ["OMNISSA_CLIENT_SECRET"]
TEAMS_WEBHOOK = os.environ["TEAMS_WEBHOOK_URL"]
REPORT_ID = os.environ.get("OMNISSA_REPORT_ID", "ca8c3507-06e3-439e-8788-2a8d76dac34a")


def http(url, method="GET", headers=None, body=None):
    req = urllib.request.Request(url, method=method, headers=headers or {})
    if body:
        req.data = body if isinstance(body, bytes) else body.encode()
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def get_token():
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    })
    data = http(TOKEN_URL, "POST",
                {"Content-Type": "application/x-www-form-urlencoded"}, body)
    return data["access_token"]


def get_report(token):
    url = f"{API_BASE}/reports/{REPORT_ID}/run"
    return http(url, "GET", {"Authorization": f"Bearer {token}"})


def build_card(report_data):
    results = report_data if isinstance(report_data, list) else report_data.get("results", report_data.get("data", []))
    total = len(results) if isinstance(results, list) else 0
    versions = {}
    for device in (results if isinstance(results, list) else []):
        ver = device.get("operating_system_version", device.get("os_version", "Inconnu"))
        versions[ver] = versions.get(ver, 0) + 1
    sorted_versions = sorted(versions.items(), key=lambda x: -x[1])[:10]
    lines = []
    for ver, count in sorted_versions:
        pct = round(count / total * 100, 1) if total > 0 else 0
        lines.append(f"**{ver}** - {count} ({pct}%)")
    ios26 = sum(c for v, c in versions.items() if v.startswith("26."))
    ios26_pct = round(ios26 / total * 100, 1) if total > 0 else 0
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    card = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.4",
                "body": [
                    {"type": "TextBlock", "text": "iPads - Versions iOS", "weight": "Bolder", "size": "Large"},
                    {"type": "ColumnSet", "columns": [
                        {"type": "Column", "width": "auto", "items": [
                            {"type": "TextBlock", "text": str(total), "weight": "Bolder", "size": "ExtraLarge", "color": "Accent"},
                            {"type": "TextBlock", "text": "Total iPads", "spacing": "None", "isSubtle": True}
                        ]},
                        {"type": "Column", "width": "auto", "items": [
                            {"type": "TextBlock", "text": f"{ios26} ({ios26_pct}%)", "weight": "Bolder", "size": "ExtraLarge", "color": "Good"},
                            {"type": "TextBlock", "text": "iOS 26.x", "spacing": "None", "isSubtle": True}
                        ]}
                    ]},
                    {"type": "TextBlock", "text": "Top 10 versions :", "weight": "Bolder", "separator": True},
                    *[{"type": "TextBlock", "text": line, "spacing": "Small", "wrap": True} for line in lines],
                    {"type": "TextBlock", "text": now, "isSubtle": True, "separator": True, "spacing": "Medium"}
                ]
            }
        }]
    }
    return card


def post_teams(card):
    req = urllib.request.Request(
        TEAMS_WEBHOOK, method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps(card).encode()
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status


def main():
    print("1. Getting OAuth token...")
    token = get_token()
    print("   OK")
    print("2. Fetching report...")
    data = get_report(token)
    print(f"   Got data: {type(data)}")
    print("3. Building Adaptive Card...")
    card = build_card(data)
    print("4. Posting to Teams...")
    status = post_teams(card)
    print(f"   Done (HTTP {status})")


if __name__ == "__main__":
    main()
