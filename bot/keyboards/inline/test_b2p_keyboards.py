from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup
from typing import Dict, List, Any


def get_test_b2p_main_menu(state_data: Dict[str, Any]) -> InlineKeyboardMarkup:
    """
    Generate main testing menu with progressive unlocking of steps

    Args:
        state_data: FSM state data containing completed steps

    Returns:
        InlineKeyboardMarkup with test menu buttons
    """
    builder = InlineKeyboardBuilder()

    # Get list of completed steps
    completed_steps = state_data.get("test_steps_completed", [])

    # Step 1: Create test user
    step1_done = "user_created" in completed_steps
    icon1 = "✅" if step1_done else "1️⃣"
    builder.button(
        text=f"{icon1} Создать тестового пользователя",
        callback_data="test_b2p:create_user"
    )

    # Step 2: Create payment (unlocked after step 1)
    if step1_done:
        step2_done = "payment_created" in completed_steps
        icon2 = "✅" if step2_done else "2️⃣"
        builder.button(
            text=f"{icon2} Создать тестовый платеж",
            callback_data="test_b2p:create_payment"
        )
    else:
        builder.button(
            text="🔒 Создать тестовый платеж",
            callback_data="test_b2p:locked"
        )

    # Step 3: Create payment URL (unlocked after step 2)
    if "payment_created" in completed_steps:
        step3_done = "payment_url_created" in completed_steps
        icon3 = "✅" if step3_done else "3️⃣"
        builder.button(
            text=f"{icon3} Сформировать ссылку на оплату",
            callback_data="test_b2p:create_url"
        )
    else:
        builder.button(
            text="🔒 Сформировать ссылку на оплату",
            callback_data="test_b2p:locked"
        )

    # Step 4 & 5: Simulate payments (unlocked after step 3)
    if "payment_url_created" in completed_steps:
        step4_done = "payment_simulated_success" in completed_steps
        icon4 = "✅" if step4_done else "4️⃣"
        builder.button(
            text=f"{icon4} Симулировать успешную оплату",
            callback_data="test_b2p:simulate_success"
        )

        step5_done = "payment_simulated_fail" in completed_steps
        icon5 = "✅" if step5_done else "5️⃣"
        builder.button(
            text=f"{icon5} Симулировать неуспешную оплату",
            callback_data="test_b2p:simulate_fail"
        )
    else:
        builder.button(
            text="🔒 Симулировать успешную оплату",
            callback_data="test_b2p:locked"
        )
        builder.button(
            text="🔒 Симулировать неуспешную оплату",
            callback_data="test_b2p:locked"
        )

    # Step 6: Check status (unlocked after step 1)
    if step1_done:
        builder.button(
            text="6️⃣ Проверить статус подписки",
            callback_data="test_b2p:check_status"
        )
    else:
        builder.button(
            text="🔒 Проверить статус подписки",
            callback_data="test_b2p:locked"
        )

    # Additional options
    builder.button(
        text="ℹ️ Показать текущий тест-кейс",
        callback_data="test_b2p:show_status"
    )

    # Cleanup (always available if user was created)
    if step1_done:
        builder.button(
            text="🗑️ Очистить тестовые данные",
            callback_data="test_b2p:cleanup"
        )

    builder.button(
        text="◀️ Назад в админку",
        callback_data="admin_action:main"
    )

    builder.adjust(1)  # One button per row
    return builder.as_markup()


def get_subscription_period_keyboard() -> InlineKeyboardMarkup:
    """
    Generate keyboard for selecting subscription period

    Returns:
        InlineKeyboardMarkup with subscription period options
    """
    builder = InlineKeyboardBuilder()

    builder.button(
        text="1 месяц - 300₽",
        callback_data="test_b2p:period:1:300"
    )
    builder.button(
        text="3 месяца - 850₽",
        callback_data="test_b2p:period:3:850"
    )
    builder.button(
        text="6 месяцев - 1600₽",
        callback_data="test_b2p:period:6:1600"
    )
    builder.button(
        text="12 месяцев - 3000₽",
        callback_data="test_b2p:period:12:3000"
    )
    builder.button(
        text="◀️ Назад",
        callback_data="test_b2p:main"
    )

    builder.adjust(2, 2, 1)  # 2-2-1 layout
    return builder.as_markup()


def get_cleanup_confirmation_keyboard() -> InlineKeyboardMarkup:
    """
    Generate keyboard for cleanup confirmation

    Returns:
        InlineKeyboardMarkup with yes/no buttons
    """
    builder = InlineKeyboardBuilder()

    builder.button(
        text="✅ Да, удалить",
        callback_data="test_b2p:cleanup_confirm"
    )
    builder.button(
        text="❌ Отмена",
        callback_data="test_b2p:main"
    )

    builder.adjust(2)
    return builder.as_markup()


def get_back_to_test_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Generate simple back button to test menu

    Returns:
        InlineKeyboardMarkup with back button
    """
    builder = InlineKeyboardBuilder()

    builder.button(
        text="◀️ Назад в тестовое меню",
        callback_data="test_b2p:main"
    )

    return builder.as_markup()


def get_test_status_keyboard(state_data: Dict[str, Any]) -> InlineKeyboardMarkup:
    """
    Generate keyboard for test status view with quick actions

    Args:
        state_data: FSM state data containing test progress

    Returns:
        InlineKeyboardMarkup with action buttons
    """
    builder = InlineKeyboardBuilder()

    completed_steps = state_data.get("test_steps_completed", [])

    # Determine next step
    if "user_created" not in completed_steps:
        builder.button(
            text="▶️ Создать пользователя",
            callback_data="test_b2p:create_user"
        )
    elif "payment_created" not in completed_steps:
        builder.button(
            text="▶️ Создать платеж",
            callback_data="test_b2p:create_payment"
        )
    elif "payment_url_created" not in completed_steps:
        builder.button(
            text="▶️ Создать ссылку",
            callback_data="test_b2p:create_url"
        )
    elif "payment_simulated_success" not in completed_steps:
        builder.button(
            text="▶️ Симулировать оплату",
            callback_data="test_b2p:simulate_success"
        )
    else:
        builder.button(
            text="✅ Все шаги выполнены",
            callback_data="test_b2p:main"
        )

    if "user_created" in completed_steps:
        builder.button(
            text="🗑️ Очистить",
            callback_data="test_b2p:cleanup"
        )

    builder.button(
        text="🔄 Начать заново",
        callback_data="test_b2p:cleanup"
    )

    builder.button(
        text="◀️ Назад",
        callback_data="test_b2p:main"
    )

    builder.adjust(1)
    return builder.as_markup()
