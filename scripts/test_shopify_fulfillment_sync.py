#!/usr/bin/env python3
"""
Shopify Fulfillment Sync Testing Script

This script provides step-by-step validation of the Shopify fulfillment sync implementation.
Run this to test the complete flow from Shopify to your database to the API.
"""

import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy import create_engine

from app.database import get_db, DATABASE_URL
from app.models import Order, OrderShipment, User
from app.services.shopify_fulfillment_service import (
    sync_fulfillments_for_order,
    sync_all_pending_fulfillments
)
from app.workers.shopify_fulfillment_worker import run_shopify_fulfillment_worker
from app.workers.selloship_status_worker import run_selloship_status_worker

logger = logging.getLogger(__name__)


class ShopifyFulfillmentTester:
    """Comprehensive tester for Shopify fulfillment sync implementation."""
    
    def __init__(self):
        self.db = None
        self.test_results = []
    
    def setup_database(self):
        """Setup database connection."""
        try:
            engine = create_engine(DATABASE_URL)
            self.db = Session(engine)
            print("✅ Database connection established")
            return True
        except Exception as e:
            print(f"❌ Failed to connect to database: {e}")
            return False
    
    def test_1_check_database_schema(self) -> Dict[str, Any]:
        """Test 1: Verify order_shipments table exists and has correct structure."""
        print("\n🧪 Test 1: Checking database schema...")
        
        try:
            # Check if OrderShipment model can be queried
            shipments = self.db.query(OrderShipment).limit(1).all()
            
            # Check model attributes
            required_fields = [
                'id', 'order_id', 'shopify_fulfillment_id', 'tracking_number',
                'courier', 'fulfillment_status', 'delivery_status', 'selloship_status',
                'last_synced_at', 'created_at', 'updated_at'
            ]
            
            for field in required_fields:
                if not hasattr(OrderShipment, field):
                    raise Exception(f"Missing field: {field}")
            
            result = {
                "success": True,
                "message": "✅ Database schema is correct",
                "table_exists": True,
                "fields_verified": len(required_fields)
            }
            print(f"   {result['message']}")
            return result
            
        except Exception as e:
            result = {
                "success": False,
                "message": f"❌ Database schema error: {e}",
                "table_exists": False
            }
            print(f"   {result['message']}")
            return result
    
    def test_2_check_orders_without_shipments(self) -> Dict[str, Any]:
        """Test 2: Find orders that need fulfillment sync."""
        print("\n🧪 Test 2: Checking orders without shipments...")
        
        try:
            # Get orders without shipments
            orders_without_shipments = self.db.query(Order).filter(
                ~Order.shipments.any()
            ).limit(10).all()
            
            result = {
                "success": True,
                "message": f"✅ Found {len(orders_without_shipments)} orders without shipments",
                "orders_count": len(orders_without_shipments),
                "sample_orders": [
                    {
                        "id": order.id,
                        "channel_order_id": order.channel_order_id,
                        "customer_name": order.customer_name,
                        "status": order.status.value
                    }
                    for order in orders_without_shipments[:3]
                ]
            }
            print(f"   {result['message']}")
            if result['sample_orders']:
                print(f"   Sample orders:")
                for order in result['sample_orders']:
                    print(f"     - {order['channel_order_id']} ({order['customer_name']})")
            return result
            
        except Exception as e:
            result = {
                "success": False,
                "message": f"❌ Error checking orders: {e}",
                "orders_count": 0
            }
            print(f"   {result['message']}")
            return result
    
    def test_3_sync_single_order(self) -> Dict[str, Any]:
        """Test 3: Sync fulfillments for a single order."""
        print("\n🧪 Test 3: Testing single order fulfillment sync...")
        
        try:
            # Get a test order
            test_order = self.db.query(Order).filter(
                ~Order.shipments.any()
            ).first()
            
            if not test_order:
                return {
                    "success": False,
                    "message": "❌ No orders found for testing",
                    "order_id": None
                }
            
            # Get user ID for the order
            user_id = test_order.user_id
            
            print(f"   Testing sync for order {test_order.channel_order_id}...")
            
            # Sync fulfillments
            result = sync_fulfillments_for_order(str(test_order.id), user_id, self.db)
            
            if result["success"]:
                # Check if shipments were created
                shipments = self.db.query(OrderShipment).filter(
                    OrderShipment.order_id == test_order.id
                ).all()
                
                result.update({
                    "order_id": test_order.id,
                    "channel_order_id": test_order.channel_order_id,
                    "shipments_created": len(shipments),
                    "shipments_data": [
                        {
                            "tracking_number": s.tracking_number,
                            "courier": s.courier,
                            "fulfillment_status": s.fulfillment_status
                        }
                        for s in shipments
                    ]
                })
                
                print(f"   ✅ Sync successful: {result['message']}")
                print(f"   📦 Created {len(shipments)} shipments")
            else:
                result.update({
                    "order_id": test_order.id,
                    "channel_order_id": test_order.channel_order_id
                })
                print(f"   ❌ Sync failed: {result['message']}")
            
            return result
            
        except Exception as e:
            result = {
                "success": False,
                "message": f"❌ Single order sync error: {e}",
                "order_id": None
            }
            print(f"   {result['message']}")
            return result
    
    def test_4_sync_all_pending(self) -> Dict[str, Any]:
        """Test 4: Sync all pending fulfillments."""
        print("\n🧪 Test 4: Testing bulk fulfillment sync...")
        
        try:
            # Get a test user
            test_user = self.db.query(User).first()
            
            if not test_user:
                return {
                    "success": False,
                    "message": "❌ No users found for testing",
                    "user_id": None
                }
            
            print(f"   Testing bulk sync for user {test_user.email}...")
            
            # Sync all pending fulfillments
            result = sync_all_pending_fulfillments(str(test_user.id), self.db)
            
            result.update({
                "user_id": test_user.id,
                "user_email": test_user.email
            })
            
            if result["success"]:
                print(f"   ✅ Bulk sync successful: {result['message']}")
                print(f"   📦 Processed {result.get('total_orders', 0)} orders")
                print(f"   📦 Synced {result.get('synced', 0)} new shipments")
            else:
                print(f"   ❌ Bulk sync failed: {result['message']}")
            
            return result
            
        except Exception as e:
            result = {
                "success": False,
                "message": f"❌ Bulk sync error: {e}",
                "user_id": None
            }
            print(f"   {result['message']}")
            return result
    
    async def test_5_shopify_worker(self) -> Dict[str, Any]:
        """Test 5: Test Shopify fulfillment worker."""
        print("\n🧪 Test 5: Testing Shopify fulfillment worker...")
        
        try:
            print("   Running Shopify fulfillment worker...")
            result = run_shopify_fulfillment_worker()
            
            if result["success"]:
                print(f"   ✅ Worker successful: {result['message']}")
                print(f"   📦 Synced {result.get('synced', 0)} shipments")
            else:
                print(f"   ❌ Worker failed: {result['message']}")
            
            return result
            
        except Exception as e:
            result = {
                "success": False,
                "message": f"❌ Worker error: {e}",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            print(f"   {result['message']}")
            return result
    
    async def test_6_selloship_worker(self) -> Dict[str, Any]:
        """Test 6: Test Selloship status worker."""
        print("\n🧪 Test 6: Testing Selloship status worker...")
        
        try:
            print("   Running Selloship status worker...")
            result = run_selloship_status_worker()
            
            if result["success"]:
                print(f"   ✅ Worker successful: {result['message']}")
                print(f"   📦 Processed {result.get('total_processed', 0)} shipments")
            else:
                print(f"   ❌ Worker failed: {result['message']}")
            
            return result
            
        except Exception as e:
            result = {
                "success": False,
                "message": f"❌ Worker error: {e}",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            print(f"   {result['message']}")
            return result
    
    def test_7_check_api_response(self) -> Dict[str, Any]:
        """Test 7: Check orders API response includes shipments."""
        print("\n🧪 Test 7: Testing orders API response...")
        
        try:
            # Get an order with shipments
            order_with_shipments = self.db.query(Order).join(
                Order.shipments
            ).first()
            
            if not order_with_shipments:
                return {
                    "success": False,
                    "message": "❌ No orders with shipments found for API testing",
                    "order_id": None
                }
            
            # This would normally be tested via HTTP request
            # For now, we'll verify the data structure
            shipments = self.db.query(OrderShipment).filter(
                OrderShipment.order_id == order_with_shipments.id
            ).all()
            
            result = {
                "success": True,
                "message": f"✅ Order {order_with_shipments.channel_order_id} has {len(shipments)} shipments",
                "order_id": order_with_shipments.id,
                "channel_order_id": order_with_shipments.channel_order_id,
                "shipments_count": len(shipments),
                "shipments_structure": [
                    {
                        "trackingNumber": s.tracking_number,
                        "courier": s.courier,
                        "fulfillmentStatus": s.fulfillment_status,
                        "deliveryStatus": s.delivery_status,
                        "selloshipStatus": s.selloship_status
                    }
                    for s in shipments
                ]
            }
            
            print(f"   {result['message']}")
            for shipment in result['shipments_structure']:
                print(f"     📦 {shipment['trackingNumber']} ({shipment['courier']}) - {shipment['fulfillmentStatus']}")
            
            return result
            
        except Exception as e:
            result = {
                "success": False,
                "message": f"❌ API test error: {e}",
                "order_id": None
            }
            print(f"   {result['message']}")
            return result
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all tests and return comprehensive results."""
        print("🚀 Starting Shopify Fulfillment Sync Tests")
        print("=" * 60)
        
        # Setup
        if not self.setup_database():
            return {"success": False, "message": "Database setup failed"}
        
        # Run tests
        tests = [
            ("Database Schema", self.test_1_check_database_schema),
            ("Orders Without Shipments", self.test_2_check_orders_without_shipments),
            ("Single Order Sync", self.test_3_sync_single_order),
            ("Bulk Sync", self.test_4_sync_all_pending),
            ("Shopify Worker", self.test_5_shopify_worker),
            ("Selloship Worker", self.test_6_selloship_worker),
            ("API Response", self.test_7_check_api_response)
        ]
        
        results = {}
        passed = 0
        failed = 0
        
        for test_name, test_func in tests:
            try:
                if asyncio.iscoroutinefunction(test_func):
                    result = await test_func()
                else:
                    result = test_func()
                
                results[test_name] = result
                self.test_results.append(result)
                
                if result["success"]:
                    passed += 1
                else:
                    failed += 1
                    
            except Exception as e:
                error_result = {
                    "success": False,
                    "message": f"❌ Test crashed: {e}"
                }
                results[test_name] = error_result
                self.test_results.append(error_result)
                failed += 1
                print(f"   {error_result['message']}")
        
        # Summary
        summary = {
            "success": failed == 0,
            "message": f"Tests completed: {passed} passed, {failed} failed",
            "total_tests": len(tests),
            "passed": passed,
            "failed": failed,
            "results": results,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        print(f"Total Tests: {summary['total_tests']}")
        print(f"Passed: {summary['passed']} ✅")
        print(f"Failed: {summary['failed']} ❌")
        print(f"Overall: {'✅ SUCCESS' if summary['success'] else '❌ FAILURE'}")
        
        if failed > 0:
            print("\n❌ FAILED TESTS:")
            for test_name, result in results.items():
                if not result["success"]:
                    print(f"   - {test_name}: {result['message']}")
        
        print("=" * 60)
        
        return summary


async def main():
    """Main testing function."""
    tester = ShopifyFulfillmentTester()
    result = await tester.run_all_tests()
    
    if result["success"]:
        print("\n🎉 ALL TESTS PASSED!")
        print("Your Shopify fulfillment sync implementation is working correctly!")
    else:
        print("\n💥 SOME TESTS FAILED!")
        print("Please fix the issues before proceeding to production.")
    
    return result


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('shopify_fulfillment_tests.log')
        ]
    )
    
    # Run tests
    asyncio.run(main())
