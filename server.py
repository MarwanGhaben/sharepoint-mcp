"""server.py: Host the SharePoint MCP JSON-RPC at /mcp"""

import os
import sys
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from datetime import datetime, timedelta

from fastmcp import FastMCP
from fastapi import FastAPI
from auth.sharepoint_auth import SharePointContext, get_auth_context
from config.settings import APP_NAME, DEBUG

# ────────────────────────────────────────────────────────────────────────────────
# Logging
# ────────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("sharepoint_mcp")

# ────────────────────────────────────────────────────────────────────────────────
# SharePoint connection lifespan
# ────────────────────────────────────────────────────────────────────────────────
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
        logger.info("Ending SharePoint connection.")

# ────────────────────────────────────────────────────────────────────────────────
# Create MCP server and register your tools
# ────────────────────────────────────────────────────────────────────────────────
mcp = FastMCP(APP_NAME, lifespan=sharepoint_lifespan)
from tools.site_tools import register_site_tools  # noqa: E402
register_site_tools(mcp)

# ────────────────────────────────────────────────────────────────────────────────
# Build a FastAPI app and mount the MCP JSON-RPC sub-app at /mcp
# ────────────────────────────────────────────────────────────────────────────────
app = FastAPI(title="SharePoint MCP JSON-RPC")
starlette_app = mcp.http_app()   # this sub-app serves JSON-RPC at its base_path
app.mount("/mcp", starlette_app)

# ────────────────────────────────────────────────────────────────────────────────
# Entrypoint
# ────────────────────────────────────────────────────────────────────────────────
def main() -> None:
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    logger.info("Starting %s on port %s", APP_NAME, port)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logger.error("Fatal error: %s", exc)
        sys.exit(1)
