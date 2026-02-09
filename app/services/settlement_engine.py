"""
Settlement Engine - Track and manage order settlements
"""
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import Order, OrderSettlement, OrderFinance, SettlementStatus

logger = logging.getLogger(__name__)


class SettlementEngine:
    """Engine for managing order settlements"""
    
    def __init__(self):
        self.settlement_rules = {
            "payment_gateway": {
                "prepaid_days": 7,    # T+7 for prepaid
                "cod_days": 15,        # T+15 for COD
                "auto_mark_settled": True
            },
            "marketplace": {
                "settlement_days": 30,  # T+30 for marketplace
                "auto_mark_settled": False
            },
            "courier": {
                "cod_days": 20,        # T+20 for courier COD
                "prepaid_days": 10      # T+10 for courier prepaid
            }
        }
    
    def compute_expected_date(self, order: Order, partner: str) -> date:
        """Compute expected settlement date for an order and partner"""
        order_date = order.created_at.date() if order.created_at else date.today()
        
        if partner.lower() == "payment gateway":
            if hasattr(order, 'payment_mode') and order.payment_mode:
                if order.payment_mode.value.upper() == 'COD':
                    days = self.settlement_rules["payment_gateway"]["cod_days"]
                else:
                    days = self.settlement_rules["payment_gateway"]["prepaid_days"]
            else:
                days = self.settlement_rules["payment_gateway"]["prepaid_days"]
        elif partner.lower() == "marketplace":
            days = self.settlement_rules["marketplace"]["settlement_days"]
        elif partner.lower() == "courier":
            if hasattr(order, 'payment_mode') and order.payment_mode:
                if order.payment_mode.value.upper() == 'COD':
                    days = self.settlement_rules["courier"]["cod_days"]
                else:
                    days = self.settlement_rules["courier"]["prepaid_days"]
            else:
                days = self.settlement_rules["courier"]["prepaid_days"]
        else:
            days = 30  # Default
        
        return order_date + timedelta(days=days)
    
    def mark_settled(
        self,
        db: Session,
        settlement_id: str,
        actual_date: Optional[date] = None,
        reference_id: Optional[str] = None,
        notes: Optional[str] = None
    ) -> OrderSettlement:
        """Mark a settlement as settled"""
        settlement = db.query(OrderSettlement).filter(OrderSettlement.id == settlement_id).first()
        if not settlement:
            raise ValueError(f"Settlement {settlement_id} not found")
        
        settlement.status = SettlementStatus.SETTLED
        settlement.actual_date = actual_date or date.today()
        if reference_id:
            settlement.reference_id = reference_id
        if notes:
            settlement.notes = notes
        
        db.commit()
        
        logger.info(f"Marked settlement {settlement_id} as settled on {settlement.actual_date}")
        return settlement
    
    def detect_overdue(self, db: Session, days_overdue: int = 0) -> List[OrderSettlement]:
        """Detect overdue settlements"""
        cutoff_date = date.today() - timedelta(days=days_overdue)
        
        overdue_settlements = db.query(OrderSettlement).filter(
            OrderSettlement.status == SettlementStatus.PENDING,
            OrderSettlement.expected_date < cutoff_date
        ).all()
        
        # Mark as overdue
        for settlement in overdue_settlements:
            settlement.status = SettlementStatus.OVERDUE
        
        db.commit()
        
        logger.info(f"Marked {len(overdue_settlements)} settlements as overdue")
        return overdue_settlements
    
    def auto_settle(self, db: Session, partner: str) -> List[OrderSettlement]:
        """Auto-settle eligible settlements based on rules"""
        if partner.lower() not in self.settlement_rules:
            return []
        
        rule = self.settlement_rules[partner.lower()]
        if not rule.get("auto_mark_settled", False):
            return []
        
        # Find settlements past their expected date
        eligible_date = date.today() - timedelta(days=1)  # Yesterday and before
        
        settlements = db.query(OrderSettlement).filter(
            OrderSettlement.partner == partner,
            OrderSettlement.status == SettlementStatus.PENDING,
            OrderSettlement.expected_date <= eligible_date
        ).all()
        
        # Mark as settled
        for settlement in settlements:
            settlement.status = SettlementStatus.SETTLED
            settlement.actual_date = settlement.expected_date
            settlement.notes = "Auto-settled by system"
        
        db.commit()
        
        logger.info(f"Auto-settled {len(settlements)} settlements for {partner}")
        return settlements
    
    def get_settlement_pipeline(self, db: Session, user_id: Optional[str] = None) -> Dict:
        """Get settlement pipeline summary"""
        query = db.query(OrderSettlement)
        
        if user_id:
            query = query.join(OrderFinance).join(Order).filter(Order.user_id == user_id)
        
        settlements = query.all()
        
        pipeline = {
            "pending": {
                "count": 0,
                "amount": 0.0,
                "items": []
            },
            "settled": {
                "count": 0,
                "amount": 0.0,
                "items": []
            },
            "overdue": {
                "count": 0,
                "amount": 0.0,
                "items": []
            }
        }
        
        for settlement in settlements:
            status_key = settlement.status.value.lower()
            if status_key in pipeline:
                pipeline[status_key]["count"] += 1
                pipeline[status_key]["amount"] += float(settlement.amount)
                
                # Add recent items (last 10)
                if len(pipeline[status_key]["items"]) < 10:
                    pipeline[status_key]["items"].append({
                        "id": settlement.id,
                        "order_id": settlement.order_id,
                        "partner": settlement.partner,
                        "amount": float(settlement.amount),
                        "expected_date": settlement.expected_date.isoformat(),
                        "actual_date": settlement.actual_date.isoformat() if settlement.actual_date else None
                    })
        
        return pipeline
    
    def get_cashflow_forecast(self, db: Session, days: int = 30, user_id: Optional[str] = None) -> Dict:
        """Get cashflow forecast for next N days"""
        start_date = date.today()
        end_date = start_date + timedelta(days=days)
        
        query = db.query(OrderSettlement).filter(
            OrderSettlement.expected_date.between(start_date, end_date),
            OrderSettlement.status == SettlementStatus.PENDING
        )
        
        if user_id:
            query = query.join(OrderFinance).join(Order).filter(Order.user_id == user_id)
        
        settlements = query.all()
        
        # Group by date
        daily_forecast = {}
        for settlement in settlements:
            date_str = settlement.expected_date.isoformat()
            if date_str not in daily_forecast:
                daily_forecast[date_str] = 0.0
            daily_forecast[date_str] += float(settlement.amount)
        
        # Calculate totals
        total_expected = sum(daily_forecast.values())
        
        return {
            "period_days": days,
            "total_expected": total_expected,
            "daily_breakdown": daily_forecast,
            "average_daily": total_expected / days if days > 0 else 0
        }
    
    def update_settlement_rule(self, partner: str, rule_config: Dict):
        """Update settlement rule for a partner"""
        self.settlement_rules[partner.lower()] = rule_config
        logger.info(f"Updated settlement rule for {partner}")


# Global settlement engine instance
settlement_engine = SettlementEngine()


def run_settlement_jobs(db: Session):
    """Run daily settlement jobs"""
    logger.info("Running settlement jobs")
    
    # Detect overdue settlements
    overdue = settlement_engine.detect_overdue(db, days_overdue=0)
    
    # Auto-settle eligible partners
    for partner in ["payment_gateway"]:  # Only auto-settle payment gateway
        settled = settlement_engine.auto_settle(db, partner)
    
    logger.info(f"Settlement jobs completed: {len(overdue)} overdue detected")


def create_manual_settlement(
    db: Session,
    order_id: str,
    finance_id: str,
    partner: str,
    amount: Decimal,
    expected_date: date,
    reference_id: Optional[str] = None,
    notes: Optional[str] = None
) -> OrderSettlement:
    """Create a manual settlement record"""
    settlement = OrderSettlement(
        order_id=order_id,
        order_finance_id=finance_id,
        partner=partner,
        expected_date=expected_date,
        amount=amount,
        status=SettlementStatus.PENDING,
        reference_id=reference_id,
        notes=notes
    )
    
    db.add(settlement)
    db.commit()
    
    logger.info(f"Created manual settlement: {partner} = {amount} for order {order_id}")
    return settlement
