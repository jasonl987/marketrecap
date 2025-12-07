"""
Test script to verify the transcription and summarization pipeline.
Uses YouTube transcript API (faster, more reliable than audio download).
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Test 1: Check OpenAI API key is set
print("=" * 50)
print("TEST 1: Checking OpenAI API key...")
api_key = os.getenv("OPENAI_API_KEY")
if not api_key or api_key.startswith("sk-..."):
    print("❌ OPENAI_API_KEY not set in .env")
    sys.exit(1)
print(f"✅ API key found: {api_key[:20]}...")

# Test 2: Test OpenAI connection
print("\n" + "=" * 50)
print("TEST 2: Testing OpenAI connection...")
from openai import OpenAI
client = OpenAI(api_key=api_key)
try:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Say 'hello' in one word"}],
        max_tokens=10
    )
    print(f"✅ OpenAI connected: {response.choices[0].message.content}")
except Exception as e:
    print(f"❌ OpenAI error: {e}")
    sys.exit(1)

# Test 3: Test YouTube transcript API
print("\n" + "=" * 50)
print("TEST 3: Testing YouTube transcript extraction...")
from youtube_transcript_api import YouTubeTranscriptApi

# Use a popular video with captions
TEST_VIDEO_ID = "dQw4w9WgXcQ"  # Rick Astley - Never Gonna Give You Up (has captions)

try:
    ytt_api = YouTubeTranscriptApi()
    fetched = ytt_api.fetch(TEST_VIDEO_ID)
    transcript = " ".join([entry.text for entry in fetched])
    print(f"✅ Transcript fetched: {len(transcript)} characters")
    print(f"   Preview: {transcript[:150]}...")
except Exception as e:
    print(f"❌ YouTube transcript error: {e}")
    # Try another video
    print("   Trying alternative video...")
    TEST_VIDEO_ID = "9bZkp7q19f0"  # Gangnam Style
    try:
        ytt_api = YouTubeTranscriptApi()
        fetched = ytt_api.fetch(TEST_VIDEO_ID)
        transcript = " ".join([entry.text for entry in fetched])
        print(f"✅ Transcript fetched: {len(transcript)} characters")
    except Exception as e2:
        print(f"❌ Alternative also failed: {e2}")
        sys.exit(1)

# Test 4: Test summarization
print("\n" + "=" * 50)
print("TEST 4: Testing summarization...")

from services.summarization import summarize_transcript

try:
    summary = summarize_transcript(transcript)
    print(f"✅ Summarization successful!")
    print(f"\n--- SUMMARY ---\n{summary}\n--- END ---")
except Exception as e:
    print(f"❌ Summarization error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 50)
print("🎉 ALL TESTS PASSED! Pipeline is working.")
print("=" * 50)
