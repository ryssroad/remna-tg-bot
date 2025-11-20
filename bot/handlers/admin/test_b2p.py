import logging
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from typing import Optional

from config.settings import Settings
from bot.states.test_b2p_states import TestB2PStates
from bot.keyboards.inline.test_b2p_keyboards import (
    get_test_b2p_main_menu,
    get_subscription_period_keyboard,
    get_cleanup_confirmation_keyboard,
    get_back_to_test_menu_keyboard,
    get_test_status_keyboard
)
from bot.services.test_b2p_service import TestB2PService
from bot.services.panel_api_service import PanelApiService
from bot.services.best2pay_service import Best2PayService
from bot.middlewares.i18n import JsonI18n


router = Router(name="test_b2p_router")


@router.callback_query(F.data == "admin_action:test_b2p")
async def show_test_b2p_menu(
    callback: types.CallbackQuery,
    state: FSMContext,
    settings: Settings
):
    """Show Best2Pay testing main menu"""

    # Get current FSM data
    state_data = await state.get_data()

    # Build menu with current progress
    keyboard = get_test_b2p_main_menu(state_data)

    message_text = (
        "<b>🧪 Тестирование Best2Pay</b>\n\n"
        "Полноценное тестовое окружение для проверки платежного пайплайна.\n\n"
        "<b>Инструкция:</b>\n"
        "1. Создайте тестового пользователя\n"
        "2. Создайте тестовый платеж\n"
        "3. Сформируйте ссылку на оплату\n"
        "4. Симулируйте успешную/неуспешную оплату\n"
        "5. Проверьте статус подписки\n"
        "6. Очистите тестовые данные\n\n"
        f"<i>Текущий API: {settings.BEST2PAY_API_URL}</i>"
    )

    await callback.message.edit_text(
        message_text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await state.set_state(TestB2PStates.main_menu)
    await callback.answer()


@router.callback_query(F.data == "test_b2p:main")
async def back_to_main_menu(
    callback: types.CallbackQuery,
    state: FSMContext,
    settings: Settings
):
    """Return to main testing menu"""
    await show_test_b2p_menu(callback, state, settings)


@router.callback_query(F.data == "test_b2p:locked")
async def locked_step_handler(callback: types.CallbackQuery):
    """Handle click on locked step"""
    await callback.answer(
        "⚠️ Выполните предыдущие шаги",
        show_alert=True
    )


@router.callback_query(F.data == "test_b2p:create_user")
async def create_test_user_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
    panel_service: PanelApiService,
    best2pay_service: Best2PayService
):
    """Create test user in panel and DB"""

    await callback.answer("Создаю тестового пользователя...")

    # Create service
    test_service = TestB2PService(settings, panel_service, best2pay_service)

    # Create test user
    user_data = await test_service.create_test_user(
        session=session,
        telegram_id=callback.from_user.id
    )

    if not user_data:
        await callback.message.edit_text(
            "❌ <b>Ошибка создания пользователя</b>\n\n"
            "Не удалось создать тестового пользователя. Проверьте логи.",
            reply_markup=get_back_to_test_menu_keyboard(),
            parse_mode="HTML"
        )
        await callback.answer()
        return

    # Save to FSM
    state_data = await state.get_data()
    completed_steps = state_data.get("test_steps_completed", [])
    if "user_created" not in completed_steps:
        completed_steps.append("user_created")

    await state.update_data(
        test_user_uuid=user_data["uuid"],
        test_user_short_uuid=user_data.get("short_uuid"),
        test_username=user_data["username"],
        test_telegram_id=user_data["telegram_id"],
        test_started_at=datetime.utcnow().isoformat(),
        test_steps_completed=completed_steps
    )

    await session.commit()

    message_text = (
        "✅ <b>Тестовый пользователь создан!</b>\n\n"
        f"<b>Username:</b> <code>{user_data['username']}</code>\n"
        f"<b>UUID:</b> <code>{user_data['uuid']}</code>\n"
        f"<b>Short UUID:</b> <code>{user_data.get('short_uuid', 'N/A')}</code>\n"
        f"<b>Telegram ID:</b> <code>{user_data['telegram_id']}</code>\n"
        f"<b>Статус:</b> Не активирован (нет подписки)\n\n"
        "📋 Скопируйте UUID для следующих шагов"
    )

    await callback.message.edit_text(
        message_text,
        reply_markup=get_back_to_test_menu_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(TestB2PStates.user_created)
    await callback.answer()


@router.callback_query(F.data == "test_b2p:create_payment")
async def create_payment_prompt_handler(
    callback: types.CallbackQuery,
    state: FSMContext
):
    """Show subscription period selection"""

    state_data = await state.get_data()
    if "test_user_uuid" not in state_data:
        await callback.answer(
            "⚠️ Сначала создайте тестового пользователя",
            show_alert=True
        )
        return

    message_text = (
        "<b>Выберите период подписки:</b>\n\n"
        "Будет создан тестовый платеж и зарегистрирован заказ в Best2Pay."
    )

    await callback.message.edit_text(
        message_text,
        reply_markup=get_subscription_period_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(TestB2PStates.selecting_subscription_period)
    await callback.answer()


@router.callback_query(F.data.startswith("test_b2p:period:"))
async def create_payment_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
    panel_service: PanelApiService,
    best2pay_service: Best2PayService
):
    """Create test payment with selected period"""

    # Parse period and amount
    parts = callback.data.split(":")
    months = int(parts[2])
    amount = float(parts[3])

    await callback.answer(f"Создаю платеж на {months} мес...")

    # Get current state data
    state_data = await state.get_data()

    # Get or create admin user in local DB for payment tracking
    from db.dal import user_dal
    admin_telegram_id = callback.from_user.id

    admin_user, _ = await user_dal.create_user(
        session=session,
        user_data={
            "user_id": admin_telegram_id,
            "username": callback.from_user.username or f"admin_{admin_telegram_id}",
            "first_name": callback.from_user.first_name or "Admin",
            "language_code": callback.from_user.language_code or "ru"
        }
    )

    if not admin_user:
        await callback.message.edit_text(
            "❌ <b>Ошибка</b>\n\n"
            "Не удалось получить данные пользователя.",
            reply_markup=get_back_to_test_menu_keyboard(),
            parse_mode="HTML"
        )
        return

    # Create service
    test_service = TestB2PService(settings, panel_service, best2pay_service)

    # Create payment (linked to admin's account for testing)
    payment_data = await test_service.create_test_payment(
        session=session,
        user_id=admin_user.user_id,
        months=months,
        amount=amount
    )

    if not payment_data:
        await callback.message.edit_text(
            "❌ <b>Ошибка создания платежа</b>\n\n"
            "Не удалось создать тестовый платеж. Проверьте логи.",
            reply_markup=get_back_to_test_menu_keyboard(),
            parse_mode="HTML"
        )
        return

    # Save to FSM
    completed_steps = state_data.get("test_steps_completed", [])
    if "payment_created" not in completed_steps:
        completed_steps.append("payment_created")

    await state.update_data(
        test_payment_id=payment_data["payment_id"],
        test_order_id=payment_data["order_id"],
        test_months=months,
        test_amount=amount,
        test_steps_completed=completed_steps
    )

    await session.commit()

    amount_kopeks = int(amount * 100)

    message_text = (
        "✅ <b>Тестовый платеж создан!</b>\n\n"
        f"<b>Payment ID (БД):</b> <code>{payment_data['payment_id']}</code>\n"
        f"<b>Best2Pay Order ID:</b> <code>{payment_data['order_id']}</code>\n"
        f"<b>Сумма:</b> {amount:.2f} RUB ({amount_kopeks} копеек)\n"
        f"<b>Период:</b> {months} месяц(ев)\n"
        f"<b>Статус:</b> {payment_data['status']}\n\n"
        "🔄 Заказ зарегистрирован в Best2Pay\n"
        "<i>Следующий шаг: Создать ссылку на оплату</i>"
    )

    await callback.message.edit_text(
        message_text,
        reply_markup=get_back_to_test_menu_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(TestB2PStates.payment_created)
    await callback.answer()


@router.callback_query(F.data == "test_b2p:create_url")
async def create_payment_url_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
    settings: Settings,
    panel_service: PanelApiService,
    best2pay_service: Best2PayService
):
    """Generate SBP payment URL"""

    state_data = await state.get_data()
    order_id = state_data.get("test_order_id")

    if not order_id:
        await callback.answer(
            "⚠️ Сначала создайте тестовый платеж",
            show_alert=True
        )
        return

    await callback.answer("Создаю ссылку на оплату...")

    # Create service
    test_service = TestB2PService(settings, panel_service, best2pay_service)

    # Create payment URL
    url_data = await test_service.create_payment_url(order_id)

    if not url_data:
        await callback.message.edit_text(
            "❌ <b>Ошибка создания ссылки</b>\n\n"
            "Не удалось создать ссылку на оплату. Проверьте логи.",
            reply_markup=get_back_to_test_menu_keyboard(),
            parse_mode="HTML"
        )
        return

    # Save to FSM
    completed_steps = state_data.get("test_steps_completed", [])
    if "payment_url_created" not in completed_steps:
        completed_steps.append("payment_url_created")

    await state.update_data(
        test_pay_url=url_data["payment_url"],
        test_steps_completed=completed_steps
    )

    message_text = (
        "✅ <b>Ссылка на оплату создана!</b>\n\n"
        f"<b>Order ID:</b> <code>{url_data['order_id']}</code>\n"
        f"<b>Метод:</b> {url_data['payment_method'].upper()} (Faster Payment System)\n\n"
        "🔗 <b>Ссылка на оплату:</b>\n"
        f"<code>{url_data['payment_url']}</code>\n\n"
        "⚠️ <b>Внимание:</b> На тестовом стенде Best2Pay реальная оплата "
        "через СБП может не работать. Используйте симуляцию (шаг 4)\n\n"
        "📲 Можете попробовать открыть ссылку (для теста UX)"
    )

    await callback.message.edit_text(
        message_text,
        reply_markup=get_back_to_test_menu_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(TestB2PStates.payment_url_created)
    await callback.answer()


@router.callback_query(F.data == "test_b2p:simulate_success")
async def simulate_success_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
    settings: Settings,
    panel_service: PanelApiService,
    best2pay_service: Best2PayService
):
    """Simulate successful payment"""

    state_data = await state.get_data()
    order_id = state_data.get("test_order_id")

    if not order_id:
        await callback.answer(
            "⚠️ Сначала создайте платеж и ссылку",
            show_alert=True
        )
        return

    await callback.answer("Симулирую успешную оплату...")

    # Create service
    test_service = TestB2PService(settings, panel_service, best2pay_service)

    # Simulate payment
    sim_data = await test_service.simulate_payment(order_id, success=True)

    if not sim_data:
        await callback.message.edit_text(
            "❌ <b>Ошибка симуляции</b>\n\n"
            "Не удалось симулировать оплату. Проверьте логи.",
            reply_markup=get_back_to_test_menu_keyboard(),
            parse_mode="HTML"
        )
        return

    # Save to FSM
    completed_steps = state_data.get("test_steps_completed", [])
    if "payment_simulated_success" not in completed_steps:
        completed_steps.append("payment_simulated_success")

    await state.update_data(test_steps_completed=completed_steps)

    message_text = (
        "✅ <b>Успешная оплата симулирована!</b>\n\n"
        f"<b>Order ID:</b> <code>{sim_data['order_id']}</code>\n"
        f"<b>Test Case:</b> {sim_data['case_id']} (успешная оплата)\n"
        f"<b>QRC ID:</b> <code>{sim_data.get('qrc_id', 'N/A')}</code>\n"
        f"<b>Ответ API:</b> <i>{sim_data.get('message', 'N/A')}</i>\n\n"
        "🔔 <b>Webhook будет отправлен в течение нескольких секунд</b>\n\n"
        "После получения webhook бот должен:\n"
        "• Обновить статус платежа на 'succeeded'\n"
        "• Активировать подписку через Panel API\n"
        "• Отправить уведомление пользователю\n\n"
        "<i>Проверьте логи бота и используйте '6️⃣ Проверить статус'</i>"
    )

    await callback.message.edit_text(
        message_text,
        reply_markup=get_back_to_test_menu_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(TestB2PStates.payment_simulated)
    await callback.answer()


@router.callback_query(F.data == "test_b2p:simulate_fail")
async def simulate_fail_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
    settings: Settings,
    panel_service: PanelApiService,
    best2pay_service: Best2PayService
):
    """Simulate failed payment"""

    state_data = await state.get_data()
    order_id = state_data.get("test_order_id")

    if not order_id:
        await callback.answer(
            "⚠️ Сначала создайте платеж и ссылку",
            show_alert=True
        )
        return

    await callback.answer("Симулирую неуспешную оплату...")

    # Create service
    test_service = TestB2PService(settings, panel_service, best2pay_service)

    # Simulate payment
    sim_data = await test_service.simulate_payment(order_id, success=False)

    if not sim_data:
        await callback.message.edit_text(
            "❌ <b>Ошибка симуляции</b>\n\n"
            "Не удалось симулировать оплату. Проверьте логи.",
            reply_markup=get_back_to_test_menu_keyboard(),
            parse_mode="HTML"
        )
        return

    # Save to FSM
    completed_steps = state_data.get("test_steps_completed", [])
    if "payment_simulated_fail" not in completed_steps:
        completed_steps.append("payment_simulated_fail")

    await state.update_data(test_steps_completed=completed_steps)

    message_text = (
        "⚠️ <b>Неуспешная оплата симулирована</b>\n\n"
        f"<b>Order ID:</b> <code>{sim_data['order_id']}</code>\n"
        f"<b>Test Case:</b> {sim_data['case_id']} (неуспешная оплата)\n"
        f"<b>QRC ID:</b> <code>{sim_data.get('qrc_id', 'N/A')}</code>\n"
        f"<b>Ответ API:</b> <i>{sim_data.get('message', 'N/A')}</i>\n\n"
        "🔔 <b>Webhook будет отправлен</b>\n\n"
        "После получения webhook бот должен:\n"
        "• Статус платежа останется 'pending_best2pay' или изменится на 'failed'\n"
        "• Подписка НЕ активируется\n"
        "• Пользователь получит уведомление об ошибке\n\n"
        "<i>Проверьте логи бота</i>"
    )

    await callback.message.edit_text(
        message_text,
        reply_markup=get_back_to_test_menu_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(TestB2PStates.payment_simulated)
    await callback.answer()


@router.callback_query(F.data == "test_b2p:check_status")
async def check_status_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
    panel_service: PanelApiService,
    best2pay_service: Best2PayService
):
    """Check subscription status"""

    state_data = await state.get_data()
    user_uuid = state_data.get("test_user_uuid")

    if not user_uuid:
        await callback.answer(
            "⚠️ Сначала создайте тестового пользователя",
            show_alert=True
        )
        return

    await callback.answer("Проверяю статус...")

    # Create service
    test_service = TestB2PService(settings, panel_service, best2pay_service)

    # Check status
    status_data = await test_service.check_subscription_status(session, user_uuid)

    if not status_data:
        await callback.message.edit_text(
            "❌ <b>Ошибка проверки статуса</b>\n\n"
            "Не удалось получить статус пользователя. Проверьте логи.",
            reply_markup=get_back_to_test_menu_keyboard(),
            parse_mode="HTML"
        )
        return

    panel_data = status_data["panel_data"]
    db_user = status_data["db_user"]
    recent_payments = status_data["recent_payments"]

    # Format status
    is_active = panel_data.get("isActive", False)
    status_emoji = "✅" if is_active else "❌"
    expires_at = panel_data.get("expiresAt", "N/A")

    # Format traffic
    traffic_limit = panel_data.get("trafficLimitBytes", 0)
    traffic_used = panel_data.get("trafficUsedBytes", 0)

    if traffic_limit == 0:
        traffic_str = "Безлимит"
        traffic_used_str = f"{traffic_used / (1024**2):.2f} MB"
        traffic_left_str = "∞"
    else:
        traffic_limit_gb = traffic_limit / (1024**3)
        traffic_used_gb = traffic_used / (1024**3)
        traffic_left_gb = (traffic_limit - traffic_used) / (1024**3)
        traffic_str = f"{traffic_limit_gb:.2f} GB"
        traffic_used_str = f"{traffic_used_gb:.2f} GB"
        traffic_left_str = f"{traffic_left_gb:.2f} GB"

    # Format payments
    payments_str = ""
    if recent_payments:
        for i, p in enumerate(recent_payments[:5], 1):
            created_at = p.created_at.strftime('%Y-%m-%d %H:%M') if p.created_at else "N/A"
            payments_str += (
                f"{i}. #{p.payment_id} - {p.status} - {p.amount} {p.currency} - "
                f"{created_at} ({p.provider})\n"
            )
    else:
        payments_str = "Нет платежей"

    message_text = (
        "📊 <b>Статус тестового пользователя</b>\n\n"
        "<b>👤 Пользователь</b>\n"
        f"Username: <code>{panel_data.get('username')}</code>\n"
        f"UUID: <code>{user_uuid}</code>\n"
        f"Telegram ID: <code>{db_user.user_id}</code>\n\n"
        "<b>📅 Подписка</b>\n"
        f"Статус: {status_emoji} {'Активна' if is_active else 'Неактивна'}\n"
        f"Истекает: {expires_at}\n\n"
        "<b>📊 Трафик</b>\n"
        f"Лимит: {traffic_str}\n"
        f"Использовано: {traffic_used_str}\n"
        f"Осталось: {traffic_left_str}\n\n"
        "<b>💳 Последние платежи</b>\n"
        f"{payments_str}"
    )

    await callback.message.edit_text(
        message_text,
        reply_markup=get_back_to_test_menu_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(TestB2PStates.checking_status)
    await callback.answer()


@router.callback_query(F.data == "test_b2p:cleanup")
async def cleanup_prompt_handler(
    callback: types.CallbackQuery,
    state: FSMContext
):
    """Show cleanup confirmation"""

    state_data = await state.get_data()
    username = state_data.get("test_username", "N/A")

    message_text = (
        "⚠️ <b>Вы уверены?</b>\n\n"
        "Будут удалены:\n"
        "• Тестовый пользователь в панели\n"
        f"  (<code>{username}</code>)\n"
        "• FSM данные текущего тест-кейса\n\n"
        "<i>Записи в БД (users, payments) сохранятся для истории</i>"
    )

    await callback.message.edit_text(
        message_text,
        reply_markup=get_cleanup_confirmation_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(TestB2PStates.confirming_cleanup)
    await callback.answer()


@router.callback_query(F.data == "test_b2p:cleanup_confirm")
async def cleanup_confirm_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
    panel_service: PanelApiService,
    best2pay_service: Best2PayService
):
    """Confirm and execute cleanup"""

    state_data = await state.get_data()
    user_uuid = state_data.get("test_user_uuid")
    user_db_id = state_data.get("test_user_db_id")
    username = state_data.get("test_username", "N/A")

    if not user_uuid:
        await callback.answer("Нет данных для очистки", show_alert=True)
        await state.clear()
        await show_test_b2p_menu(callback, state, settings)
        return

    await callback.answer("Очищаю данные...")

    # Create service
    test_service = TestB2PService(settings, panel_service, best2pay_service)

    # Cleanup
    success = await test_service.cleanup_test_data(session, user_uuid)

    await session.commit()

    # Clear FSM
    await state.clear()

    if success:
        message_text = (
            "✅ <b>Тестовые данные очищены</b>\n\n"
            "Удалено:\n"
            f"• Пользователь {username} из панели\n"
            "• FSM state сброшен\n\n"
            "Можете начать новый тест-кейс"
        )
    else:
        message_text = (
            "⚠️ <b>Частичная очистка</b>\n\n"
            "FSM очищен, но возникли проблемы с удалением из панели.\n"
            "Проверьте логи."
        )

    await callback.message.edit_text(
        message_text,
        reply_markup=get_back_to_test_menu_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "test_b2p:show_status")
async def show_test_status_handler(
    callback: types.CallbackQuery,
    state: FSMContext
):
    """Show current test case status"""

    state_data = await state.get_data()
    completed_steps = state_data.get("test_steps_completed", [])

    total_steps = 5
    completed_count = min(len(completed_steps), total_steps)
    progress_percent = int((completed_count / total_steps) * 100)
    progress_bar = "█" * (completed_count * 2) + "░" * ((total_steps - completed_count) * 2)

    # Build steps list
    steps_text = ""

    step1_status = "✅" if "user_created" in completed_steps else "⏸️"
    steps_text += f"{step1_status} 1. Пользователь создан\n"
    if "user_created" in completed_steps:
        username = state_data.get("test_username", "N/A")
        uuid = state_data.get("test_user_uuid", "N/A")
        steps_text += f"   └─ {username} (UUID: {uuid[:8]}...)\n"

    step2_status = "✅" if "payment_created" in completed_steps else "⏸️"
    steps_text += f"\n{step2_status} 2. Платеж создан\n"
    if "payment_created" in completed_steps:
        payment_id = state_data.get("test_payment_id", "N/A")
        order_id = state_data.get("test_order_id", "N/A")
        steps_text += f"   └─ Payment ID: {payment_id}, Order ID: {order_id}\n"

    step3_status = "✅" if "payment_url_created" in completed_steps else "⏸️"
    steps_text += f"\n{step3_status} 3. Ссылка сформирована\n"
    if "payment_url_created" in completed_steps:
        pay_url = state_data.get("test_pay_url", "N/A")
        steps_text += f"   └─ URL: {pay_url[:50]}...\n"

    step4_status = "✅" if "payment_simulated_success" in completed_steps else "⏸️"
    steps_text += f"\n{step4_status} 4. Оплата симулирована (успех)\n"
    if "payment_simulated_success" in completed_steps:
        steps_text += "   └─ Status: succeeded\n"

    step5_status = "✅" if "payment_simulated_fail" in completed_steps else "⏸️"
    steps_text += f"\n{step5_status} 5. Оплата симулирована (ошибка)\n"
    if "payment_simulated_fail" in completed_steps:
        steps_text += "   └─ Status: failed\n"

    # Next step
    if completed_count < total_steps:
        if "user_created" not in completed_steps:
            next_step = "Следующий шаг: Создать пользователя"
        elif "payment_created" not in completed_steps:
            next_step = "Следующий шаг: Создать платеж"
        elif "payment_url_created" not in completed_steps:
            next_step = "Следующий шаг: Создать ссылку"
        elif "payment_simulated_success" not in completed_steps:
            next_step = "Следующий шаг: Симулировать оплату"
        else:
            next_step = "Все основные шаги выполнены!"
    else:
        next_step = "✅ Все шаги выполнены!"

    message_text = (
        "📋 <b>Текущий тест-кейс</b>\n\n"
        f"<b>Прогресс:</b> {progress_bar} {progress_percent}% ({completed_count}/{total_steps} шагов)\n\n"
        f"{steps_text}\n"
        f"<b>{next_step}</b>"
    )

    await callback.message.edit_text(
        message_text,
        reply_markup=get_test_status_keyboard(state_data),
        parse_mode="HTML"
    )
    await callback.answer()
