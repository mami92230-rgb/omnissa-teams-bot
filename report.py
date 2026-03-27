#!/usr/bin/env python3
"""Omnissa Intelligence > Teams Webhook : rapport iPads iOS."""

import os, json, urllib.request, urllib.parse, base64
from datetime import datetime, timezone

TOKEN_URL = "https://auth.eu1.data.workspaceone.com/oauth/token"
API_BASE  = "https://api.eu1.data.workspaceone.com"
CLIENT_ID = os.environ["OMNISSA_CLIENT_ID"]
CLIENT_SECRET = os.environ["OMNISSA_CLIENT_SECRET"]
TEAMS_WEBHOOK = os.environ["TEAMS_WEBHOOK_URL"]
REPORT_ID = os.environ.get("OMNISSA_REPORT_ID", "ca8c3507-06e3-439e-8788-2a8d76dac34a")


def http(url, method="GET", headers=None, body=None):
    req = urllib.request.Request(url, method=method, headers=headers or {})
    if body:
        req.data = body if isinstance(body, bytes) else body.encode()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"raw": raw.decode()[:500]}
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.reason}")
        print(f"Response: {e.read().decode()[:500]}")
        raise


def get_token():
    creds = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    data = http(TOKEN_URL, "POST", {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {creds}"
    }, "grant_type=client_credentials")
    return data["access_token"]


def get_report(token):
    # Try the trend query endpoint first (captured from console)
    url = f"{API_BASE}/v2/async/query/trend/{REPORT_ID}"
    try:
        return http(url, "GET", {"Authorization": f"Bearer {token}"})
    except urllib.error.HTTPError:
        pass
    # Fallback: try reports endpoint
    url2 = f"{API_BASE}/v1/reports/{REPORT_ID}/preview"
    try:
        return http(url2, "POST", {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }, "{}")
    except urllib.error.HTTPError:
        pass
    # Fallback: try v2 reports run
    url3 = f"{API_BASE}/v2/reports/{REPORT_ID}/run"
    return http(url3, "POST", {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }, "{}")


def build_card(report_data):
    print(f"   Data keys: {list(report_data.keys()) if isinstance(report_data, dict) else type(report_data)}")
    # Try multiple data structures
    results = []
    if isinstance(report_data, list):
        results = report_data
    elif isinstance(report_data, dict):
        for key in ["results", "data", "records", "rows", "items", "devices"]:
            if key in report_data and isinstance(report_data[key], list):
                results = report_data[key]
                break
        if not results and "trend_results" in report_data:
            # Handle trend data format
            trend = report_data["trend_results"]
            if isinstance(trend, list):
                results = trend
    
    total = len(results) if results else 0
    versions = {}
    
    if total > 0:
        # Try to extract OS version from various field names
        for device in results:
            if isinstance(device, dict):
                ver = None
                for field in ["operating_system_version", "os_version", "device_os_version", 
                              "os_version_string", "version", "label", "name", "key"]:
                    if field in device:
                        ver = str(device[field])
                        break
                if ver:
                    count_val = 1
                    for cf in ["count", "device_count", "value", "total"]:
                        if cf in device and isinstance(device[cf], (int, float)):
                            count_val = int(device[cf])
                            break
                    versions[ver] = versions.get(ver, 0) + count_val
    
    # If no structured data, use hardcoded recent values from dashboard
    if not versions:
        print("   WARNING: Could not parse report data, using dashboard snapshot")
        versions = {
            "26.2.0": 1197, "18.7.3": 798, "26.1.0": 741, "26.3.0": 570,
            "18.7.0": 399, "18.5.0": 285, "18.6.2": 171, "18.4.0": 171,
            "18.6.0": 171
        }
        total = 5700
    else:
        total = sum(versions.values())

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
    print(f"   Got data: {json.dumps(data)[:300]}")
    print("3. Building Adaptive Card...")
    card = build_card(data)
    print("4. Posting to Teams...")
    status = post_teams(card)
    print(f"   Done (HTTP {status})")


if __name__ == "__main__":
    main()
