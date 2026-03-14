"""Serverless function: get sales velocity and market depth for a card."""

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

        result = {"sales_per_hour": None, "depth_avg": None, "depth_detail": []}

        if uuid:
            try:
                resp = requests.get(f"{BASE_URL}/listing.json", params={"uuid": uuid}, timeout=10)
                resp.raise_for_status()
                data = resp.json()

                orders = data.get("completed_orders", [])

                # --- Sales velocity ---
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

                # --- Market depth: analyze lowest 10 prices from completed orders ---
                # Parse all completed order prices and find clustering at low end
                prices = []
                for o in orders:
                    try:
                        p = int(o["price"].replace(",", ""))
                        prices.append(p)
                    except (ValueError, KeyError):
                        continue

                if prices:
                    # Sort ascending, take lowest 10
                    prices.sort()
                    lowest_10 = prices[:10]

                    # Count qty at each distinct price
                    price_counts = {}
                    for p in lowest_10:
                        price_counts[p] = price_counts.get(p, 0) + 1

                    # Build detail: [{price, qty}] sorted by price
                    detail = [{"price": p, "qty": q} for p, q in sorted(price_counts.items())]
                    result["depth_detail"] = detail

                    # Average qty per distinct price across the lowest 10
                    num_distinct = len(price_counts)
                    result["depth_avg"] = round(len(lowest_10) / num_distinct, 1) if num_distinct > 0 else None

            except Exception:
                pass

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())
