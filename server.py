# server.py
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
# Build Starlette app from MCP then mount at /mcp
# --------------------------------------------------------------------
from fastapi import FastAPI

starlette_app = mcp.http_app()       # JSON-RPC core
api = FastAPI(title="SharePoint MCP JSON-RPC")

# Mount the core JSON-RPC endpoint under /mcp
api.mount("/mcp", starlette_app)

# --------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------
def main() -> None:
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
