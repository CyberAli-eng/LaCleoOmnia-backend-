#!/usr/bin/env python3
"""
Profit validation script: compare system profit vs manual (e.g. Excel) for a sample of orders.
Target: variance < 1%. Run after filling SKU costs and recomputing profit.

Usage:
  cd apps/api-python && python scripts/validate_profit.py

Expects DATABASE_URL (or .env). Picks up to 20 orders with order_profit, logs:
  order_id, channel_order_id, revenue, net_profit (system), manual_net (placeholder 0), variance_pct.
"""
import os
import sys

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Load env
from dotenv import load_dotenv
load_dotenv()

from app.models import Order, OrderProfit

def main():
    database_url = os.getenv("DATABASE_URL", "postgresql://admin:password@localhost:5432/lacleo_omnia?schema=public")
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        # Orders that have order_profit, limit 20
        rows = (
            db.query(Order.id, Order.channel_order_id, OrderProfit.revenue, OrderProfit.net_profit)
            .join(OrderProfit, Order.id == OrderProfit.order_id)
            .order_by(Order.created_at.desc())
            .limit(20)
            .all()
        )
        if not rows:
            print("No orders with profit data. Run sync and recompute profit first.")
            return

        print("Order ID\tChannel Order ID\tRevenue\tSystem Net\tManual Net (placeholder)\tVariance %")
        print("-" * 90)
        total_variance_abs = Decimal("0")
        count = 0
        for order_id, channel_order_id, revenue, net_profit in rows:
            revenue = float(revenue or 0)
            system_net = float(net_profit or 0)
            manual_net = 0.0  # Replace with Excel/manual value if you have it
            if revenue != 0:
                variance_pct = abs(system_net - manual_net) / revenue * 100
            else:
                variance_pct = 0
            total_variance_abs += Decimal(str(variance_pct))
            count += 1
            print(f"{order_id}\t{channel_order_id}\t{revenue:.2f}\t{system_net:.2f}\t{manual_net:.2f}\t{variance_pct:.2f}%")

        if count:
            avg_variance = float(total_variance_abs / count)
            print("-" * 90)
            print(f"Sample size: {count} orders. Average |variance|% (vs manual placeholder 0): {avg_variance:.2f}%")
            print("To target <1%: fill manual_net from Excel for the same orders and re-run.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
