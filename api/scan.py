"""Serverless function: scan marketplace for profitable flips."""

import json
import time
import requests
from http.server import BaseHTTPRequestHandler

BASE_URL = "https://mlb26.theshow.com/apis"
TAX_RATE = 0.10


def scan_market(params):
    min_profit = int(params.get("min_profit", 100))
    min_roi = float(params.get("min_roi", 5.0))
    max_buy = int(params.get("max_buy_price", 50000))
    min_buy = int(params.get("min_buy_price", 100))
    rarity = params.get("rarity") or None
    series_id = params.get("series_id") or None
    pages = min(int(params.get("pages", 10)), 40)

    flips = []

    for page in range(1, pages + 1):
        api_params = {
            "type": "mlb_card",
            "page": page,
            "sort": "best_sell_price",
            "order": "asc",
        }
        if rarity:
            api_params["rarity"] = rarity
        if series_id and series_id != "-1":
            api_params["series_id"] = series_id
        if min_buy:
            api_params["min_best_sell_price"] = min_buy
        if max_buy:
            api_params["max_best_sell_price"] = max_buy

        try:
            resp = requests.get(f"{BASE_URL}/listings.json", params=api_params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            break

        listings = data.get("listings", [])
        if not listings:
            break

        for listing in listings:
            # In The Show marketplace:
            # best_buy_price = "Sell Now" price (highest buy order on the board)
            # best_sell_price = "Buy Now" price (lowest sell order on the board)
            #
            # Flip strategy:
            # 1. Place buy order at Sell Now + 1 to acquire card cheap
            # 2. List sell order at Buy Now - 1 to sell card high
            sell_now = listing.get("best_buy_price")   # you buy here (place order at +1)
            buy_now = listing.get("best_sell_price")    # you sell here (list at -1)

            if not isinstance(sell_now, (int, float)) or not isinstance(buy_now, (int, float)):
                continue
            if sell_now <= 0 or buy_now <= 0:
                continue

            # actual prices you'd use
            your_buy = int(sell_now) + 1       # outbid current best buy order
            your_sell = int(buy_now) - 1       # undercut current best sell order

            # profit after 10% tax
            revenue = int(your_sell * (1 - TAX_RATE))
            profit = revenue - your_buy

            if profit < min_profit:
                continue

            roi = (profit / your_buy) * 100
            if roi < min_roi:
                continue

            item = listing.get("item", {})
            flips.append({
                "name": listing.get("listing_name", "Unknown"),
                "uuid": item.get("uuid", ""),
                "rarity": item.get("rarity", "Unknown"),
                "ovr": item.get("ovr", 0),
                "team": item.get("team_short_name", ""),
                "position": item.get("display_position", ""),
                "series": item.get("series", ""),
                "sell_now": int(sell_now),
                "buy_now": int(buy_now),
                "your_buy": your_buy,
                "your_sell": your_sell,
                "profit": profit,
                "roi": round(roi, 1),
                "img": item.get("baked_img") or item.get("img", ""),
            })

        time.sleep(0.25)

    flips.sort(key=lambda f: f["profit"], reverse=True)
    return flips


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        query = parse_qs(urlparse(self.path).query)
        params = {k: v[0] for k, v in query.items()}

        flips = scan_market(params)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({"flips": flips, "count": len(flips)}).encode())
