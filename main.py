import os
import httpx
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Ollama Cloud configuration
OLLAMA_CLOUD_URL = os.getenv("OLLAMA_CLOUD_URL", "https://ollama.com")

# Parse all OLLAMA_API_KEY_N entries from environment
API_KEY_PREFIX = "OLLAMA_API_KEY_"
api_keys = []
index = 1
while True:
    key = os.getenv(f"{API_KEY_PREFIX}{index}")
    if key is None:
        break
    api_keys.append(key)
    index += 1

# Fallback to single API_KEY if no numbered keys found
if not api_keys:
    single_key = os.getenv("OLLAMA_API_KEY")
    if not single_key:
        raise ValueError("OLLAMA_API_KEY or OLLAMA_API_KEY_1 environment variable is required")
    api_keys.append(single_key)

# Current index for fill-first strategy (1-based, tracks which key to try first)
# Using 1-based indexing for consistency with OLLAMA_API_KEY_N format
current_index = 1

app = FastAPI(title="Ollama Proxy Server")


# Helper functions defined before use
def should_failover_to_next_key(status_code: int, error_details: str = "") -> bool:
    """
    Check if the error indicates we should try the next API key.
    Returns True for:
    - 429 Too Many Requests (rate limit exceeded)
    - 401 Unauthorized (invalid/expired key)
    - 403 Forbidden (quota exceeded or access denied)
    """
    if status_code == 429:
        return True
    if status_code == 401:
        return True
    if status_code == 403:
        return True
    # Also check error message for quota-related errors in other status codes
    error_lower = error_details.lower() if error_details else ""
    if "quota" in error_lower or "exceeded" in error_lower or "limit" in error_lower:
        return True
    return False


@app.get("/")
async def root():
    return {
        "service": "Ollama Proxy Server",
        "status": "running",
        "forward_to": OLLAMA_CLOUD_URL,
    }


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def v1_proxy_request(request: Request, path: str):
    """
    Proxy requests to Ollama Cloud v1 API.
    Uses fill-first strategy with cyclic fallback across multiple API keys.
    All requests to /v1/* are forwarded to https://ollama.com/v1/* with the API key in headers.
    """
    target_url = f"{OLLAMA_CLOUD_URL}/v1/{path}"
    global current_index

    # Read request body
    body = await request.body()

    # Prepare base headers (without API key)
    base_headers = {}
    for name, value in request.headers.items():
        # Skip headers that should not be forwarded
        if name.lower() in [
            "host",
            "content-length",
            "content-encoding",
            "authorization",
        ]:
            continue
        base_headers[name] = value

    # Try each API key starting from current_index, with cyclic fallback
    num_keys = len(api_keys)
    if num_keys == 0:
        raise HTTPException(status_code=500, detail="No API keys configured")

    # Build the order of keys to try: from current_index to end, then wrap to 1..current_index-1
    # This implements fill-first with cyclic fallback
    keys_to_try = []
    for i in range(num_keys):
        idx = (current_index - 1 + i) % num_keys + 1  # Convert to 1-based
        keys_to_try.append((idx, api_keys[idx - 1]))

    # Track all errors for the final error message
    all_errors = []

    # Try each key
    for key_index, api_key in keys_to_try:
        # Prepare headers with this API key
        headers = dict(base_headers)
        headers["Authorization"] = f"Bearer {api_key}"

        # Forward the request to Ollama Cloud
        async with httpx.AsyncClient() as client:
            try:
                response = await client.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    content=body,
                    timeout=60.0,
                )

                # Update current_index to the successful key's next index for next request
                
                current_index = (key_index % num_keys) + 1

                # Handle streaming response (ndjson or event-stream)
                content_type = response.headers.get("content-type", "")
                if (
                    "application/x-ndjson" in content_type
                    or "text/event-stream" in content_type
                ):
                    return Response(
                        content=response.content,
                        status_code=response.status_code,
                        headers={
                            k: v
                            for k, v in response.headers.items()
                            if k.lower() in ["content-type", "transfer-encoding"]
                        },
                    )
                else:
                    # Handle regular JSON response - omit content-length to avoid chunking issues
                    return JSONResponse(
                        content=response.json(),
                        status_code=response.status_code,
                        headers={
                            k: v
                            for k, v in response.headers.items()
                            if k.lower() != "content-length"
                        },
                    )

            except httpx.TimeoutException:
                all_errors.append(f"Key #{key_index}: Request timeout")
                # Don't advance index on timeout - continue to next key

            except httpx.ConnectError as e:
                all_errors.append(f"Key #{key_index}: Connection failed - {str(e)}")
                # Don't advance index on connection error - continue to next key

            except httpx.HTTPStatusError as e:
                error_detail = str(e.response.text) if e.response else ""
                all_errors.append(f"Key #{key_index}: HTTP {e.response.status_code} - {error_detail[:200]}")

                # Only try next key if this is a key-specific error
                if not should_failover_to_next_key(e.response.status_code, error_detail):
                    # Non-key error (e.g., upstream API error), don't try other keys
                    raise HTTPException(
                        status_code=e.response.status_code,
                        detail=f"Error from Ollama Cloud: {error_detail[:500]}"
                    )

            except httpx.HTTPError as e:
                all_errors.append(f"Key #{key_index}: HTTP error - {str(e)}")

    # All keys exhausted - return resource exhausted response
    raise HTTPException(
        status_code=503,
        detail=f"Resource exhausted - All API keys failed. Errors: {' | '.join(all_errors)}"
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 10001))
    uvicorn.run(app, host="0.0.0.0", port=port)
