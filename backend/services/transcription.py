import subprocess
import tempfile
import os
import re
import httpx
from openai import OpenAI
from youtube_transcript_api import YouTubeTranscriptApi
from dotenv import load_dotenv

load_dotenv()

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def is_x_spaces_url(url: str) -> bool:
    """Check if URL is an X/Twitter Spaces URL."""
    return bool(re.search(r'(twitter\.com|x\.com)/i/spaces/[a-zA-Z0-9]+', url))


def extract_x_spaces_id(url: str) -> str:
    """Extract Spaces ID from X/Twitter Spaces URL."""
    match = re.search(r'(twitter\.com|x\.com)/i/spaces/([a-zA-Z0-9]+)', url)
    if match:
        return match.group(2)
    raise ValueError(f"Could not extract Spaces ID from URL: {url}")


def extract_youtube_video_id(url: str) -> str:
    """Extract video ID from various YouTube URL formats.
    
    Supports:
        - https://www.youtube.com/watch?v=VIDEO_ID
        - https://youtu.be/VIDEO_ID
        - https://www.youtube.com/embed/VIDEO_ID
    """
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'v=([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"Could not extract video ID from URL: {url}")


def check_captions_available(video_id: str) -> bool:
    """Check if YouTube captions are available for a video."""
    try:
        ytt_api = YouTubeTranscriptApi()
        ytt_api.fetch(video_id)
        return True
    except Exception:
        return False


def get_video_title(url: str) -> str:
    """Get video title using yt-dlp."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--get-title", "--no-warnings", url],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def get_video_duration(url: str) -> int:
    """Get video duration in seconds using yt-dlp."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--get-duration", "--no-warnings", url],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            duration_str = result.stdout.strip()
            # Parse duration like "1:23:45" or "12:34" or "45"
            parts = duration_str.split(":")
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            elif len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            else:
                return int(parts[0])
    except Exception:
        pass
    return 0


def get_youtube_transcript(video_id: str) -> str:
    """Fetch transcript using YouTube's built-in captions.
    
    This is faster and free compared to downloading audio + Whisper.
    
    Args:
        video_id: YouTube video ID
        
    Returns:
        Transcript text
    """
    ytt_api = YouTubeTranscriptApi()
    fetched = ytt_api.fetch(video_id)
    transcript = " ".join([entry.text for entry in fetched])
    return transcript


def download_youtube_audio(url: str, output_path: str) -> str:
    """Download audio from YouTube using yt-dlp.
    
    Args:
        url: YouTube video URL
        output_path: Path to save the audio file (without extension)
        
    Returns:
        Path to the downloaded audio file
    """
    output_template = output_path.replace(".mp3", "")
    subprocess.run([
        "yt-dlp",
        "-x",  # Extract audio
        "--audio-format", "mp3",
        "--audio-quality", "5",  # Lower quality = smaller file, fine for speech
        "-o", f"{output_template}.%(ext)s",
        url
    ], check=True)
    return f"{output_template}.mp3"


def download_podcast_audio(audio_url: str, output_path: str) -> str:
    """Download audio directly from podcast RSS enclosure.
    
    Args:
        audio_url: Direct URL to audio file
        output_path: Path to save the audio file
        
    Returns:
        Path to the downloaded audio file
    """
    with httpx.Client(timeout=300) as http_client:
        response = http_client.get(audio_url, follow_redirects=True)
        response.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(response.content)
    return output_path


def split_audio_file(audio_path: str, max_size_mb: int = 20) -> list[str]:
    """Split audio file into chunks under the size limit.
    
    Args:
        audio_path: Path to the audio file
        max_size_mb: Maximum size per chunk in MB (default 20 to stay under Whisper's 25MB limit)
        
    Returns:
        List of paths to chunk files
    """
    file_size = os.path.getsize(audio_path)
    max_size_bytes = max_size_mb * 1024 * 1024
    
    if file_size <= max_size_bytes:
        return [audio_path]
    
    # Calculate number of chunks needed (add 1 extra for safety margin)
    num_chunks = (file_size // max_size_bytes) + 2
    
    # Get audio duration using ffprobe
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
        capture_output=True, text=True
    )
    total_duration = float(result.stdout.strip())
    chunk_duration = total_duration / num_chunks
    
    # Split using ffmpeg
    chunk_paths = []
    base_dir = os.path.dirname(audio_path)
    
    for i in range(num_chunks):
        start_time = i * chunk_duration
        chunk_path = os.path.join(base_dir, f"chunk_{i}.mp3")
        subprocess.run([
            "ffmpeg", "-y", "-i", audio_path,
            "-ss", str(start_time),
            "-t", str(chunk_duration),
            "-acodec", "libmp3lame",
            "-ab", "64k",  # Lower bitrate to reduce size
            chunk_path
        ], capture_output=True, check=True)
        chunk_paths.append(chunk_path)
    
    return chunk_paths


