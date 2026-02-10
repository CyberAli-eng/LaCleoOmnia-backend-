"""
Finance API Routes - Comprehensive financial endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List
from datetime import date, timedelta, datetime
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.models import (
    User,
    Order,
    ChannelAccount,
    OrderFinance,
    OrderExpense,
    OrderSettlement,
    CustomerRisk,
    ExpenseType,
    SettlementStatus,
    ExpenseSource,
    ExpenseRule,
    ExpenseRuleValueType,
    FulfilmentStatus,
)
from app.auth import get_current_user
from app.services.finance_engine import compute_order_finance, get_finance_overview
from app.services.expense_config import add_manual_expense, get_expense_summary
from app.services.settlement_engine import settlement_engine, create_manual_settlement, run_settlement_jobs
from app.services.risk_engine import risk_engine, run_risk_assessment

router = APIRouter()


# Pydantic models
class ExpenseCreate(BaseModel):
    order_id: str
    expense_type: ExpenseType
    amount: float
    description: str
    effective_date: Optional[date] = None


class SettlementCreate(BaseModel):
    order_id: str
    partner: str
    amount: float
    expected_date: date
    reference_id: Optional[str] = None
    notes: Optional[str] = None


class SettlementUpdate(BaseModel):
    actual_date: Optional[date] = None
    reference_id: Optional[str] = None
    notes: Optional[str] = None


class ExpenseRuleCreate(BaseModel):
    type: str  # GATEWAY_FEE | COD_FEE | PACKAGING_FEE
    name: str
    value: float
    valueType: ExpenseRuleValueType
    effectiveFrom: date
    effectiveTo: Optional[date] = None
    platform: Optional[str] = None


class ExpenseRuleUpdate(BaseModel):
    value: Optional[float] = None
    valueType: Optional[ExpenseRuleValueType] = None
    effectiveFrom: Optional[date] = None
    effectiveTo: Optional[date] = None
    platform: Optional[str] = None


# Finance Overview
@router.get("/overview")
async def get_finance_overview_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get finance overview statistics"""
    return get_finance_overview(db, current_user.id)


