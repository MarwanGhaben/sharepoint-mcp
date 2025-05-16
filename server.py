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
import uvicorn

from auth.sharepoint_auth import SharePointContext, get_auth_context
from config.settings import APP_NAME, DEBUG

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("sharepoint_mcp")

# ─── SharePoint lifespan ────────────────────────────────────────────────────
@asynccontextmanager
async def sharepoint_lifespan(server: FastMCP) -> AsyncIterator[SharePointContext]:
    logger.info("Initializing SharePoint connection…")
    try:
        ctx = await get_auth_context()
        logger.info("Authenticated. Token expires at %s", ctx.token_expiry)
        yield ctx
    except Exception as e:
        logger.error("Auth error: %s", e)
        yield SharePointContext(
            access_token="error",
            token_expiry=datetime.now() + timedelta(seconds=10),
            graph_url="https://graph.microsoft.com/v1.0",
        )
    finally:
        logger.info("Tearing down SharePoint connection…")

# ─── Create MCP server & register tools ──────────────────────────────────────
mcp = FastMCP(APP_NAME, lifespan=sharepoint_lifespan)
from tools.site_tools import register_site_tools  # noqa: E402
register_site_tools(mcp)

# ─── FastAPI app ─────────────────────────────────────────────────────────────
app = FastAPI(title="SharePoint MCP REST")

@app.get("/list_files", summary="List all files in SharePoint")
async def list_files():
    try:
        return await mcp.invoke_tool("list_files", {})
    except Exception as e:
        logger.error("list_files failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get(
    "/get_file_content",
    summary="Get the raw content of a single file",
)
async def get_file_content(filename: str):
    try:
        return await mcp.invoke_tool("get_file_content", {"filename": filename})
    except Exception as e:
        logger.error("get_file_content failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

# ─── Entrypoint ──────────────────────────────────────────────────────────────
def main() -> None:
    port = int(os.getenv("PORT", "8080"))
    logger.info("Starting %s on port %s", APP_NAME, port)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logger.error("Fatal error: %s", exc)
        sys.exit(1)
