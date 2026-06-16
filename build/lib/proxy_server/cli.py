import os
import sys
import time
import uvicorn
import signal
import socket
import argparse
import subprocess

from proxy_server.main import app,HOST,PORT  # your FastAPI app



def _start_server():
    """Runs uvicorn in a daemon thread — dies when main process exits."""
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


def _wait_for_server(timeout: float = 30.0):
    """Poll until the server is actually accepting connections."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((HOST, PORT), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def run_claude(model):
    # 1. Start uvicorn as a completely separate OS process
    #    stdout/stderr go to /dev/null so it doesn't pollute your terminal
    uvicorn_proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "proxy_server.main:app",   
            "--host", HOST,
            "--port", str(PORT),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    print(f"[proxy_server] Starting proxy on http://{HOST}:{PORT} ...")

    # 2. Wait until it's actually accepting connections
    if not _wait_for_server():
        print("[proxy_server] ERROR: Server didn't start in time.")
        uvicorn_proc.kill()
        sys.exit(1)

    print("[proxy_server] Proxy ready. Launching Claude Code...\n")

    os.environ["ANTHROPIC_BASE_URL"] = f"http://{HOST}:{PORT}"
    os.environ["ANTHROPIC_AUTH_TOKEN"] = f"dummy-token"
    os.environ["ANTHROPIC_API_KEY"] = ""
    os.environ["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    
    # 3. Set env vars
    env = os.environ.copy()

    # 4. Launch claude with full terminal access (no pipes — inherit everything)
    claude_proc = subprocess.Popen(
        ["claude","--model",model],
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
        env=env,
    )

    # 5. Wait for claude to exit, then kill the proxy
    try:
        claude_proc.wait()
    except KeyboardInterrupt:
        claude_proc.send_signal(signal.SIGINT)
        claude_proc.wait()
    finally:
        uvicorn_proc.kill()
    


def main():

    parser = argparse.ArgumentParser(description="")
    parser.add_argument(
        "command", 
        type=str, 
    )
    parser.add_argument(
        "cli", 
        type=str, 
    )
    parser.add_argument(
        "--model", 
        type=str, 
        required=False, 
    )
    
    args = parser.parse_args()
    
    model="qwen3-coder-next:cloud"
    
    if args.model:
        model=args.model
    

    if args.command == "launch" and args.cli == "claude":
        run_claude(model)
    else:
        print(f"Unknown command: {' '.join(sys.argv[1:])}")
        print("Usage: proxy_server run claude")
        sys.exit(1)