"""
YouTube MCP Server
-------------------
Exposes YouTube search, video details, transcripts, channel stats,
and playlist tools to any MCP client (including Claude custom connectors)
over Streamable HTTP.

Environment variables required:
    YOUTUBE_API_KEY   - a YouTube Data API v3 key from Google Cloud Console

Run locally:
    python server.py
    # server listens on http://0.0.0.0:8000/mcp

Add to Claude:
    Settings -> Connectors -> Add custom connector
    URL: https://<your-deployed-host>/mcp
"""

import os
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

API_KEY = os.environ.get("YOUTUBE_API_KEY")
if not API_KEY:
    raise RuntimeError(
        "YOUTUBE_API_KEY environment variable is not set. "
        "Get one from https://console.cloud.google.com/apis/credentials "
        "and enable the 'YouTube Data API v3' for your project."
    )

youtube = build("youtube", "v3", developerKey=API_KEY)

# The SDK's DNS-rebinding protection defaults to trusting only localhost,
# which blocks every real request once deployed behind a public host like
# Render. This server has no localhost-only trust boundary to protect
# (it's a public HTTPS API secured by our own API key), so we disable it.
mcp = FastMCP(
    "youtube",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

# Most hosting platforms (Render, Railway, Fly.io) inject a PORT env var
# and require binding to 0.0.0.0, not localhost.
mcp.settings.host = "0.0.0.0"
mcp.settings.port = int(os.environ.get("PORT", 8000))


def _resolve_channel_id(channel_id: Optional[str], handle: Optional[str]) -> str:
    """Resolve a channel to its ID, accepting either an ID or an @handle."""
    if channel_id:
        return channel_id
    if handle:
        clean = handle.lstrip("@")
        resp = youtube.channels().list(part="id", forHandle=clean).execute()
        items = resp.get("items", [])
        if not items:
            raise ValueError(f"No channel found for handle '@{clean}'")
        return items[0]["id"]
    raise ValueError("Provide either channel_id or handle")


@mcp.tool()
def search_videos(query: str, max_results: int = 5) -> str:
    """Search YouTube for videos matching a query.

    Args:
        query: Search terms.
        max_results: Number of results to return (1-25, default 5).
    """
    max_results = max(1, min(max_results, 25))
    try:
        resp = youtube.search().list(
            part="snippet",
            q=query,
            type="video",
            maxResults=max_results,
        ).execute()
    except HttpError as e:
        return f"YouTube API error: {e}"

    items = resp.get("items", [])
    if not items:
        return "No videos found."

    lines = []
    for item in items:
        vid = item["id"]["videoId"]
        snippet = item["snippet"]
        lines.append(
            f"- {snippet['title']} (by {snippet['channelTitle']})\n"
            f"  video_id: {vid}\n"
            f"  url: https://www.youtube.com/watch?v={vid}\n"
            f"  published: {snippet['publishedAt']}"
        )
    return "\n".join(lines)


@mcp.tool()
def get_video_details(video_id: str) -> str:
    """Get metadata and statistics for a specific YouTube video.

    Args:
        video_id: The YouTube video ID (the part after v= in the URL).
    """
    try:
        resp = youtube.videos().list(
            part="snippet,statistics,contentDetails",
            id=video_id,
        ).execute()
    except HttpError as e:
        return f"YouTube API error: {e}"

    items = resp.get("items", [])
    if not items:
        return f"No video found with ID '{video_id}'."

    v = items[0]
    snippet = v["snippet"]
    stats = v.get("statistics", {})
    duration = v.get("contentDetails", {}).get("duration", "unknown")

    return (
        f"Title: {snippet['title']}\n"
        f"Channel: {snippet['channelTitle']}\n"
        f"Published: {snippet['publishedAt']}\n"
        f"Duration (ISO 8601): {duration}\n"
        f"Views: {stats.get('viewCount', 'n/a')}\n"
        f"Likes: {stats.get('likeCount', 'n/a')}\n"
        f"Comments: {stats.get('commentCount', 'n/a')}\n"
        f"Description: {snippet.get('description', '')[:500]}"
    )


@mcp.tool()
def get_transcript(video_id: str, language: str = "en") -> str:
    """Get the transcript/captions for a YouTube video.

    Args:
        video_id: The YouTube video ID.
        language: Preferred language code (default "en"). Falls back to
            any available transcript if the preferred language isn't found.
    """
    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
        try:
            transcript = transcript_list.find_transcript([language])
        except NoTranscriptFound:
            transcript = transcript_list.find_transcript(
                [t.language_code for t in transcript_list]
            )
        fetched = transcript.fetch()
        text = " ".join(snippet.text for snippet in fetched)
        return text[:8000]  # cap length for context safety
    except TranscriptsDisabled:
        return "Transcripts are disabled for this video."
    except VideoUnavailable:
        return "This video is unavailable."
    except NoTranscriptFound:
        return "No transcript could be found for this video."
    except Exception as e:  # noqa: BLE001
        return f"Error fetching transcript: {e}"


@mcp.tool()
def get_channel_stats(
    channel_id: Optional[str] = None, handle: Optional[str] = None
) -> str:
    """Get subscriber, view, and video counts for a YouTube channel.

    Args:
        channel_id: The channel's raw ID (starts with UC...). Optional if
            handle is provided.
        handle: The channel's @handle (e.g. "@mkbhd"). Optional if
            channel_id is provided.
    """
    try:
        resolved_id = _resolve_channel_id(channel_id, handle)
        resp = youtube.channels().list(
            part="snippet,statistics", id=resolved_id
        ).execute()
    except (ValueError, HttpError) as e:
        return f"Error: {e}"

    items = resp.get("items", [])
    if not items:
        return "Channel not found."

    c = items[0]
    snippet = c["snippet"]
    stats = c.get("statistics", {})
    return (
        f"Channel: {snippet['title']}\n"
        f"Subscribers: {stats.get('subscriberCount', 'hidden')}\n"
        f"Total views: {stats.get('viewCount', 'n/a')}\n"
        f"Video count: {stats.get('videoCount', 'n/a')}\n"
        f"Description: {snippet.get('description', '')[:300]}"
    )


@mcp.tool()
def get_playlist_items(playlist_id: str, max_results: int = 10) -> str:
    """List videos in a YouTube playlist.

    Args:
        playlist_id: The playlist ID (starts with PL, UU, LL, etc.).
        max_results: Number of items to return (1-50, default 10).
    """
    max_results = max(1, min(max_results, 50))
    try:
        resp = youtube.playlistItems().list(
            part="snippet",
            playlistId=playlist_id,
            maxResults=max_results,
        ).execute()
    except HttpError as e:
        return f"YouTube API error: {e}"

    items = resp.get("items", [])
    if not items:
        return "No items found in this playlist."

    lines = []
    for item in items:
        snippet = item["snippet"]
        vid = snippet.get("resourceId", {}).get("videoId", "")
        lines.append(f"- {snippet['title']} (video_id: {vid})")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
