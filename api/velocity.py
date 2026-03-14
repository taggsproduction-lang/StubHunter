"""Serverless function: get sales velocity and market depth for a card."""

import json
import requests
from datetime import datetime
from http.server import BaseHTTPRequestHandler

BASE_URL = "https://mlb26.theshow.com/apis"
TAX_RATE = 0.10


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        query = parse_qs(urlparse(self.path).query)
        uuid = query.get("uuid", [None])[0]

        result = {
            "sales_per_hour": None,
            "sell_side": [],      # lowest 10 transaction prices (approximates sell now depth)
            "buy_side": [],       # highest 10 transaction prices (approximates buy now depth)
            "sell_side_avg": None,
            "buy_side_avg": None,
            "best_buy_price": None,
            "best_sell_price": None,
            "opportunity": None,
        }

        if uuid:
            try:
                resp = requests.get(f"{BASE_URL}/listing.json", params={"uuid": uuid}, timeout=10)
                resp.raise_for_status()
                data = resp.json()

                best_buy = data.get("best_buy_price")    # sell now price
                best_sell = data.get("best_sell_price")   # buy now price
                if isinstance(best_buy, (int, float)):
                    result["best_buy_price"] = int(best_buy)
                if isinstance(best_sell, (int, float)):
                    result["best_sell_price"] = int(best_sell)

                orders = data.get("completed_orders", [])

                # --- Parse all order prices + times ---
                parsed = []
                fmt = "%m/%d/%Y %H:%M:%S"
                for o in orders:
                    try:
                        p = int(o["price"].replace(",", ""))
                        t = datetime.strptime(o["date"], fmt)
                        parsed.append({"price": p, "time": t})
                    except (ValueError, KeyError):
                        continue

                # --- Sales velocity ---
                if len(parsed) >= 2:
                    times = sorted([x["time"] for x in parsed])
                    span = (times[-1] - times[0]).total_seconds() / 3600
                    if span > 0:
                        result["sales_per_hour"] = round(len(times) / span, 1)

                if parsed:
                    # Group ALL completed orders by distinct price level
                    all_counts = {}
                    for x in parsed:
                        all_counts[x["price"]] = all_counts.get(x["price"], 0) + 1

                    all_asc = sorted(all_counts.items())   # cheapest first
                    all_desc = sorted(all_counts.items(), reverse=True)  # most expensive first

                    # Buy Price (left column): 10 highest prices, sorted ascending
                    # These approximate the sell orders (what you'd pay to buy)
                    buy_10 = all_desc[:10]
                    buy_10.sort()  # ascending like the screenshot
                    result["buy_side"] = [{"price": p, "qty": q} for p, q in buy_10]
                    if buy_10:
                        total_qty = sum(q for _, q in buy_10)
                        result["buy_side_avg"] = round(total_qty / len(buy_10), 1)

                    # Sell Price (right column): 10 lowest prices, sorted descending
                    # These approximate the buy orders (what you'd get if you sell)
                    sell_10 = all_asc[:10]
                    sell_10.sort(reverse=True)  # descending like the screenshot
                    result["sell_side"] = [{"price": p, "qty": q} for p, q in sell_10]
                    if sell_10:
                        total_qty = sum(q for _, q in sell_10)
                        result["sell_side_avg"] = round(total_qty / len(sell_10), 1)

                    # --- Opportunity analysis ---
                    # Look at recent transactions sorted by time (newest first)
                    # Find thin spots: few sales in a profitable ROI band
                    by_time = sorted(parsed, key=lambda x: x["time"], reverse=True)
                    recent = by_time[:25]  # last 25 transactions

                    if best_buy and best_sell and best_buy > 0 and best_sell > 0:
                        # For each recent transaction, calculate what ROI you'd get
                        # if you bought at that price and sold at best_sell
                        opportunities = []
                        for tx in recent:
                            cost = tx["price"] + 1
                            revenue = int((best_sell - 1) * (1 - TAX_RATE))
                            profit = revenue - cost
                            if cost > 0:
                                roi = round((profit / cost) * 100, 1)
                            else:
                                continue

                            if 15 <= roi <= 85 and profit > 0:
                                opportunities.append({
                                    "price": tx["price"],
                                    "roi": roi,
                                    "profit": profit,
                                    "time": tx["time"].strftime("%H:%M"),
                                })

                        if opportunities:
                            # Count how many recent transactions fall in this sweet spot
                            count = len(opportunities)
                            avg_price = round(sum(o["price"] for o in opportunities) / count)
                            avg_roi = round(sum(o["roi"] for o in opportunities) / count, 1)
                            avg_profit = round(sum(o["profit"] for o in opportunities) / count)

                            if count <= 5:
                                tip = f"Only {count} recent sales in the 15-85% ROI zone. Thin market — get in at ~{avg_price + 1:,} stubs to undercut."
                            elif count <= 10:
                                tip = f"{count} sales in the sweet spot. Moderate competition at ~{avg_price:,} stubs."
                            else:
                                tip = f"{count} sales competing in this range. Crowded — consider a different card."

                            result["opportunity"] = {
                                "count": count,
                                "avg_price": avg_price,
                                "avg_roi": avg_roi,
                                "avg_profit": avg_profit,
                                "tip": tip,
                                "transactions": opportunities[:5],
                            }

            except Exception:
                pass

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())
