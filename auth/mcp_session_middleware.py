"""
MCP Session Middleware

This middleware intercepts MCP requests and sets the session context
for use by tool functions.

Uses pure ASGI protocol instead of BaseHTTPMiddleware to avoid
interfering with streaming responses (SSE) used by the streamable-http
MCP transport.  BaseHTTPMiddleware buffers the entire response body
before forwarding it, which blocks SSE streams and causes MCP client
``initialize()`` calls to time out — leaving unclosed aiohttp sessions.
"""

import logging

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from auth.oauth21_session_store import (
    SessionContext,
    SessionContextManager,
    extract_session_from_headers,
)

logger = logging.getLogger(__name__)


class MCPSessionMiddleware:
    """
    Pure ASGI middleware that extracts session information from MCP requests
    and makes it available to tool functions via context variables.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not path.startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        logger.debug("MCPSessionMiddleware processing request: %s %s", scope.get("method", ""), path)

        session_context = None

        try:
            # Build a lightweight Request to read headers and state from scope.
            # This does NOT consume the request body.
            request = Request(scope)

            headers = dict(request.headers)
            session_id = extract_session_from_headers(headers)

            # Try to get OAuth 2.1 auth context from FastMCP
            auth_context = None
            user_email = None
            mcp_session_id = None
            # Check for FastMCP auth context
            if hasattr(request.state, "auth"):
                auth_context = request.state.auth
                # Extract user email from auth claims if available
                if hasattr(auth_context, "claims") and auth_context.claims:
                    user_email = auth_context.claims.get("email")

            # Check for FastMCP session ID (from streamable HTTP transport)
            if hasattr(request.state, "session_id"):
                mcp_session_id = request.state.session_id
                logger.debug(f"Found FastMCP session ID: {mcp_session_id}")

            # SECURITY: Do not decode JWT without verification
            # User email must come from verified sources only (FastMCP auth context)

            # Build session context
            if session_id or auth_context or user_email or mcp_session_id:
                # Create session ID hierarchy: explicit session_id > Google user session > FastMCP session
                effective_session_id = session_id
                if not effective_session_id and user_email:
                    effective_session_id = f"google_{user_email}"
                elif not effective_session_id and mcp_session_id:
                    effective_session_id = mcp_session_id

                session_context = SessionContext(
                    session_id=effective_session_id,
                    user_id=user_email
                    or (auth_context.user_id if auth_context else None),
                    auth_context=auth_context,
                    request=request,
                    metadata={
                        "path": path,
                        "method": scope.get("method", ""),
                        "user_email": user_email,
                        "mcp_session_id": mcp_session_id,
                    },
                )

                logger.debug(
                    f"MCP request with session: session_id={session_context.session_id}, "
                    f"user_id={session_context.user_id}, path={path}"
                )

        except Exception as e:
            logger.error(f"Error extracting session info in MCP middleware: {e}")

        # Process request with session context (or None on extraction failure).
        # The downstream app receives raw scope/receive/send so SSE streams
        # are forwarded without buffering.
        with SessionContextManager(session_context):
            await self.app(scope, receive, send)
