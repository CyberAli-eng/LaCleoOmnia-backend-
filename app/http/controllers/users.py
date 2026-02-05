"""
User management routes (Admin only)
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, UserRole
from app.auth import get_current_user, require_admin
from app.http.requests import RegisterRequest
from app.auth import get_password_hash

router = APIRouter()

@router.get("")
async def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """List all users (Admin only)"""
    users = db.query(User).all()
    return {
        "users": [
            {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "role": user.role.value,
                "createdAt": user.created_at.isoformat() if user.created_at else None,
            }
            for user in users
        ]
    }

@router.post("")
async def create_user(
    request: RegisterRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Create a new user (Admin only)"""
    # Check if user already exists
    existing = db.query(User).filter(User.email == request.email.lower().strip()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists"
        )
    
    # Create user
    user = User(
        name=request.name,
        email=request.email.lower().strip(),
        password_hash=get_password_hash(request.password),
        role=UserRole.STAFF  # Default to STAFF, admin can change later
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return {
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role.value,
        }
    }

@router.patch("/{user_id}")
async def update_user(
    user_id: str,
    request: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update user (Admin only)"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if "name" in request:
        user.name = request["name"]
    if "email" in request:
        user.email = request["email"].lower().strip()
    if "role" in request:
        user.role = UserRole(request["role"])
    if "password" in request and request["password"]:
        user.password_hash = get_password_hash(request["password"])
    
    db.commit()
    db.refresh(user)
    
    return {
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "role": user.role.value,
        }
    }

@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Delete user (Admin only)"""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    db.delete(user)
    db.commit()
    
    return {"message": "User deleted successfully"}
