# LaCleoOmnia API Postman Collection

## Overview
Complete Postman collection for LaCleoOmnia e-commerce platform with Razorpay payment gateway integration, settlement automation, and comprehensive financial tracking.

## Base Configuration
- **Base URL**: `http://localhost:8000`
- **Authentication**: Bearer token (JWT)
- **Content-Type**: `application/json`

## Collections

### 1. Authentication
- **Name**: `Auth`
- **Description**: `Authentication endpoints`

#### Requests:
1. **Login**
   - **Method**: `POST`
   - **Endpoint**: `/api/auth/login`
   - **Headers**: 
     ```
     Content-Type: application/json
     ```
   - **Body**:
     ```json
     {
       "email": "your-email@example.com",
       "password": "your-password"
     }
     ```
   - **Tests**: 
     - Status: 200 OK
     - Response contains access token

2. **Refresh Token**
   - **Method**: `POST`
   - **Endpoint**: `/api/auth/refresh`
   - **Headers**: 
     ```
     Authorization: Bearer {{token}}
     Content-Type: application/json
     ```

### 2. Integrations
- **Name**: `Integrations`
- **Description**: `Integration management endpoints`

#### Requests:
1. **Get Catalog**
   - **Method**: `GET`
   - **Endpoint**: `/api/integrations/catalog`
   - **Response**: List of available integrations with Razorpay included

2. **Connect Razorpay**
   - **Method**: `POST`
   - **Endpoint**: `/api/razorpay/connect`
   - **Body**:
     ```json
     {
       "key_id": "rzp_test_1234567890",
       "key_secret": "your_razorpay_secret_key",
       "webhook_secret": "your_razorpay_webhook_secret"
     }
     ```

3. **Test Razorpay Connection**
   - **Method**: `GET`
   - **Endpoint**: `/api/razorpay/status`
   - **Response**: Connection status and test results

4. **Sync Razorpay Payments**
   - **Method**: `POST`
   - **Endpoint**: `/api/razorpay/sync/payments`
   - **Body**:
     ```json
     {
       "days": 7
     }
     ```
   - **Response**: Razorpay payment sync results

5. **Sync Razorpay Settlements**
   - **Method**: `POST`
   - **Endpoint**: `/api/razorpay/sync/settlements`
   - **Body**:
     ```json
     {
       "days": 7
     }
     ```
   - **Response**: Razorpay settlement sync results

6. **Reconcile Order**
   - **Method**: `POST`
   - **Endpoint**: `/api/razorpay/reconcile`
   - **Body**:
     ```json
     {
       "order_id": "order_123",
       "amount": 2999.00,
       "transaction_id": "pay_1234567890"
     }
     ```
   - **Response**: Order reconciliation confirmation

### 3. Orders
- **Name**: `Orders`
- **Description**: `Order management with payment and shipment tracking`

#### Requests:
1. **Get Orders**
   - **Method**: `GET`
   - **Endpoint**: `/api/orders`
   - **Query Params**: 
     - `page`: Page number (default: 1)
     - `limit`: Items per page (default: 20)
     - `search`: Search term
     - `status`: Order status filter
     - `payment_status`: Payment status filter
   - **Response**: Orders with payment gateway and shipment information

2. **Get Order Details**
   - **Method**: `GET`
   - **Endpoint**: `/api/orders/{{order_id}}`
   - **Response**: Complete order details including payment and shipment info

3. **Get Order Finance**
   - **Method**: `GET`
   - **Endpoint**: `/api/finance/orders/{{order_id}}`
   - **Response**: Financial breakdown including Razorpay payment data

### 4. Payments (Razorpay)
- **Name**: `Razorpay Payments`
- **Description**: `Razorpay payment gateway management`

#### Requests:
1. **Get Payments**
   - **Method**: `GET`
   - **Endpoint**: `/api/razorpay/payments`
   - **Query Params**:
     - `days`: Number of days to fetch (default: 7)
   - `from_date`: Start date (YYYY-MM-DD)
     - `to_date`: End date (YYYY-MM-DD)
   - **Response**: List of Razorpay payments

2. **Get Payment Details**
   - **Method**: `GET`
   - **Endpoint**: `/api/razorpay/payments/{{payment_id}}`
   - **Response**: Individual payment details

3. **Reconcile Order**
   - **Method**: `POST`
   - **Endpoint**: `/api/razorpay/reconcile`
   - **Body**:
     ```json
     {
       "order_id": "order_123",
       "amount": 2999.00,
       "transaction_id": "pay_1234567890"
     }
     ```

### 5. Settlements
- **Name**: `Settlements`
- **Description**: `Settlement management and tracking`

#### Requests:
1. **Get Settlements**
   - **Method**: `GET`
   - **Endpoint**: `/api/settlements`
   - **Query Params**:
     - `days`: Number of days (default: 30)
     - `status`: Settlement status filter (PENDING, PROCESSING, SETTLED, FAILED, OVERDUE)
     - `partner`: Partner filter (RAZORPAY, COD, SELLOSHIP, DELHIVERY)
   - **Response**: Settlements with comprehensive breakdown

2. **Get Settlement Forecast**
   - **Method**: `GET`
   - **Endpoint**: `/api/settlements/forecast`
   - **Query Params**:
     - `days`: Number of days to forecast (default: 30)
   - **Response**: Future settlement predictions

