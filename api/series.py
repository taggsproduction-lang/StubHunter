"""Serverless function: fetch available series from meta_data."""

import json
import requests
from http.server import BaseHTTPRequestHandler

BASE_URL = "https://mlb26.theshow.com/apis"


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        series = []
        try:
            resp = requests.get(f"{BASE_URL}/meta_data.json", timeout=10)
            resp.raise_for_status()
            data = resp.json()
            series = data.get("series", [])
        except Exception:
            pass

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({"series": series}).encode())
