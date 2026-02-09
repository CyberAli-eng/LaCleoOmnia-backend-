"""
Finance API Routes - Comprehensive financial endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date, timedelta
from pydantic import BaseModel

from app.database import get_db
from app.models import User, OrderFinance, OrderExpense, OrderSettlement, CustomerRisk, ExpenseType, SettlementStatus
from app.auth import get_current_user
from app.services.finance_engine import compute_order_finance, get_finance_overview
from app.services.expense_config import add_manual_expense, get_expense_summary
from app.services.settlement_engine import settlement_engine, create_manual_settlement, run_settlement_jobs
from app.services.risk_engine import risk_engine, run_risk_assessment, should_block_order

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
    # Verify order belongs to user
    from app.models import Order
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == current_user.id).first()
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
    
    return {
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
            {
                "id": exp.id,
                "type": exp.type.value,
                "source": exp.source.value,
                "amount": float(exp.amount),
                "effective_date": exp.effective_date.isoformat(),
                "editable": exp.editable,
                "description": exp.description,
                "created_at": exp.created_at.isoformat()
            }
            for exp in expenses
        ],
        "settlements": [
            {
                "id": setl.id,
                "partner": setl.partner,
                "expected_date": setl.expected_date.isoformat(),
                "actual_date": setl.actual_date.isoformat() if setl.actual_date else None,
                "amount": float(setl.amount),
                "status": setl.status.value,
                "reference_id": setl.reference_id,
                "notes": setl.notes,
                "created_at": setl.created_at.isoformat()
            }
            for setl in settlements
        ]
    }


# P&L Report
@router.get("/pnl")
async def get_pnl_report(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get Profit & Loss report for a date range"""
    query = db.query(OrderFinance).join(Order).filter(Order.user_id == current_user.id)
    
    if start_date:
        query = query.filter(func.date(Order.created_at) >= start_date)
    if end_date:
        query = query.filter(func.date(Order.created_at) <= end_date)
    
    finances = query.all()
    
    # Calculate P&L metrics
    total_revenue = sum(f.revenue_realized for f in finances)
    total_expenses = sum(f.total_expense for f in finances)
    total_profit = sum(f.net_profit for f in finances)
    
    # Expense breakdown
    expense_breakdown = {}
    for finance in finances:
        expenses = db.query(OrderExpense).filter(OrderExpense.order_finance_id == finance.id).all()
        for exp in expenses:
            exp_type = exp.type.value
            if exp_type not in expense_breakdown:
                expense_breakdown[exp_type] = 0
            expense_breakdown[exp_type] += float(exp.amount)
    
    # Order status breakdown
    status_breakdown = {}
    for finance in finances:
        status = finance.fulfilment_status.value
        if status not in status_breakdown:
            status_breakdown[status] = {"count": 0, "revenue": 0, "profit": 0}
        status_breakdown[status]["count"] += 1
        status_breakdown[status]["revenue"] += float(finance.revenue_realized)
        status_breakdown[status]["profit"] += float(finance.net_profit)
    
    return {
        "period": {
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None
        },
        "summary": {
            "total_orders": len(finances),
            "total_revenue": float(total_revenue),
            "total_expenses": float(total_expenses),
            "total_profit": float(total_profit),
            "profit_margin": float(total_profit / total_revenue * 100) if total_revenue > 0 else 0
        },
        "expense_breakdown": expense_breakdown,
        "status_breakdown": status_breakdown
    }


# Settlements
@router.get("/settlements")
async def get_settlements(
    status: Optional[SettlementStatus] = Query(None),
    partner: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get settlement pipeline"""
    pipeline = settlement_engine.get_settlement_pipeline(db, current_user.id)
    
    # Filter by status if provided
    if status:
        for key in pipeline:
            pipeline[key]["items"] = [
                item for item in pipeline[key]["items"]
                if item.get("status") == status.value
            ]
    
    # Filter by partner if provided
    if partner:
        for key in pipeline:
            pipeline[key]["items"] = [
                item for item in pipeline[key]["items"]
                if item.get("partner") == partner
            ]
    
    return pipeline


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
    """Get risk summary for user's customers"""
    # Get customer IDs for this user
    from app.models import Order
    customer_ids = db.query(Order.customer_id).filter(
        Order.user_id == current_user.id,
        Order.customer_id.isnot(None)
    ).distinct().all()
    
    customer_ids = [cid[0] for cid in customer_ids]
    
    # Get risk profiles for these customers
    risks = db.query(CustomerRisk).filter(CustomerRisk.customer_id.in_(customer_ids)).all()
    
    # Calculate summary
    total_customers = len(risks)
    risk_counts = {}
    high_risk_customers = []
    
    for risk in risks:
        tag = risk.risk_tag.value
        if tag not in risk_counts:
            risk_counts[tag] = 0
        risk_counts[tag] += 1
        
        if risk.risk_tag.value == "HIGH":
            high_risk_customers.append({
                "customer_id": risk.customer_id,
                "risk_score": float(risk.risk_score),
                "total_orders": risk.total_orders,
                "rto_count": risk.rto_count,
                "loss_amount": float(risk.loss_amount)
            })
    
    return {
        "total_customers": total_customers,
        "risk_distribution": risk_counts,
        "high_risk_customers": high_risk_customers[:20]  # Top 20 high-risk customers
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
