# Reddit MCP Server

![Reddit MCP Server — logo](https://github.com/Simonc44/Reddit-MCP-Server/blob/main/assets/logo.png?raw=true)

---

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server that lets AI assistants like Claude search, browse, and analyze Reddit in real-time using Playwright web scraping.

> **No Reddit API key required** — works by scraping the public Reddit interface.

---

## Features

-  **Search Reddit** by keywords or browse subreddits (hot/new/top/rising)
-  **Read comments** and full post content from any Reddit thread
-  **Analyze business opportunities** with smart scoring (engagement ratio, keyword matching)
-  **Get subreddit info** — description, members, trending posts
-  **Fast** — blocks images/media loading, deduplicates results
-  **Robust** — fallback CSS selectors, error handling, timeout management

## Available Tools

| Tool | Description |
|------|-------------|
| `search_reddit` | Browse one or multiple subreddits with sorting and keyword filtering |
| `search_reddit_query` | Full-text search across Reddit (like the Reddit search bar) |
| `get_post_comments` | Get comments from a specific post with author, text, score and depth |
| `get_post_details` | Get full post content: selftext, flair, external links, metadata |
| `get_subreddit_info` | Get subreddit description, member count, and top posts |
| `analyze_opportunities` | Score posts for business potential using engagement and keyword analysis |

## Installation

### Prerequisites

- Python 3.10+
- Playwright with Chromium

### Setup

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/reddit-mcp-server.git
cd reddit-mcp-server

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (first time only)
playwright install chromium
```

## Usage

### Run the server

```bash
python server.py
```

Or using the FastMCP CLI:

```bash
fastmcp run server.py
```

### Test with the MCP Inspector

```bash
fastmcp dev server.py
```

## Configure with Claude

### Claude Desktop

Add this to your Claude Desktop config file:

- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "reddit": {
      "command": "python",
      "args": ["/absolute/path/to/server.py"]
    }
  }
}
```

### Claude Code (CLI)

```bash
claude mcp add reddit -- python /absolute/path/to/server.py
```

## Tool Examples

### Search subreddits

```json
{
  "tool": "search_reddit",
  "arguments": {
    "subreddits": ["python", "webdev", "programming"],
    "sort": "top",
    "time_filter": "week",
    "limit": 10
  }
}
```

### Search by keywords

```json
{
  "tool": "search_reddit_query",
  "arguments": {
    "query": "best framework for SaaS 2025",
    "sort": "relevance",
    "time_filter": "month",
    "limit": 15
  }
}
```

### Get post comments

```json
{
  "tool": "get_post_comments",
  "arguments": {
    "post_url": "https://www.reddit.com/r/webdev/comments/abc123/...",
    "limit": 30
  }
}
```

### Analyze business opportunities

```json
{
  "tool": "analyze_opportunities",
  "arguments": {
    "subreddits": ["SomebodyMakeThis", "StartupIdeas", "Entrepreneur"],
    "min_score": 200,
    "keywords": ["need", "wish", "frustrated", "automate"],
    "limit": 20
  }
}
```

## Opportunity Scoring

The `analyze_opportunities` tool scores posts using:

| Factor | Weight |
|--------|--------|
| Upvotes | × 2 |
| Comments | × 3 |
| High engagement ratio (comments/upvotes > 0.3) | × 1.3 bonus |
| Money keywords (`subscription`, `saas`, `pricing`, `mvp`...) | +15 per match |
| Impact keywords (`problem`, `frustrated`, `need`, `wish`...) | +20 per match |
| Both categories matched | × 1.25 super bonus |

Default subreddits scanned: `SomebodyMakeThis`, `StartupIdeas`, `businessideas`, `Entrepreneur`, `saas`, `technology`, `antiwork`

## Tech Stack

- **[FastMCP](https://gofastmcp.com)** — Python MCP framework
- **[Playwright](https://playwright.dev/python/)** — Headless browser automation
- **Transport**: stdio (standard for Claude Desktop / Claude Code)

## Limitations

- **Rate limiting**: Reddit may throttle or block excessive scraping. The server includes delays between requests to mitigate this.
- **No authentication**: Only public content is accessible.
- **Dynamic selectors**: Reddit's HTML structure may change over time, which could require updating CSS selectors.
- **Speed**: Each tool call takes 5-30 seconds depending on the number of subreddits and scroll depth.

## License

MIT
