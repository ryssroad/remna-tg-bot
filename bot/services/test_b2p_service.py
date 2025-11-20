import logging
import time
from typing import Dict, Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings
from bot.services.panel_api_service import PanelApiService
from bot.services.best2pay_service import Best2PayService
from db.dal import user_dal, payment_dal


class TestB2PService:
    """Service for Best2Pay testing pipeline"""

    def __init__(
        self,
        settings: Settings,
        panel_service: PanelApiService,
        best2pay_service: Best2PayService
    ):
        self.settings = settings
        self.panel = panel_service
        self.b2p = best2pay_service

    async def create_test_user(
        self,
        session: AsyncSession,
        telegram_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Create test user in panel and local DB

        Args:
            session: Database session
            telegram_id: Telegram user ID of the admin creating the test

        Returns:
            Dictionary with user data or None on error
        """
        try:
            # Generate unique username
            timestamp = int(time.time())
            username = f"test_user_{timestamp}"

            logging.info(f"[TEST_B2P] Creating test user: {username}")

            # Create user in panel
            panel_response = await self.panel.create_panel_user(
                username_on_panel=username,
                telegram_id=None,  # Don't link to actual telegram ID
                email=f"{username}@test.local",
                default_expire_days=1,
                default_traffic_limit_bytes=10737418240,  # 10GB
                default_traffic_limit_strategy="NO_RESET",
                specific_squad_uuids=self.settings.parsed_user_squad_uuids,
                tag="TEST_USER",
                status="DISABLED"  # Create disabled initially
            )

            if not panel_response or panel_response.get("error"):
                logging.error(f"[TEST_B2P] Failed to create user in panel: {panel_response}")
                return None

            panel_user_data = panel_response.get("response", {})
            user_uuid = panel_user_data.get("uuid")
            short_uuid = panel_user_data.get("shortUuid")

            if not user_uuid:
                logging.error(f"[TEST_B2P] No UUID in panel response")
                return None

            # For test users, we don't create a local DB entry
            # They only exist in the panel for testing purposes
            logging.info(
                f"[TEST_B2P] User created: username={username}, "
                f"uuid={user_uuid}, short_uuid={short_uuid}"
            )

            return {
                "username": username,
                "uuid": user_uuid,
                "short_uuid": short_uuid,
                "telegram_id": telegram_id,
                "panel_data": panel_user_data
            }

        except Exception as e:
            logging.error(f"[TEST_B2P] Error creating test user: {e}", exc_info=True)
            return None

    async def create_test_payment(
        self,
        session: AsyncSession,
        user_id: int,
        months: int,
        amount: float
    ) -> Optional[Dict[str, Any]]:
        """
        Create test payment and register order in Best2Pay

        Args:
            session: Database session
            user_id: User ID from database
            months: Subscription duration in months
            amount: Payment amount in rubles

        Returns:
            Dictionary with payment data or None on error
        """
        try:
            logging.info(
                f"[TEST_B2P] Creating payment: user_id={user_id}, "
                f"months={months}, amount={amount}"
            )

            # Create payment record in DB
            payment_data = {
                "user_id": user_id,
                "amount": amount,
                "currency": "RUB",
                "status": "pending_best2pay",
                "subscription_duration_months": months,
                "provider": "best2pay",
                "description": "Техподдержка"
            }

            payment_record = await payment_dal.create_payment_record(session, payment_data)
            await session.flush()
            await session.refresh(payment_record)

            payment_db_id = payment_record.payment_id

            logging.info(f"[TEST_B2P] Payment record created: payment_id={payment_db_id}")

            # Register order in Best2Pay
            register_result = await self.b2p.register_order(
                amount=amount,
                reference=str(payment_db_id),
                currency="RUB",
                description="Техподдержка",
                url=self.settings.best2pay_success_full_webhook_url,
                fail_url=self.settings.best2pay_fail_full_webhook_url
            )

            if not register_result or not register_result.get("order_id"):
                logging.error(f"[TEST_B2P] Failed to register order in Best2Pay")
                return None

            order_id = register_result["order_id"]

            # Update payment record with order ID
            payment_record.provider_payment_id = f"b2p_{order_id}"
            await session.flush()

            logging.info(
                f"[TEST_B2P] Payment created: payment_id={payment_db_id}, "
                f"order_id={order_id}"
            )

            return {
                "payment_id": payment_db_id,
                "order_id": order_id,
                "amount": amount,
                "months": months,
                "status": "pending_best2pay"
            }

        except Exception as e:
            logging.error(f"[TEST_B2P] Error creating test payment: {e}", exc_info=True)
            return None

    async def create_payment_url(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        Generate SBP payment URL

        Args:
            order_id: Order ID from Best2Pay

        Returns:
            Dictionary with payment URL data or None on error
        """
        try:
            logging.info(f"[TEST_B2P] Creating payment URL for order_id={order_id}")

            payment_url = await self.b2p.create_payment_url(
                order_id=order_id,
                payment_method="sbp"
            )

            if not payment_url:
                logging.error(f"[TEST_B2P] Failed to create payment URL")
                return None

            logging.info(f"[TEST_B2P] Payment URL created: {payment_url[:50]}...")

            return {
                "order_id": order_id,
                "payment_url": payment_url,
                "payment_method": "sbp"
            }

        except Exception as e:
            logging.error(f"[TEST_B2P] Error creating payment URL: {e}", exc_info=True)
            return None

    async def simulate_payment(
        self,
        order_id: str,
        success: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Trigger test case in Best2Pay to simulate payment

        Args:
            order_id: Order ID from Best2Pay
            success: True for successful payment (case 150), False for failed (case 151)

        Returns:
            Dictionary with simulation result or None on error
        """
        try:
            case_id = "150" if success else "151"
            logging.info(
                f"[TEST_B2P] Simulating payment: order_id={order_id}, "
                f"success={success}, case_id={case_id}"
            )

            result = await self.b2p.trigger_test_case(
                order_id=order_id,
                case_id=case_id
            )

            if not result:
                logging.error(f"[TEST_B2P] Failed to trigger test case")
                return None

            logging.info(
                f"[TEST_B2P] Payment simulated: order_id={order_id}, "
                f"success={success}, message={result.get('message')}"
            )

            return {
                "order_id": order_id,
                "case_id": case_id,
                "success": success,
                "message": result.get("message"),
                "qrc_id": result.get("qrc_id")
            }

        except Exception as e:
            logging.error(f"[TEST_B2P] Error simulating payment: {e}", exc_info=True)
            return None

    async def check_subscription_status(
        self,
        session: AsyncSession,
        user_uuid: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get user status from panel and local DB

        Args:
            session: Database session
            user_uuid: Panel user UUID

        Returns:
            Dictionary with status data or None on error
        """
        try:
            logging.info(f"[TEST_B2P] Checking status for user_uuid={user_uuid}")

            # Get data from panel
            panel_data = await self.panel.get_user_by_uuid(user_uuid)

            if not panel_data:
                logging.error(f"[TEST_B2P] User not found in panel")
                return None

            # Get data from local DB
            db_user = await user_dal.get_user_by_panel_uuid(session, user_uuid)

            if not db_user:
                logging.error(f"[TEST_B2P] User not found in local DB")
                return None

            # Get recent payments
            recent_payments = await payment_dal.get_recent_payment_logs_with_user(
                session=session,
                limit=5,
                offset=0
            )

            # Filter payments for this user
            user_payments = [p for p in recent_payments if p.user_id == db_user.user_id]

            logging.info(f"[TEST_B2P] Status check complete for {user_uuid}")

            return {
                "panel_data": panel_data,
                "db_user": db_user,
                "recent_payments": user_payments
            }

        except Exception as e:
            logging.error(f"[TEST_B2P] Error checking status: {e}", exc_info=True)
            return None

    async def cleanup_test_data(
        self,
        session: AsyncSession,
        user_uuid: str
    ) -> bool:
        """
        Delete test user from panel

        Args:
            session: Database session
            user_uuid: Panel user UUID

        Returns:
            True if cleanup successful, False otherwise
        """
        try:
            logging.info(f"[TEST_B2P] Cleaning up test data: uuid={user_uuid}")

            # Delete from panel only (test users don't exist in local DB)
            panel_deleted = await self.panel.delete_user_by_uuid(user_uuid)

            if not panel_deleted:
                logging.warning(f"[TEST_B2P] Failed to delete user from panel")
                return False

            logging.info(f"[TEST_B2P] Test data cleaned up successfully")
            return True

        except Exception as e:
            logging.error(f"[TEST_B2P] Error cleaning up test data: {e}", exc_info=True)
            return False
