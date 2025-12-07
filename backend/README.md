# Daily Knowledge Feed - Backend

AI-powered summaries of YouTube videos and podcasts, delivered to your inbox or Telegram.

## Architecture

```
User submits URL → Extract/Transcribe → Summarize → Deliver (Email/Telegram)
                         ↓
                   Store in DB (deduped by URL hash)
```

## Tech Stack

- **API**: FastAPI
- **Database**: PostgreSQL
- **Queue**: Redis + Celery
- **Transcription**: OpenAI Whisper API
- **Summarization**: GPT-4o
- **Delivery**: Resend (email), python-telegram-bot

## Setup

### 1. Prerequisites

- Python 3.11+
- PostgreSQL
- Redis
- yt-dlp (`brew install yt-dlp` or `pip install yt-dlp`)

### 2. Install Dependencies

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

### 4. Setup Database

```bash
# Create database
createdb knowledge_feed

# Run migrations
alembic upgrade head
```

### 5. Start Services

**Terminal 1 - API:**
```bash
uvicorn api.main:app --reload --port 8000
```

**Terminal 2 - Celery Worker:**
```bash
celery -A workers.celery_app worker --loglevel=info
```

**Terminal 3 - Celery Beat (scheduler):**
```bash
celery -A workers.celery_app beat --loglevel=info
```

## API Endpoints

### Sources (Channels/Feeds)
- `GET /api/sources` - List all sources
- `POST /api/sources` - Add a source
- `POST /api/sources/{id}/poll` - Manually poll for new episodes
- `GET /api/sources/{id}/episodes` - List episodes for a source

### Users
- `POST /api/users` - Create user
- `GET /api/users/{id}` - Get user
- `PATCH /api/users/{id}` - Update user settings
- `POST /api/users/{id}/subscribe` - Subscribe to a source
- `GET /api/users/{id}/subscriptions` - List subscriptions
- `GET /api/users/{id}/digest-queue` - View pending digest items

### Episodes
- `POST /api/episodes/submit` - Submit a one-off URL
- `GET /api/episodes/{id}` - Get episode details
- `GET /api/episodes/{id}/status` - Check processing status

## Example Usage

### Add a YouTube channel:
```bash
curl -X POST http://localhost:8000/api/sources \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UC2D2CMWXMOVWx7giW1n3LIg",
    "name": "Huberman Lab",
    "source_type": "youtube"
  }'
```

### Submit a one-off video:
```bash
curl -X POST http://localhost:8000/api/episodes/submit \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/watch?v=VIDEO_ID",
    "user_id": 1
  }'
```

## Deduplication

Content is deduplicated by URL hash. If 1,000 users subscribe to the same channel:
- Episode is transcribed **once**
- Summary is generated **once**
- Delivery is fanned out to all subscribers

## Scheduled Tasks

- **Hourly at :00** - Poll all sources for new episodes
- **Hourly at :05** - Send digests to users whose preferred time matches
