"""
Finance Engine Tests - Comprehensive test coverage
"""
import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal
from sqlalchemy.orm import Session

from app.models import (
    Order, OrderFinance, OrderExpense, OrderSettlement, CustomerRisk,
    OrderItem, PaymentType, FulfilmentStatus, ProfitStatus, ExpenseType, RiskTag
)
from app.services.finance_engine import compute_order_finance
from app.services.expense_config import expense_config, add_manual_expense
from app.services.settlement_engine import settlement_engine
from app.services.risk_engine import risk_engine


class TestFinanceEngine:
    """Test core finance engine functionality"""
    
    def test_compute_order_finance_delivered_prepaid(self, db_session, test_order):
        """Test finance calculation for delivered prepaid order"""
        # Setup order as delivered prepaid
        test_order.total_amount = Decimal("1000.00")
        test_order.payment_mode = "PREPAID"
        test_order.status = "DELIVERED"
        test_order.created_at = datetime.now()
        db_session.commit()
        
        # Create order items
        from app.models import SkuCost
        sku_cost = SkuCost(
            sku="TEST-SKU",
            product_cost=Decimal("300"),
            packaging_cost=Decimal("50"),
            box_cost=Decimal("20"),
            inbound_cost=Decimal("30")
        )
        db_session.add(sku_cost)
        
        order_item = OrderItem(
            order_id=test_order.id,
            sku="TEST-SKU",
            quantity=2,
            price=Decimal("500")
        )
        db_session.add(order_item)
        db_session.commit()
        
        # Compute finance
        finance = compute_order_finance(db_session, test_order.id)
        
        # Assertions
        assert finance.order_value == Decimal("1000.00")
        assert finance.revenue_realized == Decimal("1000.00")  # Delivered = full revenue
        assert finance.payment_type == PaymentType.PREPAID
        assert finance.fulfilment_status == FulfilmentStatus.DELIVERED
        assert finance.profit_status == ProfitStatus.PROFIT  # Should be profitable
        assert finance.net_profit > 0
        
        # Check expenses were created
        expenses = db_session.query(OrderExpense).filter(OrderExpense.order_finance_id == finance.id).all()
        assert len(expenses) > 0
        
        # Check settlements were created
        settlements = db_session.query(OrderSettlement).filter(OrderSettlement.order_finance_id == finance.id).all()
        assert len(settlements) > 0
    
    def test_compute_order_finance_rto_cod(self, db_session, test_order):
        """Test finance calculation for RTO COD order"""
        # Setup order as RTO COD
        test_order.total_amount = Decimal("1000.00")
        test_order.payment_mode = "COD"
        test_order.status = "RTO"
        test_order.created_at = datetime.now()
        db_session.commit()
        
        # Compute finance
        finance = compute_order_finance(db_session, test_order.id)
        
        # Assertions
        assert finance.order_value == Decimal("1000.00")
        assert finance.revenue_realized == Decimal("0.00")  # RTO = no revenue
        assert finance.payment_type == PaymentType.COD
        assert finance.fulfilment_status == FulfilmentStatus.RTO
        assert finance.profit_status == ProfitStatus.LOSS  # Should be loss
        assert finance.net_profit < 0
    
    def test_compute_order_finance_cancelled(self, db_session, test_order):
        """Test finance calculation for cancelled order"""
        # Setup order as cancelled
        test_order.total_amount = Decimal("1000.00")
        test_order.payment_mode = "PREPAID"
        test_order.status = "CANCELLED"
        test_order.created_at = datetime.now()
        db_session.commit()
        
        # Compute finance
        finance = compute_order_finance(db_session, test_order.id)
        
        # Assertions
        assert finance.order_value == Decimal("1000.00")
        assert finance.revenue_realized == Decimal("0.00")  # Cancelled = no revenue
        assert finance.fulfilment_status == FulfilmentStatus.CANCELLED
        assert finance.profit_status == ProfitStatus.LOSS  # Should be loss


