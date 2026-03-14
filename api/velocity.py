"""Serverless function: get sales velocity for a card."""

import json
import requests
from datetime import datetime
from http.server import BaseHTTPRequestHandler

BASE_URL = "https://mlb26.theshow.com/apis"


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        query = parse_qs(urlparse(self.path).query)
        uuid = query.get("uuid", [None])[0]

        result = {"sales_per_hour": None}

        if uuid:
            try:
                resp = requests.get(f"{BASE_URL}/listing.json", params={"uuid": uuid}, timeout=10)
                resp.raise_for_status()
                data = resp.json()

                orders = data.get("completed_orders", [])
                if len(orders) >= 2:
                    fmt = "%m/%d/%Y %H:%M:%S"
                    times = []
                    for o in orders:
                        try:
                            times.append(datetime.strptime(o["date"], fmt))
                        except (ValueError, KeyError):
                            continue

                    if len(times) >= 2:
                        times.sort()
                        span = (times[-1] - times[0]).total_seconds() / 3600
                        if span > 0:
                            result["sales_per_hour"] = round(len(times) / span, 1)
            except Exception:
                pass

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())
