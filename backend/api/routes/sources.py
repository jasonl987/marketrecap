from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from models.database import get_db
from models.schemas import Source, Episode, EpisodeStatus
from services.poller import extract_youtube_channel_id
from workers.tasks import poll_source_task

router = APIRouter()


class SourceCreate(BaseModel):
    url: str
    name: str
    source_type: str  # "youtube" or "podcast"


class SourceResponse(BaseModel):
    id: int
    url: str
    name: str
    source_type: str
    last_checked_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/")
def list_sources(db: Session = Depends(get_db)):
    """List all sources."""
    sources = db.query(Source).all()
    return sources


@router.post("/", response_model=SourceResponse)
def add_source(source: SourceCreate, db: Session = Depends(get_db)):
    """Add a new source (YouTube channel or podcast RSS).
    
    For YouTube, provide the channel URL or RSS feed URL.
    For podcasts, provide the RSS feed URL.
    """
    # Check if already exists
    existing = db.query(Source).filter(Source.url == source.url).first()
    if existing:
        return existing
    
    new_source = Source(
        url=source.url,
        name=source.name,
        source_type=source.source_type
    )
    db.add(new_source)
    db.commit()
    db.refresh(new_source)
    
    # Trigger initial poll
    poll_source_task.delay(new_source.id)
    
    return new_source


@router.get("/{source_id}")
def get_source(source_id: int, db: Session = Depends(get_db)):
    """Get a source by ID."""
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.delete("/{source_id}")
def delete_source(source_id: int, db: Session = Depends(get_db)):
    """Delete a source."""
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    
    db.delete(source)
    db.commit()
    return {"message": "Source deleted"}


@router.post("/{source_id}/poll")
def poll_source(source_id: int, db: Session = Depends(get_db)):
    """Manually trigger polling for a source."""
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    
    poll_source_task.delay(source_id)
    return {"message": "Poll queued", "source_id": source_id}


@router.get("/{source_id}/episodes")
def list_source_episodes(source_id: int, db: Session = Depends(get_db)):
    """List all episodes for a source."""
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    
    episodes = db.query(Episode).filter(Episode.source_id == source_id).order_by(
        Episode.published_at.desc()
    ).all()
    return episodes
