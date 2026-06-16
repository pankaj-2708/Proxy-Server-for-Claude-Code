# Ollama Proxy Server

A resilient proxy server that forwards requests to Ollama Cloud with intelligent API key management, automatic failover, and load balancing.

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.0+-orange.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## Features

- **Automatic API Key Rotation**: Supports multiple API keys via `OLLAMA_API_KEY_N` environment variables
- **Fill-First Strategy**: Distributes requests across keys using a cyclic failover approach
- **Intelligent Failover**: Automatically retries with the next API key on:
  - 429 Too Many Requests (rate limiting)
  - 401 Unauthorized (invalid/expired key)
  - 403 Forbidden (quota exceeded)
- **Streaming Support**: Properly handles server-sent events (SSE) and NDJSON streaming responses
- **Production-Ready**: Built with FastAPI and uvicorn for high performance

## Installation

### Prerequisites

- Python 3.11 or higher
- pip or uv for package management

### Quick Start

```bash
# Clone the repository
git clone <repository-url>
cd proxy-server

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate    # Windows

# Install dependencies
pip install -e .
```

### Using uv (Recommended)

```bash
uv sync
uv run python main.py
```

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
# Your Ollama Cloud API Key(s)
OLLAMA_API_KEY_1=your_first_api_key
OLLAMA_API_KEY_2=your_second_api_key
OLLAMA_API_KEY_3=your_third_api_key

# Optional: Ollama Cloud base URL (default: https://ollama.com)
# OLLAMA_CLOUD_URL=https://ollama.com

# Optional: Server port (default: 10001)
# PORT=10001
```

**Note**: You can use either `OLLAMA_API_KEY_N` (numbered) or a single `OLLAMA_API_KEY`. Numbered keys are recommended for production.

## Usage

### Running the Server

```bash
# Using Python
python main.py

# Using uv
uv run python main.py
```

The server will start on `http://0.0.0.0:10001` (or your configured PORT).

### API Endpoint

All requests to `/v1/*` are proxied to Ollama Cloud:

```bash
# Example: Proxy a completions request
curl http://localhost:10001/v1/chat/completions \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3.2",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### Streaming Responses

Streaming works transparently through the proxy:

```bash
curl http://localhost:10001/v1/chat/completions \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"model": "llama3.2", "messages": [{"role": "user", "content": "Hello!"}], "stream": true}'
```

## API Key Management

### Fill-First Strategy

The proxy uses a **fill-first** approach with cyclic fallback:

1. Requests start with key #1
2. On failure, automatically retries with key #2, #3, etc.
3. After success, the next request starts with the successful key's **next** key in rotation
4. This ensures fair distribution while prioritizing keys that recently succeeded

### Adding/Removing API Keys

1. Update your `.env` file with the new keys
2. Restart the server

The proxy will automatically pick up the new configuration on restart.

## Error Handling

### Key Exhaustion

When all API keys fail, the server returns a 503 error:

```json
{
  "detail": "Resource exhausted - All API keys failed. Errors: Key #1: 429 Too Many Requests | Key #2: 401 Unauthorized"
}
```

### Error Codes

| Status Code | Meaning | Action |
|-------------|---------|--------|
| 503 | All keys exhausted | Wait and retry later |
| 500 | Configuration error | Check environment variables |
| 502 | Upstream connection failed | Check Ollama Cloud availability |

## Project Structure

```
proxy_server/
├── main.py          # FastAPI application and proxy logic
├── pyproject.toml   # Project dependencies
├── .env             # Environment configuration (gitignored)
├── .env.example     # Template for environment variables
└── README.md
```


## Claude Code Integration

This proxy server is fully compatible with **Claude Code**, allowing you to run local Ollama models through the Claude CLI.

### Configuration

Set the following environment variables before running Claude Code:

```powershell
# Windows (PowerShell)
$env:ANTHROPIC_AUTH_TOKEN="dummy-token"  # Any non-empty string works
$env:ANTHROPIC_API_KEY=""                # Can be empty
$env:ANTHROPIC_BASE_URL="http://localhost:10001"
$env:CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1"
```

### Usage

After setting the environment variables, run:

```bash
claude --model 'model-name'
```

Replace `model-name` with the Ollama cloud model you want to use .

### How It Works

Claude Code uses the Anthropic API protocol. Your proxy server translates these requests to Ollama Cloud's v1 API, enabling Claude Code to work with any Ollama model while benefiting from:

- Automatic API key rotation
- Intelligent failover across multiple keys
- Rate limit handling
