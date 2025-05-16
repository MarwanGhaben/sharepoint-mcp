"""Main implementation of the SharePoint MCP Server."""

import os
import sys
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from datetime import datetime, timedelta

from mcp.server.fastmcp import FastMCP
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
        logger.debug("Attempting to get authentication context...")
        context = await get_auth_context()
        logger.info("Authentication successful. Token expiry: %s", context.token_expiry)
        yield context

    except Exception as e:
        logger.error("Error during SharePoint authentication: %s", e)

        # Fallback “error” context so the server still starts
        yield SharePointContext(
            access_token="error",
            token_expiry=datetime.now() + timedelta(seconds=10),
            graph_url="https://graph.microsoft.com/v1.0",
        )

    finally:
        logger.info("Ending SharePoint connection...")

# --------------------------------------------------------------------
# Create the MCP server and register tools
# --------------------------------------------------------------------
mcp = FastMCP(APP_NAME, lifespan=sharepoint_lifespan)

from tools.site_tools import register_site_tools  # noqa: E402
register_site_tools(mcp)

# --------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------
def main() -> None:
    """Start the SharePoint MCP server under Uvicorn on Render."""
    import uvicorn

    try:
        logger.info("Starting %s server...", APP_NAME)

        # Render sets the listening port in the PORT env var
        port = int(os.getenv("PORT", "8080"))

        # Get a FastAPI/Starlette ASGI app from FastMCP (works in MCP 1.x)
        app = mcp.http_app()

        # Launch Uvicorn
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

    except Exception as e:
        logger.error("Fatal startup error: %s", e)
        raise

# --------------------------------------------------------------------
# Script execution guard
# --------------------------------------------------------------------
if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logger.error("Uncaught fatal error: %s", exc)
        sys.exit(1)
