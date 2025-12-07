from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from api.routes import sources, users, episodes
from models.database import engine, Base
from models.schemas import *  # Import all models to register them

# Create tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Daily Knowledge Feed",
    description="AI-powered summaries of YouTube videos and podcasts",
    version="0.1.0"
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(sources.router, prefix="/api/sources", tags=["sources"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(episodes.router, prefix="/api/episodes", tags=["episodes"])


@app.get("/")
def root():
    return {"message": "Daily Knowledge Feed API", "docs": "/docs"}


@app.get("/health")
def health_check():
    return {"status": "ok"}


# Serve frontend
# In production (Docker): /app/frontend
# In development: ../frontend relative to backend
FRONTEND_DIR = "/app/frontend" if os.path.exists("/app/frontend") else os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend")

@app.get("/app")
def serve_frontend():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
