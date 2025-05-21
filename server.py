# server.py
"""SharePoint MCP REST wrapper for list_files and get_file_content."""

import os
import sys
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from collections.abc import AsyncIterator

from fastmcp import FastMCP
from fastapi import FastAPI, HTTPException
import uvicorn, httpx

from auth.sharepoint_auth import SharePointContext, get_auth_context
from config.settings import APP_NAME, DEBUG

# ────────────────────────────────────────────────────────────────────────────────
# Logging
# ────────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("sharepoint_mcp")

@asynccontextmanager
async def sharepoint_lifespan(server: FastMCP) -> AsyncIterator[SharePointContext]:
    logger.info("Initializing SharePoint connection…")
    try:
        ctx = await get_auth_context()
        logger.info("Authenticated. Token expires at %s", ctx.token_expiry)
        yield ctx
    except Exception as e:
        logger.error("Authentication error: %s", e)
        yield SharePointContext(
            access_token="error",
            token_expiry=datetime.now() + timedelta(seconds=10),
            graph_url="https://graph.microsoft.com/v1.0",
        )
    finally:
        logger.info("Tearing down SharePoint connection…")

mcp = FastMCP(APP_NAME, lifespan=sharepoint_lifespan)
from tools.site_tools import register_site_tools  # noqa: E402
register_site_tools(mcp)

# ────────────────────────────────────────────────────────────────────────────────
# Build REST API
# ────────────────────────────────────────────────────────────────────────────────
app = FastAPI(title="SharePoint MCP REST")

@app.get("/", summary="Health check")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "message": "SharePoint MCP server is running."}

# Mount the core JSON-RPC at /mcp/ (note trailing slash)
starlette_app = mcp.http_app()
# Log all available routes for debugging
for route in getattr(starlette_app, "routes", []):
    logger.error("MCP CORE ROUTE: %s   PATH: %s", getattr(route, "name", "-"), getattr(route, "path", getattr(route, "path_regex", "-")))
app.mount("/mcp/", starlette_app)

# Figure out internal RPC URL (with trailing slash to avoid redirect)
_RPC_PORT = os.getenv("PORT", "8080")
RPC_URL = f"http://127.0.0.1:{_RPC_PORT}/mcp/"
logger.error("REST wrapper will POST to %s", RPC_URL)

async def _rpc_call(method: str, params: dict):
    """Call the internal JSON-RPC endpoint and return .result or raise."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.post(RPC_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
    if "error" in data:
        err = data["error"]
        raise HTTPException(status_code=500, detail=f"{err.get('code')}: {err.get('message')}")
    return data.get("result")

@app.get("/list_files", summary="List all files in SharePoint")
async def list_files():
    try:
        return await _rpc_call("list_files", {})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("list_files wrapper error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/get_file_content", summary="Get the raw content of a file")
async def get_file_content(filename: str):
    try:
        return await _rpc_call("get_file_content", {"filename": filename})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_file_content wrapper error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=int(_RPC_PORT), reload=True)
