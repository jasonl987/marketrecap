from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from models.database import get_db
from models.schemas import User, Subscription, Source, DailyDigestQueue, Episode

router = APIRouter()


class UserCreate(BaseModel):
    email: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    preferred_digest_time: str = "08:00"
    timezone: str = "UTC"


class UserUpdate(BaseModel):
    email: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    preferred_digest_time: Optional[str] = None
    timezone: Optional[str] = None


class SubscriptionCreate(BaseModel):
    source_id: int


class UserResponse(BaseModel):
    id: int
    email: Optional[str]
    telegram_chat_id: Optional[str]
    preferred_digest_time: str
    timezone: str
    created_at: datetime

    class Config:
        from_attributes = True


@router.post("/", response_model=UserResponse)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    """Create a new user."""
    if not user.email and not user.telegram_chat_id:
        raise HTTPException(
            status_code=400, 
            detail="Must provide either email or telegram_chat_id"
        )
    
    new_user = User(
        email=user.email,
        telegram_chat_id=user.telegram_chat_id,
        preferred_digest_time=user.preferred_digest_time,
        timezone=user.timezone
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db)):
    """Get a user by ID."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(user_id: int, user_update: UserUpdate, db: Session = Depends(get_db)):
    """Update user settings."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user_update.email is not None:
        user.email = user_update.email
    if user_update.telegram_chat_id is not None:
        user.telegram_chat_id = user_update.telegram_chat_id
    if user_update.preferred_digest_time is not None:
        user.preferred_digest_time = user_update.preferred_digest_time
    if user_update.timezone is not None:
        user.timezone = user_update.timezone
    
    db.commit()
    db.refresh(user)
    return user


@router.post("/{user_id}/subscribe")
def subscribe_to_source(user_id: int, sub: SubscriptionCreate, db: Session = Depends(get_db)):
    """Subscribe user to a source."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    source = db.query(Source).filter(Source.id == sub.source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    
    # Check if already subscribed
    existing = db.query(Subscription).filter(
        Subscription.user_id == user_id,
        Subscription.source_id == sub.source_id
    ).first()
    if existing:
        return {"message": "Already subscribed", "subscription_id": existing.id}
    
    subscription = Subscription(user_id=user_id, source_id=sub.source_id)
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return {"message": "Subscribed", "subscription_id": subscription.id}


@router.delete("/{user_id}/subscribe/{source_id}")
def unsubscribe_from_source(user_id: int, source_id: int, db: Session = Depends(get_db)):
    """Unsubscribe user from a source."""
    subscription = db.query(Subscription).filter(
        Subscription.user_id == user_id,
        Subscription.source_id == source_id
    ).first()
    
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    db.delete(subscription)
    db.commit()
    return {"message": "Unsubscribed"}


@router.get("/{user_id}/subscriptions")
def list_subscriptions(user_id: int, db: Session = Depends(get_db)):
    """List all subscriptions for a user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    subscriptions = db.query(Subscription).filter(
        Subscription.user_id == user_id
    ).all()
    
    result = []
    for sub in subscriptions:
        source = db.query(Source).filter(Source.id == sub.source_id).first()
        result.append({
            "subscription_id": sub.id,
            "source_id": source.id,
            "source_name": source.name,
            "source_type": source.source_type,
            "subscribed_at": sub.created_at
        })
    return result


@router.get("/{user_id}/digest-queue")
def get_digest_queue(user_id: int, db: Session = Depends(get_db)):
    """Get pending digest items for a user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    queue_items = db.query(DailyDigestQueue).filter(
        DailyDigestQueue.user_id == user_id
    ).all()
    
    result = []
    for item in queue_items:
        episode = db.query(Episode).filter(Episode.id == item.episode_id).first()
        result.append({
            "queue_id": item.id,
            "episode_id": episode.id,
            "episode_title": episode.title,
            "status": episode.status.value,
            "queued_at": item.date_added
        })
    return result
