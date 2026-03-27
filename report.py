#!/usr/bin/env python3
"""Omnissa Intelligence > Teams Webhook : rapport distribution iOS iPads."""

import os, json, urllib.request, urllib.parse, base64, time
from datetime import datetime, timezone
from collections import Counter

TOKEN_URL   = "https://auth.eu1.data.workspaceone.com/oauth/token"
API_BASE    = "https://api.eu1.data.workspaceone.com"
CLIENT_ID   = os.environ["OMNISSA_CLIENT_ID"]
CLIENT_SECRET = os.environ["OMNISSA_CLIENT_SECRET"]
TEAMS_WEBHOOK = os.environ["TEAMS_WEBHOOK_URL"]
REPORT_ID   = os.environ["OMNISSA_REPORT_ID"]
PAGE_SIZE = 100


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
        {"Content-Type": "application/x-www-form-urlencoded", "Authorization": f"Basic {creds}"},
        "grant_type=client_credentials")
    print(f"[OK] Token obtenu")
    return data["access_token"]


def get_report_data(token):
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    all_results = []
    offset = 0
    total = None
    while True:
        url = f"{API_BASE}/v2/reports/{REPORT_ID}/preview?page_size={PAGE_SIZE}&offset={offset}"
        resp = http(url, "GET", headers)
        data = resp.get("data", resp)
        results = data.get("results", [])
        if total is None:
            total = data.get("total_count", 0)
            print(f"[OK] Rapport: {total} devices")
        all_results.extend(results)
        offset += PAGE_SIZE
        if offset >= total or not results:
            break
        time.sleep(0.2)
    print(f"[OK] {len(all_results)} devices recuperes")
    return all_results


def aggregate_versions(devices):
    counter = Counter()
    for d in devices:
        version = d.get("airwatch.device.device_os_version", "Inconnu")
        counter[version] += 1
    return counter.most_common(), sum(counter.values())


def build_card(versions, total):
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    rows = []
    for version, count in versions:
        pct = round(count / total * 100, 1)
        rows.append({"type": "TableRow", "cells": [
            {"type": "TableCell", "items": [{"type": "TextBlock", "text": version, "weight": "Bolder"}]},
            {"type": "TableCell", "items": [{"type": "TextBlock", "text": str(count)}]},
            {"type": "TableCell", "items": [{"type": "TextBlock", "text": f"{pct}%"}]}
        ]})
    return {"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "contentUrl": None, "content": {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard", "version": "1.4",
        "body": [
            {"type": "TextBlock", "text": "iPads - Distribution iOS", "weight": "Bolder", "size": "Large", "style": "heading"},
            {"type": "TextBlock", "text": f"Mis a jour le {now} - {total} iPads", "isSubtle": True, "spacing": "None"},
            {"type": "Table", "gridStyle": "accent", "firstRowAsHeader": True,
             "columns": [{"width": 2}, {"width": 1}, {"width": 1}],
             "rows": [{"type": "TableRow", "style": "accent", "cells": [
                 {"type": "TableCell", "items": [{"type": "TextBlock", "text": "Version iOS", "weight": "Bolder"}]},
                 {"type": "TableCell", "items": [{"type": "TextBlock", "text": "Nombre", "weight": "Bolder"}]},
                 {"type": "TableCell", "items": [{"type": "TextBlock", "text": "%", "weight": "Bolder"}]}
             ]}] + rows}
        ]
    }}]}


def post_teams(card):
    http(TEAMS_WEBHOOK, "POST", {"Content-Type": "application/json"}, json.dumps(card))
    print("[OK] Message envoye sur Teams")


def main():
    print("=" * 50)
    print("Omnissa Intelligence > Teams Report")
    print("=" * 50)
    token = get_token()
    devices = get_report_data(token)
    versions, total = aggregate_versions(devices)
    print(f"\n--- Distribution iOS ({total} iPads) ---")
    for v, c in versions:
        print(f"  {v}: {c} ({round(c/total*100, 1)}%)")
    card = build_card(versions, total)
    post_teams(card)
    print("\n[DONE] Rapport envoye avec succes !")


if __name__ == "__main__":
    main()
