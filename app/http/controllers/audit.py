"""
Audit log routes
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional
from app.database import get_db
from app.models import AuditLog, User, AuditLogAction, UserRole
from app.auth import get_current_user

router = APIRouter()

@router.get("")
async def list_audit_logs(
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List audit logs. Users see their own logs; admins also see system logs (user_id IS NULL)."""
    if current_user.role == UserRole.ADMIN:
        query = db.query(AuditLog).filter(
            or_(AuditLog.user_id == current_user.id, AuditLog.user_id.is_(None))
        )
    else:
        query = db.query(AuditLog).filter(AuditLog.user_id == current_user.id)

    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)

    if entity_id:
        query = query.filter(AuditLog.entity_id == entity_id)

    if action:
        query = query.filter(AuditLog.action == action)

    logs = query.order_by(AuditLog.created_at.desc()).limit(limit).all()
    
    return {
        "logs": [
            {
                "id": log.id,
                "userId": log.user_id,
                "userName": log.user.name if log.user else "System",
                "action": log.action.value,
                "entityType": log.entity_type,
                "entityId": log.entity_id,
                "details": log.details,
                "createdAt": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]
    }
