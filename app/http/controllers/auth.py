"""
Authentication routes
"""
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, UserRole
from app.auth import verify_password, create_access_token, get_current_user
from app.http.requests import (
    LoginRequest,
    LoginResponse,
    UserResponse,
    RegisterRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)
from app.auth import get_password_hash
from app.config import settings
from app.services.email_service import send_password_reset_email

router = APIRouter()

RESET_TOKEN_EXPIRE_HOURS = 24

@router.post("/login", response_model=LoginResponse)
async def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    """Login with email and password"""
    # Validate input
    if not credentials.email or not credentials.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email and password are required"
        )
    
    # Find user
    user = db.query(User).filter(User.email == credentials.email).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    # Verify password
    if not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    # Generate token
    access_token_expires = timedelta(minutes=60 * 24 * 7)  # 7 days
    access_token = create_access_token(
        data={"sub": user.id, "role": user.role.value},
        expires_delta=access_token_expires
    )
    
    return LoginResponse(
        user={
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role.value
        },
        token=access_token
    )

@router.post("/register", response_model=LoginResponse)
async def register(user_data: RegisterRequest, db: Session = Depends(get_db)):
    """Register a new user"""
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create new user
    new_user = User(
        email=user_data.email,
        name=user_data.name,
        password_hash=get_password_hash(user_data.password),
        role=UserRole.STAFF  # Default to STAFF role
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Generate token
    access_token_expires = timedelta(minutes=60 * 24 * 7)  # 7 days
    access_token = create_access_token(
        data={"sub": new_user.id, "role": new_user.role.value},
        expires_delta=access_token_expires
    )
    
    return LoginResponse(
        user={
            "id": new_user.id,
            "email": new_user.email,
            "name": new_user.name,
            "role": new_user.role.value
        },
        token=access_token
    )

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user"""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        role=current_user.role
    )

@router.post("/logout")
async def logout():
    """Logout (client-side token removal)"""
    return {"message": "Logged out successfully"}


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Request a password reset. If the email exists, a reset token is stored and the user
    can use it on the reset-password page. In development (or when email is not configured),
    the reset link can be returned in the response for testing.
    """
    user = db.query(User).filter(User.email == body.email).first()
    if not user:
        return {"message": "If an account exists with this email, you will receive a password reset link."}
    token = secrets.token_urlsafe(32)
    user.password_reset_token = token
    user.password_reset_expires = datetime.now(timezone.utc) + timedelta(hours=RESET_TOKEN_EXPIRE_HOURS)
    db.commit()

    frontend_url = (getattr(settings, "FRONTEND_URL", None) or "").strip().rstrip("/") or "http://localhost:3000"
    reset_link = f"{frontend_url}/reset-password?token={token}"

    # Send email when SMTP is configured; otherwise user gets link from response
    sent = send_password_reset_email(user.email, reset_link, getattr(user, "name", None))
    out = {
        "message": "If an account exists with this email, you will receive a password reset link.",
        "reset_link": reset_link,
    }
    if sent:
        out["message"] = "A password reset link has been sent to your email."
    return out


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Set a new password using the token from the forgot-password email."""
    if not body.token or not body.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token and new password are required.",
        )
    user = (
        db.query(User)
        .filter(
            User.password_reset_token == body.token,
            User.password_reset_expires.isnot(None),
            User.password_reset_expires > datetime.now(timezone.utc),
        )
        .first()
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset link. Please request a new one.",
        )
    user.password_hash = get_password_hash(body.new_password)
    user.password_reset_token = None
    user.password_reset_expires = None
    db.commit()
    return {"message": "Password has been reset. You can sign in with your new password."}
