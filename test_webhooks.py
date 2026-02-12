#!/usr/bin/env python3
"""
Test script for webhook functionality.
Tests webhook endpoints, real-time updates, and channel integrations.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any

import httpx
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app.models import WebhookEvent, ChannelAccount, Channel, ChannelType
from app.services.realtime_service import realtime_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WebhookTester:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=base_url)
        
    async def test_shopify_webhook(self):
        """Test Shopify webhook endpoint"""
        logger.info("Testing Shopify webhook endpoint...")
        
        # Sample Shopify order payload
        shopify_payload = {
            "id": 123456789,
            "email": "customer@example.com",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "total_price": "99.99",
            "financial_status": "paid",
            "fulfillment_status": None,
            "line_items": [
                {
                    "id": 987654321,
                    "variant_id": 456789123,
                    "title": "Test Product",
                    "quantity": 1,
                    "price": "99.99",
                    "sku": "TEST-SKU-001"
                }
            ],
            "billing_address": {
                "first_name": "John",
                "last_name": "Doe",
                "address1": "123 Test St",
                "city": "Test City",
                "province": "CA",
                "country": "US",
                "zip": "12345"
            },
            "shipping_address": {
                "first_name": "John",
                "last_name": "Doe",
                "address1": "123 Test St",
                "city": "Test City",
                "province": "CA",
                "country": "US",
                "zip": "12345"
            }
        }
        
        headers = {
            "X-Shopify-Topic": "orders/create",
            "X-Shopify-Shop-Domain": "test-shop.myshopify.com",
            "X-Shopify-Hmac-Sha256": "test-signature",  # In real implementation, this would be properly signed
            "Content-Type": "application/json"
        }
        
        try:
            response = await self.client.post(
                "/api/webhooks/shopify",
                json=shopify_payload,
                headers=headers
            )
            logger.info(f"Shopify webhook response: {response.status_code}")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Shopify webhook test failed: {e}")
            return False
    
    async def test_amazon_webhook(self):
        """Test Amazon webhook endpoint"""
        logger.info("Testing Amazon webhook endpoint...")
        
        # Sample Amazon notification payload
        amazon_payload = {
            "notificationType": "ORDER_CHANGE",
            "marketplaceId": "ATVPDKIKX0DER",
            "payload": {
                "OrderChangeNotification": {
                    "AmazonOrderId": "123-4567890-1234567",
                    "OrderStatus": "Pending"
                }
            }
        }
        
        headers = {
            "X-Amz-Sns-Message-Signature": "test-signature",
            "X-Amz-Sns-Topic": "arn:aws:sns:us-east-1:123456789012:TestTopic",
            "Content-Type": "application/json"
        }
        
        try:
            response = await self.client.post(
                "/api/webhooks/amazon",
                json=amazon_payload,
                headers=headers
            )
            logger.info(f"Amazon webhook response: {response.status_code}")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Amazon webhook test failed: {e}")
            return False
    
    async def test_flipkart_webhook(self):
        """Test Flipkart webhook endpoint"""
        logger.info("Testing Flipkart webhook endpoint...")
        
        # Sample Flipkart order payload
        flipkart_payload = {
            "order": {
                "orderId": "OD123456789012345678",
                "status": "PACKED",
                "totalAmount": 999.99,
                "paymentMode": "PREPAID",
                "customer": {
                    "name": "John Doe",
                    "email": "customer@example.com"
                },
                "orderItems": [
                    {
                        "sku": "FLIPKART-SKU-001",
                        "title": "Test Product",
                        "quantity": 1,
                        "price": 999.99
                    }
                ]
            }
        }
        
        headers = {
            "X-Flipkart-Event-Type": "ORDER_UPDATED",
            "X-Flipkart-Seller-Id": "test-seller-id",
            "X-Flipkart-Signature": "test-signature",
            "Content-Type": "application/json"
        }
        
        try:
            response = await self.client.post(
                "/api/webhooks/flipkart",
                json=flipkart_payload,
                headers=headers
            )
            logger.info(f"Flipkart webhook response: {response.status_code}")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Flipkart webhook test failed: {e}")
            return False
    
    async def test_webhook_events_list(self):
        """Test webhook events listing endpoint"""
        logger.info("Testing webhook events list...")
        
        try:
            response = await self.client.get("/api/webhooks")
            logger.info(f"Webhook events list response: {response.status_code}")
            if response.status_code == 200:
                events = response.json()
                logger.info(f"Found {len(events)} webhook events")
                return True
            return False
        except Exception as e:
            logger.error(f"Webhook events list test failed: {e}")
            return False
    
    async def test_webhook_subscriptions(self):
        """Test webhook subscriptions endpoint"""
        logger.info("Testing webhook subscriptions...")
        
        try:
            response = await self.client.get("/api/webhooks/subscriptions")
            logger.info(f"Webhook subscriptions response: {response.status_code}")
            if response.status_code == 200:
                subscriptions = response.json()
                logger.info(f"Found {len(subscriptions)} webhook subscriptions")
                return True
            return False
        except Exception as e:
            logger.error(f"Webhook subscriptions test failed: {e}")
            return False
    
    def check_database_events(self):
        """Check database for webhook events"""
        logger.info("Checking database for webhook events...")
        
        db = SessionLocal()
        try:
            events = db.query(WebhookEvent).all()
            logger.info(f"Database contains {len(events)} webhook events")
            
            for event in events[-5:]:  # Show last 5 events
                logger.info(f"Event: {event.source} - {event.topic} - {event.status}")
            
            return len(events) > 0
        except Exception as e:
            logger.error(f"Database check failed: {e}")
            return False
        finally:
            db.close()
    
    async def test_selloship_webhook(self):
        """Test Selloship webhook endpoint"""
        logger.info("Testing Selloship webhook endpoint...")
        
        # Sample Selloship shipment update payload
        selloship_payload = {
            "status": "IN_TRANSIT",
            "tracking_number": "SELLO123456789",
            "updated_at": datetime.utcnow().isoformat(),
            "location": {
                "city": "Mumbai",
                "state": "MH",
                "country": "India"
            },
            "estimated_delivery": datetime.utcnow().isoformat()
        }
        
        headers = {
            "X-Selloship-Event-Type": "SHIPMENT_UPDATED",
            "X-Selloship-Tracking-Number": "SELLO123456789",
            "X-Selloship-Signature": "test-signature",
            "Content-Type": "application/json"
        }
        
        try:
            response = await self.client.post(
                "/api/webhooks/selloship",
                json=selloship_payload,
                headers=headers
            )
            logger.info(f"Selloship webhook response: {response.status_code}")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Selloship webhook test failed: {e}")
            return False
    
    async def test_realtime_service(self):
        """Test real-time service functionality"""
        logger.info("Testing real-time service...")
        
        try:
            # Test creating a mock event and broadcasting it
            db = SessionLocal()
            try:
                # Create a test webhook event
                test_event = WebhookEvent(
                    id="test-event-123",
                    source="test",
                    shop_domain="test-shop.com",
                    topic="test/topic",
                    payload_summary="test event"
                )
                db.add(test_event)
                db.commit()
                
                # Test broadcasting
                await realtime_service.broadcast_webhook_event(db, test_event)
                logger.info("Real-time broadcast test completed")
                
                # Clean up
                db.delete(test_event)
                db.commit()
                
                return True
            except Exception as e:
                logger.error(f"Real-time test failed: {e}")
                return False
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Real-time service test failed: {e}")
            return False
    
    async def run_all_tests(self):
        """Run all webhook tests"""
        logger.info("Starting comprehensive webhook tests...")
        
        results = {
            "shopify_webhook": await self.test_shopify_webhook(),
            "amazon_webhook": await self.test_amazon_webhook(),
            "flipkart_webhook": await self.test_flipkart_webhook(),
            "selloship_webhook": await self.test_selloship_webhook(),
            "webhook_events_list": await self.test_webhook_events_list(),
            "webhook_subscriptions": await self.test_webhook_subscriptions(),
            "database_events": self.check_database_events(),
            "realtime_service": await self.test_realtime_service(),
        }
        
        logger.info("\n=== TEST RESULTS ===")
        for test_name, result in results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            logger.info(f"{test_name}: {status}")
        
        total_tests = len(results)
        passed_tests = sum(results.values())
        logger.info(f"\nTotal: {passed_tests}/{total_tests} tests passed")
        
        return results

async def main():
    """Main test function"""
    tester = WebhookTester()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())
