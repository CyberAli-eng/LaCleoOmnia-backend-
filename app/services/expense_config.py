"""
Expense Configuration Engine - Dynamic expense management
"""
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Dict, List
from sqlalchemy.orm import Session

from app.models import Order, OrderExpense, ExpenseType, ExpenseSource

logger = logging.getLogger(__name__)


class ExpenseConfig:
    """Configuration for automatic expense calculations"""
    
    def __init__(self):
        self.configs = {
            # Gateway fees: percentage of order value
            ExpenseType.GATEWAY: {
                "prepaid_rate": Decimal("0.02"),  # 2% for prepaid
                "cod_rate": Decimal("0.025"),      # 2.5% for COD
                "min_fee": Decimal("5.0")          # Minimum ₹5
            },
            
            # COD fees: fixed + percentage
            ExpenseType.COD_FEE: {
                "fixed_fee": Decimal("30.0"),      # ₹30 fixed
                "percentage": Decimal("0.03"),      # 3% of order value
                "min_order_value": Decimal("100")   # Only for orders > ₹100
            },
            
            # Packaging fees: tiered by order value
            ExpenseType.FIXED: {
                "packaging_tiers": [
                    {"min_value": Decimal("0"), "max_value": Decimal("500"), "fee": Decimal("20")},
                    {"min_value": Decimal("500"), "max_value": Decimal("2000"), "fee": Decimal("40")},
                    {"min_value": Decimal("2000"), "max_value": Decimal("999999"), "fee": Decimal("60")}
                ]
            },
            
            # Overhead: percentage of total costs
            ExpenseType.OVERHEAD: {
                "rate": Decimal("0.05")  # 5% of total expenses
            }
        }
    
    def calculate_expense(self, expense_type: ExpenseType, order: Order, context: Optional[Dict] = None) -> Decimal:
        """Calculate expense amount based on type and order data"""
        if expense_type not in self.configs:
            return Decimal("0")
        
        config = self.configs[expense_type]
        order_value = Decimal(str(order.total_amount or 0))
        
        if expense_type == ExpenseType.GATEWAY:
            return self._calculate_gateway_fee(order_value, order, config)
        elif expense_type == ExpenseType.COD_FEE:
            return self._calculate_cod_fee(order_value, config)
        elif expense_type == ExpenseType.FIXED:
            return self._calculate_packaging_fee(order_value, config)
        elif expense_type == ExpenseType.OVERHEAD:
            return self._calculate_overhead(order, context, config)
        
        return Decimal("0")
    
    def _calculate_gateway_fee(self, order_value: Decimal, order: Order, config: Dict) -> Decimal:
        """Calculate payment gateway fee"""
        # Determine rate based on payment type
        if hasattr(order, 'payment_mode') and order.payment_mode:
            if order.payment_mode.value.upper() == 'COD':
                rate = config["cod_rate"]
            else:
                rate = config["prepaid_rate"]
        else:
            rate = config["prepaid_rate"]  # Default to prepaid
        
        fee = order_value * rate
        min_fee = config["min_fee"]
        
        return max(fee, min_fee)
    
    def _calculate_cod_fee(self, order_value: Decimal, config: Dict) -> Decimal:
        """Calculate COD processing fee"""
        min_order_value = config["min_order_value"]
        
        if order_value < min_order_value:
            return Decimal("0")
        
        fixed_fee = config["fixed_fee"]
        percentage_fee = order_value * config["percentage"]
        
        return fixed_fee + percentage_fee
    
    def _calculate_packaging_fee(self, order_value: Decimal, config: Dict) -> Decimal:
        """Calculate packaging fee based on tiered structure"""
        tiers = config["packaging_tiers"]
        
        for tier in tiers:
            if tier["min_value"] <= order_value < tier["max_value"]:
                return Decimal(str(tier["fee"]))
        
        return Decimal("0")
    
    def _calculate_overhead(self, order: Order, context: Optional[Dict], config: Dict) -> Decimal:
        """Calculate overhead as percentage of other expenses"""
        if not context or "total_other_expenses" not in context:
            return Decimal("0")
        
        total_other_expenses = Decimal(str(context["total_other_expenses"]))
        return total_other_expenses * config["rate"]
    
    def update_config(self, expense_type: ExpenseType, new_config: Dict):
        """Update expense configuration"""
        if expense_type in self.configs:
            self.configs[expense_type].update(new_config)
            logger.info(f"Updated expense config for {expense_type}")
        else:
            self.configs[expense_type] = new_config
            logger.info(f"Added new expense config for {expense_type}")
    
    def get_config(self, expense_type: ExpenseType) -> Optional[Dict]:
        """Get expense configuration"""
        return self.configs.get(expense_type)


# Global expense config instance
expense_config = ExpenseConfig()


def apply_expense_configs(db: Session, order_id: str):
    """Apply all expense configurations to an order"""
    from app.services.finance_engine import compute_order_finance
    
    # This will trigger expense calculation with new configs
    compute_order_finance(db, order_id)


def add_manual_expense(
    db: Session,
    order_id: str,
    finance_id: str,
    expense_type: ExpenseType,
    amount: Decimal,
    description: str,
    effective_date: Optional[date] = None
) -> OrderExpense:
    """Add a manual expense to an order"""
    expense = OrderExpense(
        order_id=order_id,
        order_finance_id=finance_id,
        type=expense_type,
        source=ExpenseSource.MANUAL,
        amount=amount,
        effective_date=effective_date or date.today(),
        editable=True,
        description=description
    )
    
    db.add(expense)
    db.commit()
    
    logger.info(f"Added manual expense: {expense_type.value} = {amount} for order {order_id}")
    return expense


def get_expense_summary(db: Session, user_id: Optional[str] = None) -> Dict:
    """Get expense summary by type"""
    query = db.query(OrderExpense)
    
    if user_id:
        query = query.join(OrderFinance).join(Order).filter(Order.user_id == user_id)
    
    expenses = query.all()
    
    summary = {}
    for expense_type in ExpenseType:
        total = sum(exp.amount for exp in expenses if exp.type == expense_type)
        summary[expense_type.value] = float(total)
    
    return summary
