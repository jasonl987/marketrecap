from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import hashlib

from models.database import get_db
from models.schemas import Episode, Source, EpisodeStatus, User, DailyDigestQueue
from workers.tasks import process_episode_task, send_immediate_digest
from services.transcription import is_x_spaces_url

router = APIRouter()


class EpisodeSubmit(BaseModel):
    """Submit a one-off URL for processing."""
    url: str
    user_id: Optional[int] = None  # If provided, will deliver to user when ready


class EpisodeResponse(BaseModel):
    id: int
    title: Optional[str]
    url: str
    status: str
    summary: Optional[str]

    class Config:
        from_attributes = True


def normalize_url(url: str) -> str:
    """Normalize URL for deduplication."""
    # YouTube
    if "youtube.com" in url or "youtu.be" in url:
        if "youtu.be/" in url:
            video_id = url.split("youtu.be/")[-1].split("?")[0]
        elif "v=" in url:
            video_id = url.split("v=")[-1].split("&")[0]
        else:
            video_id = url
        return f"https://youtube.com/watch?v={video_id}"
    
    # X Spaces - normalize to x.com format
    if is_x_spaces_url(url):
        import re
        match = re.search(r'(?:twitter\.com|x\.com)/i/spaces/([a-zA-Z0-9]+)', url)
        if match:
            return f"https://x.com/i/spaces/{match.group(1)}"
    
    # Strip query params for other URLs
    return url.split("?")[0]


def get_url_hash(url: str) -> str:
    """Generate hash for URL deduplication."""
    normalized = normalize_url(url)
    return hashlib.sha256(normalized.encode()).hexdigest()[:32]


@router.post("/submit")
def submit_url(submission: EpisodeSubmit, db: Session = Depends(get_db)):
    """Submit a URL for processing (one-off, not subscription-based).
    
    This is for users who want to summarize a specific video/podcast
    without subscribing to the entire channel.
    """
    url_hash = get_url_hash(submission.url)
    normalized_url = normalize_url(submission.url)
    
    # Check if already exists
    existing = db.query(Episode).filter(Episode.unique_id == url_hash).first()
    
    if existing:
        # Already processed or processing
        if existing.status == EpisodeStatus.COMPLETED and submission.user_id:
            # Send immediately if already done
            send_immediate_digest.delay(submission.user_id, existing.id)
            return {
                "message": "Summary already available, sending now",
                "episode_id": existing.id,
                "status": existing.status.value
            }
        elif existing.status == EpisodeStatus.FAILED:
            # Retry failed episodes - reset status and reprocess
            existing.status = EpisodeStatus.PENDING
            existing.error_message = None
            existing.url = normalize_url(submission.url)  # Update URL in case format changed
            db.commit()
            
            # Queue for processing
            process_episode_task.delay(existing.id)
            
            return {
                "message": "Retrying failed episode",
                "episode_id": existing.id,
                "status": "pending"
            }
        elif submission.user_id:
            # Queue for delivery when ready
            queue_item = DailyDigestQueue(
                user_id=submission.user_id,
                episode_id=existing.id
            )
            db.add(queue_item)
            db.commit()
        
        return {
            "message": "Already processing",
            "episode_id": existing.id,
            "status": existing.status.value
        }
    
    # Determine source type from URL
    if "youtube.com" in normalized_url or "youtu.be" in normalized_url:
        source_type = "youtube"
    elif is_x_spaces_url(normalized_url):
        source_type = "x_spaces"
    else:
        source_type = "podcast"
    
    # Create episode without a source (one-off)
    # For X Spaces and YouTube, store URL in url field (not audio_url)
    episode = Episode(
        unique_id=url_hash,
        url=normalized_url,
        audio_url=submission.url if source_type == "podcast" else None,
        status=EpisodeStatus.PENDING
    )
    db.add(episode)
    db.commit()
    db.refresh(episode)
    
    # Queue for delivery if user provided
    if submission.user_id:
        queue_item = DailyDigestQueue(
            user_id=submission.user_id,
            episode_id=episode.id
        )
        db.add(queue_item)
        db.commit()
    
    # Queue processing
    process_episode_task.delay(episode.id)
    
    return {
        "message": "Processing started",
        "episode_id": episode.id,
        "status": "pending"
    }


@router.get("/{episode_id}")
def get_episode(episode_id: int, db: Session = Depends(get_db)):
    """Get episode details including summary if available."""
    episode = db.query(Episode).filter(Episode.id == episode_id).first()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    
    return {
        "id": episode.id,
        "title": episode.title,
        "url": episode.url,
        "status": episode.status.value,
        "summary": episode.summary if episode.status == EpisodeStatus.COMPLETED else None,
        "published_at": episode.published_at,
        "processed_at": episode.processed_at
    }


@router.get("/{episode_id}/status")
def get_episode_status(episode_id: int, db: Session = Depends(get_db)):
    """Check processing status of an episode."""
    episode = db.query(Episode).filter(Episode.id == episode_id).first()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    
    return {
        "episode_id": episode.id,
        "status": episode.status.value,
        "has_summary": episode.summary is not None
    }


@router.post("/{episode_id}/reprocess")
def reprocess_episode(episode_id: int, db: Session = Depends(get_db)):
    """Reprocess a failed episode."""
    episode = db.query(Episode).filter(Episode.id == episode_id).first()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    
    if episode.status == EpisodeStatus.PROCESSING:
        return {"message": "Already processing"}
    
    episode.status = EpisodeStatus.PENDING
    db.commit()
    
    process_episode_task.delay(episode_id)
    return {"message": "Reprocessing started"}
