"""
Worker job management routes
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import SyncJob, User, ChannelAccount, SyncJobStatus
from app.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("")
async def list_worker_jobs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all worker jobs for the current user. Returns [] if none or on error."""
    try:
        user_account_ids = [
            acc.id for acc in db.query(ChannelAccount).filter(
                ChannelAccount.user_id == current_user.id
            ).all()
        ]
        if not user_account_ids:
            return []

        jobs = db.query(SyncJob).filter(
            SyncJob.channel_account_id.in_(user_account_ids)
        ).all()

        return [
            {
                "id": job.id,
                "type": getattr(job.job_type, "value", str(job.job_type)) if job.job_type else "UNKNOWN",
                "status": getattr(job.status, "value", str(job.status)) if job.status else "QUEUED",
                "attempts": 0,
                "lastError": getattr(job, "error_message", None),
                "createdAt": job.created_at.isoformat() if job.created_at else None,
                "updatedAt": (lambda t: t.isoformat() if t else None)(
                    job.finished_at or job.started_at or job.created_at
                ),
            }
            for job in jobs
        ]
    except Exception as e:
        logger.exception("list_worker_jobs error: %s", e)
        return []

@router.post("/{job_id}/{action}")
async def control_worker_job(
    job_id: str,
    action: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Control worker job (retry, cancel, etc.)"""
    # Get user's channel accounts
    user_account_ids = [acc.id for acc in db.query(ChannelAccount).filter(
        ChannelAccount.user_id == current_user.id
    ).all()]
    
    if not user_account_ids:
        raise HTTPException(
            status_code=404,
            detail="Job not found"
        )
    
    job = db.query(SyncJob).filter(
        SyncJob.id == job_id,
        SyncJob.channel_account_id.in_(user_account_ids)
    ).first()
    
    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job not found"
        )
    
    if action == "retry":
        job.status = SyncJobStatus.QUEUED
        db.commit()
        return {"message": "Job queued for retry"}
    elif action == "cancel":
        job.status = SyncJobStatus.FAILED
        db.commit()
        return {"message": "Job cancelled"}
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown action: {action}"
        )
