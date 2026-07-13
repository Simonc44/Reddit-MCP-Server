# Reddit MCP Server

<div align="center">

<img width="550" alt="Reddit MCP Server Logo" src="https://github.com/Simonc44/Reddit-MCP-Server/blob/main/assets/logo.png?raw=true">

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Model Context Protocol](https://img.shields.io/badge/MCP-1.0.0-green.svg)](https://modelcontextprotocol.io)
[![Playwright](https://img.shields.io/badge/playwright-chromium-orange.svg)](https://playwright.dev/python/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

</div>

---

A **Model Context Protocol (MCP)** server that enables AI assistants (such as Claude Desktop, Claude Code, and other MCP clients) to search, browse, and analyze Reddit in real-time.

Built using **FastMCP** and **Playwright**, this server operates without requiring a Reddit API key by dynamically scraping the public Reddit interface with optimized, headless browser sessions.

> [!NOTE]
> **No Reddit API key required** — It works by scraping the public Reddit web interface.

---

## 📖 Table of Contents

1. [Features](#-features)
2. [Architecture Overview](#%EF%B8%8F-architecture-overview)
3. [Available Tools](#-available-tools)
4. [Installation & Setup](#-installation--setup)
   - [Prerequisites](#prerequisites)
   - [Quick Start](#quick-start)
5. [Client Configuration](#%EF%B8%8F-client-configuration)
   - [Claude Desktop](#claude-desktop)
   - [Claude Code](#claude-code)
6. [Tool Usage & Examples](#-tool-usage--examples)
7. [Opportunity Scoring Algorithm](#-opportunity-scoring-algorithm)
8. [Advanced Configuration](#-advanced-configuration)
9. [Troubleshooting & Limitations](#-troubleshooting--limitations)
10. [Contributing](#-contributing)
11. [Security](#-security)
12. [License](#-license)

---

## ✨ Features

- 🔍 **Reddit Search:** Browse one or multiple subreddits simultaneously with native sorting and keyword filtering.
- 💬 **Comment Extraction:** Fetch complete threaded comments from any Reddit post, preserving authors, scores, and depth.
- 📈 **Subreddit Analytics:** Retrieve subreddit description, active member counts, and trending/top posts.
- 💡 **Business Opportunity Discovery:** Scan specific subreddits for startup ideas or pain points with smart scoring.
- ⚡ **Performance Optimized:** Blocks heavy assets (images, fonts, media, tracking) to ensure lightning-fast scraping.
- 🛡️ **Robust Scraper:** Implements resilient CSS selectors, automatic scroll-loading, and timeout handling.

---

## 🛠️ Architecture Overview

The server communicates via standard I/O (stdin/stdout) using the Model Context Protocol. When an AI client invokes a tool:
1. **FastMCP** dispatches the tool call to Python.
2. A headless **Playwright (Chromium)** instance is initialized with custom headers and a realistic user-agent.
3. Media and unnecessary network assets are intercepted and blocked to minimize bandwidth and processing time.
4. The requested Reddit page is loaded, scrolled dynamically if necessary, and scraped via robust selectors.
5. Data is structured, analyzed (e.g. scored for opportunities), and returned to the client as JSON.

---

## 🧰 Available Tools

| Tool | Parameters | Description |
|------|------------|-------------|
| `search_reddit` | `subreddits` (list), `sort`, `time_filter`, `limit`, `keywords` (list) | Browse posts from specific subreddits with sorting. |
| `search_reddit_query` | `query` (str), `sort`, `time_filter`, `subreddit`, `limit` | Perform a global keyword search across Reddit. |
| `get_post_comments` | `post_url` (str), `limit` | Extract threaded comments with hierarchical depth. |
| `get_post_details` | `post_url` (str) | Get full details including post selftext, link, and metadata. |
| `get_subreddit_info` | `subreddit` (str) | Retrieve member statistics, description, and top posts. |
| `analyze_opportunities`| `subreddits` (list), `min_score`, `limit`, `keywords` (list) | Identify high-potential SaaS and startup pain points. |

---

## 🚀 Installation & Setup

### Prerequisites

- **Python 3.10** or higher
- **pip** (Python package installer)
- **Node.js** (optional, for running `fastmcp` CLI easily)

### Quick Start

1. **Clone the repository:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/reddit-mcp-server.git
   cd reddit-mcp-server
   ```

2. **Create and activate a virtual environment (recommended):**
   ```bash
   python -m venv .venv

   # On macOS/Linux:
   source .venv/bin/activate

   # On Windows (Command Prompt):
   .venv\Scripts\activate.bat

   # On Windows (PowerShell):
   .venv\Scripts\Activate.ps1
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install Playwright Chromium browser:**
   ```bash
   playwright install chromium
   ```

---

## ⚙️ Client Configuration

### Claude Desktop

To integrate this server with Claude Desktop, add it to your configuration file:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Add the following inside the `mcpServers` block (make sure to use absolute paths):

```json
{
  "mcpServers": {
    "reddit-mcp": {
      "command": "/path/to/your/virtualenv/bin/python",
      "args": ["/path/to/reddit-mcp-server/server.py"]
    }
  }
}
```

*Note for Windows users:* Use double backslashes in your paths (e.g., `"C:\\path\\to\\python.exe"`).

### Claude Code

Install and register the server globally using Claude Code CLI:

```bash
claude mcp add reddit-mcp -- python /path/to/reddit-mcp-server/server.py
```

---

## 💡 Tool Usage & Examples

### Global Search
Ask your AI assistant: *"Search Reddit for 'best keyboard for typing 2025' from the last month."*
Under the hood, the AI will invoke:
```json
{
  "tool": "search_reddit_query",
  "arguments": {
    "query": "best keyboard for typing 2025",
    "sort": "relevance",
    "time_filter": "month"
  }
}
```

### Business Opportunity Analysis
Ask your AI assistant: *"Analyze r/SaaS and r/Entrepreneur for startup pain points."*
Under the hood, the AI will invoke:
```json
{
  "tool": "analyze_opportunities",
  "arguments": {
    "subreddits": ["saas", "Entrepreneur"],
    "min_score": 150,
    "limit": 20
  }
}
```

---

## 📊 Opportunity Scoring Algorithm

The `analyze_opportunities` tool implements a proprietary scoring function to identify valid business ideas and high-impact problems:

$$Score = (Upvotes \times 2) + (Comments \times 3)$$

Additionally, the following multipliers and bonuses are applied:
* **High Engagement Ratio:** If comments-to-upvotes ratio is $> 0.3$, the score is multiplied by **1.3** (or **1.15** if $> 0.15$).
* **Monetization Keywords:** $+15$ points per match for words like `subscription`, `SaaS`, `buy`, `pricing`, `charge`, `dollar`.
* **Impact & Pain Point Keywords:** $+20$ points per match for words like `problem`, `frustrated`, `annoying`, `broken`, `wish`, `need`, `hate`.
* **Dual-Category Match Bonus:** If both monetization and pain point keywords are detected, the overall score is multiplied by **1.25**.

---

## 🛠️ Advanced Configuration

### Customized Scraper Parameters
The browser scraping parameters can be fine-tuned directly in `server.py`:
- **Viewport Size:** Configured to `1280x900` to simulate a real desktop.
- **User Agent:** Utilizes a modern, realistic user-agent string to prevent blockages.
- **Media Blocklist:** All routes ending in visual assets (`.png`, `.jpg`, `.gif`, etc.) are aborted to optimize performance.

---

## ⚠️ Troubleshooting & Limitations

- **Rate Limits & IP Blocks:** Heavy automated scraping may trigger Reddit's anti-bot system, leading to HTTP 429 errors or temporary blocks. Ensure you do not make rapid sequential calls.
- **Dynamic CSS Selectors:** Since this server relies on web scraping instead of the official API, updates to Reddit's frontend architecture (e.g., changing `shreddit-post` tags) may break selectors. Please open an issue if this occurs.
- **Speed Performance:** Rendering Chromium headlessly and scrolling to load content takes between 5 to 30 seconds per request depending on your connection speed and system performance.
- **No Private Auth:** This tool operates on public-facing Reddit pages and does not support logging into accounts or viewing private communities.

---

## 🤝 Contributing

Contributions are highly appreciated! Whether you want to improve the scraping selectors, add new analytical tools, or refine the documentation, we welcome your input.

Please read our [**Contributing Guidelines**](CONTRIBUTING.md) to get started on setting up the local development environment and creating pull requests.

---

## 🔒 Security

We take security seriously. If you discover any vulnerability in this server, please refer to our [**Security Policy**](SECURITY.md) for details on how to report it securely.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
