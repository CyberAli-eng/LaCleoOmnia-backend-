#!/usr/bin/env python3
"""
Fix NULL profit_status in OrderFinance records
"""
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text
from app.config import settings

def fix_null_profit_status():
    """Update NULL profit_status values based on net_profit"""
    engine = create_engine(settings.DATABASE_URL)
    
    with engine.connect() as conn:
        # Update NULL profit_status based on net_profit
        result = conn.execute(text("""
            UPDATE order_finance 
            SET profit_status = CASE 
                WHEN net_profit > 0 THEN 'PROFIT'
                WHEN net_profit < 0 THEN 'LOSS'
                WHEN net_profit = 0 THEN 'PROFIT'
                ELSE 'PROFIT'
            END
            WHERE profit_status IS NULL
        """))
        
        print(f"Updated {result.rowcount} records with NULL profit_status")
        
        # Check current status
        count_result = conn.execute(text("SELECT COUNT(*) FROM order_finance WHERE profit_status IS NULL"))
        null_count = count_result.scalar()
        print(f"Remaining NULL profit_status records: {null_count}")
        
        conn.commit()

if __name__ == "__main__":
    fix_null_profit_status()
