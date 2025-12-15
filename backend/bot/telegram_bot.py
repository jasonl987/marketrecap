"""
MarketRecap Telegram Bot

Commands:
    /start - Register and get welcome message
    /help - Show available commands
    /settings - View/update delivery preferences
    
Usage:
    - Send any YouTube URL to get an AI summary
    - Subscribe to channels for automatic daily digests
"""
import os
import re
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from dotenv import load_dotenv

# Add parent directory to path for imports
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.database import SessionLocal
from models.schemas import User, Episode, EpisodeStatus, DailyDigestQueue
from workers.tasks import process_episode_task
from services.transcription import extract_youtube_video_id, check_captions_available, get_video_duration, is_x_spaces_url

load_dotenv()

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


def get_or_create_user(chat_id: str) -> User:
    """Get existing user or create new one."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_chat_id == str(chat_id)).first()
        if not user:
            user = User(
                telegram_chat_id=str(chat_id),
                preferred_digest_time="08:00",
                timezone="UTC"
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return user
    finally:
        db.close()


from typing import Optional

def extract_url(text: str) -> Optional[str]:
    """Extract YouTube or X Spaces URL from message text."""
    patterns = [
        # YouTube patterns
        r'(https?://(?:www\.)?youtube\.com/watch\?v=[a-zA-Z0-9_-]+)',
        r'(https?://youtu\.be/[a-zA-Z0-9_-]+)',
        r'(https?://(?:www\.)?youtube\.com/embed/[a-zA-Z0-9_-]+)',
        # X/Twitter Spaces patterns
        r'(https?://(?:www\.)?(?:twitter\.com|x\.com)/i/spaces/[a-zA-Z0-9]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


def normalize_url(url: str) -> str:
    """Normalize URL to standard format for deduplication."""
    if is_x_spaces_url(url):
        # Extract spaces ID and normalize
        match = re.search(r'(?:twitter\.com|x\.com)/i/spaces/([a-zA-Z0-9]+)', url)
        if match:
            return f"https://x.com/i/spaces/{match.group(1)}"
    else:
        # YouTube URL
        video_id = extract_youtube_video_id(url)
        return f"https://youtube.com/watch?v={video_id}"
    return url


def get_url_hash(url: str) -> str:
    """Generate hash for URL deduplication."""
    import hashlib
    normalized = normalize_url(url)
    return hashlib.sha256(normalized.encode()).hexdigest()[:32]


# ============== Command Handlers ==============

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command - register user."""
    chat_id = update.effective_chat.id
    user = get_or_create_user(chat_id)
    
    welcome_message = """
🎯 *Welcome to Punchlite!*

I turn YouTube videos and X Spaces into concise AI summaries.

*How to use:*
• Send me any YouTube or X Spaces link → I'll summarize it
• Get key takeaways, main topics, and action items

*Commands:*
/help - Show all commands
/settings - View your preferences

Just paste a URL to get started! 🚀
"""
    await update.message.reply_text(welcome_message, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    help_text = """
📖 *Punchlite Commands*

/start - Register & welcome message
/help - Show this help
/settings - View your preferences
/history - View recent summaries

*To get a summary:*
Send me any YouTube or X Spaces URL!

*Examples:*
`https://youtube.com/watch?v=...`
`https://x.com/i/spaces/...`

I'll generate a summary with:
• Key takeaways
• Main topics
• Notable quotes
• Action items
"""
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /settings command."""
    chat_id = update.effective_chat.id
    user = get_or_create_user(chat_id)
    
    settings_text = f"""
⚙️ *Your Settings*

📧 Email: {user.email or 'Not set'}
⏰ Digest Time: {user.preferred_digest_time} UTC
🌍 Timezone: {user.timezone}

_More settings coming soon!_
"""
    await update.message.reply_text(settings_text, parse_mode="Markdown")


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /history command - show recent summaries."""
    chat_id = update.effective_chat.id
    user = get_or_create_user(chat_id)
    
    db = SessionLocal()
    try:
        # Get recent episodes from digest queue or direct requests
        recent = db.query(Episode).filter(
            Episode.status == EpisodeStatus.COMPLETED
        ).order_by(Episode.processed_at.desc()).limit(5).all()
        
        if not recent:
            await update.message.reply_text("No summaries yet! Send me a YouTube URL to get started.")
            return
        
        history_text = "📚 *Recent Summaries*\n\n"
        for ep in recent:
            title = ep.title or "Untitled"
            if len(title) > 40:
                title = title[:40] + "..."
            history_text += f"• {title}\n"
        
        await update.message.reply_text(history_text, parse_mode="Markdown")
    finally:
        db.close()


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle YouTube URL - submit for processing."""
    chat_id = update.effective_chat.id
    text = update.message.text
    
    # Extract URL from message
    url = extract_url(text)
    if not url:
        await update.message.reply_text(
            "I couldn't find a valid YouTube URL in your message. "
            "Please send a link like:\n`https://www.youtube.com/watch?v=...`",
            parse_mode="Markdown"
        )
        return
    
    # Get or create user
    user = get_or_create_user(chat_id)
    
    # Check if already processed
    db = SessionLocal()
    try:
        url_hash = get_url_hash(url)
        normalized_url = normalize_url(url)
        
        existing = db.query(Episode).filter(Episode.unique_id == url_hash).first()
        
        if existing and existing.status == EpisodeStatus.COMPLETED:
            # Already have summary - send it directly
            await update.message.reply_text("✅ I already have this summary! Sending now...")
            await send_summary(update, existing)
            return
        
        if existing and existing.status == EpisodeStatus.PROCESSING:
            await update.message.reply_text(
                "⏳ This video is already being processed. I'll send the summary when it's ready!"
            )
            return
        
        # Create new episode
        if not existing:
            episode = Episode(
                unique_id=url_hash,
                url=normalized_url,
                status=EpisodeStatus.PENDING
            )
            db.add(episode)
            db.commit()
            db.refresh(episode)
        else:
            episode = existing
            episode.status = EpisodeStatus.PENDING
            db.commit()
        
        # Store chat_id in context for callback (we'll poll for completion)
        episode_id = episode.id
        
    finally:
        db.close()
    
    # Check if captions are available to estimate processing time
    video_id = extract_youtube_video_id(normalized_url)
    has_captions = check_captions_available(video_id)
    
    if has_captions:
        await update.message.reply_text(
            "🔄 *Processing your video...*\n\n"
            "Captions found! This should take about 10-30 seconds.",
            parse_mode="Markdown"
        )
    else:
        # Get duration for time estimate
        duration_secs = get_video_duration(normalized_url)
        if duration_secs > 0:
            # Estimate: ~1 min processing per 10 min of audio
            est_minutes = max(1, duration_secs // 600 + 1)
            duration_display = f"{duration_secs // 60} min" if duration_secs >= 60 else f"{duration_secs} sec"
            await update.message.reply_text(
                f"🔄 *Processing your video...*\n\n"
                f"No captions available, so I need to transcribe the audio.\n"
                f"Video length: {duration_display}\n"
                f"Estimated time: *{est_minutes}-{est_minutes + 2} minutes*\n\n"
                f"I'll send the summary when it's ready!",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "🔄 *Processing your video...*\n\n"
                "No captions available, so I need to transcribe the audio. "
                "This may take several minutes for longer videos.",
                parse_mode="Markdown"
            )
    
    # Queue the processing task
    process_episode_task.delay(episode_id)
    
    # Poll for completion and send result
    await poll_and_send_result(update, context, episode_id)


async def poll_and_send_result(update: Update, context: ContextTypes.DEFAULT_TYPE, episode_id: int):
    """Poll for episode completion and send result."""
    import asyncio
    
    db = SessionLocal()
    max_attempts = 60  # 60 seconds max
    
    try:
        for attempt in range(max_attempts):
            episode = db.query(Episode).filter(Episode.id == episode_id).first()
            
            if episode.status == EpisodeStatus.COMPLETED:
                db.close()
                await send_summary(update, episode)
                return
            
            if episode.status == EpisodeStatus.FAILED:
                db.close()
                error_msg = getattr(episode, 'error_message', None)
                if error_msg and "captions" in error_msg.lower():
                    await update.message.reply_text(
                        "❌ This video doesn't have captions available.\n\n"
                        "You can still get a summary by uploading the audio file directly. You can download audio from sites such as [YTMP3](https://ytmp3.ai/)"
                        "Just send me an MP3 or M4A file of the content you want summarized."
                    )
                else:
                    await update.message.reply_text(
                        "❌ Sorry, I couldn't process this video. Please try again later."
                    )
                return
            
            # Still processing - wait and check again
            await asyncio.sleep(1)
            db.expire_all()  # Refresh from DB
        
        # Timeout
        await update.message.reply_text(
            "⏰ Processing is taking longer than expected. "
            "I'll send the summary when it's ready!"
        )
    finally:
        db.close()


async def send_summary(update: Update, episode: Episode):
    """Send the summary to the user."""
    title = episode.title or "Video Summary"
    summary = episode.summary or "No summary available."
    
    # Telegram has a 4096 character limit
    message = f"📝 *{title}*\n\n{summary}"
    
    # Try with Markdown first, fall back to plain text if parsing fails
    try:
        if len(message) > 4000:
            # Split into chunks
            chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
            for chunk in chunks:
                await update.message.reply_text(chunk, parse_mode="Markdown")
        else:
            await update.message.reply_text(message, parse_mode="Markdown")
    except Exception as e:
        # Markdown parsing failed - send as plain text
        logger.warning(f"Markdown parsing failed, sending as plain text: {e}")
        if len(message) > 4000:
            chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
            for chunk in chunks:
                await update.message.reply_text(chunk)
        else:
            await update.message.reply_text(message)


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle audio file uploads for transcription."""
    import tempfile
    
    chat_id = update.effective_chat.id
    
    # Get the audio file
    if update.message.audio:
        file = update.message.audio
        file_name = file.file_name or "audio.mp3"
    elif update.message.voice:
        file = update.message.voice
        file_name = "voice.ogg"
    elif update.message.document:
        file = update.message.document
        file_name = file.file_name or "audio"
        # Check if it's an audio file
        mime = file.mime_type or ""
        if not any(t in mime for t in ["audio", "video", "ogg", "mp3", "m4a", "wav"]):
            await update.message.reply_text(
                "Please send an audio file (MP3, M4A, WAV, etc.)"
            )
            return
    else:
        return
    
    # Check file size (Telegram bot API limit is 20MB for downloads)
    if file.file_size and file.file_size > 20 * 1024 * 1024:
        await update.message.reply_text(
            "❌ File is too large. Please send an audio file under 20MB."
        )
        return
    
    await update.message.reply_text(
        "🎵 *Received your audio file!*\n\n"
        "Transcribing and generating summary... This may take a few minutes.",
        parse_mode="Markdown"
    )
    
    # Get or create user
    user = get_or_create_user(chat_id)
    
    # Download the file
    try:
        telegram_file = await file.get_file()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = f"{tmpdir}/{file_name}"
            await telegram_file.download_to_drive(local_path)
            
            # Import here to avoid circular imports
            from services.transcription import process_audio_file
            from services.summarization import summarize_transcript
            
            # Transcribe
            transcript = process_audio_file(local_path)
            
            # Summarize
            summary = summarize_transcript(transcript)
            
            # Send result
            message = f"📝 *Audio Summary*\n\n{summary}"
            if len(message) > 4000:
                chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
                for chunk in chunks:
                    await update.message.reply_text(chunk, parse_mode="Markdown")
            else:
                await update.message.reply_text(message, parse_mode="Markdown")
                
    except Exception as e:
        logger.error(f"Error processing audio: {e}")
        await update.message.reply_text(
            "❌ Sorry, I couldn't process this audio file. "
            "Please make sure it's a valid audio format."
        )


async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle unknown messages."""
    await update.message.reply_text(
        "I'm not sure what to do with that. "
        "Send me a YouTube URL or use /help to see available commands."
    )


def main():
    """Start the bot."""
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not set in environment")
    
    # Create application
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("history", history_command))
    
    # URL handler - matches messages containing YouTube URLs
    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r'(youtube\.com|youtu\.be)'),
        handle_url
    ))
    
    # Audio file handler
    app.add_handler(MessageHandler(
        filters.AUDIO | filters.VOICE | filters.Document.AUDIO,
        handle_audio
    ))
    
    # Unknown message handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unknown))
    
    # Start polling
    logger.info("Starting MarketRecap bot...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
