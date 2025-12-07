FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install yt-dlp
RUN pip install --no-cache-dir yt-dlp

WORKDIR /app

# Copy requirements first for caching
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ .

# Copy frontend
COPY frontend/ /app/frontend/

# Expose port
EXPOSE 8000

# Default command (can be overridden per service)
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
