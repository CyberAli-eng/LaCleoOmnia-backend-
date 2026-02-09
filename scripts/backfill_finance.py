#!/usr/bin/env python3
"""
Backfill Finance Engine - Recompute financial data for existing orders
"""
import sys
import os
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, engine
from app.models import Order, OrderFinance, CustomerRisk
from app.services.finance_engine import compute_order_finance
from app.services.risk_engine import run_risk_assessment

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def backfill_all_orders():
    """Backfill finance data for all existing orders"""
    db = SessionLocal()
    
    try:
        # Get all orders without finance records
        orders_without_finance = db.query(Order).outerjoin(OrderFinance).filter(OrderFinance.id.is_(None)).all()
        
        logger.info(f"Found {len(orders_without_finance)} orders without finance records")
        
        # Process in batches to avoid memory issues
        batch_size = 100
        processed = 0
        failed = 0
        
        for i in range(0, len(orders_without_finance), batch_size):
            batch = orders_without_finance[i:i + batch_size]
            
            for order in batch:
                try:
                    compute_order_finance(db, order.id)
                    processed += 1
                    
                    if processed % 50 == 0:
                        logger.info(f"Processed {processed} orders...")
                        db.commit()
                        
                except Exception as e:
                    logger.error(f"Failed to process order {order.id}: {e}")
                    failed += 1
                    db.rollback()
            
            # Commit batch
            db.commit()
            logger.info(f"Batch completed: {processed + failed} orders processed")
        
        logger.info(f"Backfill completed: {processed} successful, {failed} failed")
        
    except Exception as e:
        logger.error(f"Backfill failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def backfill_customer_risk():
    """Backfill risk profiles for all customers"""
    db = SessionLocal()
    
    try:
        # Get all unique customer IDs
        customer_ids = db.query(Order.customer_id).filter(
            Order.customer_id.isnot(None)
        ).distinct().all()
        
        customer_ids = [cid[0] for cid in customer_ids]
        logger.info(f"Found {len(customer_ids)} unique customers")
        
        processed = 0
        failed = 0
        
        for customer_id in customer_ids:
            try:
                run_risk_assessment(db, customer_id)
                processed += 1
                
                if processed % 100 == 0:
                    logger.info(f"Processed {processed} customers...")
                    db.commit()
                    
            except Exception as e:
                logger.error(f"Failed to process customer {customer_id}: {e}")
                failed += 1
                db.rollback()
        
        db.commit()
        logger.info(f"Risk backfill completed: {processed} successful, {failed} failed")
        
    except Exception as e:
        logger.error(f"Risk backfill failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def recompute_recent_orders(days: int = 30):
    """Recompute finance for recent orders (last N days)"""
    db = SessionLocal()
    
    try:
        cutoff_date = datetime.now() - timedelta(days=days)
        
        orders = db.query(Order).filter(Order.created_at >= cutoff_date).all()
        logger.info(f"Found {len(orders)} orders from last {days} days")
        
        processed = 0
        failed = 0
        
        for order in orders:
            try:
                compute_order_finance(db, order.id)
                processed += 1
                
                if processed % 50 == 0:
                    logger.info(f"Processed {processed} orders...")
                    db.commit()
                    
            except Exception as e:
                logger.error(f"Failed to process order {order.id}: {e}")
                failed += 1
                db.rollback()
        
        db.commit()
        logger.info(f"Recompute completed: {processed} successful, {failed} failed")
        
    except Exception as e:
        logger.error(f"Recompute failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def get_backfill_stats():
    """Get statistics about backfill status"""
    db = SessionLocal()
    
    try:
        total_orders = db.query(Order).count()
        orders_with_finance = db.query(OrderFinance).count()
        orders_without_finance = total_orders - orders_with_finance
        
        # Customer risk stats
        unique_customers = db.query(func.count(func.distinct(Order.customer_id))).filter(
            Order.customer_id.isnot(None)
        ).scalar()
        
        customers_with_risk = db.query(func.count(func.distinct(CustomerRisk.customer_id))).scalar()
        
        logger.info(f"Backfill Statistics:")
        logger.info(f"  Total Orders: {total_orders}")
        logger.info(f"  Orders with Finance: {orders_with_finance}")
        logger.info(f"  Orders without Finance: {orders_without_finance}")
        logger.info(f"  Finance Coverage: {(orders_with_finance/total_orders*100):.1f}%" if total_orders > 0 else "0%")
        logger.info(f"  Unique Customers: {unique_customers}")
        logger.info(f"  Customers with Risk: {customers_with_risk}")
        logger.info(f"  Risk Coverage: {(customers_with_risk/unique_customers*100):.1f}%" if unique_customers > 0 else "0%")
        
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python backfill_finance.py [command]")
        print("Commands:")
        print("  all          - Backfill all orders without finance records")
        print("  risk         - Backfill customer risk profiles")
        print("  recent [N]   - Recompute recent orders (default: 30 days)")
        print("  stats        - Show backfill statistics")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "all":
        logger.info("Starting full backfill...")
        backfill_all_orders()
        backfill_customer_risk()
        
    elif command == "risk":
        logger.info("Starting risk backfill...")
        backfill_customer_risk()
        
    elif command == "recent":
        days = 30
        if len(sys.argv) > 2:
            days = int(sys.argv[2])
        logger.info(f"Recomputing orders from last {days} days...")
        recompute_recent_orders(days)
        
    elif command == "stats":
        get_backfill_stats()
        
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
