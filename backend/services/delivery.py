import os
import asyncio
import resend
from telegram import Bot
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL", "summaries@example.com")

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

TELEGRAM_MAX_LENGTH = 4096


async def send_telegram(chat_id: str, message: str) -> bool:
    """Send summary via Telegram.
    
    Args:
        chat_id: Telegram chat ID
        message: Markdown-formatted message
        
    Returns:
        True if sent successfully
    """
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not configured")
    
    bot = Bot(token=TELEGRAM_TOKEN)
    
    try:
        if len(message) <= TELEGRAM_MAX_LENGTH:
            await bot.send_message(
                chat_id=chat_id, 
                text=message, 
                parse_mode="Markdown"
            )
        else:
            # Split into chunks at paragraph boundaries
            chunks = split_message(message, TELEGRAM_MAX_LENGTH)
            for i, chunk in enumerate(chunks):
                if i > 0:
                    await asyncio.sleep(0.5)  # Rate limiting
                await bot.send_message(
                    chat_id=chat_id, 
                    text=chunk, 
                    parse_mode="Markdown"
                )
        return True
    except Exception as e:
        print(f"Telegram send error: {e}")
        raise


def split_message(message: str, max_length: int) -> list[str]:
    """Split a long message into chunks at paragraph boundaries.
    
    Args:
        message: Full message text
        max_length: Maximum length per chunk
        
    Returns:
        List of message chunks
    """
    if len(message) <= max_length:
        return [message]
    
    chunks = []
    current_chunk = ""
    
    paragraphs = message.split("\n\n")
    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 <= max_length:
            current_chunk += para + "\n\n"
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            # If single paragraph is too long, force split
            if len(para) > max_length:
                for i in range(0, len(para), max_length):
                    chunks.append(para[i:i+max_length])
                current_chunk = ""
            else:
                current_chunk = para + "\n\n"
    
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    return chunks


def send_email(to: str, subject: str, html_content: str) -> bool:
    """Send summary via email.
    
    Args:
        to: Recipient email address
        subject: Email subject
        html_content: HTML email body
        
    Returns:
        True if sent successfully
    """
    if not RESEND_API_KEY:
        raise ValueError("RESEND_API_KEY not configured")
    
    try:
        resend.emails.send({
            "from": FROM_EMAIL,
            "to": to,
            "subject": subject,
            "html": html_content,
        })
        return True
    except Exception as e:
        print(f"Email send error: {e}")
        raise


def markdown_to_html(markdown_text: str) -> str:
    """Convert markdown to simple HTML for email.
    
    Args:
        markdown_text: Markdown-formatted text
        
    Returns:
        HTML string
    """
    html = markdown_text
    
    # Headers
    html = html.replace("### ", "<h3>").replace("\n", "</h3>\n", 1)
    html = html.replace("## ", "<h2>").replace("\n", "</h2>\n", 1)
    html = html.replace("# ", "<h1>").replace("\n", "</h1>\n", 1)
    
    # Bold
    import re
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    
    # Italic
    html = re.sub(r'\*(.+?)\*', r'<em>\1</em>', html)
    
    # Line breaks
    html = html.replace("\n\n", "</p><p>")
    html = html.replace("\n", "<br>")
    
    # Wrap in basic structure
    html = f"""
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                 max-width: 600px; margin: 0 auto; padding: 20px; line-height: 1.6;">
        <p>{html}</p>
    </body>
    </html>
    """
    return html
