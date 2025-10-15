import logging
import hashlib
from typing import Optional
from aiohttp import web
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


class FreeKassaService:
    """Service for handling FreeKassa payment operations and webhooks"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.merchant_id = settings.FREEKASSA_MERCHANT_ID
        self.secret_word_1 = settings.FREEKASSA_SECRET_WORD_1  # For generating payment signature
        self.secret_word_2 = settings.FREEKASSA_SECRET_WORD_2  # For verifying notification signature
        self.payment_url = "https://pay.freekassa.net/"

    def create_payment_link(
        self,
        amount: float,
        order_id: int,
        months: int,
        email: Optional[str] = None,
        currency: str = "RUB"
    ) -> Optional[str]:
        """
        Create payment link for FreeKassa

        Args:
            amount: Payment amount
            order_id: Unique order ID (payment_db_id from database)
            months: Subscription duration in months
            email: User email (optional)
            currency: Currency code (RUB, USD, EUR, KZT, UAH)

        Returns:
            Payment URL or None if not configured
        """
        if not self.merchant_id or not self.secret_word_1:
            logging.error("FreeKassa merchant_id or secret_word_1 not configured")
            return None

        try:
            # Amount should be integer (rubles without decimal point)
            amount_int = int(amount)

            # Generate signature: MD5(MerchantID:Amount:SecretKey1:Currency:OrderID)
            signature_string = f"{self.merchant_id}:{amount_int}:{self.secret_word_1}:{currency}:{order_id}"
            signature = hashlib.md5(signature_string.encode()).hexdigest()

            # Build payment URL parameters
            params = {
                "m": self.merchant_id,
                "oa": str(amount_int),
                "o": str(order_id),
                "s": signature,
                "currency": currency,
                "us_months": str(months),  # Custom parameter to pass subscription duration
            }

            if email:
                params["em"] = email

            # Construct URL with parameters
            from urllib.parse import urlencode
            query_string = urlencode(params)
            payment_link = f"{self.payment_url}?{query_string}"

            logging.info(f"Created FreeKassa payment link for order {order_id}, amount {amount_int} {currency}, {months} months")
            return payment_link

        except Exception as e:
            logging.error(f"Error creating FreeKassa payment link: {e}", exc_info=True)
            return None

    def verify_notification_signature(self, merchant_id: str, amount: str,
                                      merchant_order_id: str, sign: str) -> bool:
        """Verify the signature from FreeKassa notification"""
        if not self.secret_word_2:
            logging.error("FREEKASSA_SECRET_WORD_2 not configured")
            return False

        # FreeKassa signature format: MD5(merchant_id:amount:secret_word_2:merchant_order_id)
        signature_string = f"{merchant_id}:{amount}:{self.secret_word_2}:{merchant_order_id}"
        expected_sign = hashlib.md5(signature_string.encode()).hexdigest()

        return sign.lower() == expected_sign.lower()

    async def close(self):
        """Cleanup resources"""
        pass


async def process_freekassa_payment(
    session: AsyncSession,
    bot: Bot,
    payment_data: dict,
    i18n: JsonI18n,
    settings: Settings,
    panel_service: PanelApiService,
    subscription_service: SubscriptionService,
    referral_service: ReferralService
):
    """Process successful FreeKassa payment"""

    # Extract data from payment_data
    merchant_order_id = payment_data.get("MERCHANT_ORDER_ID")
    amount = float(payment_data.get("AMOUNT", 0))

    if not merchant_order_id:
        logging.error(f"Missing MERCHANT_ORDER_ID in FreeKassa payment data")
        return

    try:
        # merchant_order_id should be our payment_db_id
        payment_db_id = int(merchant_order_id)

        # Get payment record from database
        payment_record = await payment_dal.get_payment_by_db_id(session, payment_db_id)
        if not payment_record:
            logging.error(f"Payment record {payment_db_id} not found for FreeKassa payment")
            return

        user_id = payment_record.user_id
        subscription_months = payment_record.subscription_duration_months
        promo_code_id = payment_record.promo_code_id

        # Get user
        db_user = await user_dal.get_user_by_id(session, user_id)
        if not db_user:
            logging.error(f"User {user_id} not found during FreeKassa payment processing")
            await payment_dal.update_payment_status_by_db_id(
                session, payment_db_id, "failed_user_not_found",
                payment_data.get("intid")
            )
            return

        # Update payment status
        freekassa_payment_id = payment_data.get("intid")
        updated_payment = await payment_dal.update_payment_status_by_db_id(
            session,
            payment_db_id=payment_db_id,
            new_status="succeeded",
            yk_payment_id=freekassa_payment_id
        )

        if not updated_payment:
            logging.error(f"Failed to update payment record {payment_db_id}")
            raise Exception(f"DB Error: Could not update payment record {payment_db_id}")

        # Activate subscription
        activation_details = await subscription_service.activate_subscription(
            session,
            user_id,
            subscription_months,
            amount,
            payment_db_id,
            promo_code_id_from_payment=promo_code_id,
            provider="freekassa"
        )

        if not activation_details or not activation_details.get('end_date'):
            logging.error(f"Failed to activate subscription for user {user_id} after FreeKassa payment")
            raise Exception(f"Subscription Error: Failed to activate for user {user_id}")

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
        user_lang = db_user.language_code if db_user and db_user.language_code else settings.DEFAULT_LANGUAGE
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
            logging.error(f"Critical error: final_end_date_for_user is None for user {user_id}")
            details_message = _("payment_successful_error_details")

        # Send message to user
        details_markup = get_connect_and_main_keyboard(user_lang, i18n, settings, config_link)
        try:
            await bot.send_message(
                user_id,
                details_message,
                reply_markup=details_markup,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception as e_notify:
            logging.error(f"Failed to send payment details message to user {user_id}: {e_notify}")

        # Send notification about payment
        try:
            notification_service = NotificationService(bot, settings, i18n)
            user = await user_dal.get_user_by_id(session, user_id)
            await notification_service.notify_payment_received(
                user_id=user_id,
                amount=amount,
                currency=settings.DEFAULT_CURRENCY_SYMBOL,
                months=subscription_months,
                payment_provider="freekassa",
                username=user.username if user else None
            )
        except Exception as e:
            logging.error(f"Failed to send payment notification: {e}")

    except Exception as e:
        logging.error(f"Error processing FreeKassa payment: {e}", exc_info=True)
        raise


async def freekassa_notify_webhook(request: web.Request):
    """Handle FreeKassa payment notification webhook"""

    try:
        bot: Bot = request.app['bot']
        i18n_instance: JsonI18n = request.app['i18n']
        settings: Settings = request.app['settings']
        panel_service: PanelApiService = request.app['panel_service']
        subscription_service: SubscriptionService = request.app['subscription_service']
        referral_service: ReferralService = request.app['referral_service']
        freekassa_service: FreeKassaService = request.app['freekassa_service']
        async_session_factory: sessionmaker = request.app['async_session_factory']
    except KeyError as e_app_ctx:
        logging.error(f"KeyError accessing app context in freekassa_notify_webhook: {e_app_ctx}")
        return web.Response(status=500, text="Internal Server Error")

    try:
        # FreeKassa sends data as form parameters
        data = await request.post()

        # Log all received parameters for debugging
        logging.info(f"FreeKassa notify webhook received data: {dict(data)}")

        # Check if this is a status check from FreeKassa
        if data.get('status_check') == '1':
            logging.info("FreeKassa status check received - responding with YES")
            return web.Response(status=200, text="YES")

        merchant_id = data.get('MERCHANT_ID')
        amount = data.get('AMOUNT')
        merchant_order_id = data.get('MERCHANT_ORDER_ID')
        sign = data.get('SIGN')
        intid = data.get('intid')  # FreeKassa internal payment ID

        logging.info(
            f"FreeKassa notify webhook parsed: "
            f"merchant_id={merchant_id}, amount={amount}, "
            f"order_id={merchant_order_id}, intid={intid}, sign={sign}"
        )

        if not all([merchant_id, amount, merchant_order_id, sign]):
            logging.error(f"Missing required parameters in FreeKassa notification. Received: {dict(data)}")
            return web.Response(status=400, text="Bad Request: Missing parameters")

        # Verify signature
        if not freekassa_service.verify_notification_signature(
            merchant_id, amount, merchant_order_id, sign
        ):
            logging.error(f"Invalid signature in FreeKassa notification for order {merchant_order_id}")
            return web.Response(status=400, text="Bad Request: Invalid signature")

        payment_data = {
            "MERCHANT_ID": merchant_id,
            "AMOUNT": amount,
            "MERCHANT_ORDER_ID": merchant_order_id,
            "SIGN": sign,
            "intid": intid,
        }

        async with async_session_factory() as session:
            try:
                await process_freekassa_payment(
                    session, bot, payment_data, i18n_instance, settings,
                    panel_service, subscription_service, referral_service
                )
                await session.commit()

                # FreeKassa expects "YES" response for successful processing
                return web.Response(status=200, text="YES")

            except Exception as e:
                await session.rollback()
                logging.error(f"Error processing FreeKassa payment: {e}", exc_info=True)
                return web.Response(status=200, text="YES")  # Still return YES to avoid retries

    except Exception as e:
        logging.error(f"FreeKassa notify webhook general error: {e}", exc_info=True)
        return web.Response(status=500, text="Internal Server Error")


async def freekassa_success_webhook(request: web.Request):
    """Handle FreeKassa success redirect (user returned after successful payment)"""

    logging.info("FreeKassa success webhook called")

    # You can redirect user to a success page or just return a message
    return web.Response(
        status=200,
        text="Payment successful! You can close this page and return to the bot.",
        content_type="text/html"
    )


async def freekassa_fail_webhook(request: web.Request):
    """Handle FreeKassa failure redirect (user returned after failed payment)"""

    logging.info("FreeKassa fail webhook called")

    # You can redirect user to a failure page or return a message
    return web.Response(
        status=200,
        text="Payment failed. Please try again or contact support.",
        content_type="text/html"
    )
