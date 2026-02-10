"""
Risk Engine - Customer risk assessment and scoring
"""
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from app.models import Order, CustomerRisk, OrderFinance, RiskTag, FulfilmentStatus

logger = logging.getLogger(__name__)


class RiskEngine:
    """Engine for customer risk assessment"""
    
    def __init__(self):
        self.risk_thresholds = {
            "rto_ratio": {
                "safe": 0.1,      # < 10% RTO ratio
                "medium": 0.25,    # 10-25% RTO ratio  
                "high": 0.4        # > 25% RTO ratio
            },
            "loss_amount": {
                "safe": Decimal("100"),    # < ₹100 loss
                "medium": Decimal("500"),  # ₹100-500 loss
                "high": Decimal("1000")    # > ₹500 loss
            },
            "order_frequency": {
                "min_orders": 5,           # Need at least 5 orders for reliable scoring
                "inactive_days": 90        # Inactive for >90 days increases risk
            },
            "avg_order_value": {
                "low": Decimal("500"),     # Low AOV might indicate casual buyers
                "high": Decimal("5000")    # High AOV increases risk for COD
            }
        }
    
    def calculate_risk_score(self, db: Session, customer_id: str) -> Dict:
        """Calculate comprehensive risk score for a customer"""
        # Get customer's order history
        orders = db.query(Order).filter(Order.customer_id == customer_id).all()
        
        if not orders:
            return {
                "customer_id": customer_id,
                "risk_score": 50.0,  # Neutral score for new customers
                "risk_tag": RiskTag.MEDIUM,
                "factors": {
                    "total_orders": 0,
                    "rto_ratio": 0,
                    "loss_amount": 0,
                    "days_since_last_order": None,
                    "avg_order_value": 0
                }
            }
        
        # Calculate risk factors
        total_orders = len(orders)
        rto_orders = len([o for o in orders if hasattr(o, 'status') and o.status and o.status.value.upper() in ('RTO', 'RETURNED')])
        rto_ratio = rto_orders / total_orders if total_orders > 0 else 0
        
        # Calculate total loss
        loss_amount = Decimal("0")
        for order in orders:
            if hasattr(order, 'finance') and order.finance and order.finance.net_profit < 0:
                loss_amount += abs(order.finance.net_profit)
        
        # Order frequency and recency
        last_order_date = max([o.created_at for o in orders if o.created_at])
        days_since_last_order = (date.today() - last_order_date.date()).days
        
        # Average order value
        total_value = sum([Decimal(str(o.total_amount or 0)) for o in orders])
        avg_order_value = total_value / total_orders if total_orders > 0 else Decimal("0")
        
        # Calculate risk score (0-100)
        risk_score = self._calculate_composite_score(
            rto_ratio, loss_amount, days_since_last_order, avg_order_value, total_orders
        )
        
        # Determine risk tag
        risk_tag = self._determine_risk_tag(risk_score, rto_ratio, loss_amount)
        
        return {
            "customer_id": customer_id,
            "risk_score": risk_score,
            "risk_tag": risk_tag,
            "factors": {
                "total_orders": total_orders,
                "rto_ratio": rto_ratio,
                "loss_amount": float(loss_amount),
                "days_since_last_order": days_since_last_order,
                "avg_order_value": float(avg_order_value)
            }
        }
    
    def _calculate_composite_score(
        self,
        rto_ratio: float,
        loss_amount: Decimal,
        days_since_last_order: int,
        avg_order_value: Decimal,
        total_orders: int
    ) -> float:
        """Calculate composite risk score from multiple factors"""
        score = 0.0
        
        # RTO ratio (40% weight)
        if rto_ratio > self.risk_thresholds["rto_ratio"]["high"]:
            score += 40
        elif rto_ratio > self.risk_thresholds["rto_ratio"]["medium"]:
            score += 25
        elif rto_ratio > self.risk_thresholds["rto_ratio"]["safe"]:
            score += 10
        else:
            score += 0
        
        # Loss amount (30% weight)
        if loss_amount > self.risk_thresholds["loss_amount"]["high"]:
            score += 30
        elif loss_amount > self.risk_thresholds["loss_amount"]["medium"]:
            score += 20
        elif loss_amount > self.risk_thresholds["loss_amount"]["safe"]:
            score += 10
        else:
            score += 0
        
        # Order recency (15% weight)
        if days_since_last_order > self.risk_thresholds["order_frequency"]["inactive_days"]:
            score += 15
        elif days_since_last_order > 60:
            score += 10
        elif days_since_last_order > 30:
            score += 5
        else:
            score += 0
        
        # Order value (10% weight) - higher value = higher risk for COD
        if avg_order_value > self.risk_thresholds["avg_order_value"]["high"]:
            score += 10
        elif avg_order_value < self.risk_thresholds["avg_order_value"]["low"]:
            score += 5
        else:
            score += 0
        
        # Order history (5% weight) - fewer orders = higher risk
        if total_orders < self.risk_thresholds["order_frequency"]["min_orders"]:
            score += 5
        else:
            score += 0
        
        return min(score, 100.0)  # Cap at 100
    
    def _determine_risk_tag(self, risk_score: float, rto_ratio: float, loss_amount: Decimal) -> RiskTag:
        """Determine risk tag based on score and key factors"""
        # High risk conditions
        if (risk_score >= 70 or 
            rto_ratio > self.risk_thresholds["rto_ratio"]["high"] or
            loss_amount > self.risk_thresholds["loss_amount"]["high"]):
            return RiskTag.HIGH
        
        # Safe conditions
        elif (risk_score < 30 and 
              rto_ratio < self.risk_thresholds["rto_ratio"]["safe"] and
              loss_amount < self.risk_thresholds["loss_amount"]["safe"]):
            return RiskTag.SAFE
        
        # Medium risk
        else:
            return RiskTag.MEDIUM
    
    def update_customer_risk(self, db: Session, customer_id: str) -> CustomerRisk:
        """Update customer risk profile"""
        risk_data = self.calculate_risk_score(db, customer_id)
        
        # Get or create customer risk record
        risk = db.query(CustomerRisk).filter(CustomerRisk.customer_id == customer_id).first()
        if not risk:
            risk = CustomerRisk(customer_id=customer_id)
            db.add(risk)
            db.flush()
        
        # Update risk fields
        risk.risk_score = Decimal(str(risk_data["risk_score"]))
        risk.risk_tag = risk_data["risk_tag"]
        risk.total_orders = risk_data["factors"]["total_orders"]
        risk.rto_count = int(risk_data["factors"]["total_orders"] * risk_data["factors"]["rto_ratio"])
        risk.loss_amount = Decimal(str(risk_data["factors"]["loss_amount"]))
        
        # Update last order date
        orders = db.query(Order).filter(Order.customer_id == customer_id).all()
        if orders:
            last_order = max([o for o in orders if o.created_at], key=lambda x: x.created_at)
            risk.last_order_date = last_order.created_at.date()
        
        risk.last_updated_at = datetime.now()
        
        db.commit()
        
        logger.info(f"Updated risk for customer {customer_id}: score={risk.risk_score}, tag={risk.risk_tag.value}")
        return risk
    
    def get_high_risk_customers(self, db: Session, limit: int = 50) -> List[CustomerRisk]:
        """Get high-risk customers for review"""
        return db.query(CustomerRisk).filter(
            CustomerRisk.risk_tag == RiskTag.HIGH
        ).order_by(CustomerRisk.risk_score.desc()).limit(limit).all()
    
    def get_risk_summary(self, db: Session) -> Dict:
        """Get overall risk summary"""
        total_customers = db.query(CustomerRisk).count()
        
        risk_counts = {}
        for tag in RiskTag:
            count = db.query(CustomerRisk).filter(CustomerRisk.risk_tag == tag).count()
            risk_counts[tag.value] = count
        
        # Calculate percentages
        risk_percentages = {}
        if total_customers > 0:
            for tag, count in risk_counts.items():
                risk_percentages[tag] = (count / total_customers) * 100
        
        # High risk details
        high_risk_customers = self.get_high_risk_customers(db, limit=10)
        
        return {
            "total_customers": total_customers,
            "risk_distribution": risk_counts,
            "risk_percentages": risk_percentages,
            "high_risk_customers": [
                {
                    "customer_id": risk.customer_id,
                    "risk_score": float(risk.risk_score),
                    "total_orders": risk.total_orders,
                    "rto_count": risk.rto_count,
                    "loss_amount": float(risk.loss_amount),
                    "last_order_date": risk.last_order_date.isoformat() if risk.last_order_date else None
                }
                for risk in high_risk_customers
            ]
        }
    
    def should_block_order(self, db: Session, customer_id: str, order_value: Decimal) -> Dict:
        """Determine if an order should be blocked based on risk"""
        risk = db.query(CustomerRisk).filter(CustomerRisk.customer_id == customer_id).first()
        
        if not risk:
            # New customer - allow with caution
            return {
                "should_block": False,
                "reason": "New customer",
                "recommendation": "Verify contact details"
            }
        
        # High risk + high value order = block
        if (risk.risk_tag == RiskTag.HIGH and 
            risk.risk_score >= 80 and 
            order_value > Decimal("2000")):
            return {
                "should_block": True,
                "reason": f"High risk customer (score: {risk.risk_score}) with high value order",
                "recommendation": "Require advance payment or block"
            }
        
        # Medium risk + COD + high value = caution
        if (risk.risk_tag == RiskTag.MEDIUM and 
            order_value > Decimal("5000")):
            return {
                "should_block": False,
                "reason": "Medium risk with high value order",
                "recommendation": "Prefer prepaid payment"
            }
        
        # High RTO ratio
        if risk.total_orders > 0:
            rto_ratio = risk.rto_count / risk.total_orders
            if rto_ratio > 0.5:  # >50% RTO rate
                return {
                    "should_block": True,
                    "reason": f"Very high RTO rate ({rto_ratio:.1%})",
                    "recommendation": "Block COD orders"
                }
        
        return {
            "should_block": False,
            "reason": "Acceptable risk",
            "recommendation": "Proceed normally"
        }


# Global risk engine instance
risk_engine = RiskEngine()


def run_risk_assessment(db: Session, customer_id: str):
    """Run risk assessment for a customer"""
    return risk_engine.update_customer_risk(db, customer_id)


def batch_risk_update(db: Session, limit: int = 100):
    """Update risk scores for customers (batch job)"""
    # Get customers with recent orders or outdated risk scores
    cutoff_date = datetime.now() - timedelta(days=7)
    
    customers = db.query(Order.customer_id).filter(
        Order.created_at >= cutoff_date
    ).distinct().limit(limit).all()
    
    updated_count = 0
    for (customer_id,) in customers:
        try:
            risk_engine.update_customer_risk(db, customer_id)
            updated_count += 1
        except Exception as e:
            logger.error(f"Failed to update risk for customer {customer_id}: {e}")
    
    logger.info(f"Batch risk update completed: {updated_count} customers updated")
    return updated_count
