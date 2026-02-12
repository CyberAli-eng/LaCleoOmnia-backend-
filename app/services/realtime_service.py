"""
Real-time notification service using Server-Sent Events (SSE).
Manages client connections and broadcasts webhook events to connected clients.
"""
import asyncio
import json
import logging
from typing import Dict, Set, Any, Optional
from fastapi import Request
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session

from app.models import User, WebhookEvent
from app.auth import get_current_user

logger = logging.getLogger(__name__)

class RealtimeService:
    def __init__(self):
        # Store active connections by user_id
        self.connections: Dict[str, Set[asyncio.Queue]] = {}
        # Store event queues for broadcasting
        self.event_queue = asyncio.Queue()
        # Background task for processing events
        self._background_task = None

    async def connect(self, user_id: str) -> asyncio.Queue:
        """Add a new connection for a user and return their event queue."""
        if user_id not in self.connections:
            self.connections[user_id] = set()
        
        queue = asyncio.Queue()
        self.connections[user_id].add(queue)
        
        # Start background task if not running
        if self._background_task is None:
            self._background_task = asyncio.create_task(self._process_events())
        
        logger.info("User %s connected to real-time updates", user_id)
        return queue

    async def disconnect(self, user_id: str, queue: asyncio.Queue):
        """Remove a connection for a user."""
        if user_id in self.connections:
            self.connections[user_id].discard(queue)
            if not self.connections[user_id]:
                del self.connections[user_id]
        
        logger.info("User %s disconnected from real-time updates", user_id)

    async def broadcast_to_user(self, user_id: str, event_data: Dict[str, Any]):
        """Send an event to all connections for a specific user."""
        if user_id in self.connections:
            message = json.dumps(event_data)
            for queue in self.connections[user_id]:
                try:
                    await queue.put(message)
                except Exception as e:
                    logger.error("Error sending message to queue: %s", e)

    async def broadcast_webhook_event(self, db: Session, webhook_event: WebhookEvent):
        """Broadcast a webhook event to relevant users."""
        try:
            # Find users who should receive this webhook event
            # Users who have connected shops matching the webhook's shop_domain
            from app.models import ChannelAccount
            
            relevant_accounts = db.query(ChannelAccount).filter(
                ChannelAccount.shop_domain == webhook_event.shop_domain
            ).all()
            
            user_ids = {str(account.user_id) for account in relevant_accounts}
            
            # Prepare event data
            event_data = {
                "type": "webhook_event",
                "data": {
                    "id": webhook_event.id,
                    "source": webhook_event.source,
                    "shopDomain": webhook_event.shop_domain,
                    "topic": webhook_event.topic,
                    "payloadSummary": webhook_event.payload_summary,
                    "status": "processed" if webhook_event.processed_at else "failed" if webhook_event.error else "pending",
                    "createdAt": webhook_event.created_at.isoformat() if webhook_event.created_at else None,
                    "processedAt": webhook_event.processed_at.isoformat() if webhook_event.processed_at else None,
                    "error": webhook_event.error,
                }
            }
            
            # Broadcast to all relevant users
            for user_id in user_ids:
                await self.broadcast_to_user(user_id, event_data)
                
        except Exception as e:
            logger.error("Error broadcasting webhook event: %s", e)

    async def broadcast_order_update(self, db: Session, order_id: str, update_type: str):
        """Broadcast order updates to relevant users."""
        try:
            from app.models import Order, ChannelAccount
            
            order = db.query(Order).filter(Order.id == order_id).first()
            if not order:
                return
            
            # Find users who should receive this order update
            relevant_accounts = db.query(ChannelAccount).filter(
                ChannelAccount.id == order.channel_account_id
            ).all()
            
            user_ids = {str(account.user_id) for account in relevant_accounts}
            
            # Prepare event data
            event_data = {
                "type": "order_update",
                "data": {
                    "orderId": order.id,
                    "channelOrderId": order.channel_order_id,
                    "status": order.status.value,
                    "updateType": update_type,
                    "updatedAt": order.updated_at.isoformat() if order.updated_at else None,
                }
            }
            
            # Broadcast to all relevant users
            for user_id in user_ids:
                await self.broadcast_to_user(user_id, event_data)
                
        except Exception as e:
            logger.error("Error broadcasting order update: %s", e)

    async def _process_events(self):
        """Background task to process queued events."""
        while True:
            try:
                # Process any queued events
                # This can be used for system-wide broadcasts
                await asyncio.sleep(1)
            except Exception as e:
                logger.error("Error in background event processor: %s", e)
                await asyncio.sleep(5)

    async def generate_events(self, request: Request, current_user: User):
        """Generate SSE events for a connected client."""
        user_id = str(current_user.id)
        queue = await self.connect(user_id)
        
        try:
            while True:
                # Send events to the client
                message = await queue.get()
                yield {
                    "event": "update",
                    "data": message
                }
        except asyncio.CancelledError:
            await self.disconnect(user_id, queue)
            raise
        except Exception as e:
            logger.error("Error in SSE stream for user %s: %s", user_id, e)
            await self.disconnect(user_id, queue)

# Global instance
realtime_service = RealtimeService()
