import asyncio
from datetime import datetime
from typing import Optional

from .celery_app import celery_app
from models.database import SessionLocal, engine, Base
from models.schemas import (
    Source, Episode, User, Subscription, DailyDigestQueue, EpisodeStatus
)

# Create tables on worker startup
Base.metadata.create_all(bind=engine)
from services.poller import fetch_youtube_feed, fetch_podcast_feed, extract_youtube_channel_id
from services.transcription import (
    process_youtube_episode, process_podcast_episode, process_audio_file, 
    process_x_spaces, is_x_spaces_url, NoCaptionsError, get_video_title
)
from services.summarization import summarize_transcript, synthesize_digest
from services.delivery import send_telegram, send_email, markdown_to_html


@celery_app.task(bind=True, max_retries=3)
def process_episode_task(self, episode_id: int):
    """Transcribe and summarize an episode.
    
    Args:
        episode_id: Database ID of the episode to process
    """
    db = SessionLocal()
    try:
        episode = db.query(Episode).filter(Episode.id == episode_id).first()
        if not episode:
            return {"error": "Episode not found"}
        
        if episode.status == EpisodeStatus.COMPLETED:
            return {"status": "already_completed"}
        
        # Mark as processing
        episode.status = EpisodeStatus.PROCESSING
        db.commit()
        
        # Determine source type
        source = None
        if episode.source_id:
            source = db.query(Source).filter(Source.id == episode.source_id).first()
        
        # Detect type from URL if no source (one-off submission)
        if source:
            source_type = source.source_type
        elif "youtube.com" in episode.url or "youtu.be" in episode.url:
            source_type = "youtube"
        elif is_x_spaces_url(episode.url):
            source_type = "x_spaces"
        elif episode.audio_url:
            source_type = "podcast"
        else:
            raise ValueError(f"Cannot determine source type for episode {episode_id}")
        
        # Transcribe based on source type
        if source_type == "youtube":
            # Fetch video title if not already set
            if not episode.title:
                title = get_video_title(episode.url)
                if title:
                    episode.title = title
                    db.commit()
            
            transcript = process_youtube_episode(episode.url)
        elif source_type == "x_spaces":
            # X/Twitter Spaces - download and transcribe audio
            if not episode.title:
                title = get_video_title(episode.url)  # yt-dlp can get Spaces titles too
                if title:
                    episode.title = title
                    db.commit()
            
            transcript = process_x_spaces(episode.url)
        else:
            # Podcast - use audio_url
            if not episode.audio_url:
                raise ValueError("No audio URL for podcast episode")
            transcript = process_podcast_episode(episode.audio_url)
        
        episode.transcript = transcript
        
        # Summarize
        summary = summarize_transcript(transcript)
        episode.summary = summary
        episode.status = EpisodeStatus.COMPLETED
        episode.processed_at = datetime.utcnow()
        db.commit()
        
        # Queue for all subscribers
        queue_for_subscribers(db, episode)
        
        return {"status": "completed", "episode_id": episode_id}
        
    except NoCaptionsError as e:
        # Don't retry for videos without captions - mark as failed with specific message
        db.rollback()
        episode = db.query(Episode).filter(Episode.id == episode_id).first()
        if episode:
            episode.status = EpisodeStatus.FAILED
            episode.error_message = str(e)
            db.commit()
        return {"status": "failed", "error": str(e), "no_captions": True}
        
    except Exception as e:
        db.rollback()
        episode = db.query(Episode).filter(Episode.id == episode_id).first()
        if episode:
            episode.status = EpisodeStatus.FAILED
            db.commit()
        
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
    finally:
        db.close()


def queue_for_subscribers(db, episode: Episode):
    """Add episode to digest queue for all subscribers of its source."""
    subscriptions = db.query(Subscription).filter(
        Subscription.source_id == episode.source_id
    ).all()
    
    for sub in subscriptions:
        # Check if already queued
        existing = db.query(DailyDigestQueue).filter(
            DailyDigestQueue.user_id == sub.user_id,
            DailyDigestQueue.episode_id == episode.id
        ).first()
        
        if not existing:
            queue_item = DailyDigestQueue(
                user_id=sub.user_id,
                episode_id=episode.id
            )
            db.add(queue_item)
    
    db.commit()


