# Webhook Implementation Guide

This document describes the comprehensive webhook implementation that provides real-time updates for all supported channels (Shopify, Amazon, Flipkart, Myntra).

## Overview

The webhook system consists of:
1. **Backend webhook handlers** for receiving and processing channel events
2. **Real-time service** using Server-Sent Events (SSE) for live updates
3. **Frontend integration** for displaying real-time updates
4. **Comprehensive testing** tools

## Architecture

```
Channel Servers (Shopify, Amazon, etc.)
    ↓ (Webhook Events)
Backend API (FastAPI)
    ↓ (Process Events)
Database + Real-time Service
    ↓ (SSE Stream)
Frontend (React/Next.js)
```

## Backend Implementation

### 1. Webhook Endpoints

#### Shopify (`/api/webhooks/shopify`)
- **Topics**: `orders/create`, `orders/updated`, `orders/cancelled`, `refunds/create`, `inventory_levels/update`, `products/update`
- **Security**: HMAC-SHA256 signature verification
- **Handler**: `app/services/shopify_webhook_handler.py`

#### Selloship (`/api/webhooks/selloship`)
- **Topics**: `SHIPMENT_CREATED`, `SHIPMENT_UPDATED`, `SHIPMENT_DELIVERED`, `SHIPMENT_RTO`
- **Security**: HMAC-SHA256 signature verification
- **Handler**: `app/services/selloship_webhook_handler.py`

#### Amazon (`/api/webhooks/amazon`)
- **Topics**: `ORDER_CHANGE`, `FEED_PROCESSING_FINISHED`, `REPORT_PROCESSING_FINISHED`
- **Security**: RSA-SHA256 signature verification
- **Handler**: `app/services/amazon_webhook_handler.py`

#### Flipkart (`/api/webhooks/flipkart`)
- **Topics**: `ORDER_CREATED`, `ORDER_UPDATED`, `SHIPMENT_CREATED`, `PAYMENT_UPDATED`
- **Security**: HMAC-SHA256 signature verification
- **Handler**: `app/services/flipkart_webhook_handler.py`

### 2. Real-time Service

**File**: `app/services/realtime_service.py`

Features:
- **Server-Sent Events (SSE)** for real-time communication
- **User-specific broadcasting** based on connected channels
- **Connection management** with automatic reconnection
- **Event filtering** by user permissions

**Endpoints**:
- `GET /api/webhooks/events/stream` - SSE stream for real-time updates

### 3. Database Models

**WebhookEvent Model**:
```python
class WebhookEvent(Base):
    id: str
    source: str  # shopify, amazon, flipkart
    shop_domain: str
    topic: str
    payload_summary: str
    processed_at: datetime
    error: str
```

## Frontend Implementation

### 1. Real-time Service

**File**: `src/services/realtime.ts`

Features:
- **EventSource connection** to SSE endpoint
- **Automatic reconnection** with exponential backoff
- **Event filtering** and routing
- **React hooks** for easy integration

### 2. Webhook Events Page

**File**: `app/dashboard/webhooks/page.tsx`

Features:
- **Live event stream** display
- **Real-time status indicator**
- **Event filtering** and pagination
- **Connection management** (connect/disconnect)

### 3. Orders Page

**File**: `app/dashboard/orders/page.tsx`

Features:
- **Live order updates** when status changes
- **Real-time indicators** in UI
- **Automatic refresh** of order details
- **Connection status** display

## Installation & Setup

### 1. Backend Dependencies

Add to `requirements.txt`:
```
sse-starlette==2.1.3
cryptography==43.0.1  # For webhook signature verification
```

### 2. Environment Variables

```bash
# Base URL for webhook registration
WEBHOOK_BASE_URL=https://your-domain.com

# Shopify App Configuration (optional, can be set per user)
SHOPIFY_API_KEY=your_shopify_api_key
SHOPIFY_API_SECRET=your_shopify_api_secret

# Amazon SP-API Configuration (optional)
AMAZON_ACCESS_KEY=your_amazon_access_key
AMAZON_SECRET_KEY=your_amazon_secret_key

# Flipkart Configuration (optional)
FLIPKART_CLIENT_ID=your_flipkart_client_id
FLIPKART_CLIENT_SECRET=your_flipkart_client_secret
```

### 3. Database Migration

The webhook system uses existing database models. No additional migrations needed.

## Configuration

### 1. Channel Webhook Registration