class TestExpenseConfig:
    """Test expense configuration engine"""
    
    def test_gateway_fee_calculation(self, test_order):
        """Test payment gateway fee calculation"""
        test_order.total_amount = Decimal("1000.00")
        test_order.payment_mode = "PREPAID"
        
        fee = expense_config.calculate_expense(ExpenseType.GATEWAY, test_order)
        
        # Should be 2% of 1000 = 20, but minimum 5
        assert fee == Decimal("20.00")
    
    def test_gateway_fee_cod(self, test_order):
        """Test gateway fee for COD orders"""
        test_order.total_amount = Decimal("1000.00")
        test_order.payment_mode = "COD"
        
        fee = expense_config.calculate_expense(ExpenseType.GATEWAY, test_order)
        
        # Should be 2.5% of 1000 = 25
        assert fee == Decimal("25.00")
    
    def test_cod_fee_calculation(self, test_order):
        """Test COD fee calculation"""
        test_order.total_amount = Decimal("1000.00")
        test_order.payment_mode = "COD"
        
        fee = expense_config.calculate_expense(ExpenseType.COD_FEE, test_order)
        
        # Should be 30 fixed + 3% of 1000 = 60
        assert fee == Decimal("60.00")
    
    def test_packaging_fee_tiers(self, test_order):
        """Test packaging fee tiered calculation"""
        # Test different order values
        test_cases = [
            (Decimal("300"), Decimal("20")),   # 0-500 tier
            (Decimal("1000"), Decimal("40")), # 500-2000 tier
            (Decimal("5000"), Decimal("60"))   # 2000+ tier
        ]
        
        for order_value, expected_fee in test_cases:
            test_order.total_amount = order_value
            fee = expense_config.calculate_expense(ExpenseType.FIXED, test_order)
            assert fee == expected_fee


class TestSettlementEngine:
    """Test settlement engine functionality"""
    
    def test_expected_date_calculation(self, test_order):
        """Test expected settlement date calculation"""
        test_order.created_at = datetime(2024, 1, 1)
        test_order.payment_mode = "PREPAID"
        
        # Payment gateway prepaid should be T+7
        expected_date = settlement_engine.compute_expected_date(test_order, "Payment Gateway")
        assert expected_date == date(2024, 1, 8)
        
        # Payment gateway COD should be T+15
        test_order.payment_mode = "COD"
        expected_date = settlement_engine.compute_expected_date(test_order, "Payment Gateway")
        assert expected_date == date(2024, 1, 16)
    
    def test_marketplace_settlement(self, test_order):
        """Test marketplace settlement calculation"""
        test_order.created_at = datetime(2024, 1, 1)
        
        expected_date = settlement_engine.compute_expected_date(test_order, "Marketplace")
        assert expected_date == date(2024, 1, 31)  # T+30


