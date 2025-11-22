import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from sqlalchemy.orm import sessionmaker

from config.settings import Settings


async def build_and_start_web_app(
    dp: Dispatcher,
    bot: Bot,
    settings: Settings,
    async_session_factory: sessionmaker,
):
    app = web.Application()
    app["bot"] = bot
    app["dp"] = dp
    app["settings"] = settings
    app["async_session_factory"] = async_session_factory
    # Inject shared instances used by webhook handlers
    app["i18n"] = dp.get("i18n_instance")
    for key in (
        "yookassa_service",
        "subscription_service",
        "referral_service",
        "panel_service",
        "stars_service",
        "cryptopay_service",
        "tribute_service",
        "panel_webhook_service",
        "freekassa_service",
        "best2pay_service",
        "nowpayments_service",
    ):
        # Access dispatcher workflow_data directly to avoid sequence protocol issues
        if hasattr(dp, "workflow_data") and key in dp.workflow_data:  # type: ignore
            app[key] = dp.workflow_data[key]  # type: ignore

    setup_application(app, dp, bot=bot)

    telegram_uses_webhook_mode = bool(settings.WEBHOOK_BASE_URL)

    if telegram_uses_webhook_mode:
        telegram_webhook_path = f"/{settings.BOT_TOKEN}"
        app.router.add_post(telegram_webhook_path, SimpleRequestHandler(dispatcher=dp, bot=bot))
        logging.info(
            f"Telegram webhook route configured at: [POST] {telegram_webhook_path} (relative to base URL)"
        )

    from bot.handlers.user.payment import yookassa_webhook_route
    from bot.services.tribute_service import tribute_webhook_route
    from bot.services.crypto_pay_service import cryptopay_webhook_route
    from bot.services.panel_webhook_service import panel_webhook_route
    from bot.services.freekassa_service import (
        freekassa_notify_webhook,
        freekassa_success_webhook,
        freekassa_fail_webhook
    )
    from bot.services.best2pay_service import (
        best2pay_notify_webhook,
        best2pay_success_webhook,
        best2pay_fail_webhook
    )
    from bot.services.nowpayments_service import nowpayments_ipn_webhook

    tribute_path = settings.tribute_webhook_path
    if tribute_path.startswith("/"):
        app.router.add_post(tribute_path, tribute_webhook_route)
        logging.info(f"Tribute webhook route configured at: [POST] {tribute_path}")

    cp_path = settings.cryptopay_webhook_path
    if cp_path.startswith("/"):
        app.router.add_post(cp_path, cryptopay_webhook_route)
        logging.info(f"CryptoPay webhook route configured at: [POST] {cp_path}")

    # YooKassa webhook (register only when base URL present and path configured)
    yk_path = settings.yookassa_webhook_path
    if settings.WEBHOOK_BASE_URL and yk_path and yk_path.startswith("/"):
        app.router.add_post(yk_path, yookassa_webhook_route)
        logging.info(f"YooKassa webhook route configured at: [POST] {yk_path}")

    panel_path = settings.panel_webhook_path
    if panel_path.startswith("/"):
        app.router.add_post(panel_path, panel_webhook_route)
        logging.info(f"Panel webhook route configured at: [POST] {panel_path}")

    # FreeKassa webhooks
    freekassa_notify_path = settings.freekassa_notify_webhook_path
    if freekassa_notify_path.startswith("/"):
        app.router.add_post(freekassa_notify_path, freekassa_notify_webhook)
        logging.info(f"FreeKassa notify webhook route configured at: [POST] {freekassa_notify_path}")

    freekassa_success_path = settings.freekassa_success_webhook_path
    if freekassa_success_path.startswith("/"):
        app.router.add_post(freekassa_success_path, freekassa_success_webhook)
        logging.info(f"FreeKassa success webhook route configured at: [POST] {freekassa_success_path}")

    freekassa_fail_path = settings.freekassa_fail_webhook_path
    if freekassa_fail_path.startswith("/"):
        app.router.add_post(freekassa_fail_path, freekassa_fail_webhook)
        logging.info(f"FreeKassa fail webhook route configured at: [POST] {freekassa_fail_path}")

    # Best2Pay webhooks
    best2pay_notify_path = settings.best2pay_notify_webhook_path
    if best2pay_notify_path.startswith("/"):
        app.router.add_post(best2pay_notify_path, best2pay_notify_webhook)
        logging.info(f"Best2Pay notify webhook route configured at: [POST] {best2pay_notify_path}")

    best2pay_success_path = settings.best2pay_success_webhook_path
    if best2pay_success_path.startswith("/"):
        app.router.add_get(best2pay_success_path, best2pay_success_webhook)
        logging.info(f"Best2Pay success webhook route configured at: [GET] {best2pay_success_path}")

    best2pay_fail_path = settings.best2pay_fail_webhook_path
    if best2pay_fail_path.startswith("/"):
        app.router.add_get(best2pay_fail_path, best2pay_fail_webhook)
        logging.info(f"Best2Pay fail webhook route configured at: [GET] {best2pay_fail_path}")

    # NOWPayments IPN webhook
    nowpayments_path = settings.nowpayments_ipn_webhook_path
    if nowpayments_path.startswith("/"):
        app.router.add_post(nowpayments_path, nowpayments_ipn_webhook)
        logging.info(f"NOWPayments IPN webhook route configured at: [POST] {nowpayments_path}")

    web_app_runner = web.AppRunner(app)
    await web_app_runner.setup()
    site = web.TCPSite(
        web_app_runner,
        host=settings.WEB_SERVER_HOST,
        port=settings.WEB_SERVER_PORT,
    )

    await site.start()
    logging.info(
        f"AIOHTTP server started on http://{settings.WEB_SERVER_HOST}:{settings.WEB_SERVER_PORT}"
    )

    # Run until cancelled
    await asyncio.Event().wait()


