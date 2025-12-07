# MarketRecap - AI Video Summaries

AI-powered summaries of YouTube videos and podcasts, available via web and Telegram.

## Features

- 🎬 YouTube video summarization
- 🎙️ Podcast episode summaries
- 🤖 Telegram bot interface
- 🌐 Web interface
- ⚡ Background processing with Celery

## Local Development

### Prerequisites

- Python 3.9+
- Redis
- ffmpeg

### Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Copy environment variables
cp ../.env.example .env
# Edit .env with your API keys
```

### Run locally

```bash
# Terminal 1: Redis
redis-server

# Terminal 2: API server
cd backend
source venv/bin/activate
uvicorn api.main:app --reload --port 8000

# Terminal 3: Celery worker
cd backend
source venv/bin/activate
celery -A workers.celery_app worker --loglevel=info

# Terminal 4: Telegram bot
cd backend
source venv/bin/activate
python -m bot.telegram_bot
```

Visit http://localhost:8000/app for the web interface.

## Deploy to Railway

### 1. Create Railway Project

1. Go to [railway.app](https://railway.app) and create a new project
2. Connect your GitHub repository

### 2. Add Redis

1. In your Railway project, click "New"
2. Select "Database" → "Redis"

### 3. Configure Environment Variables

In Railway dashboard, add these variables:

```
OPENAI_API_KEY=sk-...
OPENROUTER_API_KEY=sk-or-...
TELEGRAM_BOT_TOKEN=...
DATABASE_URL=${{Postgres.DATABASE_URL}}  # If using Postgres
REDIS_URL=${{Redis.REDIS_URL}}
```

### 4. Deploy Services

Railway will automatically detect the Dockerfile and deploy. You'll need to create 3 services:

**Service 1: Web (API + Frontend)**
- Start command: `uvicorn api.main:app --host 0.0.0.0 --port $PORT`

**Service 2: Worker (Celery)**
- Start command: `celery -A workers.celery_app worker --loglevel=info`

**Service 3: Bot (Telegram)**
- Start command: `python -m bot.telegram_bot`

### 5. Set Up Domain

1. Go to your web service settings
2. Generate a Railway domain or add a custom domain
3. Your app will be available at `https://your-domain.railway.app/app`

## API Endpoints

- `POST /api/episodes/submit` - Submit a URL for processing
- `GET /api/episodes/{id}` - Get episode details and summary
- `GET /api/episodes/{id}/status` - Check processing status
- `GET /app` - Web interface
- `GET /docs` - API documentation

## Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key for Whisper transcription |
| `OPENROUTER_API_KEY` | OpenRouter API key for LLM summarization |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather |
| `REDIS_URL` | Redis connection URL |
| `DATABASE_URL` | PostgreSQL connection URL (optional, defaults to SQLite) |
