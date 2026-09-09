"""
Magneetar WebSocket Handlers (extracted from main.py — Phase 0).

WebSocket endpoints for real-time dashboard and admin updates.
These are registered on the FastAPI app in main.py via app.websocket().

Separated from main.py to:
- Reduce main.py from 738 lines to < 400
- Group WebSocket logic in one file
- Make WebSocket auth and message handling testable independently
"""

from auth import decode_token, user_id_from_subject
from database import get_db_context
from fastapi import WebSocket, WebSocketDisconnect
from logging_config import get_logger
from websocket_manager import (
    ADMIN_OWNER,
    MAX_DASHBOARD_CONNECTIONS,
    active_dashboard_connections,
    add_connection,
    can_accept_new_connection,
    close_lowest_priority_connection,
    record_pong,
    remove_websocket,
    update_device_owner,
)

logger = get_logger("magneetar")


def _is_pong_message(data: str) -> bool:
    """True when a client keepalive message is a pong."""
    if data == "pong":
        return True
    return data.replace(" ", "") == '{"type":"pong"}'


def register_websocket_routes(app):
    """Register WebSocket routes on the FastAPI app.

    Called in main.py after the app instance is created. Keeps WebSocket
    handlers defined here (in infrastructure/) while registration happens
    in main.py.
    """

    @app.websocket("/ws/dashboard")
    async def dashboard_websocket(websocket: WebSocket):
        """WebSocket for real-time dashboard updates."""
        await websocket.accept()

        token = websocket.query_params.get("token")
        if not token:
            await websocket.close(code=4408, reason="Authentication required")
            return

        owner = None
        device_ids = None
        try:
            payload = decode_token(token)
            if payload.get("type") not in ("dashboard", "access"):
                await websocket.close(code=4001, reason="Invalid token type")
                return
            sub = payload.get("sub", "")
            user_id = user_id_from_subject(sub)
            if user_id:
                owner = user_id
                try:
                    with get_db_context() as conn:
                        owned = conn.execute("SELECT id FROM devices WHERE owner_id=?", (owner,)).fetchall()
                        for row in owned:
                            update_device_owner(row["id"], owner)
                        shared = conn.execute(
                            "SELECT device_id AS id FROM device_shares "
                            "WHERE grantee_user_id=? AND role != 'device_only'",
                            (owner,),
                        ).fetchall()
                        device_ids = {row["id"] for row in owned} | {row["id"] for row in shared}
                except Exception:
                    pass
            elif sub.startswith("dashboard:"):
                owner = ADMIN_OWNER
        except Exception:
            await websocket.close(code=4001, reason="Invalid token")
            return

        if owner is None:
            await websocket.close(code=4001, reason="Invalid token subject")
            return

        if not can_accept_new_connection():
            logger.warning(
                "WebSocket at capacity — evicting oldest connection",
                extra={
                    "extra_data": {
                        "active": len(active_dashboard_connections),
                        "max": MAX_DASHBOARD_CONNECTIONS,
                    }
                },
            )
            await close_lowest_priority_connection()

        add_connection(websocket, owner, device_ids)
        logger.info(
            "WebSocket connected",
            extra={
                "extra_data": {
                    "total": len(active_dashboard_connections),
                    "max": MAX_DASHBOARD_CONNECTIONS,
                }
            },
        )

        try:
            while True:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
                elif _is_pong_message(data):
                    record_pong(websocket)
        except WebSocketDisconnect:
            remove_websocket(websocket)

    @app.websocket("/ws/admin")
    async def admin_websocket(websocket: WebSocket):
        """WebSocket for real-time admin dashboard updates."""
        from websocket_manager import admin_connect, admin_disconnect

        await websocket.accept()

        token = websocket.query_params.get("token")
        if not token:
            await websocket.close(code=4408, reason="Authentication required")
            return

        try:
            payload = decode_token(token)
            user_id = payload.get("sub", "")

            with get_db_context() as db:
                user = db.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
                if not user or user[0] != "admin":
                    await websocket.close(code=4003, reason="Admin access required")
                    return
        except Exception:
            await websocket.close(code=4001, reason="Invalid token")
            return

        await admin_connect(websocket)

        try:
            from routes.admin import get_admin_stats

            stats = await get_admin_stats(admin=user_id)
            await websocket.send_json({"type": "stats_update", "data": stats})

            while True:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
                elif data == "refresh":
                    stats = await get_admin_stats(admin=user_id)
                    await websocket.send_json({"type": "stats_update", "data": stats})
        except WebSocketDisconnect:
            await admin_disconnect(websocket)
