# NOWPayments Integration Guide

## Overview

This document describes the NOWPayments cryptocurrency payment gateway integration in the Telegram VPN bot and provides guidance for integrating it into the Next.js subscription management application.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Configuration](#configuration)
3. [Payment Flow](#payment-flow)
4. [API Reference](#api-reference)
5. [Webhook (IPN) Processing](#webhook-ipn-processing)
6. [Database Schema](#database-schema)
7. [Next.js Integration Guide](#nextjs-integration-guide)
8. [Testing](#testing)
9. [Security Considerations](#security-considerations)

---

## Architecture Overview

### Components

1. **NOWPayments Service** (`bot/services/nowpayments_service.py`)
   - Handles invoice creation via NOWPayments API
   - Verifies IPN webhook signatures (HMAC SHA-512)
   - Processes payment notifications

2. **Payment Handler** (`bot/handlers/user/subscription/payments.py`)
   - Creates payment records in database
   - Generates payment links for users
   - Handles callback button interactions

3. **Webhook Endpoint** (`/webhook/nowpayments`)
   - Receives IPN notifications from NOWPayments
   - Validates signatures
   - Triggers payment processing

### Payment Flow Diagram

```
User clicks "Crypto" button
        ↓
Create payment record (status: pending_nowpayments)
        ↓
Call NOWPayments API /v1/invoice
        ↓
Send invoice_url to user
        ↓
User pays with cryptocurrency
        ↓
NOWPayments sends IPN webhook
        ↓
Verify HMAC SHA-512 signature
        ↓
Process payment (status: succeeded)
        ↓
Activate subscription
        ↓
Send notification to user
```

---

## Configuration

### Environment Variables

Add to `.env`:

```bash
# NOWPayments Cryptocurrency Gateway Configuration
NOWPAYMENTS_API_KEY=your_api_key_here          # Get from https://nowpayments.io
NOWPAYMENTS_IPN_SECRET=your_ipn_secret_here    # IPN secret for webhook signature verification
NOWPAYMENTS_ENABLED=True                        # Enable/disable NOWPayments

# Webhook Base URL (required for IPN callbacks)
WEBHOOK_BASE_URL=https://your-domain.com
```

### Configuration in Code

**File: `config/settings.py`**

```python
class Settings(BaseSettings):
    # NOWPayments
    NOWPAYMENTS_API_KEY: Optional[str] = Field(default=None)
    NOWPAYMENTS_IPN_SECRET: Optional[str] = Field(default=None)
    NOWPAYMENTS_ENABLED: bool = Field(default=True)

    @computed_field
    @property
    def nowpayments_ipn_webhook_path(self) -> str:
        return "/webhook/nowpayments"

    @computed_field
    @property
    def nowpayments_ipn_full_webhook_url(self) -> Optional[str]:
        base = self.WEBHOOK_BASE_URL
        if base:
            return f"{base.rstrip('/')}{self.nowpayments_ipn_webhook_path}"
        return None
```

### NOWPayments Dashboard Configuration

1. Log in to [NOWPayments Dashboard](https://nowpayments.io)
2. Navigate to **Settings → IPN**
3. Set IPN Callback URL:
   ```
   https://your-domain.com/webhook/nowpayments
   ```
4. Copy your **IPN Secret Key** to `NOWPAYMENTS_IPN_SECRET`
5. Copy your **API Key** to `NOWPAYMENTS_API_KEY`

---

## Payment Flow

### 1. Create Payment

**Handler: `pay_nowpayments_callback_handler`**

```python
# User clicks "💎 Crypto (NOWPayments)" button
# Callback data format: "pay_nowp:{months}:{price}"

# 1. Create payment record in database
db_payment_record = await payment_dal.create_payment_record(
    session,
    {
        "user_id": user_id,
        "amount": price_amount,
        "currency": "RUB",
        "status": "pending_nowpayments",
        "subscription_duration_months": months,
        "provider": "nowpayments",
    }
)

# 2. Create invoice via NOWPayments API
invoice_data = await nowpayments_service.create_invoice(
    price_amount=price_amount,
    price_currency="RUB",
    order_id=str(db_payment_record.payment_id),
    order_description=f"Subscription payment for {months} mo.",
)

# 3. Send payment link to user
invoice_url = invoice_data["invoice_url"]
# User receives link like: https://nowpayments.io/payment/?iid=5431072121
```

### 2. User Pays

User completes payment on NOWPayments hosted page:
- Selects cryptocurrency (BTC, ETH, USDT, etc.)
- Sends payment to provided address
- NOWPayments confirms transaction

### 3. IPN Webhook

NOWPayments sends webhook notification when payment status changes:

**Endpoint:** `POST /webhook/nowpayments`

**Headers:**
```http
Content-Type: application/json
x-nowpayments-sig: <HMAC_SHA512_signature>
```

**Payload Example:**
```json
{
  "payment_id": "5708499725",
  "invoice_id": "5431072121",
  "payment_status": "finished",
  "pay_address": "bc1q...",
  "price_amount": "150",
  "price_currency": "rub",
  "pay_amount": "0.00123456",
  "actually_paid": "0.00123456",
  "pay_currency": "btc",
  "order_id": "22",
  "order_description": "Subscription payment for 1 mo.",
  "purchase_id": "22",
  "outcome_amount": "0.00123456",
  "outcome_currency": "btc",
  "created_at": "2025-10-14T18:22:05.073Z",
  "updated_at": "2025-10-14T19:30:00.000Z"
}
```

### 4. Process Payment

When `payment_status` = `"finished"`:

1. Verify signature
2. Update payment status to `"succeeded"`
3. Activate/extend subscription
4. Apply referral bonuses (if applicable)
5. Send notification to user

---

## API Reference

### NOWPayments API Endpoints

**Base URL:** `https://api.nowpayments.io/v1`

#### Create Invoice

**Endpoint:** `POST /v1/invoice`

**Headers:**
```http
x-api-key: {NOWPAYMENTS_API_KEY}
Content-Type: application/json
```

**Request Body:**
```json
{
  "price_amount": 150,
  "price_currency": "rub",
  "order_id": "22",
  "order_description": "Subscription payment for 1 mo.",
  "ipn_callback_url": "https://your-domain.com/webhook/nowpayments",
  "is_fixed_rate": true,
  "is_fee_paid_by_user": false
}
```

**Response (200 or 201):**
```json
{
  "id": "5431072121",
  "token_id": "unique_token",
  "order_id": "22",
  "order_description": "Subscription payment for 1 mo.",
  "price_amount": "150",
  "price_currency": "rub",
  "pay_currency": null,
  "ipn_callback_url": "https://your-domain.com/webhook/nowpayments",
  "invoice_url": "https://nowpayments.io/payment/?iid=5431072121",
  "success_url": null,
  "cancel_url": null,
  "is_fixed_rate": true,
  "is_fee_paid_by_user": false,
  "created_at": "2025-10-14T18:22:05.073Z",
  "updated_at": "2025-10-14T18:22:05.073Z"
}
```

**Implementation:**
```python
async def create_invoice(
    self,
    price_amount: float,
    price_currency: str,
    order_id: str,
    order_description: str,
    success_url: Optional[str] = None,
    cancel_url: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    headers = {
        "x-api-key": self.api_key,
        "Content-Type": "application/json"
    }

    payload = {
        "price_amount": price_amount,
        "price_currency": price_currency.lower(),
        "order_id": order_id,
        "order_description": order_description,
        "ipn_callback_url": self.settings.nowpayments_ipn_full_webhook_url,
        "is_fixed_rate": True,
        "is_fee_paid_by_user": False
    }

    async with ClientSession() as session:
        url = f"{self.api_url}/invoice"
        async with session.post(url, json=payload, headers=headers) as response:
            if response.status in (200, 201):
                return await response.json()
            else:
                error_text = await response.text()
                logging.error(f"NOWPayments invoice creation failed: status={response.status}, error={error_text}")
                return None
```

---

## Webhook (IPN) Processing

### Signature Verification

NOWPayments uses **HMAC SHA-512** to sign IPN notifications.

#### Algorithm

1. **Recursively sort** the JSON payload by keys
2. Convert to JSON string with **no spaces**: `separators=(',', ':')`
3. Calculate HMAC SHA-512 using `NOWPAYMENTS_IPN_SECRET`
4. Compare with `x-nowpayments-sig` header

#### Implementation

```python
def verify_ipn_signature(self, payload: Dict[str, Any], received_signature: str) -> bool:
    """Verify IPN webhook signature using HMAC SHA-512"""

    # Step 1: Recursively sort dictionary by keys
    def sort_dict(obj):
        if isinstance(obj, dict):
            return {k: sort_dict(obj[k]) for k in sorted(obj.keys())}
        elif isinstance(obj, list):
            return [sort_dict(item) for item in obj]
        else:
            return obj

    sorted_payload = sort_dict(payload)

    # Step 2: Convert to JSON string (no spaces)
    json_string = json.dumps(sorted_payload, separators=(',', ':'))

    # Step 3: Calculate HMAC SHA-512
    signature = hmac.new(
        self.ipn_secret.encode('utf-8'),
        json_string.encode('utf-8'),
        hashlib.sha512
    ).hexdigest()

    # Step 4: Compare signatures (timing-safe)
    return hmac.compare_digest(signature, received_signature)
```

### Webhook Handler

**File: `bot/services/nowpayments_service.py`**

```python
async def nowpayments_ipn_webhook(request: web.Request):
    """Handle NOWPayments IPN webhook"""

    # Get services from app context
    nowpayments_service = request.app["nowpayments_service"]
    bot = request.app["bot"]
    session_maker = request.app["session_maker"]
    # ... other services

    # Extract signature and payload
    signature = request.headers.get('x-nowpayments-sig')
    if not signature:
        logging.warning("NOWPayments IPN: Missing signature header")
        return web.Response(status=400, text="Bad Request: Missing signature")

    try:
        payload = await request.json()
    except Exception as e:
        logging.error(f"NOWPayments IPN: Invalid JSON payload: {e}")
        return web.Response(status=400, text="Bad Request: Invalid JSON")

    # Verify signature
    if not nowpayments_service.verify_ipn_signature(payload, signature):
        logging.warning(f"NOWPayments IPN: Invalid signature. Payload: {payload}")
        return web.Response(status=400, text="Bad Request: Invalid signature")

    logging.info(f"NOWPayments IPN received: {payload}")

    # Process only finished payments
    payment_status = payload.get("payment_status")
    if payment_status == "finished":
        async with session_maker() as session:
            try:
                await process_nowpayments_payment(
                    session=session,
                    bot=bot,
                    payment_data=payload,
                    i18n=i18n,
                    settings=settings,
                    panel_service=panel_service,
                    subscription_service=subscription_service,
                    referral_service=referral_service
                )
            except Exception as e:
                logging.error(f"Error processing NOWPayments payment: {e}", exc_info=True)
                return web.Response(status=500, text="Internal Server Error")
    else:
        logging.info(f"NOWPayments IPN: Ignoring status '{payment_status}'")

    return web.Response(status=200, text="OK")
```

### Payment Processing Logic

**File: `bot/services/nowpayments_service.py`**

```python
async def process_nowpayments_payment(
    session: AsyncSession,
    bot: Bot,
    payment_data: dict,
    i18n: JsonI18n,
    settings: Settings,
    panel_service: PanelApiService,
    subscription_service: SubscriptionService,
    referral_service: ReferralService
):
    """Process successful NOWPayments cryptocurrency payment"""

    # Extract order_id (our payment_id)
    order_id = payment_data.get("order_id")
    if not order_id:
        logging.error("NOWPayments IPN: Missing order_id")
        return

    # Find payment record
    payment_dal = PaymentDAL(session)
    db_payment = await payment_dal.get_payment_by_id(int(order_id))

    if not db_payment:
        logging.error(f"NOWPayments IPN: Payment {order_id} not found")
        return

    if db_payment.status == "succeeded":
        logging.info(f"NOWPayments payment {order_id} already processed")
        return

    # Extract payment details
    nowpayments_payment_id = payment_data.get("payment_id")
    actually_paid = payment_data.get("actually_paid", "0")
    pay_currency = payment_data.get("pay_currency", "").upper()

    # Update payment record
    await payment_dal.update_payment_status(
        payment_id=db_payment.payment_id,
        status="succeeded",
        provider_payment_id=f"nowpayments_{nowpayments_payment_id}"
    )

    await session.commit()

    # Activate/extend subscription
    user_id = db_payment.user_id
    months = db_payment.subscription_duration_months

    await subscription_service.extend_subscription(
        session=session,
        user_id=user_id,
        months=months,
        panel_service=panel_service,
        provider="nowpayments"
    )

    # Apply referral bonuses
    if months > 0:
        await referral_service.apply_referral_bonus(
            session=session,
            user_id=user_id,
            months=months,
            panel_service=panel_service
        )

    # Send notification to user
    user_lang = await get_user_language(session, user_id)
    i18n_instance = i18n.get_translator_by_locale(user_lang)

    message = i18n_instance.get("subscription_activated_message", months=months)

    try:
        await bot.send_message(user_id, message)
    except Exception as e:
        logging.error(f"Failed to send notification to user {user_id}: {e}")

    logging.info(f"NOWPayments payment {order_id} processed successfully for user {user_id}")
```

---

## Database Schema

### Payments Table

Payment records are stored with provider-specific information:

```python
# Payment record structure
{
    "payment_id": 22,                          # Primary key (auto-increment)
    "user_id": 6920793486,                     # Telegram user ID
    "amount": 150,                             # Price in RUB
    "currency": "RUB",                         # Price currency
    "status": "succeeded",                     # pending_nowpayments → succeeded
    "subscription_duration_months": 1,         # Subscription duration
    "provider": "nowpayments",                 # Payment provider
    "yookassa_payment_id": "nowpayments_5708499725",  # Provider payment ID (stored here for all providers)
    "created_at": "2025-10-14 19:34:57"
}
```

**Status Flow:**
- `pending_nowpayments` → Payment created, waiting for user
- `succeeded` → Payment confirmed, subscription activated

### Subscriptions Table

```python
{
    "subscription_id": 24,
    "user_id": 388151034,
    "panel_user_uuid": "571b5886-2a95-495d-b483-812a49d749a9",
    "panel_subscription_uuid": "PRk71xf0Hy53QBnLYE0b-J1Ft",
    "start_date": "2025-09-27 21:29:03",
    "end_date": "2025-10-27 21:29:03",
    "duration_months": 1,
    "is_active": true,
    "provider": "nowpayments",                 # Tracks payment provider
    "skip_notifications": false,
    "auto_renew_enabled": true
}
```

---

## Next.js Integration Guide

### Overview

To integrate NOWPayments into your Next.js subscription management application, you need to:

1. Create API routes for invoice creation
2. Implement webhook endpoint for IPN notifications
3. Add payment UI components
4. Handle payment status updates

### 1. API Route: Create Invoice

**File: `app/api/payments/nowpayments/create-invoice/route.ts`**

```typescript
import { NextRequest, NextResponse } from 'next/server';
import crypto from 'crypto';

const NOWPAYMENTS_API_URL = 'https://api.nowpayments.io/v1';
const NOWPAYMENTS_API_KEY = process.env.NOWPAYMENTS_API_KEY!;
const WEBHOOK_BASE_URL = process.env.NEXT_PUBLIC_WEBHOOK_BASE_URL!;

interface CreateInvoiceRequest {
  userId: number;
  amount: number;
  currency: string;
  months: number;
  description: string;
}

export async function POST(request: NextRequest) {
  try {
    const body: CreateInvoiceRequest = await request.json();

    // 1. Create payment record in your database
    const payment = await db.payments.create({
      data: {
        userId: body.userId,
        amount: body.amount,
        currency: body.currency,
        status: 'pending_nowpayments',
        subscriptionDurationMonths: body.months,
        provider: 'nowpayments',
      }
    });

    // 2. Create invoice via NOWPayments API
    const response = await fetch(`${NOWPAYMENTS_API_URL}/invoice`, {
      method: 'POST',
      headers: {
        'x-api-key': NOWPAYMENTS_API_KEY,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        price_amount: body.amount,
        price_currency: body.currency.toLowerCase(),
        order_id: payment.id.toString(),
        order_description: body.description,
        ipn_callback_url: `${WEBHOOK_BASE_URL}/api/webhooks/nowpayments`,
        is_fixed_rate: true,
        is_fee_paid_by_user: false,
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('NOWPayments API error:', errorText);
      return NextResponse.json(
        { error: 'Failed to create invoice' },
        { status: 500 }
      );
    }

    const invoiceData = await response.json();

    return NextResponse.json({
      paymentId: payment.id,
      invoiceUrl: invoiceData.invoice_url,
      invoiceId: invoiceData.id,
    });

  } catch (error) {
    console.error('Error creating NOWPayments invoice:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
```

### 2. Webhook Route: IPN Handler

**File: `app/api/webhooks/nowpayments/route.ts`**

```typescript
import { NextRequest, NextResponse } from 'next/server';
import crypto from 'crypto';

const NOWPAYMENTS_IPN_SECRET = process.env.NOWPAYMENTS_IPN_SECRET!;

// Recursively sort object by keys
function sortObject(obj: any): any {
  if (Array.isArray(obj)) {
    return obj.map(sortObject);
  } else if (obj !== null && typeof obj === 'object') {
    return Object.keys(obj)
      .sort()
      .reduce((result: any, key) => {
        result[key] = sortObject(obj[key]);
        return result;
      }, {});
  }
  return obj;
}

// Verify HMAC SHA-512 signature
function verifySignature(payload: any, receivedSignature: string): boolean {
  const sortedPayload = sortObject(payload);
  const jsonString = JSON.stringify(sortedPayload);

  const hmac = crypto.createHmac('sha512', NOWPAYMENTS_IPN_SECRET);
  hmac.update(jsonString);
  const calculatedSignature = hmac.digest('hex');

  return crypto.timingSafeEqual(
    Buffer.from(calculatedSignature, 'hex'),
    Buffer.from(receivedSignature, 'hex')
  );
}

export async function POST(request: NextRequest) {
  try {
    // Extract signature from header
    const signature = request.headers.get('x-nowpayments-sig');
    if (!signature) {
      console.warn('NOWPayments IPN: Missing signature header');
      return NextResponse.json(
        { error: 'Missing signature' },
        { status: 400 }
      );
    }

    // Parse payload
    const payload = await request.json();

    // Verify signature
    if (!verifySignature(payload, signature)) {
      console.warn('NOWPayments IPN: Invalid signature', payload);
      return NextResponse.json(
        { error: 'Invalid signature' },
        { status: 400 }
      );
    }

    console.log('NOWPayments IPN received:', payload);

    // Process only finished payments
    if (payload.payment_status === 'finished') {
      const orderId = parseInt(payload.order_id);

      // Find payment record
      const payment = await db.payments.findUnique({
        where: { id: orderId },
        include: { user: true }
      });

      if (!payment) {
        console.error(`NOWPayments IPN: Payment ${orderId} not found`);
        return NextResponse.json({ error: 'Payment not found' }, { status: 404 });
      }

      if (payment.status === 'succeeded') {
        console.log(`NOWPayments payment ${orderId} already processed`);
        return NextResponse.json({ status: 'ok' });
      }

      // Update payment status
      await db.payments.update({
        where: { id: orderId },
        data: {
          status: 'succeeded',
          providerPaymentId: `nowpayments_${payload.payment_id}`,
        }
      });

      // Activate/extend subscription
      await extendSubscription({
        userId: payment.userId,
        months: payment.subscriptionDurationMonths,
        provider: 'nowpayments'
      });

      // Apply referral bonuses (if applicable)
      await applyReferralBonus({
        userId: payment.userId,
        months: payment.subscriptionDurationMonths
      });

      // Send notification to user
      await sendNotificationToUser(payment.userId, {
        type: 'subscription_activated',
        months: payment.subscriptionDurationMonths
      });

      console.log(`NOWPayments payment ${orderId} processed successfully`);
    } else {
      console.log(`NOWPayments IPN: Ignoring status '${payload.payment_status}'`);
    }

    return NextResponse.json({ status: 'ok' });

  } catch (error) {
    console.error('Error processing NOWPayments webhook:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
```

### 3. React Component: Payment Button

**File: `components/payment/NOWPaymentsButton.tsx`**

```typescript
'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';

interface NOWPaymentsButtonProps {
  userId: number;
  amount: number;
  currency: string;
  months: number;
  onSuccess?: () => void;
}

export function NOWPaymentsButton({
  userId,
  amount,
  currency,
  months,
  onSuccess
}: NOWPaymentsButtonProps) {
  const [loading, setLoading] = useState(false);

  const handlePayment = async () => {
    setLoading(true);

    try {
      const response = await fetch('/api/payments/nowpayments/create-invoice', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          userId,
          amount,
          currency,
          months,
          description: `Subscription payment for ${months} month(s)`
        })
      });

      if (!response.ok) {
        throw new Error('Failed to create invoice');
      }

      const data = await response.json();

      // Redirect to payment page
      window.open(data.invoiceUrl, '_blank');

      // Optionally: poll payment status or wait for webhook
      onSuccess?.();

    } catch (error) {
      console.error('Payment error:', error);
      alert('Failed to create payment. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Button
      onClick={handlePayment}
      disabled={loading}
      className="w-full"
    >
      {loading ? (
        'Creating invoice...'
      ) : (
        <>
          💎 Pay with Crypto (NOWPayments)
        </>
      )}
    </Button>
  );
}
```

### 4. Payment Status Polling (Optional)

**File: `hooks/usePaymentStatus.ts`**

```typescript
import { useEffect, useState } from 'react';

export function usePaymentStatus(paymentId: number | null) {
  const [status, setStatus] = useState<'pending' | 'succeeded' | 'failed'>('pending');

  useEffect(() => {
    if (!paymentId) return;

    const interval = setInterval(async () => {
      try {
        const response = await fetch(`/api/payments/${paymentId}/status`);
        const data = await response.json();

        if (data.status === 'succeeded') {
          setStatus('succeeded');
          clearInterval(interval);
        } else if (data.status === 'failed') {
          setStatus('failed');
          clearInterval(interval);
        }
      } catch (error) {
        console.error('Error polling payment status:', error);
      }
    }, 5000); // Poll every 5 seconds

    return () => clearInterval(interval);
  }, [paymentId]);

  return status;
}
```

### Environment Variables for Next.js

**File: `.env.local`**

```bash
NOWPAYMENTS_API_KEY=your_api_key_here
NOWPAYMENTS_IPN_SECRET=your_ipn_secret_here
NEXT_PUBLIC_WEBHOOK_BASE_URL=https://your-domain.com
```

---

## Testing

### Test Script

Use the provided test script to simulate IPN webhooks without real cryptocurrency:

**File: `test_nowpayments_webhook.py`**

```bash
# Usage
python3 test_nowpayments_webhook.py <payment_id> <user_id>

# Example
python3 test_nowpayments_webhook.py 23 388151034
```

### Manual Testing Flow

1. **Create test payment:**
   ```sql
   INSERT INTO payments (user_id, amount, currency, status, subscription_duration_months, provider)
   VALUES (123456, 150, 'RUB', 'pending_nowpayments', 1, 'nowpayments')
   RETURNING payment_id;
   ```

2. **Run test webhook:**
   ```bash
   python3 test_nowpayments_webhook.py <payment_id> <user_id>
   ```

3. **Verify results:**
   ```sql
   -- Check payment status
   SELECT payment_id, status, yookassa_payment_id
   FROM payments
   WHERE payment_id = <payment_id>;

   -- Check subscription
   SELECT subscription_id, end_date, provider
   FROM subscriptions
   WHERE user_id = <user_id> AND is_active = true;
   ```

### Sandbox Testing

NOWPayments provides a sandbox environment for testing:

1. Sign up for [NOWPayments Sandbox](https://sandbox.nowpayments.io)
2. Use sandbox API key and IPN secret
3. Change base URL to `https://api-sandbox.nowpayments.io/v1`
4. Use test cryptocurrencies (no real funds required)

---

## Security Considerations

### 1. Signature Verification

**Always verify** the HMAC SHA-512 signature on incoming IPN webhooks:

```python
if not nowpayments_service.verify_ipn_signature(payload, signature):
    return web.Response(status=400, text="Bad Request: Invalid signature")
```

### 2. Idempotency

Handle duplicate webhook notifications gracefully:

```python
if db_payment.status == "succeeded":
    logging.info(f"NOWPayments payment {order_id} already processed")
    return web.Response(status=200, text="OK")
```

### 3. Unique Payment IDs

Ensure each payment has a unique identifier to prevent database constraint violations:

```python
# Store NOWPayments payment_id with provider prefix
provider_payment_id = f"nowpayments_{nowpayments_payment_id}"
```

### 4. HTTPS Only

NOWPayments webhooks require HTTPS endpoints. Use SSL/TLS certificates in production.

### 5. Rate Limiting

Implement rate limiting on webhook endpoints to prevent abuse:

```python
from aiohttp import web
from aiohttp_limiter import RateLimiter

limiter = RateLimiter()

@limiter.limit("10/minute")
async def nowpayments_ipn_webhook(request: web.Request):
    # ...
```

### 6. Secret Management

Store API keys and secrets securely:
- Use environment variables (never hardcode)
- Use secret management services (AWS Secrets Manager, HashiCorp Vault)
- Rotate secrets periodically

---

## Payment Statuses

NOWPayments uses multiple payment statuses. Only process `"finished"` status:

| Status | Description | Action |
|--------|-------------|--------|
| `waiting` | Payment created, waiting for funds | Ignore |
| `confirming` | Transaction detected, waiting for confirmations | Ignore |
| `confirmed` | Transaction confirmed on blockchain | Ignore (wait for finished) |
| `sending` | Sending funds to merchant | Ignore |
| `partially_paid` | Underpaid (less than required) | Ignore or refund |
| `finished` | **Payment complete and confirmed** | **Process payment** |
| `failed` | Payment failed | Update status to failed |
| `refunded` | Payment refunded to user | Update status accordingly |
| `expired` | Payment expired (timeout) | Update status to expired |

---

## Troubleshooting

### Issue: Webhook not received

**Solutions:**
1. Check IPN Callback URL in NOWPayments dashboard
2. Verify webhook endpoint is accessible (use ngrok for local testing)
3. Check server logs for incoming requests
4. Ensure HTTPS is enabled (required for production)

### Issue: Invalid signature error

**Solutions:**
1. Verify `NOWPAYMENTS_IPN_SECRET` matches dashboard settings
2. Check JSON serialization (must use `separators=(',', ':')`)
3. Ensure recursive sorting of nested objects
4. Check for encoding issues (use UTF-8)

### Issue: Payment status not updating

**Solutions:**
1. Check webhook handler logs for errors
2. Verify database transaction commits
3. Check payment status in NOWPayments dashboard
4. Ensure `payment_status === "finished"` before processing

### Issue: Duplicate key constraint violation

**Solutions:**
1. Use unique payment IDs: `f"nowpayments_{payment_id}"`
2. Implement idempotency checks
3. Handle race conditions with database locks

---

## Additional Resources

- [NOWPayments API Documentation](https://documenter.getpostman.com/view/7907941/S1a32n38)
- [NOWPayments Dashboard](https://nowpayments.io)
- [NOWPayments IPN Documentation](https://nowpayments.io/help/how-to-use-ipn)
- [Supported Cryptocurrencies](https://nowpayments.io/supported-coins/)

---

## Support

For technical support:
- NOWPayments: support@nowpayments.io
- Telegram: @NOWPayments

---

**Last Updated:** 2025-10-14
