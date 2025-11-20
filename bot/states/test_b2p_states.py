from aiogram.fsm.state import State, StatesGroup


class TestB2PStates(StatesGroup):
    """FSM states for Best2Pay testing pipeline"""

    # Main menu
    main_menu = State()

    # Creating test user
    awaiting_user_creation = State()
    user_created = State()

    # Creating payment
    selecting_subscription_period = State()
    payment_created = State()

    # Payment URL
    payment_url_created = State()

    # Payment simulation
    payment_simulated = State()

    # Status checking
    checking_status = State()

    # Cleanup
    confirming_cleanup = State()
