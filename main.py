import os
import httpx
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Ollama Cloud configuration
OLLAMA_CLOUD_URL = os.getenv("OLLAMA_CLOUD_URL", "https://ollama.com")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY")

if not OLLAMA_API_KEY:
    raise ValueError("OLLAMA_API_KEY environment variable is required")

app = FastAPI(title="Ollama Proxy Server")


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
    All requests to /v1/* are forwarded to https://ollama.com/v1/* with the API key in headers.
    """
    target_url = f"{OLLAMA_CLOUD_URL}/v1/{path}"

    # Prepare headers, adding API key
    headers = {}
    for name, value in request.headers.items():
        # Skip headers that should not be forwarded
        if name.lower() in [
            "host",
            "content-length",
            "content-encoding",
            "authorization",
        ]:
            continue
        headers[name] = value

    # Add API key to headers
    headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"

    # Read request body
    body = await request.body()

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
            raise HTTPException(
                status_code=504, detail="Request to Ollama Cloud timed out"
            )
        except httpx.ConnectError as e:
            raise HTTPException(
                status_code=503, detail=f"Failed to connect to Ollama Cloud: {str(e)}"
            )
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=500, detail=f"Error proxying request: {str(e)}"
            )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 10001))
    uvicorn.run(app, host="0.0.0.0", port=port)
