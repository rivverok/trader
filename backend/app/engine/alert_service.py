"""Alert service — creates alerts and broadcasts via WebSocket.

Provides a simple `create_alert()` function used by other modules
(executor, risk manager, ML tasks) to fire alerts.
WebSocket connections are managed for real-time push to the frontend.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert

logger = logging.getLogger(__name__)

# In-memory set of connected WebSocket clients
_ws_clients: set = set()


def register_ws(ws):
    _ws_clients.add(ws)


def unregister_ws(ws):
    _ws_clients.discard(ws)


async def broadcast(data: dict):
    """Send a JSON message to all connected WebSocket clients."""
    import json
    message = json.dumps(data)
    dead = set()
    for ws in _ws_clients:
        try:
            await ws.send_text(message)
        except Exception:
            dead.add(ws)
    _ws_clients -= dead


async def create_alert(
    db: AsyncSession,
    alert_type: str,
    message: str,
    severity: str = "info",
) -> Alert:
    """Create an alert, persist it, and broadcast to WebSocket clients."""
    alert = Alert(
        type=alert_type,
        severity=severity,
        message=message,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)

    # Broadcast to connected frontends
    await broadcast({
        "event": "alert",
        "alert": {
            "id": alert.id,
            "type": alert.type,
            "severity": alert.severity,
            "message": alert.message,
            "acknowledged": alert.acknowledged,
            "created_at": alert.created_at.isoformat(),
        },
    })

    logger.info("Alert [%s/%s]: %s", severity, alert_type, message)
    return alert