class TestRiskEngine:
    """Test risk engine functionality"""
    
    def test_new_customer_risk(self, db_session, test_order):
        """Test risk calculation for new customer"""
        customer_id = "new_customer_123"
        test_order.customer_id = customer_id
        test_order.created_at = datetime.now()
        db_session.commit()
        
        risk_data = risk_engine.calculate_risk_score(db_session, customer_id)
        
        # New customer should have neutral risk
        assert risk_data["risk_score"] == 50.0
        assert risk_data["risk_tag"] == RiskTag.MEDIUM
        assert risk_data["factors"]["total_orders"] == 1
    
    def test_high_rto_customer(self, db_session, test_order):
        """Test risk calculation for high RTO customer"""
        customer_id = "high_rto_customer"
        test_order.customer_id = customer_id
        test_order.created_at = datetime.now()
        db_session.commit()
        
        # Create multiple orders with high RTO rate
        for i in range(10):
            order = Order(
                id=f"order_{i}",
                customer_id=customer_id,
                total_amount=Decimal("1000.00"),
                status="RTO" if i < 7 else "DELIVERED",  # 70% RTO rate
                created_at=datetime.now() - timedelta(days=i)
            )
            db_session.add(order)
        
        db_session.commit()
        
        risk_data = risk_engine.calculate_risk_score(db_session, customer_id)
        
        # High RTO should result in HIGH risk
        assert risk_data["risk_tag"] == RiskTag.HIGH
        assert risk_data["risk_score"] >= 70
        assert risk_data["factors"]["rto_ratio"] > 0.4
    
    def test_should_block_order(self, db_session, test_order):
        """Test order blocking logic"""
        customer_id = "test_block_customer"
        
        # Create high risk customer
        risk = CustomerRisk(
            customer_id=customer_id,
            risk_tag=RiskTag.HIGH,
            risk_score=Decimal("85"),
            total_orders=5,
            rto_count=4,
            loss_amount=Decimal("2000")
        )
        db_session.add(risk)
        db_session.commit()
        
        # High value order should be blocked
        block_decision = risk_engine.should_block_order(db_session, customer_id, Decimal("3000"))
        assert block_decision["should_block"] is True
        assert "high risk" in block_decision["reason"].lower()
        
        # Low value order might not be blocked
        block_decision = risk_engine.should_block_order(db_session, customer_id, Decimal("500"))
        assert block_decision["should_block"] is False


class TestFinanceIntegration:
    """Integration tests for complete finance workflow"""
    
    def test_complete_order_lifecycle(self, db_session, test_order):
        """Test complete order lifecycle from creation to settlement"""
        # Setup order
        test_order.total_amount = Decimal("1000.00")
        test_order.payment_mode = "PREPAID"
        test_order.status = "NEW"
        test_order.customer_id = "integration_test_customer"
        test_order.created_at = datetime.now()
        db_session.commit()
        
        # Step 1: Compute initial finance
        finance = compute_order_finance(db_session, test_order.id)
        assert finance.fulfilment_status == FulfilmentStatus.IN_TRANSIT
        assert finance.revenue_realized == Decimal("0.00")  # Not delivered yet
        
        # Step 2: Mark as delivered
        test_order.status = "DELIVERED"
        db_session.commit()
        
        # Recompute finance
        finance = compute_order_finance(db_session, test_order.id)
        assert finance.fulfilment_status == FulfilmentStatus.DELIVERED
        assert finance.revenue_realized == Decimal("1000.00")
        
        # Step 3: Add manual expense
        manual_expense = add_manual_expense(
            db_session,
            test_order.id,
            finance.id,
            ExpenseType.OVERHEAD,
            Decimal("50"),
            "Manual overhead adjustment"
        )
        assert manual_expense.source.value == "MANUAL"
        assert manual_expense.editable is True
        
        # Step 4: Mark settlement as settled
        settlements = db_session.query(OrderSettlement).filter(
            OrderSettlement.order_finance_id == finance.id
        ).all()
        assert len(settlements) > 0
        
        settlement = settlements[0]
        settled = settlement_engine.mark_settled(
            db_session,
            settlement.id,
            actual_date=date.today(),
            reference_id="SETTLE_123"
        )
        assert settled.status.value == "SETTLED"
        assert settled.actual_date is not None
        
        # Step 5: Update customer risk
        risk = risk_engine.update_customer_risk(db_session, test_order.customer_id)
        assert risk.customer_id == test_order.customer_id
        assert risk.total_orders >= 1


# Test fixtures
@pytest.fixture
def test_order(db_session):
    """Create test order"""
    from app.models import User
    user = User(
        name="Test User",
        email="test@example.com",
        password_hash="hash",
        role="STAFF"
    )
    db_session.add(user)
    db_session.flush()
    
    order = Order(
        id="test_order_123",
        user_id=user.id,
        customer_id="test_customer_123",
        total_amount=Decimal("1000.00"),
        created_at=datetime.now()
    )
    db_session.add(order)
    db_session.commit()
    return order


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
