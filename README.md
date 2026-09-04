# YouTube MCP Server

A remote MCP server exposing YouTube tools (search, video details, transcripts,
channel stats, playlist items) that you can connect to Claude as a custom
connector.

## 1. Get a YouTube API key

1. Go to https://console.cloud.google.com/apis/credentials
2. Create a project (or pick an existing one)
3. Enable **YouTube Data API v3** for that project (APIs & Services > Library)
4. Create an API key (APIs & Services > Credentials > Create Credentials > API Key)
5. (Recommended) Restrict the key to the YouTube Data API v3

## 2. Run it locally (optional, to test first)

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export YOUTUBE_API_KEY="your_key_here"
python server.py
```

The server listens on `http://0.0.0.0:8000/mcp`.

You can sanity-check it with the MCP Inspector:

```bash
npx @modelcontextprotocol/inspector
```
Point it at `http://localhost:8000/mcp`.

## 3. Deploy it so Claude can reach it

Claude's custom connectors call your server over the public internet, so it
needs a public HTTPS URL. A `render.yaml` is included for a quick free deploy
on Render:

1. Push this folder to a GitHub repo
2. Go to https://render.com > New > Blueprint, point it at the repo
3. Render will read `render.yaml` automatically
4. When prompted, set the `YOUTUBE_API_KEY` environment variable
5. Deploy — you'll get a URL like `https://youtube-mcp.onrender.com`
6. Your MCP endpoint is `https://youtube-mcp.onrender.com/mcp`

Any host that runs a long-lived Python process and gives you a public HTTPS
URL works the same way (Railway, Fly.io, a VPS, etc.) — just make sure
`YOUTUBE_API_KEY` is set as an environment variable there too.

Note: Render's free tier spins down when idle, so the first request after a
period of inactivity will be slow (~30–60s) while it wakes up.

## 4. Connect it to Claude

1. In Claude, go to **Settings → Connectors → Add custom connector**
2. Paste your server's `/mcp` URL, e.g. `https://youtube-mcp.onrender.com/mcp`
3. Give it a name like "YouTube"
4. Leave OAuth Client ID / Secret blank — this server is authless
5. Save, then try asking Claude something like "search YouTube for videos
   about sourdough bread" or "get the transcript for video ID abc123"

## Tools included

| Tool | Description |
|---|---|
| `search_videos` | Search YouTube by keyword |
| `get_video_details` | Title, stats, description for a video ID |
| `get_transcript` | Full transcript text for a video ID |
| `get_channel_stats` | Subscriber/view/video counts by channel ID or @handle |
| `get_playlist_items` | List videos in a playlist |

## Notes / limitations

- Transcripts come from `youtube-transcript-api`, an unofficial library that
  scrapes YouTube's caption data — it can break if YouTube changes its
  internal APIs, and doesn't work on videos with captions disabled.
- The YouTube Data API v3 free quota is 10,000 units/day. `search` costs 100
  units per call, so you get roughly 100 searches/day before hitting the cap.
- This server is authless (no OAuth) since it only reads public YouTube data
  with your own API key — nobody using your connector needs their own key.
