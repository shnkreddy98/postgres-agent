# Postgres Agent

A Model Context Protocol (MCP) server for PostgreSQL databases with Claude LLM integration.

## Prerequisites

Install uv (Python package manager):

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or with pip
pip install uv
```

## Quick Start

### 1. Clone and Setup

```bash
git clone https://github.com/shnkreddy98/postgres-agent.git
cd postgres-agent
uv venv
uv sync
```

### 2. Activate Virtual Environment

```bash
source .venv/bin/activate
# On Windows: .venv\Scripts\activate
```

### 3. Setup Environment Variables

Create a `.env` file in the project root:

```env
ANTHROPIC_API_KEY=your_anthropic_api_key_here
PGUSER=your_postgres_username
PGDATABASE=your_database_name
PGHOST=localhost
PGPASSWORD=your_postgres_password
```

### 4. Run the Server

```bash
uv run main.py postgres_server.py
```

## Alternative: Configure with Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "postgres-agent": {
      "command": "uv",
      "args": ["run", "main.py", "postgres_server.py"],
      "cwd": "/path/to/postgres-agent"
    }
  }
}
```

Then restart Claude Desktop.

That's it! You can now ask Claude to query your PostgreSQL database.