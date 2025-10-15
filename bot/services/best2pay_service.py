import logging
import hashlib
import base64
import xml.etree.ElementTree as ET
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


class Best2PayService:
    """Service for handling Best2Pay payment operations and webhooks"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.sector_id = settings.BEST2PAY_SECTOR_ID
        self.sector_uuid = settings.BEST2PAY_SECTOR_UUID  # UUID для API запросов
        self.password = settings.BEST2PAY_PASSWORD
        self.api_url = "https://pay.best2pay.net/webapi/"

        # Используем числовой ID для API запросов (UUID не принимается)
        self.sector_for_api = self.sector_id

        if not self.sector_for_api or not self.password:
            logging.warning(
                "Best2Pay SECTOR_ID/UUID or PASSWORD not configured. "
                "Best2Pay payment functionality will be DISABLED."
            )
            self.configured = False
        else:
            self.configured = True
            logging.info(
                f"Best2Pay service configured:\n"
                f"  Sector ID: {self.sector_id}\n"
                f"  Sector UUID: {self.sector_uuid}\n"
                f"  Using for API: {self.sector_for_api}"
            )

    def _generate_signature(self, data: str) -> str:
        """
        Generate SHA256 + Base64 signature for Best2Pay requests

        Algorithm:
        1. Concatenate parameters + password
        2. Calculate SHA256 hash (hexadecimal lowercase)
        3. Encode hex string to Base64

        Args:
            data: String to sign (format varies by operation)

        Returns:
            Base64-encoded SHA256 hash
        """
        # Concatenate data with password
        signature_string = f"{data}{self.password}"

        # Calculate SHA256 hash (UTF-8 encoding)
        sha256_hash = hashlib.sha256(signature_string.encode('utf-8')).hexdigest().lower()

        # Encode hex string to Base64
        signature = base64.b64encode(sha256_hash.encode('utf-8')).decode('utf-8')

        return signature

    async def register_order(
        self,
        amount: float,
        reference: str,
        currency: str = "RUB",
        description: str = "",
        email: Optional[str] = None,
        url: Optional[str] = None,
        fail_url: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Register order in Best2Pay system (webapi/Register)

        Args:
            amount: Payment amount in rubles
            reference: Unique order reference (payment_db_id from database)
            currency: Currency code (default: RUB)
            description: Payment description
            email: Customer email (optional)
            url: Success redirect URL
            fail_url: Failure redirect URL

        Returns:
            Dictionary with order ID or None if error
        """
        if not self.configured:
            logging.error("Best2Pay service is not configured")
            return None

        try:
            # Convert amount to kopecks (cents)
            amount_cents = int(amount * 100)

            # Currency code mapping
            currency_code = "643" if currency == "RUB" else currency

            # Generate signature: sector + amount + currency + password
            signature_data = f"{self.sector_for_api}{amount_cents}{currency_code}"
            signature = self._generate_signature(signature_data)

            # Debug logging
            logging.info(
                f"Best2Pay Register signature debug:\n"
                f"  sector_for_api: {self.sector_for_api}\n"
                f"  amount_cents: {amount_cents}\n"
                f"  currency_code: {currency_code}\n"
                f"  signature_data (before password): {signature_data}\n"
                f"  password: {'*' * len(self.password)}\n"
                f"  signature: {signature[:30]}..."
            )

            # Build request payload
            payload = {
                "sector": self.sector_for_api,
                "amount": amount_cents,
                "currency": currency_code,
                "description": description,
                "reference": reference,  # Our payment_db_id
                "signature": signature,
            }

            if email:
                payload["email"] = email

            # Add success/fail URLs if webhook base is configured
            if url:
                payload["url"] = url
            if fail_url:
                payload["failurl"] = fail_url

            async with ClientSession() as session:
                url = f"{self.api_url}Register"

                logging.info(f"Sending Best2Pay Register request to {url}")
                logging.debug(f"Payload: {payload}")

                async with session.post(url, data=payload) as response:
                    if response.status == 200:
                        # Best2Pay returns XML response
                        xml_text = await response.text()
                        logging.debug(f"Best2Pay Register response XML:\n{xml_text}")

                        try:
                            root = ET.fromstring(xml_text)
                            order_id = root.findtext('id')

                            if order_id:
                                logging.info(
                                    f"Registered Best2Pay order {order_id} "
                                    f"for reference {reference}, amount {amount} {currency}"
                                )
                                return {
                                    "order_id": order_id,
                                    "reference": reference,
                                }
                            else:
                                # Check for error
                                error_code = root.findtext('code')
                                error_desc = root.findtext('description')
                                logging.error(
                                    f"Best2Pay Register error: code={error_code}, desc={error_desc}"
                                )
                                logging.error(f"Full XML response:\n{xml_text}")
                                return None
                        except ET.ParseError as e:
                            logging.error(f"Failed to parse Best2Pay XML response: {e}")
                            logging.debug(f"XML content: {xml_text}")
                            return None
                    else:
                        logging.error(
                            f"Best2Pay Register failed with status {response.status}"
                        )
                        return None

        except Exception as e:
            logging.error(f"Error registering Best2Pay order: {e}", exc_info=True)
            return None

    async def create_payment_url(
        self,
        order_id: str,
        payment_method: str = "sbp"
    ) -> Optional[str]:
        """
        Create payment URL for registered order

        Args:
            order_id: Order ID from Register response
            payment_method: Payment method (sbp, card, etc.)

        Returns:
            Payment URL to redirect user
        """
        if not self.configured:
            logging.error("Best2Pay service is not configured")
            return None

        try:
            # Generate signature: sector + id + password
            signature_data = f"{self.sector_for_api}{order_id}"
            signature = self._generate_signature(signature_data)

            # Choose payment method endpoint
            if payment_method.lower() == "sbp":
                endpoint = "PurchaseSBP"
            else:
                endpoint = "Purchase"

            # Build payment URL
            from urllib.parse import urlencode
            params = {
                "sector": self.sector_for_api,
                "id": order_id,
                "signature": signature,
            }

            query_string = urlencode(params)
            payment_url = f"{self.api_url}{endpoint}?{query_string}"

            logging.info(
                f"Created Best2Pay payment URL for order {order_id} "
                f"using {endpoint}"
            )

            return payment_url

        except Exception as e:
            logging.error(f"Error creating Best2Pay payment URL: {e}", exc_info=True)
            return None

    def verify_signature(self, xml_string: str, received_signature: str) -> bool:
        """
        Verify signature from Best2Pay notification

        Args:
            xml_string: XML string with all tags
            received_signature: Signature from notification

        Returns:
            True if signature is valid
        """
        if not self.password:
            logging.error("BEST2PAY_PASSWORD not configured")
            return False

        try:
            # Parse XML
            root = ET.fromstring(xml_string)

            # Collect all tag values in order (excluding signature tag)
            values = []
            for child in root:
                if child.tag != 'signature':
                    values.append(child.text or '')

            # Concatenate all values
            data = ''.join(values)

            # Generate expected signature
            expected_signature = self._generate_signature(data)

            return received_signature == expected_signature

        except Exception as e:
            logging.error(f"Error verifying Best2Pay signature: {e}", exc_info=True)
            return False

    async def close(self):
        """Cleanup resources"""
        pass


