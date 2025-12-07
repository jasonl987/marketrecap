from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from .database import Base


class EpisodeStatus(enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Source(Base):
    """YouTube channels or podcast RSS feeds."""
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True)
    url = Column(String(500), unique=True, nullable=False)
    name = Column(String(200))
    source_type = Column(String(50))  # youtube, podcast
    last_checked_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    episodes = relationship("Episode", back_populates="source")
    subscriptions = relationship("Subscription", back_populates="source")


class Episode(Base):
    """Individual videos or podcast episodes."""
    __tablename__ = "episodes"

    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey("sources.id"))
    unique_id = Column(String(200), unique=True, nullable=False)  # video ID or episode GUID
    title = Column(String(500))
    url = Column(String(500))
    audio_url = Column(String(500))  # Direct audio URL for podcasts
    transcript = Column(Text)
    summary = Column(Text)
    status = Column(Enum(EpisodeStatus), default=EpisodeStatus.PENDING)
    error_message = Column(String(500))  # Error details if processing failed
    published_at = Column(DateTime)
    processed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    source = relationship("Source", back_populates="episodes")
    digest_items = relationship("DailyDigestQueue", back_populates="episode")


class User(Base):
    """User accounts."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(200), unique=True)
    telegram_chat_id = Column(String(100), unique=True)
    preferred_digest_time = Column(String(5), default="08:00")  # HH:MM format
    timezone = Column(String(50), default="UTC")
    created_at = Column(DateTime, default=datetime.utcnow)

    subscriptions = relationship("Subscription", back_populates="user")
    digest_queue = relationship("DailyDigestQueue", back_populates="user")


class Subscription(Base):
    """User subscriptions to sources."""
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    source_id = Column(Integer, ForeignKey("sources.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="subscriptions")
    source = relationship("Source", back_populates="subscriptions")


class DailyDigestQueue(Base):
    """Pending summaries to be delivered to users."""
    __tablename__ = "daily_digest_queue"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    episode_id = Column(Integer, ForeignKey("episodes.id"))
    date_added = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="digest_queue")
    episode = relationship("Episode", back_populates="digest_items")