#### Shopify
```bash
curl -X POST "http://localhost:8000/api/webhooks/register/{integration_id}" \
  -H "Authorization: Bearer {token}"
```

#### Amazon & Flipkart
Webhooks need to be configured in the respective channel developer consoles:
- **Amazon**: Configure SNS topics to send notifications to your endpoint
- **Flipkart**: Configure webhook URLs in the Flipkart Seller Portal

### 2. Real-time Service Configuration

The real-time service is configured automatically but can be customized:

```python
# In app/services/realtime_service.py
class RealtimeService:
    def __init__(self):
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 1000  # milliseconds
```

## Testing

### 1. Run Test Script

```bash
cd /Users/alikhusroo/Projects/api-python
python test_webhooks.py
```

The test script will:
- Test all webhook endpoints
- Verify database storage
- Test real-time broadcasting
- Check API responses

### 2. Manual Testing

#### Shopify Webhook Test
```bash
curl -X POST "http://localhost:8000/api/webhooks/shopify" \
  -H "X-Shopify-Topic: orders/create" \
  -H "X-Shopify-Shop-Domain: test-shop.myshopify.com" \
  -H "Content-Type: application/json" \
  -d @test_shopify_payload.json
```

#### Real-time Stream Test
```bash
curl -N -H "Authorization: Bearer {token}" \
  "http://localhost:8000/api/webhooks/events/stream"
```

## Security Considerations

### 1. Webhook Signature Verification

All webhook endpoints verify signatures:
- **Shopify**: HMAC-SHA256 with app secret
- **Amazon**: RSA-SHA256 with public key
- **Flipkart**: HMAC-SHA256 with secret

### 2. User Authorization

- Webhook endpoints are **public** (no JWT) for channel compatibility
- Real-time streams require **user authentication**
- Events are **filtered by user** based on connected channels

### 3. Rate Limiting

Consider implementing rate limiting for webhook endpoints:
```python
from slowapi import Limiter
limiter = Limiter(key_func=lambda: "webhook")

@router.post("/shopify")
@limiter.limit("100/minute")
async def shopify_webhook_receive(request: Request):
    # ... handler code
```

## Monitoring & Debugging

### 1. Log Monitoring

Monitor these log messages:
```
INFO: Webhook orders/create: upserted order 123 and recomputed profit
INFO: Real-time service connected
ERROR: Webhook signature verification failed
```

### 2. Database Monitoring

Check webhook events table:
```sql
SELECT source, topic, status, COUNT(*) 
FROM webhook_events 
GROUP BY source, topic, status;
```

### 3. Real-time Connection Monitoring

Monitor active connections:
```python
# Add to realtime service
def get_connection_stats():
    return {
        "total_connections": sum(len(conns) for conns in self.connections.values()),
        "active_users": len(self.connections)
    }
```

## Performance Considerations

### 1. Database Optimization

- Add indexes on `webhook_events.shop_domain` and `webhook_events.created_at`
- Consider archiving old webhook events
- Use connection pooling for database operations

### 2. Memory Management

- Limit event history in frontend (keep last 50 events)
- Implement connection timeouts for SSE streams
- Use efficient JSON serialization

### 3. Scaling

For high-volume scenarios:
- Use Redis for connection management
- Implement horizontal scaling with load balancers
- Consider message queues for webhook processing

## Troubleshooting

### Common Issues

1. **Webhook not received**
   - Check channel webhook configuration
   - Verify webhook URL is accessible
   - Check signature verification

2. **Real-time updates not working**
   - Check SSE connection status
   - Verify user authentication
   - Check browser console for errors

3. **Database errors**
   - Check database connection
   - Verify table schemas
   - Check for constraint violations

### Debug Commands

```bash
# Check webhook events
curl "http://localhost:8000/api/webhooks" -H "Authorization: Bearer {token}"

# Test SSE connection
curl -N "http://localhost:8000/api/webhooks/events/stream" \
  -H "Authorization: Bearer {token}"

# Check real-time service logs
tail -f logs/app.log | grep "realtime"
```

## Future Enhancements

1. **Additional Channels**: Add support for more marketplaces
2. **Webhook Retry Logic**: Implement exponential backoff for failed webhooks
3. **Event Filtering**: Allow users to filter webhook events by type
4. **Analytics Dashboard**: Add webhook performance metrics
5. **Alert System**: Send notifications for webhook failures

## Support

For issues or questions:
1. Check the logs for error messages
2. Run the test script to verify functionality
3. Review the troubleshooting section
4. Check the API documentation for endpoint details