async def process_best2pay_payment(
    session: AsyncSession,
    bot: Bot,
    payment_data: dict,
    i18n: JsonI18n,
    settings: Settings,
    panel_service: PanelApiService,
    subscription_service: SubscriptionService,
    referral_service: ReferralService
):
    """Process successful Best2Pay payment"""

    # Extract data from payment_data
    order_id = payment_data.get("order_id")
    reference = payment_data.get("reference")
    amount_cents = int(payment_data.get("amount", 0))
    amount = amount_cents / 100  # Convert from kopecks to rubles
    operation_id = payment_data.get("id")  # Best2Pay internal operation ID

    if not reference:
        logging.error("Missing reference in Best2Pay payment data")
        return

    try:
        # reference is our payment_db_id
        payment_db_id = int(reference)

        # Get payment record from database
        payment_record = await payment_dal.get_payment_by_db_id(session, payment_db_id)
        if not payment_record:
            logging.error(
                f"Payment record {payment_db_id} not found for Best2Pay payment"
            )
            return

        user_id = payment_record.user_id
        subscription_months = payment_record.subscription_duration_months
        promo_code_id = payment_record.promo_code_id

        # Get user
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user:
            logging.error(
                f"User {user_id} not found during Best2Pay payment processing"
            )
            await payment_dal.update_payment_status_by_db_id(
                session,
                payment_db_id,
                "failed_user_not_found",
                f"b2p_{operation_id}"
            )
            return

        # Update payment status
        updated_payment = await payment_dal.update_payment_status_by_db_id(
            session,
            payment_db_id=payment_db_id,
            new_status="succeeded",
            yk_payment_id=f"b2p_{operation_id}"  # Reuse this field for provider ID
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
            amount,
            payment_db_id,
            promo_code_id_from_payment=promo_code_id,
            provider="best2pay"
        )

        if not activation_details or not activation_details.get('end_date'):
            logging.error(
                f"Failed to activate subscription for user {user_id} "
                f"after Best2Pay payment"
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
                amount=amount,
                currency=settings.DEFAULT_CURRENCY_SYMBOL,
                months=subscription_months,
                payment_provider="Best2Pay (СБП)",
                username=user.username if user else None
            )
        except Exception as e:
            logging.error(f"Failed to send payment notification: {e}")

    except Exception as e:
        logging.error(f"Error processing Best2Pay payment: {e}", exc_info=True)
        raise