3. **Mark Settlement Overdue**
   - **Method**: `POST`
   - **Endpoint**: `/api/settlements/{{settlement_id}}/mark-overdue`
   - **Response**: Settlement status update

4. **Sync Settlements**
   - **Method**: `POST`
   - **Endpoint**: `/api/settlements/sync`
   - **Body**:
     ```json
     {
       "days": 7
     }
     ```

### 6. Finance
- **Name**: `Finance`
- **Description**: `Financial management and reporting`

#### Requests:
1. **Get Finance Overview**
   - **Method**: `GET`
   - **Endpoint**: `/api/finance/overview`
   - **Response**: Dashboard KPIs including Razorpay metrics

2. **Get P&L Report**
   - **Method**: `GET`
   - **Endpoint**: `/api/finance/pnl`
   - **Query Params**:
     - `start_date`: Report start date
     - `end_date`: Report end date
   - **Response**: Profit & Loss breakdown

3. **Get Settlement Summary**
   - **Method**: `GET`
   - **Endpoint**: `/api/finance/settlements`
   - **Query Params**:
     - `days`: Number of days (default: 30)
   - **Response**: Settlement summary by partner

4. **Create/Update Expense**
   - **Method**: `POST`
   - **Endpoint**: `/api/finance/expense`
   - **Body**:
     ```json
     {
       "order_id": "order_123",
       "category": "gateway_fee",
       "description": "Razorpay processing fee",
       "amount": 29.90
     }
     ```

5. **Delete Expense**
   - **Method**: `DELETE`
   - **Endpoint**: `/api/finance/expense/{{expense_id}}`
   - **Response**: Expense deletion confirmation

### 7. Webhooks (Razorpay)
- **Name**: `Razorpay Webhooks`
- **Description**: `Razorpay webhook event handling`

#### Requests:
1. **Payment Captured Webhook**
   - **Method**: `POST`
   - **Endpoint**: `/api/webhooks/razorpay`
   - **Headers**:
     ```
     X-Razorpay-Signature: {{webhook_signature}}
     Content-Type: application/json
     ```
   - **Body**: Razorpay payment.captured event payload
   - **Response**: Webhook processing confirmation

2. **Settlement Processed Webhook**
   - **Method**: `POST`
   - **Endpoint**: `/api/webhooks/razorpay`
   - **Headers**: Same as above
   - **Body**: Razorpay settlement.processed event payload
   - **Response**: Settlement processing confirmation

3. **Payout Processed Webhook**
   - **Method**: `POST`
   - **Endpoint**: `/api/webhooks/razorpay`
   - **Headers**: Same as above
   - **Body**: Razorpay payout.processed event payload
   - **Response**: Bank credit confirmation

### 8. COD & Logistics
- **Name**: `COD & Logistics`
- **Description**: `COD remittance and shipment tracking`

#### Requests:
1. **Sync COD Settlements**
   - **Method**: `POST`
   - **Endpoint**: `/api/settlements/sync/cod`
   - **Body**:
     ```json
     {
       "days": 7,
       "providers": ["selloship", "delhivery"]
     }
     ```

2. **Get Selloship Status**
   - **Method**: `GET`
   - **Endpoint**: `/api/logistics/selloship/status`
   - **Response**: Selloship connection and AWB status

3. **Sync Shipments**
   - **Method**: `POST`
   - **Endpoint**: `/api/logistics/sync`
   - **Body**:
     ```json
     {
       "order_id": "order_123"
     }
     ```

## Environment Variables
Set these in your `.env` file:
```bash
# Razorpay Configuration
RAZORPAY_KEY_ID=rzp_test_1234567890
RAZORPAY_KEY_SECRET=your_razorpay_secret_key
RAZORPAY_WEBHOOK_SECRET=your_webhook_secret

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/lacleo_omnia
```

## Testing Scenarios

### 1. Complete Razorpay Flow
1. Connect Razorpay gateway
2. Create test order with Razorpay payment
3. Verify payment appears in orders list
4. Check settlement creation
5. Verify webhook processing
6. Confirm profit calculation

### 2. Settlement Automation
1. Trigger daily settlement sync
2. Verify COD remittance processing
3. Check overdue settlement detection
4. Validate profit recompute

### 3. Error Handling
1. Test invalid webhook signatures
2. Test failed API connections
3. Verify proper error responses
4. Check database transaction rollback

## Response Examples

### Success Response
```json
{
  "status": "success",
  "message": "Operation completed successfully",
  "data": {
    "id": "settlement_123",
    "amount": 2999.00,
    "status": "SETTLED"
  }
}
```

### Error Response
```json
{
  "status": "error",
  "message": "Invalid webhook signature",
  "error_code": "WEBHOOK_SIGNATURE_INVALID"
}
```

## Import Instructions
1. Import this collection into Postman
2. Set environment variables
3. Update base URL to match your deployment
4. Test authentication flow first
5. Execute requests in order shown in collections

## Notes
- All monetary values are in INR
- Dates are in ISO format (YYYY-MM-DDTHH:mm:ss)
- All timestamps are in UTC
- Webhook signatures must be verified
- Settlement automation runs daily at 2 AM IST
- No manual confirmation buttons - everything is automated