@celery_app.task
def poll_all_sources():
    """Poll all sources for new episodes. Runs hourly via beat schedule."""
    db = SessionLocal()
    try:
        sources = db.query(Source).all()
        for source in sources:
            poll_source_task.delay(source.id)
        return {"sources_queued": len(sources)}
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=3)
def poll_source_task(self, source_id: int):
    """Poll a single source for new episodes.
    
    Args:
        source_id: Database ID of the source to poll
    """
    db = SessionLocal()
    try:
        source = db.query(Source).filter(Source.id == source_id).first()
        if not source:
            return {"error": "Source not found"}
        
        # Fetch episodes based on source type
        if source.source_type == "youtube":
            channel_id = extract_youtube_channel_id(source.url)
            episodes_data = asyncio.run(fetch_youtube_feed(channel_id))
        else:
            episodes_data = fetch_podcast_feed(source.url)
        
        new_count = 0
        for ep_data in episodes_data:
            # Check if episode already exists (deduplication)
            existing = db.query(Episode).filter(
                Episode.unique_id == ep_data["unique_id"]
            ).first()
            
            if existing:
                continue
            
            # Create new episode
            episode = Episode(
                source_id=source.id,
                unique_id=ep_data["unique_id"],
                title=ep_data["title"],
                url=ep_data["url"],
                audio_url=ep_data.get("audio_url"),
                published_at=ep_data.get("published_at"),
                status=EpisodeStatus.PENDING
            )
            db.add(episode)
            db.commit()
            db.refresh(episode)
            
            # Queue for processing
            process_episode_task.delay(episode.id)
            new_count += 1
        
        # Update last checked timestamp
        source.last_checked_at = datetime.utcnow()
        db.commit()
        
        return {"source_id": source_id, "new_episodes": new_count}
        
    except Exception as e:
        raise self.retry(exc=e, countdown=300)
    finally:
        db.close()


@celery_app.task
def send_scheduled_digests():
    """Send digests to users whose preferred time matches current hour."""
    db = SessionLocal()
    try:
        current_hour = datetime.utcnow().strftime("%H")
        
        # Find users who want digest this hour
        users = db.query(User).filter(
            User.preferred_digest_time.like(f"{current_hour}:%")
        ).all()
        
        for user in users:
            send_user_digest_task.delay(user.id)
        
        return {"users_queued": len(users)}
    finally:
        db.close()


@celery_app.task(bind=True, max_retries=3)
def send_user_digest_task(self, user_id: int):
    """Compile and send digest for a single user.
    
    Args:
        user_id: Database ID of the user
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"error": "User not found"}
        
        # Get pending digest items
        queue_items = db.query(DailyDigestQueue).filter(
            DailyDigestQueue.user_id == user_id
        ).all()
        
        if not queue_items:
            return {"status": "no_pending_items"}
        
        # Gather summaries
        summaries = []
        for item in queue_items:
            episode = db.query(Episode).filter(Episode.id == item.episode_id).first()
            if episode and episode.summary and episode.status == EpisodeStatus.COMPLETED:
                summaries.append({
                    "title": episode.title,
                    "summary": episode.summary
                })
        
        if not summaries:
            return {"status": "no_completed_summaries"}
        
        # Synthesize digest
        digest = synthesize_digest(summaries)
        
        # Deliver via available channels
        delivered = False
        
        if user.telegram_chat_id:
            try:
                asyncio.run(send_telegram(user.telegram_chat_id, digest))
                delivered = True
            except Exception as e:
                print(f"Telegram delivery failed for user {user_id}: {e}")
        
        if user.email:
            try:
                html_digest = markdown_to_html(digest)
                send_email(
                    user.email,
                    f"Your Daily Knowledge Digest - {datetime.utcnow().strftime('%B %d')}",
                    html_digest
                )
                delivered = True
            except Exception as e:
                print(f"Email delivery failed for user {user_id}: {e}")
        
        if delivered:
            # Clear queue
            for item in queue_items:
                db.delete(item)
            db.commit()
            return {"status": "delivered", "items_count": len(summaries)}
        else:
            raise Exception("No delivery channel succeeded")
        
    except Exception as e:
        raise self.retry(exc=e, countdown=300)
    finally:
        db.close()


@celery_app.task
def send_immediate_digest(user_id: int, episode_id: int):
    """Send a single episode summary immediately (for one-off requests).
    
    Args:
        user_id: Database ID of the user
        episode_id: Database ID of the episode
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        episode = db.query(Episode).filter(Episode.id == episode_id).first()
        
        if not user or not episode:
            return {"error": "User or episode not found"}
        
        if episode.status != EpisodeStatus.COMPLETED:
            return {"error": "Episode not yet processed"}
        
        message = f"# {episode.title}\n\n{episode.summary}"
        
        if user.telegram_chat_id:
            asyncio.run(send_telegram(user.telegram_chat_id, message))
        
        if user.email:
            html = markdown_to_html(message)
            send_email(user.email, f"Summary: {episode.title}", html)
        
        return {"status": "sent"}
    finally:
        db.close()