# Order Finance Details
@router.get("/orders/{order_id}")
async def get_order_finance(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get detailed finance information for a specific order"""
    # Verify order belongs to user (via ChannelAccount.user_id; Order has no user_id)
    account_ids = [
        ca.id
        for ca in db.query(ChannelAccount).filter(ChannelAccount.user_id == current_user.id).all()
    ]
    order = (
        db.query(Order)
        .filter(Order.id == order_id, Order.channel_account_id.in_(account_ids))
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Get finance record
    finance = db.query(OrderFinance).filter(OrderFinance.order_id == order_id).first()
    if not finance:
        # Compute finance if not exists
        finance = compute_order_finance(db, order_id)
    
    # Get expenses and settlements
    expenses = db.query(OrderExpense).filter(OrderExpense.order_finance_id == finance.id).all()
    settlements = db.query(OrderSettlement).filter(OrderSettlement.order_finance_id == finance.id).all()
    
    # Flattened keys for frontend drawer (revenue, netProfit, expenseBreakdown, settlementTimeline, risk)
    expense_breakdown = [{"type": exp.type.value, "amount": float(exp.amount), "description": exp.description or ""} for exp in expenses]
    settlement_timeline = [
        {"partner": setl.partner, "expected_date": setl.expected_date.isoformat(), "actual_date": setl.actual_date.isoformat() if setl.actual_date else None, "amount": float(setl.amount), "status": setl.status.value}
        for setl in settlements
    ]
    return {
        "revenue": float(finance.revenue_realized),
        "order_value": float(finance.order_value),
        "netProfit": float(finance.net_profit),
        "total_expense": float(finance.total_expense),
        "status": finance.fulfilment_status.value,
        "expenseBreakdown": expense_breakdown,
        "settlementTimeline": settlement_timeline,
        "risk": finance.profit_status.value,
        "finance": {
            "id": finance.id,
            "order_value": float(finance.order_value),
            "revenue_realized": float(finance.revenue_realized),
            "payment_type": finance.payment_type.value,
            "fulfilment_status": finance.fulfilment_status.value,
            "total_expense": float(finance.total_expense),
            "net_profit": float(finance.net_profit),
            "profit_status": finance.profit_status.value,
            "created_at": finance.created_at.isoformat(),
            "updated_at": finance.updated_at.isoformat()
        },
        "expenses": [
            {"id": exp.id, "type": exp.type.value, "source": exp.source.value, "amount": float(exp.amount), "effective_date": exp.effective_date.isoformat(), "editable": exp.editable, "description": exp.description, "created_at": exp.created_at.isoformat()}
            for exp in expenses
        ],
        "settlements": [
            {"id": setl.id, "partner": setl.partner, "expected_date": setl.expected_date.isoformat(), "actual_date": setl.actual_date.isoformat() if setl.actual_date else None, "amount": float(setl.amount), "status": setl.status.value, "reference_id": setl.reference_id, "notes": setl.notes, "created_at": setl.created_at.isoformat()}
            for setl in settlements
        ]
    }


# P&L Report
@router.get("/pnl")
async def get_pnl_report(
    period: Optional[str] = Query(None, description="7d, 30d, 90d, 1y"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    channel: Optional[str] = Query(None),
    sku: Optional[str] = Query(None),
    courier: Optional[str] = Query(None),
    payment: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get Profit & Loss report. Supports period (7d,30d,90d,1y) or start_date/end_date, and filters."""
    query = db.query(OrderFinance).join(Order, OrderFinance.order_id == Order.id).filter(Order.user_id == current_user.id)

    # Resolve date range from period if not provided
    if not start_date or not end_date:
        today = date.today()
        if period == "7d":
            end_date = end_date or today
            start_date = start_date or (end_date - timedelta(days=7))
        elif period == "30d":
            end_date = end_date or today
            start_date = start_date or (end_date - timedelta(days=30))
        elif period == "90d":
            end_date = end_date or today
            start_date = start_date or (end_date - timedelta(days=90))
        elif period == "1y":
            end_date = end_date or today
            start_date = start_date or (end_date - timedelta(days=365))
        else:
            end_date = end_date or today
            start_date = start_date or (end_date - timedelta(days=30))

    if start_date:
        query = query.filter(func.date(Order.created_at) >= start_date)
    if end_date:
        query = query.filter(func.date(Order.created_at) <= end_date)
    # Optional filters (apply if backend has these on Order)
    if channel:
        if hasattr(Order, "channel_id"):
            query = query.filter(Order.channel_id == channel)
        elif hasattr(Order, "source"):
            query = query.filter(Order.source == channel)
    if payment:
        if hasattr(Order, "payment_mode"):
            from app.models import PaymentType
            try:
                query = query.filter(Order.payment_mode == getattr(PaymentType, payment.upper(), None))
            except Exception:
                pass

    finances = query.all()

    total_revenue = sum(f.revenue_realized for f in finances)
    total_expenses = sum(f.total_expense for f in finances)
    total_profit = sum(f.net_profit for f in finances)
    margin_pct = float(total_profit / total_revenue * 100) if total_revenue > 0 else 0

    # Expense breakdown by category
    expense_breakdown = {}
    for finance in finances:
        expenses = db.query(OrderExpense).filter(OrderExpense.order_finance_id == finance.id).all()
        for exp in expenses:
            exp_type = exp.type.value
            if exp_type not in expense_breakdown:
                expense_breakdown[exp_type] = 0
            expense_breakdown[exp_type] += float(exp.amount)

    # Period data (daily/weekly buckets for charts)
    period_data = []
    if finances:
        orders_by_date = {}
        for f in finances:
            o = db.query(Order).filter(Order.id == f.order_id).first()
            d = (o.created_at.date() if o and o.created_at else date.today()).isoformat()
            if d not in orders_by_date:
                orders_by_date[d] = {"revenue": 0, "expenses": 0, "profit": 0, "count": 0}
            orders_by_date[d]["revenue"] += float(f.revenue_realized)
            orders_by_date[d]["expenses"] += float(f.total_expense)
            orders_by_date[d]["profit"] += float(f.net_profit)
            orders_by_date[d]["count"] += 1
        for d in sorted(orders_by_date.keys()):
            row = orders_by_date[d]
            period_data.append({
                "period": d,
                "revenue": row["revenue"],
                "expenses": row["expenses"],
                "profit": row["profit"],
                "orderCount": row["count"],
                "avgOrderValue": row["revenue"] / row["count"] if row["count"] else 0,
                "margin": (row["profit"] / row["revenue"] * 100) if row["revenue"] else 0,
            })

    expense_categories = [
        {"category": k, "amount": v, "percentage": (v / total_expenses * 100) if total_expenses else 0}
        for k, v in expense_breakdown.items()
    ]
    revenue_breakdown = [{"source": "Orders", "amount": float(total_revenue), "percentage": 100.0}]

    return {
        "totalRevenue": float(total_revenue),
        "totalExpenses": float(total_expenses),
        "netProfit": float(total_profit),
        "margin": margin_pct,
        "periodData": period_data,
        "expenseCategories": expense_categories,
        "revenueBreakdown": revenue_breakdown,
    }


# Settlements
@router.get("/settlements")
async def get_settlements(
    status: Optional[SettlementStatus] = Query(None),
    partner: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get settlements list and summary for frontend (settlements[], summary)."""
    query = (
        db.query(OrderSettlement)
        .join(OrderFinance, OrderSettlement.order_finance_id == OrderFinance.id)
        .join(Order, OrderFinance.order_id == Order.id)
        .filter(Order.user_id == current_user.id)
    )
    if status:
        query = query.filter(OrderSettlement.status == status)
    if partner:
        query = query.filter(OrderSettlement.partner == partner)
    all_settlements = query.all()

    total_pending = sum(1 for s in all_settlements if s.status.value == "PENDING")
    total_processing = sum(1 for s in all_settlements if s.status.value == "PROCESSING")
    total_settled = sum(1 for s in all_settlements if s.status.value == "SETTLED")
    total_failed = sum(1 for s in all_settlements if s.status.value == "FAILED")
    overdue = [
        s for s in all_settlements
        if s.status.value == "PENDING" and s.expected_date and s.expected_date < date.today()
    ]
    total_overdue = len(overdue)
    pending_amount = sum(float(s.amount) for s in all_settlements if s.status.value == "PENDING")
    processing_amount = sum(float(s.amount) for s in all_settlements if s.status.value == "PROCESSING")
    settled_amount = sum(float(s.amount) for s in all_settlements if s.status.value == "SETTLED")
    failed_amount = sum(float(s.amount) for s in all_settlements if s.status.value == "FAILED")
    overdue_amount = sum(float(s.amount) for s in overdue)

    # Get channel_order_id for display (from orders table)
    order_ids = [s.order_id for s in all_settlements]
    orders_map = {}
    if order_ids:
        for o in db.query(Order).filter(Order.id.in_(order_ids)).all():
            orders_map[o.id] = getattr(o, "channel_order_id", None) or o.id[:8]

    settlements_list = [
        {
            "id": s.id,
            "orderId": s.order_id,
            "channelOrderId": orders_map.get(s.order_id, s.order_id[:8]),
            "channel": s.partner,
            "paymentMethod": "COD" if "courier" in s.partner.lower() or "COD" in s.partner else "PREPAID",
            "amount": float(s.amount),
            "status": s.status.value,
            "expectedDate": s.expected_date.isoformat() if s.expected_date else None,
            "settledDate": s.actual_date.isoformat() if s.actual_date else None,
            "transactionId": s.reference_id,
            "failureReason": getattr(s, "failure_reason", None),
        }
        for s in all_settlements
    ]

    return {
        "settlements": settlements_list,
        "summary": {
            "totalPending": total_pending,
            "totalProcessing": total_processing,
            "totalSettled": total_settled,
            "totalFailed": total_failed,
            "totalOverdue": total_overdue,
            "pendingAmount": pending_amount,
            "processingAmount": processing_amount,
            "settledAmount": settled_amount,
            "failedAmount": failed_amount,
            "overdueAmount": overdue_amount,
        },
    }


@router.post("/settlements")
async def create_settlement(
    settlement: SettlementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create manual settlement"""
    # Verify order belongs to user
    from app.models import Order
    order = db.query(Order).filter(Order.id == settlement.order_id, Order.user_id == current_user.id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Get finance record
    finance = db.query(OrderFinance).filter(OrderFinance.order_id == settlement.order_id).first()
    if not finance:
        finance = compute_order_finance(db, settlement.order_id)
    
    # Create settlement
    new_settlement = create_manual_settlement(
        db=db,
        order_id=settlement.order_id,
        finance_id=finance.id,
        partner=settlement.partner,
        amount=settlement.amount,
        expected_date=settlement.expected_date,
        reference_id=settlement.reference_id,
        notes=settlement.notes
    )
    
    return {"id": new_settlement.id, "message": "Settlement created successfully"}


@router.patch("/settlements/{settlement_id}")
async def update_settlement(
    settlement_id: str,
    update: SettlementUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update settlement (mark as settled)"""
    # Verify settlement belongs to user
    settlement = db.query(OrderSettlement).join(OrderFinance).join(Order).filter(
        OrderSettlement.id == settlement_id,
        Order.user_id == current_user.id
    ).first()
    
    if not settlement:
        raise HTTPException(status_code=404, detail="Settlement not found")
    
    # Update settlement
    updated = settlement_engine.mark_settled(
        db=db,
        settlement_id=settlement_id,
        actual_date=update.actual_date,
        reference_id=update.reference_id,
        notes=update.notes
    )
    
    return {"message": "Settlement updated successfully"}


@router.get("/settlements/forecast")
async def get_cashflow_forecast(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get cashflow forecast"""
    return settlement_engine.get_cashflow_forecast(db, days, current_user.id)


# Risk Management
@router.get("/risk")
async def get_risk_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get risk summary and customers list for frontend (customers[], summary)."""
    customer_ids = [
        cid[0] for cid in db.query(Order.customer_id).filter(
            Order.user_id == current_user.id,
            Order.customer_id.isnot(None)
        ).distinct().all()
    ]
    if not customer_ids:
        return {
            "customers": [],
            "summary": {
                "totalCustomers": 0,
                "highRiskCustomers": 0,
                "mediumRiskCustomers": 0,
                "lowRiskCustomers": 0,
                "totalRtoLoss": 0,
                "totalFailedPayments": 0,
                "rtoRate": 0,
                "failureRate": 0,
            },
        }

    risks = db.query(CustomerRisk).filter(CustomerRisk.customer_id.in_(customer_ids)).all()
    total_rto_loss = sum(float(r.loss_amount) for r in risks)

    high = [r for r in risks if r.risk_tag.value == "HIGH"]
    medium = [r for r in risks if r.risk_tag.value == "MEDIUM"]
    low = [r for r in risks if r.risk_tag.value in ("SAFE", "LOW")]

    # Build customer list: get first order per customer for email/address
    first_order = {}
    for o in db.query(Order).filter(Order.customer_id.in_(customer_ids), Order.user_id == current_user.id).all():
        if o.customer_id and o.customer_id not in first_order:
            first_order[o.customer_id] = o

    customers_list = []
    for risk in risks:
        o = first_order.get(risk.customer_id)
        successful = max(0, risk.total_orders - risk.rto_count)
        risk_level = "HIGH" if risk.risk_tag.value == "HIGH" else "MEDIUM" if risk.risk_tag.value == "MEDIUM" else "LOW"
        customers_list.append({
            "id": risk.customer_id,
            "name": getattr(o, "customer_name", None) or risk.customer_id[:8],
            "email": getattr(o, "customer_email", None) or "",
            "phone": getattr(o, "customer_phone", None) or "",
            "address": (getattr(o, "shipping_address", None) or getattr(o, "billing_address", None)) or "",
            "totalOrders": risk.total_orders,
            "successfulOrders": successful,
            "failedOrders": 0,
            "rtoOrders": risk.rto_count,
            "totalValue": 0,
            "averageOrderValue": 0,
            "riskScore": int(float(risk.risk_score)),
            "riskLevel": risk_level,
            "lastOrderDate": risk.last_order_date.isoformat() if risk.last_order_date else None,
            "issues": [],
        })

    return {
        "customers": customers_list,
        "summary": {
            "totalCustomers": len(risks),
            "highRiskCustomers": len(high),
            "mediumRiskCustomers": len(medium),
            "lowRiskCustomers": len(low),
            "totalRtoLoss": total_rto_loss,
            "totalFailedPayments": 0,
            "rtoRate": round(sum(r.rto_count for r in risks) / sum(r.total_orders for r in risks) * 100, 1) if risks and sum(r.total_orders for r in risks) else 0,
            "failureRate": 0,
        },
    }


@router.get("/risk/{customer_id}")
async def get_customer_risk(
    customer_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get detailed risk profile for a customer"""
    # Verify customer belongs to user
    from app.models import Order
    order = db.query(Order).filter(
        Order.customer_id == customer_id,
        Order.user_id == current_user.id
    ).first()
    
    if not order:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Get or calculate risk
    risk = db.query(CustomerRisk).filter(CustomerRisk.customer_id == customer_id).first()
    if not risk:
        risk = run_risk_assessment(db, customer_id)
    
    # Get detailed risk analysis
    risk_analysis = risk_engine.calculate_risk_score(db, customer_id)
    
    return {
        "customer_id": customer_id,
        "risk_score": float(risk.risk_score),
        "risk_tag": risk.risk_tag.value,
        "total_orders": risk.total_orders,
        "rto_count": risk.rto_count,
        "loss_amount": float(risk.loss_amount),
        "last_order_date": risk.last_order_date.isoformat() if risk.last_order_date else None,
        "risk_factors": risk_analysis["factors"]
    }


# Expense Management
@router.post("/expenses")
async def add_expense(
    expense: ExpenseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Add manual expense to an order"""
    # Verify order belongs to user
    from app.models import Order
    order = db.query(Order).filter(Order.id == expense.order_id, Order.user_id == current_user.id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Get finance record
    finance = db.query(OrderFinance).filter(OrderFinance.order_id == expense.order_id).first()
    if not finance:
        finance = compute_order_finance(db, expense.order_id)
    
    # Add expense
    new_expense = add_manual_expense(
        db=db,
        order_id=expense.order_id,
        finance_id=finance.id,
        expense_type=expense.expense_type,
        amount=expense.amount,
        description=expense.description,
        effective_date=expense.effective_date
    )
    
    # Recalculate finance
    compute_order_finance(db, expense.order_id)
    
    return {"id": new_expense.id, "message": "Expense added successfully"}


# Frontend-friendly single-expense endpoints (ExpenseEditor)
def _map_ui_category_to_expense_type(category: str) -> ExpenseType:
    c = (category or "").strip().lower()
    if c in ("shipping", "forward shipping", "courier"):
        return ExpenseType.FWD_SHIP
    if c in ("returns", "reverse", "reverse shipping", "rto"):
        return ExpenseType.REV_SHIP
    if c in ("marketing", "ads", "ad spend"):
        return ExpenseType.ADS
    if c in ("payment processing", "gateway", "gateway fee"):
        return ExpenseType.GATEWAY
    if c in ("cod", "cod fee", "cod processing"):
        return ExpenseType.COD_FEE
    if c in ("packaging", "platform fees", "customer service", "other", "overhead"):
        return ExpenseType.OVERHEAD
    return ExpenseType.OVERHEAD


class ExpenseUpdate(BaseModel):
    category: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[float] = None


@router.patch("/expense/{expense_id}")
async def update_expense(
    expense_id: str,
    body: ExpenseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exp = db.query(OrderExpense).filter(OrderExpense.id == expense_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail="Expense not found")
    order = db.query(Order).filter(Order.id == exp.order_id, Order.user_id == current_user.id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if not exp.editable or exp.source != ExpenseSource.MANUAL:
        raise HTTPException(status_code=403, detail="This expense cannot be edited")

    if body.category is not None:
        exp.type = _map_ui_category_to_expense_type(body.category)
    if body.description is not None:
        exp.description = body.description
    if body.amount is not None:
        exp.amount = body.amount
    db.commit()

    compute_order_finance(db, exp.order_id)
    return {"message": "Expense updated"}


@router.delete("/expense/{expense_id}")
async def delete_expense(
    expense_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exp = db.query(OrderExpense).filter(OrderExpense.id == expense_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail="Expense not found")
    order = db.query(Order).filter(Order.id == exp.order_id, Order.user_id == current_user.id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if not exp.editable or exp.source != ExpenseSource.MANUAL:
        raise HTTPException(status_code=403, detail="This expense cannot be deleted")

    order_id = exp.order_id
    db.delete(exp)
    db.commit()

    compute_order_finance(db, order_id)
    return {"message": "Expense deleted"}


# Expense rules (versioned)
@router.get("/expense-rules")
async def list_expense_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rules = (
        db.query(ExpenseRule)
        .filter(ExpenseRule.user_id == current_user.id)
        .order_by(ExpenseRule.type.asc(), ExpenseRule.effective_from.desc())
        .all()
    )
    return {
        "rules": [
            {
                "id": r.id,
                "type": r.type,
                "name": r.name,
                "value": float(r.value or 0),
                "valueType": r.value_type.value,
                "effectiveFrom": r.effective_from.isoformat(),
                "effectiveTo": r.effective_to.isoformat() if r.effective_to else None,
                "platform": r.platform,
            }
            for r in rules
        ]
    }


@router.post("/expense-rules")
async def create_expense_rule(
    body: ExpenseRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rule = ExpenseRule(
        user_id=current_user.id,
        type=(body.type or "").strip().upper(),
        name=(body.name or "").strip()[:255],
        value=body.value,
        value_type=body.valueType,
        effective_from=body.effectiveFrom,
        effective_to=body.effectiveTo,
        platform=(body.platform or "").strip().lower() or None,
    )
    db.add(rule)
    db.commit()
    return {"id": rule.id, "message": "Rule created"}


@router.patch("/expense-rules/{rule_id}")
async def update_expense_rule(
    rule_id: str,
    body: ExpenseRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rule = db.query(ExpenseRule).filter(ExpenseRule.id == rule_id, ExpenseRule.user_id == current_user.id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    if body.value is not None:
        rule.value = body.value
    if body.valueType is not None:
        rule.value_type = body.valueType
    if body.effectiveFrom is not None:
        rule.effective_from = body.effectiveFrom
    if body.effectiveTo is not None:
        rule.effective_to = body.effectiveTo
    if body.platform is not None:
        rule.platform = (body.platform or "").strip().lower() or None
    db.commit()
    return {"message": "Rule updated"}


@router.get("/ads")
async def get_ads_attribution(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Ads attribution (v1): summary from ad_spend_daily + overall orders/profit by date.
    True campaign-level attribution is a future extension.
    """
    from app.models import AdSpendDaily

    end = date.today()
    start = end - timedelta(days=days)

    spends = (
        db.query(AdSpendDaily)
        .filter(AdSpendDaily.date >= start, AdSpendDaily.date <= end)
        .all()
    )
    spend_by_platform: dict[str, float] = {}
    total_spend = 0.0
    for row in spends:
        p = (row.platform or "unknown").lower()
        amt = float(row.spend or 0)
        spend_by_platform[p] = spend_by_platform.get(p, 0.0) + amt
        total_spend += amt

    # Overall revenue/profit in this window (not attributed per platform yet)
    q = (
        db.query(func.coalesce(func.sum(OrderFinance.revenue_realized), 0), func.coalesce(func.sum(OrderFinance.net_profit), 0))
        .join(Order, OrderFinance.order_id == Order.id)
        .filter(Order.user_id == current_user.id)
        .filter(func.date(Order.created_at) >= start)
        .filter(func.date(Order.created_at) <= end)
    ).first()
    total_revenue = float(q[0] or 0)
    total_profit = float(q[1] or 0)

    channels = [
        {
            "id": platform,
            "name": platform.replace("_", " ").title(),
            "spend": spend,
            "orders": 0,
            "revenue": 0,
            "profit": 0,
            "roas": (total_revenue / total_spend) if total_spend else None,
        }
        for platform, spend in sorted(spend_by_platform.items(), key=lambda x: x[0])
    ]
    return {
        "channels": channels,
        "orders": [],
        "totalSpend": total_spend,
        "totalRevenue": total_revenue,
        "totalProfit": total_profit,
    }


@router.get("/expenses/summary")
async def get_expense_summary_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get expense summary by type"""
    return get_expense_summary(db, current_user.id)


# Jobs and Operations
@router.post("/jobs/settlements")
async def run_settlement_job(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Run settlement job (admin only)"""
    if current_user.role.value != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    results = run_settlement_jobs(db)
    return {"message": "Settlement job completed", "results": results}


@router.post("/orders/{order_id}/compute")
async def compute_order_finance_endpoint(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Manually trigger finance computation for an order"""
    # Verify order belongs to user
    from app.models import Order
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == current_user.id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    finance = compute_order_finance(db, order_id)
    
    return {
        "id": finance.id,
        "order_value": float(finance.order_value),
        "revenue_realized": float(finance.revenue_realized),
        "total_expense": float(finance.total_expense),
        "net_profit": float(finance.net_profit),
        "profit_status": finance.profit_status.value
    }
