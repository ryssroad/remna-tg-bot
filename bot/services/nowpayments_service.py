import logging
import hmac
import hashlib
import json
from typing import Optional, Dict, Any
from aiohttp import web, ClientSession
from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from db.dal import payment_dal, user_dal
from bot.services.subscription_service import SubscriptionService
from bot.services.referral_service import ReferralService
from bot.services.panel_api_service import PanelApiService
from bot.middlewares.i18n import JsonI18n
from config.settings import Settings
from bot.services.notification_service import NotificationService
from bot.keyboards.inline.user_keyboards import get_connect_and_main_keyboard


class NOWPaymentsService:
    """Service for handling NOWPayments cryptocurrency payment operations and IPN webhooks"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.api_key = settings.NOWPAYMENTS_API_KEY
        self.ipn_secret = settings.NOWPAYMENTS_IPN_SECRET
        self.api_url = "https://api.nowpayments.io/v1"

        if not self.api_key or not self.ipn_secret:
            logging.warning(
                "NOWPayments API_KEY or IPN_SECRET not configured. "
                "NOWPayments payment functionality will be DISABLED."
            )
            self.configured = False
        else:
            self.configured = True
            logging.info("NOWPayments service configured successfully")

    async def get_api_status(self) -> Optional[Dict[str, Any]]:
        """
        Check API availability
        GET /v1/status

        Returns:
            Dict with status message or None if error
        """
        if not self.configured:
            logging.error("NOWPayments service is not configured")
            return None

        try:
            async with ClientSession() as session:
                url = f"{self.api_url}/status"

                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        logging.info(f"NOWPayments API status: {data.get('message', 'OK')}")
                        return data
                    else:
                        logging.error(f"NOWPayments API status check failed: {response.status}")
                        return None

        except Exception as e:
            logging.error(f"Error checking NOWPayments API status: {e}", exc_info=True)
            return None

    async def create_invoice(
        self,
        price_amount: float,
        price_currency: str,
        order_id: str,
        order_description: str,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Create payment invoice
        POST /v1/invoice

        Args:
            price_amount: Amount in fiat currency (e.g. 150.0 for $150)
            price_currency: Fiat currency code (e.g. "usd", "rub")
            order_id: Internal order ID (our payment_db_id)
            order_description: Description of the order
            success_url: URL to redirect after successful payment
            cancel_url: URL to redirect after failed payment

        Returns:
            Dictionary with invoice data including invoice_url or None if error
        """
        if not self.configured:
            logging.error("NOWPayments service is not configured")
            return None

        try:
            headers = {
                "x-api-key": self.api_key,
                "Content-Type": "application/json"
            }

            # IPN callback URL from settings
            ipn_callback_url = self.settings.nowpayments_ipn_full_webhook_url

            payload = {
                "price_amount": price_amount,
                "price_currency": price_currency.lower(),  # NOWPayments expects lowercase
                "order_id": order_id,
                "order_description": order_description,
                "ipn_callback_url": ipn_callback_url,
                "is_fixed_rate": True,  # Fix exchange rate for 20 minutes
                "is_fee_paid_by_user": False  # We pay the fees
            }

            if success_url:
                payload["success_url"] = success_url
            if cancel_url:
                payload["cancel_url"] = cancel_url

            logging.info(
                f"Creating NOWPayments invoice for order {order_id}: "
                f"{price_amount} {price_currency.upper()}"
            )

            async with ClientSession() as session:
                url = f"{self.api_url}/invoice"

                async with session.post(url, json=payload, headers=headers) as response:
                    # NOWPayments returns 200 or 201 on success
                    if response.status in (200, 201):
                        data = await response.json()
                        invoice_id = data.get("id")
                        invoice_url = data.get("invoice_url")

                        logging.info(
                            f"Created NOWPayments invoice {invoice_id} for order {order_id}"
                        )
                        logging.info(f"Invoice URL: {invoice_url}")

                        return data
                    else:
                        error_text = await response.text()
                        logging.error(
                            f"NOWPayments invoice creation failed: "
                            f"status={response.status}, error={error_text}"
                        )
                        return None

        except Exception as e:
            logging.error(f"Error creating NOWPayments invoice: {e}", exc_info=True)
            return None

    def verify_ipn_signature(self, payload: Dict[str, Any], received_signature: str) -> bool:
        """
        Verify IPN webhook signature

        Algorithm:
        1. Sort payload by keys recursively
        2. Convert to JSON string without spaces
        3. Calculate HMAC SHA-512 with IPN secret
        4. Compare with received signature

        Args:
            payload: IPN notification payload (dict)
            received_signature: Signature from x-nowpayments-sig header

        Returns:
            True if signature is valid
        """
        if not self.ipn_secret:
            logging.error("NOWPAYMENTS_IPN_SECRET not configured")
            return False

        try:
            # Recursively sort dictionary by keys
            def sort_dict(obj):
                if isinstance(obj, dict):
                    return {k: sort_dict(obj[k]) for k in sorted(obj.keys())}
                elif isinstance(obj, list):
                    return [sort_dict(item) for item in obj]
                else:
                    return obj

            sorted_payload = sort_dict(payload)

            # Convert to JSON string without spaces
            json_string = json.dumps(sorted_payload, separators=(',', ':'))

            # Calculate HMAC SHA-512
            signature = hmac.new(
                self.ipn_secret.encode('utf-8'),
                json_string.encode('utf-8'),
                hashlib.sha512
            ).hexdigest()

            # Compare signatures
            is_valid = hmac.compare_digest(signature, received_signature)

            if not is_valid:
                logging.error(
                    f"NOWPayments IPN signature mismatch!\n"
                    f"  Expected: {signature}\n"
                    f"  Received: {received_signature}\n"
                    f"  Payload: {json_string}"
                )

            return is_valid

        except Exception as e:
            logging.error(f"Error verifying NOWPayments IPN signature: {e}", exc_info=True)
            return False

    async def close(self):
        """Cleanup resources"""
        pass


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

    # Extract data from IPN notification
    payment_id = payment_data.get("payment_id")
    order_id = payment_data.get("order_id")
    payment_status = payment_data.get("payment_status")
    price_amount = float(payment_data.get("price_amount", 0))
    price_currency = payment_data.get("price_currency", "").upper()
    pay_amount = float(payment_data.get("pay_amount", 0))
    pay_currency = payment_data.get("pay_currency", "").upper()

    logging.info(
        f"Processing NOWPayments payment: "
        f"payment_id={payment_id}, order_id={order_id}, status={payment_status}, "
        f"amount={price_amount} {price_currency}"
    )

    if not order_id:
        logging.error("Missing order_id in NOWPayments payment data")
        return

    # Only process finished payments
    if payment_status != "finished":
        logging.info(
            f"NOWPayments payment {payment_id} status is {payment_status}, "
            f"not processing yet"
        )
        return

    try:
        # order_id is our payment_db_id
        payment_db_id = int(order_id)

        # Get payment record from database
        payment_record = await payment_dal.get_payment_by_db_id(session, payment_db_id)
        if not payment_record:
            logging.error(
                f"Payment record {payment_db_id} not found for NOWPayments payment"
            )
            return

        user_id = payment_record.user_id
        subscription_months = payment_record.subscription_duration_months
        promo_code_id = payment_record.promo_code_id

        # Get user
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user:
            logging.error(
                f"User {user_id} not found during NOWPayments payment processing"
            )
            await payment_dal.update_payment_status_by_db_id(
                session,
                payment_db_id,
                "failed_user_not_found",
                f"nowpayments_{payment_id}"
            )
            return

        # Update payment status
        updated_payment = await payment_dal.update_payment_status_by_db_id(
            session,
            payment_db_id=payment_db_id,
            new_status="succeeded",
            yk_payment_id=f"nowpayments_{payment_id}"  # Reuse this field for provider ID
        )

        if not updated_payment:
            logging.error(f"Failed to update payment record {payment_db_id}")
            raise Exception(
                f"DB Error: Could not update payment record {payment_db_id}"
            )

        # Activate subscription
        activation_details = await subscription_service.activate_subscription(
            session,
            user_id,
            subscription_months,
            price_amount,
            payment_db_id,
            promo_code_id_from_payment=promo_code_id,
            provider="nowpayments"
        )

        if not activation_details or not activation_details.get('end_date'):
            logging.error(
                f"Failed to activate subscription for user {user_id} "
                f"after NOWPayments payment"
            )
            raise Exception(
                f"Subscription Error: Failed to activate for user {user_id}"
            )

        base_subscription_end_date = activation_details['end_date']
        final_end_date_for_user = base_subscription_end_date
        applied_promo_bonus_days = activation_details.get("applied_promo_bonus_days", 0)

        # Apply referral bonuses
        referral_bonus_info = await referral_service.apply_referral_bonuses_for_payment(
            session,
            user_id,
            subscription_months,
            current_payment_db_id=payment_db_id,
            skip_if_active_before_payment=False,
        )

        applied_referee_bonus_days_from_referral: Optional[int] = None
        if referral_bonus_info and referral_bonus_info.get("referee_new_end_date"):
            final_end_date_for_user = referral_bonus_info["referee_new_end_date"]
            applied_referee_bonus_days_from_referral = referral_bonus_info.get(
                "referee_bonus_applied_days"
            )

        # Prepare user notification
        user_lang = (
            db_user.language_code
            if db_user and db_user.language_code
            else settings.DEFAULT_LANGUAGE
        )
        _ = lambda key, **kwargs: i18n.gettext(user_lang, key, **kwargs)

        config_link = activation_details.get("subscription_url") or _(
            "config_link_not_available"
        )

        # Generate appropriate message
        if applied_referee_bonus_days_from_referral and final_end_date_for_user:
            inviter_name_display = _("friend_placeholder")
            if db_user and db_user.referred_by_id:
                inviter = await user_dal.get_user_by_id(session, db_user.referred_by_id)
                if inviter and inviter.first_name:
                    inviter_name_display = inviter.first_name
                elif inviter and inviter.username:
                    inviter_name_display = f"@{inviter.username}"

            details_message = _(
                "payment_successful_with_referral_bonus_full",
                months=subscription_months,
                base_end_date=base_subscription_end_date.strftime('%Y-%m-%d'),
                bonus_days=applied_referee_bonus_days_from_referral,
                final_end_date=final_end_date_for_user.strftime('%Y-%m-%d'),
                inviter_name=inviter_name_display,
                config_link=config_link,
            )
        elif applied_promo_bonus_days > 0 and final_end_date_for_user:
            details_message = _(
                "payment_successful_with_promo_full",
                months=subscription_months,
                bonus_days=applied_promo_bonus_days,
                end_date=final_end_date_for_user.strftime('%Y-%m-%d'),
                config_link=config_link,
            )
        elif final_end_date_for_user:
            details_message = _(
                "payment_successful_full",
                months=subscription_months,
                end_date=final_end_date_for_user.strftime('%Y-%m-%d'),
                config_link=config_link,
            )
        else:
            logging.error(
                f"Critical error: final_end_date_for_user is None for user {user_id}"
            )
            details_message = _("payment_successful_error_details")

        # Send message to user
        details_markup = get_connect_and_main_keyboard(
            user_lang, i18n, settings, config_link
        )
        try:
            await bot.send_message(
                user_id,
                details_message,
                reply_markup=details_markup,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception as e_notify:
            logging.error(
                f"Failed to send payment details message to user {user_id}: {e_notify}"
            )

        # Send notification about payment
        try:
            notification_service = NotificationService(bot, settings, i18n)
            user = await user_dal.get_user_by_id(session, user_id)
            await notification_service.notify_payment_received(
                user_id=user_id,
                amount=price_amount,
                currency=price_currency,
                months=subscription_months,
                payment_provider=f"NOWPayments ({pay_currency})",
                username=user.username if user else None
            )
        except Exception as e:
            logging.error(f"Failed to send payment notification: {e}")

    except Exception as e:
        logging.error(f"Error processing NOWPayments payment: {e}", exc_info=True)
        raise


async def nowpayments_ipn_webhook(request: web.Request):
    """Handle NOWPayments IPN (Instant Payment Notification) webhook"""

    try:
        bot: Bot = request.app['bot']
        i18n_instance: JsonI18n = request.app['i18n']
        settings: Settings = request.app['settings']
        panel_service: PanelApiService = request.app['panel_service']
        subscription_service: SubscriptionService = request.app['subscription_service']
        referral_service: ReferralService = request.app['referral_service']
        nowpayments_service: NOWPaymentsService = request.app['nowpayments_service']
        async_session_factory: sessionmaker = request.app['async_session_factory']
    except KeyError as e_app_ctx:
        logging.error(
            f"KeyError accessing app context in nowpayments_ipn_webhook: {e_app_ctx}"
        )
        return web.Response(status=500, text="Internal Server Error")

    try:
        # Get signature from header
        signature = request.headers.get('x-nowpayments-sig')
        if not signature:
            logging.error("Missing x-nowpayments-sig header in NOWPayments IPN")
            return web.Response(status=400, text="Bad Request: Missing signature")

        # Get JSON payload
        payload = await request.json()

        logging.info(
            f"NOWPayments IPN received: "
            f"payment_id={payload.get('payment_id')}, "
            f"status={payload.get('payment_status')}"
        )
        logging.debug(f"NOWPayments IPN payload: {json.dumps(payload, indent=2)}")

        # Verify signature
        if not nowpayments_service.verify_ipn_signature(payload, signature):
            logging.error(
                f"Invalid signature in NOWPayments IPN for payment "
                f"{payload.get('payment_id')}"
            )
            return web.Response(status=400, text="Bad Request: Invalid signature")

        # Process payment
        payment_status = payload.get("payment_status")

        # Only process finished payments
        if payment_status == "finished":
            async with async_session_factory() as session:
                try:
                    await process_nowpayments_payment(
                        session,
                        bot,
                        payload,
                        i18n_instance,
                        settings,
                        panel_service,
                        subscription_service,
                        referral_service
                    )
                    await session.commit()

                    return web.Response(status=200, text="OK")

                except Exception as e:
                    await session.rollback()
                    logging.error(
                        f"Error processing NOWPayments payment: {e}", exc_info=True
                    )
                    # Still return OK to avoid retries
                    return web.Response(status=200, text="OK")
        else:
            logging.info(
                f"NOWPayments IPN received with status {payment_status}, "
                f"acknowledging but not processing"
            )
            return web.Response(status=200, text="OK")

    except Exception as e:
        logging.error(
            f"NOWPayments IPN webhook general error: {e}", exc_info=True
        )
        return web.Response(status=500, text="Internal Server Error")