def transcribe_audio(audio_path: str) -> str:
    """Transcribe audio using OpenAI Whisper API.
    
    Automatically splits large files into chunks.
    
    Args:
        audio_path: Path to the audio file
        
    Returns:
        Transcribed text
    """
    chunk_paths = split_audio_file(audio_path)
    
    transcripts = []
    for i, chunk_path in enumerate(chunk_paths):
        print(f"[Transcription] Processing chunk {i+1}/{len(chunk_paths)}")
        with open(chunk_path, "rb") as audio_file:
            transcript = openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text"
            )
        transcripts.append(transcript)
    
    return " ".join(transcripts)


class NoCaptionsError(Exception):
    """Raised when a YouTube video has no captions available."""
    pass


def process_youtube_episode(url: str) -> str:
    """Get transcript for a YouTube video.
    
    Only uses YouTube's built-in captions. Raises NoCaptionsError if unavailable.
    
    Args:
        url: YouTube video URL
        
    Returns:
        Transcript text
        
    Raises:
        NoCaptionsError: If the video has no captions
    """
    video_id = extract_youtube_video_id(url)
    
    try:
        transcript = get_youtube_transcript(video_id)
        print(f"[Transcription] Used YouTube captions for {video_id}")
        return transcript
    except Exception as e:
        print(f"[Transcription] YouTube captions unavailable for {video_id}: {e}")
        raise NoCaptionsError(f"This video doesn't have captions available.")


def process_audio_file(audio_path: str) -> str:
    """Transcribe a user-uploaded audio file.
    
    Args:
        audio_path: Path to the audio file
        
    Returns:
        Transcript text
    """
    print(f"[Transcription] Processing uploaded audio file: {audio_path}")
    return transcribe_audio(audio_path)


def process_podcast_episode(audio_url: str) -> str:
    """Download and transcribe a podcast episode.
    
    Args:
        audio_url: Direct URL to podcast audio
        
    Returns:
        Transcribed text
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = os.path.join(tmpdir, "audio.mp3")
        download_podcast_audio(audio_url, audio_path)
        transcript = transcribe_audio(audio_path)
    return transcript


def download_x_spaces_audio(url: str, output_dir: str) -> str:
    """Download audio from X/Twitter Spaces using yt-dlp.
    
    Args:
        url: X Spaces URL
        output_dir: Directory to save the audio file
        
    Returns:
        Path to the downloaded audio file
    """
    import glob
    
    output_template = os.path.join(output_dir, "spaces_audio.%(ext)s")
    result = subprocess.run([
        "yt-dlp",
        "-x",  # Extract audio
        "--audio-format", "mp3",
        "--audio-quality", "9",  # Lower quality = smaller file
        "--postprocessor-args", "-ac 1 -ar 16000 -b:a 32k",  # Mono, 16kHz, 32kbps for smaller files
        "-o", output_template,
        "--no-warnings",
        url
    ], capture_output=True, text=True)
    
    if result.returncode != 0:
        error_msg = result.stderr or result.stdout
        if "login" in error_msg.lower() or "cookie" in error_msg.lower():
            raise ValueError("This X Space requires authentication. Please try a public Space.")
        raise ValueError(f"Failed to download X Space: {error_msg}")
    
    # Find the downloaded file (extension might vary)
    downloaded_files = glob.glob(os.path.join(output_dir, "spaces_audio.*"))
    if not downloaded_files:
        raise ValueError("Failed to download X Space: no audio file found")
    
    return downloaded_files[0]


def process_x_spaces(url: str) -> str:
    """Download and transcribe an X/Twitter Spaces recording.
    
    Args:
        url: X Spaces URL
        
    Returns:
        Transcribed text
    """
    spaces_id = extract_x_spaces_id(url)
    print(f"[Transcription] Processing X Space: {spaces_id}")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = download_x_spaces_audio(url, tmpdir)
        print(f"[Transcription] Downloaded audio to: {audio_path}")
        transcript = transcribe_audio(audio_path)
    
    return transcript
