"""Serverless function: scan marketplace for profitable flips."""

import json
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler

BASE_URL = "https://mlb26.theshow.com/apis"
TAX_RATE = 0.10


def fetch_page(api_params):
    """Fetch a single page of listings."""
    try:
        resp = requests.get(f"{BASE_URL}/listings.json", params=api_params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def scan_market(params):
    min_profit = int(params.get("min_profit", 0))
    min_roi = float(params.get("min_roi", 5.0))
    max_buy = int(params.get("max_buy_price", 0))   # 0 = no limit
    min_buy = int(params.get("min_buy_price", 0))
    rarity = params.get("rarity") or None
    series_id = params.get("series_id") or None

    # Build base API params (without page)
    base_params = {
        "type": "mlb_card",
        "sort": "best_sell_price",
        "order": "asc",
    }
    if rarity:
        base_params["rarity"] = rarity
    if series_id and series_id != "-1":
        base_params["series_id"] = series_id
    if min_buy > 0:
        base_params["min_best_sell_price"] = min_buy
    if max_buy > 0:
        base_params["max_best_sell_price"] = max_buy

    # First request to get total_pages
    first_params = {**base_params, "page": 1}
    first_data = fetch_page(first_params)
    if not first_data:
        return []

    total_pages = first_data.get("total_pages", 1)
    all_listings = first_data.get("listings", [])

    # Fetch remaining pages in parallel (up to 5 at a time)
    if total_pages > 1:
        remaining = list(range(2, total_pages + 1))
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {
                pool.submit(fetch_page, {**base_params, "page": p}): p
                for p in remaining
            }
            for future in as_completed(futures):
                data = future.result()
                if data and data.get("listings"):
                    all_listings.extend(data["listings"])

    # Process all listings
    flips = []
    for listing in all_listings:
        sell_now = listing.get("best_buy_price")   # you buy here (place order at +1)
        buy_now = listing.get("best_sell_price")    # you sell here (list at -1)

        if not isinstance(sell_now, (int, float)) or not isinstance(buy_now, (int, float)):
            continue
        if sell_now <= 0 or buy_now <= 0:
            continue

        your_buy = int(sell_now) + 1
        your_sell = int(buy_now) - 1

        revenue = int(your_sell * (1 - TAX_RATE))
        profit = revenue - your_buy

        if profit < min_profit:
            continue

        if your_buy <= 0:
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
