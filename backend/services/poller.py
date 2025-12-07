import feedparser
import httpx
from datetime import datetime
from typing import List, Dict

YOUTUBE_RSS_TEMPLATE = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


async def fetch_youtube_feed(channel_id: str) -> List[Dict]:
    """Fetch new videos from YouTube channel RSS.
    
    Args:
        channel_id: YouTube channel ID (e.g., UC...)
        
    Returns:
        List of episode dicts with unique_id, title, url, published_at
    """
    url = YOUTUBE_RSS_TEMPLATE.format(channel_id=channel_id)
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        feed = feedparser.parse(response.text)
    
    episodes = []
    for entry in feed.entries:
        episodes.append({
            "unique_id": entry.yt_videoid,
            "title": entry.title,
            "url": entry.link,
            "published_at": datetime(*entry.published_parsed[:6]) if entry.get("published_parsed") else None,
        })
    return episodes


def fetch_podcast_feed(rss_url: str) -> List[Dict]:
    """Fetch new episodes from podcast RSS.
    
    Args:
        rss_url: Podcast RSS feed URL
        
    Returns:
        List of episode dicts with unique_id, title, url, audio_url, published_at
    """
    feed = feedparser.parse(rss_url)
    
    episodes = []
    for entry in feed.entries:
        # Find audio enclosure
        audio_url = None
        for link in entry.get("links", []):
            if link.get("type", "").startswith("audio/"):
                audio_url = link.get("href")
                break
        
        # Fallback to enclosures
        if not audio_url and entry.get("enclosures"):
            for enc in entry.enclosures:
                if enc.get("type", "").startswith("audio/"):
                    audio_url = enc.get("href")
                    break
        
        episodes.append({
            "unique_id": entry.get("id", entry.get("guid", entry.link)),
            "title": entry.title,
            "url": entry.link,
            "audio_url": audio_url,
            "published_at": datetime(*entry.published_parsed[:6]) if entry.get("published_parsed") else None,
        })
    return episodes


def extract_youtube_channel_id(url: str) -> str:
    """Extract channel ID from various YouTube URL formats.
    
    Supports:
        - https://www.youtube.com/channel/UC...
        - https://www.youtube.com/feeds/videos.xml?channel_id=UC...
    """
    if "channel_id=" in url:
        return url.split("channel_id=")[-1].split("&")[0]
    elif "/channel/" in url:
        return url.split("/channel/")[-1].split("/")[0].split("?")[0]
    return url  # Assume it's already a channel ID
