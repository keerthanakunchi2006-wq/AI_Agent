"""Authentication endpoints: login (OAuth2 password), register, me."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, UserRole
from ..schemas import Token, UserCreate, UserOut
from ..auth import hash_password, verify_password, create_access_token
from ..deps import get_current_user
from ..config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token, summary="Login and obtain a JWT")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Incorrect username or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")
    token = create_access_token(user.username, user.role.value)
    return Token(
        access_token=token, role=user.role.value, username=user.username,
        full_name=user.full_name,
    )


@router.post("/register", response_model=UserOut, summary="Register a new user")
def register(payload: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already exists")
    user = User(
        username=payload.username, email=payload.email, full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=UserRole(payload.role), is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/me", response_model=UserOut, summary="Current user profile")
def me(current: User = Depends(get_current_user)):
    return current