async def best2pay_notify_webhook(request: web.Request):
    """Handle Best2Pay payment notification webhook (XML format)"""

    try:
        bot: Bot = request.app['bot']
        i18n_instance: JsonI18n = request.app['i18n']
        settings: Settings = request.app['settings']
        panel_service: PanelApiService = request.app['panel_service']
        subscription_service: SubscriptionService = request.app['subscription_service']
        referral_service: ReferralService = request.app['referral_service']
        best2pay_service: Best2PayService = request.app['best2pay_service']
        async_session_factory: sessionmaker = request.app['async_session_factory']
    except KeyError as e_app_ctx:
        logging.error(
            f"KeyError accessing app context in best2pay_notify_webhook: {e_app_ctx}"
        )
        return web.Response(status=500, text="Internal Server Error")

    try:
        # Best2Pay sends data as XML
        xml_text = await request.text()

        logging.info(f"Best2Pay notify webhook received XML")
        logging.debug(f"XML content: {xml_text}")

        # Parse XML
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logging.error(f"Failed to parse Best2Pay XML: {e}")
            return web.Response(status=400, text="Bad Request: Invalid XML")

        # Extract data
        order_id = root.findtext('order_id')
        order_state = root.findtext('order_state')
        reference = root.findtext('reference')
        operation_id = root.findtext('id')
        operation_type = root.findtext('type')
        operation_state = root.findtext('state')
        amount = root.findtext('amount')
        currency = root.findtext('currency')
        signature = root.findtext('signature')

        logging.info(
            f"Best2Pay notify: order_id={order_id}, reference={reference}, "
            f"type={operation_type}, state={operation_state}, amount={amount}"
        )

        if not all([order_id, reference, operation_id, signature]):
            logging.error(
                f"Missing required fields in Best2Pay notification"
            )
            return web.Response(status=400, text="Bad Request: Missing fields")

        # Verify signature
        if not best2pay_service.verify_signature(xml_text, signature):
            logging.error(
                f"Invalid signature in Best2Pay notification for order {order_id}"
            )
            return web.Response(status=400, text="Bad Request: Invalid signature")

        # Only process approved operations
        if operation_state != "APPROVED":
            logging.warning(
                f"Received Best2Pay notification with state {operation_state}, ignoring"
            )
            return web.Response(status=200, text="OK")

        payment_data = {
            "order_id": order_id,
            "reference": reference,
            "id": operation_id,
            "amount": amount,
            "currency": currency,
            "type": operation_type,
            "state": operation_state,
        }

        async with async_session_factory() as session:
            try:
                await process_best2pay_payment(
                    session,
                    bot,
                    payment_data,
                    i18n_instance,
                    settings,
                    panel_service,
                    subscription_service,
                    referral_service
                )
                await session.commit()

                # Best2Pay expects "OK" response for successful processing
                return web.Response(status=200, text="OK")

            except Exception as e:
                await session.rollback()
                logging.error(
                    f"Error processing Best2Pay payment: {e}", exc_info=True
                )
                # Still return OK to avoid retries
                return web.Response(status=200, text="OK")

    except Exception as e:
        logging.error(
            f"Best2Pay notify webhook general error: {e}", exc_info=True
        )
        return web.Response(status=500, text="Internal Server Error")


async def best2pay_success_webhook(request: web.Request):
    """Handle Best2Pay success redirect (user returned after successful payment)"""

    logging.info("Best2Pay success webhook called")

    # Redirect user to success page or return message
    return web.Response(
        status=200,
        text="✅ Оплата успешно завершена! Вы можете закрыть эту страницу и вернуться в бот.",
        content_type="text/html; charset=utf-8"
    )


async def best2pay_fail_webhook(request: web.Request):
    """Handle Best2Pay failure redirect (user returned after failed payment)"""

    logging.info("Best2Pay fail webhook called")

    # Redirect user to failure page or return message
    return web.Response(
        status=200,
        text="❌ Оплата не удалась. Пожалуйста, попробуйте снова или обратитесь в поддержку.",
        content_type="text/html; charset=utf-8"
    )
