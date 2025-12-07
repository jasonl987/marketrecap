import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Use OpenRouter for summarization (Gemini 2.5 Flash)
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

# Model to use for summarization
SUMMARY_MODEL = "google/gemini-2.5-flash-preview-09-2025"

SUMMARY_PROMPT = """## PRIMARY TASK
Summarize an audio transcript of a podcast or YouTube video in an easily digestible format.

## OVERALL FORMAT & STYLE GUIDELINES
- The summary will contain four sections: 1) Overall Summary, 2) Main Topics Discussed, 3) Notable Quotes, and 4) Action Items
- Overall Summary limited to 1-2 sentences only and less than 250 characters
- Main Topics discussed limit to at most 5 main topics, with a total character limit of less than 2000
- Notable Quotes limited to 3 quotes
- Action Items limited to 2 items
- Use informal, conversational language
- Do NOT use emojis or hashtags
- CRITICAL: Use single asterisks for bold text like *this* NOT double asterisks **like this**. Single asterisks render as bold in Telegram.
- CRITICAL: For italics, use underscores like _this_. Every opening underscore MUST have a closing underscore. Do not leave any unclosed formatting.
- IMPORTANT: Identify the host and guest(s) from context clues in the transcript (names mentioned, introductions, how people address each other). Always mention who is speaking in the summary and attribute quotes to specific people.

## OUTPUT FORMAT

*Summary: [Video or podcast title here]*

[1-2 sentence overview mentioning the host and guest(s) by name, under 275 characters]

*Main Topics Discussed:*

1. *[Topic Title]*: [Synopsis of the topic discussion]

2. *[Topic Title]*: [Synopsis of the topic discussion]

3. *[Topic Title]*: [Synopsis of the topic discussion]

[Up to 5 topics maximum]

*Notable Quotes:*

1. "_[Quote text]_" ([Speaker name], [brief context])

2. "_[Quote text]_" ([Speaker name], [brief context])

3. "_[Quote text]_" ([Speaker name], [brief context])

*Action Items:*

1. [Actionable takeaway from the content]

2. [Actionable takeaway from the content]

3. [Actionable takeaway from the content]

## TRANSCRIPT
{transcript}
"""

DIGEST_SYNTHESIS_PROMPT = """You are creating a daily knowledge briefing for a user.

Here are summaries from content they follow. Write:
1. A 2-3 sentence "Executive Summary" connecting any themes across the content
2. Then list each individual summary below, separated by horizontal rules

Keep it scannable and useful. Use Markdown formatting.

SUMMARIES:
{summaries}
"""


def summarize_transcript(transcript: str, max_chars: int = 100000) -> str:
    """Generate a summary from a transcript.
    
    Args:
        transcript: Full transcript text
        max_chars: Maximum characters to process (truncates if longer)
        
    Returns:
        Markdown-formatted summary
    """
    # Truncate if too long (>100k chars ≈ 25k tokens)
    if len(transcript) > max_chars:
        transcript = transcript[:max_chars] + "\n\n[Transcript truncated due to length...]"
    
    response = client.chat.completions.create(
        model=SUMMARY_MODEL,
        messages=[
            {"role": "user", "content": SUMMARY_PROMPT.format(transcript=transcript)}
        ],
        max_tokens=2000,
    )
    return response.choices[0].message.content


def synthesize_digest(summaries: list[dict]) -> str:
    """Create a unified digest from multiple summaries.
    
    Args:
        summaries: List of dicts with 'title' and 'summary' keys
        
    Returns:
        Markdown-formatted digest with executive summary
    """
    if not summaries:
        return "No new content to summarize today."
    
    if len(summaries) == 1:
        # Single item, no need for synthesis
        return f"# {summaries[0]['title']}\n\n{summaries[0]['summary']}"
    
    formatted = "\n\n---\n\n".join(
        f"**{s['title']}**\n\n{s['summary']}" for s in summaries
    )
    
    response = client.chat.completions.create(
        model=SUMMARY_MODEL,
        messages=[
            {"role": "user", "content": DIGEST_SYNTHESIS_PROMPT.format(summaries=formatted)}
        ],
        max_tokens=3000,
    )
    return response.choices[0].message.content
