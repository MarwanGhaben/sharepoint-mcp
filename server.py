"""Main implementation of the SharePoint MCP Server."""

import os
import sys
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from datetime import datetime, timedelta

from fastmcp import FastMCP
from auth.sharepoint_auth import SharePointContext, get_auth_context
from config.settings import APP_NAME, DEBUG

# --------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------
logging_level = logging.DEBUG if DEBUG else logging.INFO
logging.basicConfig(
    level=logging_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("sharepoint_mcp")

# --------------------------------------------------------------------
# SharePoint connection lifecycle
# --------------------------------------------------------------------
@asynccontextmanager
async def sharepoint_lifespan(server: FastMCP) -> AsyncIterator[SharePointContext]:
    """Establish and tear down the SharePoint auth context."""
    logger.info("Initializing SharePoint connection...")
    try:
        context = await get_auth_context()
        logger.info("Authentication successful. Token expiry: %s", context.token_expiry)
        yield context
    except Exception as e:
        logger.error("Auth failure: %s", e)
        yield SharePointContext(
            access_token="error",
            token_expiry=datetime.now() + timedelta(seconds=10),
            graph_url="https://graph.microsoft.com/v1.0",
        )
    finally:
        logger.info("Ending SharePoint connection...")

# --------------------------------------------------------------------
# Create MCP server & register tools
# --------------------------------------------------------------------
mcp = FastMCP(APP_NAME, lifespan=sharepoint_lifespan)

from tools.site_tools import register_site_tools  # noqa: E402
register_site_tools(mcp)

# --------------------------------------------------------------------
# Build Starlette app from MCP then mount it inside FastAPI
# --------------------------------------------------------------------
from fastapi import FastAPI, APIRouter, HTTPException

starlette_app = mcp.http_app()       # Starlette instance supplied by FastMCP
api = FastAPI(title="SharePoint MCP Wrapper")

# Mount original Starlette app at /mcp/core  (keeps JSON-RPC endpoint alive)
api.mount("/mcp/core", starlette_app)

# --------------------------------------------------------------------
# Add simple REST helper routes at /mcp/...
# --------------------------------------------------------------------
router = APIRouter(prefix="/mcp", tags=["wrappers"])

@router.get("/list_files")
async def list_files_route():
    try:
        return await mcp.call_tool("list_files", {})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get_file_content")
async def get_file_content_route(filename: str):
    try:
        return await mcp.call_tool("get_file_content", {"filename": filename})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

api.include_router(router)

# --------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------
def main() -> None:
    """Run Uvicorn on Render."""
    import uvicorn
    try:
        port = int(os.getenv("PORT", "8080"))
        logger.info("Starting %s on port %s", APP_NAME, port)
        uvicorn.run(api, host="0.0.0.0", port=port, log_level="info")
    except Exception as e:
        logger.error("Fatal startup error: %s", e)
        raise

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logger.error("Uncaught fatal error: %s", exc)
        sys.exit(1)
