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

# Set logging level
logging_level = logging.DEBUG if DEBUG else logging.INFO
logging.basicConfig(level=logging_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("sharepoint_mcp")

# Import tool registrations
from tools.site_tools import register_site_tools

@asynccontextmanager
async def sharepoint_lifespan(server: FastMCP) -> AsyncIterator[SharePointContext]:
    """Manage SharePoint connection lifecycle."""
    logger.info("Initializing SharePoint connection...")
    
    try:
        # Get SharePoint authentication context
        logger.debug("Attempting to get authentication context...")
        context = await get_auth_context()
        logger.info(f"Authentication successful. Token expiry: {context.token_expiry}")
        
        # Yield context for use in the application
        yield context
        
    except Exception as e:
        logger.error(f"Error during SharePoint authentication: {e}")
        
        # Create error context
        error_context = SharePointContext(
            access_token="error",
            token_expiry=datetime.now() + timedelta(seconds=10),  # Short expiry
            graph_url="https://graph.microsoft.com/v1.0"
        )
        
        logger.warning("Using error context due to authentication failure")
        yield error_context
        
    finally:
        logger.info("Ending SharePoint connection...")

# Create MCP server at module level so CLI can find it
mcp = FastMCP(APP_NAME, lifespan=sharepoint_lifespan)

# Register tools
register_site_tools(mcp)

def main():
    """Main entry point for the SharePoint MCP server."""
    try:
        logger.info(f"Starting %s server...", APP_NAME)

        # Render injects its port into the PORT env var; default to 8080 locally
        port = int(os.getenv("PORT", "8080"))

        # 👉 Tell FastMCP to serve over HTTP (Streamable-HTTP transport)
        mcp.run(
            transport="streamable-http",   # critical!
            host="0.0.0.0",
            port=port,
            log_level="info",
        )

    except Exception as e:
        logger.error("Error occurred during MCP server startup: %s", e)
        raise

# Main execution
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Fatal error in SharePoint MCP server: {e}")
        sys.exit(1)
