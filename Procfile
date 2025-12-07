web: uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}
worker: celery -A workers.celery_app worker --loglevel=info
bot: python -m bot.telegram_bot
