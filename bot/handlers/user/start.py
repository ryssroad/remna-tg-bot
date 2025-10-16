import logging
import re
from aiogram import Router, F, types, Bot
from aiogram.utils.text_decorations import html_decoration as hd
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from typing import Optional, Union
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from db.dal import user_dal

from bot.keyboards.inline.user_keyboards import get_main_menu_inline_keyboard, get_language_selection_keyboard
from bot.services.subscription_service import SubscriptionService
from bot.services.panel_api_service import PanelApiService
from bot.services.referral_service import ReferralService
from bot.services.promo_code_service import PromoCodeService
from config.settings import Settings
from bot.middlewares.i18n import JsonI18n

router = Router(name="user_start_router")


async def send_main_menu(target_event: Union[types.Message,
                                             types.CallbackQuery],
                         settings: Settings,
                         i18n_data: dict,
                         subscription_service: SubscriptionService,
                         session: AsyncSession,
                         is_edit: bool = False):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")

    user_id = target_event.from_user.id
    user_full_name = hd.quote(target_event.from_user.full_name)

    if not i18n:
        logging.error(
            f"i18n_instance missing in send_main_menu for user {user_id}")
        err_msg_fallback = "Error: Language service unavailable. Please try again later."
        if isinstance(target_event, types.CallbackQuery):
            try:
                await target_event.answer(err_msg_fallback, show_alert=True)
            except Exception:
                pass
        elif isinstance(target_event, types.Message):
            try:
                await target_event.answer(err_msg_fallback)
            except Exception:
                pass
        return

    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    show_trial_button_in_menu = False
    if settings.TRIAL_ENABLED:
        if hasattr(
                subscription_service, 'has_had_any_subscription') and callable(
                    getattr(subscription_service, 'has_had_any_subscription')):
            if not await subscription_service.has_had_any_subscription(
                    session, user_id):
                show_trial_button_in_menu = True
        else:
            logging.error(
                "Method has_had_any_subscription is missing in SubscriptionService for send_main_menu!"
            )

    text = _(key="main_menu_greeting", user_name=user_full_name)
    reply_markup = get_main_menu_inline_keyboard(current_lang, i18n, settings,
                                                 show_trial_button_in_menu)

    target_message_obj: Optional[types.Message] = None
    if isinstance(target_event, types.Message):
        target_message_obj = target_event
    elif isinstance(target_event,
                    types.CallbackQuery) and target_event.message:
        target_message_obj = target_event.message

    if not target_message_obj:
        logging.error(
            f"send_main_menu: target_message_obj is None for event from user {user_id}."
        )
        if isinstance(target_event, types.CallbackQuery):
            await target_event.answer(_("error_displaying_menu"),
                                      show_alert=True)
        return

    try:
        if is_edit:
            await target_message_obj.edit_text(text, reply_markup=reply_markup)
        else:
            await target_message_obj.answer(text, reply_markup=reply_markup)

        if isinstance(target_event, types.CallbackQuery):
            try:
                await target_event.answer()
            except Exception:
                pass
    except Exception as e_send_edit:
        logging.warning(
            f"Failed to send/edit main menu (user: {user_id}, is_edit: {is_edit}): {type(e_send_edit).__name__} - {e_send_edit}."
        )
        if is_edit and target_message_obj:
            try:
                await target_message_obj.answer(text, reply_markup=reply_markup)
            except Exception as e_send_new:
                logging.error(
                    f"Also failed to send new main menu message for user {user_id}: {e_send_new}"
                )
        if isinstance(target_event, types.CallbackQuery):
            try:
                await target_event.answer(
                    _("error_occurred_try_again") if is_edit else None)
            except Exception:
                pass


@router.message(CommandStart())
@router.message(CommandStart(magic=F.args.regexp(r"^ref_(\d+)$").as_("ref_match")))
@router.message(CommandStart(magic=F.args.regexp(r"^promo_(\w+)$").as_("promo_match")))
async def start_command_handler(message: types.Message,
                                state: FSMContext,
                                settings: Settings,
                                i18n_data: dict,
                                subscription_service: SubscriptionService,
                                session: AsyncSession,
                                ref_match: Optional[re.Match] = None,
                                promo_match: Optional[re.Match] = None):
    await state.clear()
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs
                                           ) if i18n else key

    user = message.from_user
    user_id = user.id

    referred_by_user_id: Optional[int] = None
    promo_code_to_apply: Optional[str] = None

    if ref_match:
        potential_referrer_id = int(ref_match.group(1))
        if await user_dal.get_user_by_id(session, potential_referrer_id):
            referred_by_user_id = potential_referrer_id
    elif promo_match:
        promo_code_to_apply = promo_match.group(1)
        logging.info(f"User {user_id} started with promo code: {promo_code_to_apply}")

    db_user = await user_dal.get_user_by_id(session, user_id)
    if not db_user:
        user_data_to_create = {
            "user_id": user_id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "language_code": current_lang,
            "referred_by_id": referred_by_user_id,
            "registration_date": datetime.now(timezone.utc)
        }
        try:
            db_user, created = await user_dal.create_user(session, user_data_to_create)

            if created:
                logging.info(
                    f"New user {user_id} added to session. Referred by: {referred_by_user_id or 'N/A'}."
                )

                # Send notification about new user registration
                try:
                    from bot.services.notification_service import NotificationService
                    notification_service = NotificationService(message.bot, settings, i18n)
                    await notification_service.notify_new_user_registration(
                        user_id=user_id,
                        username=user.username,
                        first_name=user.first_name,
                        referred_by_id=referred_by_user_id
                    )
                except Exception as e:
                    logging.error(f"Failed to send new user notification: {e}")
        except Exception as e_create:

            logging.error(
                f"Failed to add new user {user_id} to session: {e_create}",
                exc_info=True)
            await message.answer(_("error_occurred_processing_request"))
            return
    else:
        update_payload = {}
        if db_user.language_code != current_lang:
            update_payload["language_code"] = current_lang
        # Set referral only if not already set AND user is not currently active.
        # This allows previously subscribed but currently inactive users to be attributed.
        if referred_by_user_id and db_user.referred_by_id is None:
            try:
                is_active_now = await subscription_service.has_active_subscription(session, user_id)
            except Exception:
                is_active_now = False
            if not is_active_now:
                update_payload["referred_by_id"] = referred_by_user_id
        if user.username != db_user.username:
            update_payload["username"] = user.username
        if user.first_name != db_user.first_name:
            update_payload["first_name"] = user.first_name
        if user.last_name != db_user.last_name:
            update_payload["last_name"] = user.last_name

        if update_payload:
            try:
                await user_dal.update_user(session, user_id, update_payload)

                logging.info(
                    f"Updated existing user {user_id} in session: {update_payload}"
                )
            except Exception as e_update:

                logging.error(
                    f"Failed to update existing user {user_id} in session: {e_update}",
                    exc_info=True)

    # Send welcome message if not disabled
    if not settings.DISABLE_WELCOME_MESSAGE:
        await message.answer(_(key="welcome", user_name=hd.quote(user.full_name)))
    
    # Auto-apply promo code if provided via start parameter
    if promo_code_to_apply:
        try:
            from bot.services.promo_code_service import PromoCodeService
            promo_code_service = PromoCodeService(settings, subscription_service, message.bot, i18n)
            
            success, result = await promo_code_service.apply_promo_code(
                session, user_id, promo_code_to_apply, current_lang
            )
            
            if success:
                await session.commit()
                logging.info(f"Auto-applied promo code '{promo_code_to_apply}' for user {user_id}")
                
                # Get updated subscription details
                active = await subscription_service.get_active_subscription_details(session, user_id)
                config_link = active.get("config_link") if active else None
                config_link = config_link or _("config_link_not_available")
                
                new_end_date = result if isinstance(result, datetime) else None
                
                promo_success_text = _(
                    "promo_code_applied_success_full",
                    end_date=(new_end_date.strftime("%d.%m.%Y %H:%M:%S") if new_end_date else "N/A"),
                    config_link=config_link,
                )
                
                from bot.keyboards.inline.user_keyboards import get_connect_and_main_keyboard
                await message.answer(
                    promo_success_text,
                    reply_markup=get_connect_and_main_keyboard(current_lang, i18n, settings, config_link),
                    parse_mode="HTML"
                )
                
                # Don't show main menu if promo was successfully applied
                return
            else:
                await session.rollback()
                logging.warning(f"Failed to auto-apply promo code '{promo_code_to_apply}' for user {user_id}: {result}")
                # Continue to show main menu if promo failed
                
        except Exception as e:
            logging.error(f"Error auto-applying promo code '{promo_code_to_apply}' for user {user_id}: {e}")
            await session.rollback()
    
    await send_main_menu(message,
                         settings,
                         i18n_data,
                         subscription_service,
                         session,
                         is_edit=False)


@router.message(Command("language"))
@router.callback_query(F.data == "main_action:language")
async def language_command_handler(
    event: Union[types.Message, types.CallbackQuery],
    i18n_data: dict,
    settings: Settings,
):
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs
                                           ) if i18n else key

    text_to_send = _(key="choose_language")
    reply_markup = get_language_selection_keyboard(i18n, current_lang)

    target_message_obj = event.message if isinstance(
        event, types.CallbackQuery) else event
    if not target_message_obj:
        if isinstance(event, types.CallbackQuery):
            await event.answer(_("error_occurred_try_again"), show_alert=True)
        return

    if isinstance(event, types.CallbackQuery):
        if event.message:
            try:
                await event.message.edit_text(text_to_send,
                                              reply_markup=reply_markup)
            except Exception:
                await target_message_obj.answer(text_to_send,
                                                reply_markup=reply_markup)
        await event.answer()
    else:
        await target_message_obj.answer(text_to_send,
                                        reply_markup=reply_markup)


@router.callback_query(F.data.startswith("set_lang_"))
async def select_language_callback_handler(
        callback: types.CallbackQuery, i18n_data: dict, settings: Settings,
        subscription_service: SubscriptionService, session: AsyncSession):
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    if not i18n or not callback.message:
        await callback.answer("Service error or message context lost.",
                              show_alert=True)
        return

    try:
        lang_code = callback.data.split("_")[2]
    except IndexError:
        await callback.answer("Error processing language selection.",
                              show_alert=True)
        return

    user_id = callback.from_user.id
    try:
        updated = await user_dal.update_user_language(session, user_id,
                                                      lang_code)
        if updated:

            i18n_data["current_language"] = lang_code
            _ = lambda key, **kwargs: i18n.gettext(lang_code, key, **kwargs)
            await callback.answer(_(key="language_set_alert"))
            logging.info(
                f"User {user_id} language updated to {lang_code} in session.")
        else:
            await callback.answer("Could not set language.", show_alert=True)
            return
    except Exception as e_lang_update:

        logging.error(
            f"Error updating lang for user {user_id}: {e_lang_update}",
            exc_info=True)
        await callback.answer("Error setting language.", show_alert=True)
        return
    await send_main_menu(callback,
                         settings,
                         i18n_data,
                         subscription_service,
                         session,
                         is_edit=True)


async def handle_personal_cabinet(
        callback: types.CallbackQuery,
        i18n_data: dict,
        settings: Settings,
        session: AsyncSession,
        subscription_service: SubscriptionService):
    """Handle personal cabinet button click - generate one-time auth link"""
    import aiohttp

    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs) if i18n else key

    user_id = callback.from_user.id

    try:
        # Get user's panel UUID from database
        db_user = await user_dal.get_user_by_id(session, user_id)

        if not db_user:
            await callback.answer("❌ User not found. Please try /start again.", show_alert=True)
            return

        # If user doesn't have panel_user_uuid, create panel user now
        if not db_user.panel_user_uuid:
            logging.info(f"User {user_id} has no panel_user_uuid. Creating panel user for personal cabinet access...")

            # Use subscription service to create/get panel user
            panel_uuid, panel_sub_link_id, panel_short_uuid, panel_user_created = (
                await subscription_service._get_or_create_panel_user_link_details(session, user_id, db_user)
            )

            if not panel_uuid:
                await callback.answer("❌ Failed to create panel user. Please try again later or contact support.", show_alert=True)
                return

            # Commit the panel_user_uuid update to database
            await session.commit()

            logging.info(f"✅ Panel user created for user {user_id}: UUID {panel_uuid}")
        else:
            panel_uuid = db_user.panel_user_uuid

        logging.info(f"Generating personal cabinet link for user {user_id}, panel_uuid: {panel_uuid}")

        # Ensure user exists in auth database by inserting if not exists
        try:
            from sqlalchemy import text
            auth_db_url = "postgresql://lider:nopass000@localhost:5432/liderdb"

            # Create user in auth database if not exists
            import asyncpg
            auth_conn = await asyncpg.connect(auth_db_url)
            try:
                await auth_conn.execute(
                    'INSERT INTO "User" (id, email, "createdAt", "updatedAt") VALUES ($1, NULL, NOW(), NOW()) ON CONFLICT (id) DO NOTHING',
                    panel_uuid
                )
            finally:
                await auth_conn.close()
        except Exception as e:
            logging.error(f"Failed to ensure user exists in auth database: {e}")

        # Call auth service to generate one-time link
        auth_url = "http://localhost:4000/auth/link"

        async with aiohttp.ClientSession() as http_session:
            async with http_session.post(auth_url, json={"userId": panel_uuid}) as response:
                if response.status == 200:
                    data = await response.json()
                    one_time_link = data.get("url")

                    if one_time_link:
                        # Send the link to user
                        if current_lang == "ru":
                            message_text = f"🏠 <b>Личный кабинет</b>\n\n🔗 Ваша персональная ссылка для входа:\n{one_time_link}\n\n⚠️ Ссылка одноразовая и действительна в течение 5 минут."
                        else:
                            message_text = f"🏠 <b>Personal Cabinet</b>\n\n🔗 Your personal login link:\n{one_time_link}\n\n⚠️ Link is one-time use and valid for 5 minutes."

                        from bot.keyboards.inline.user_keyboards import get_back_to_main_menu_markup

                        if callback.message:
                            try:
                                await callback.message.edit_text(
                                    message_text,
                                    reply_markup=get_back_to_main_menu_markup(current_lang, i18n),
                                    parse_mode="HTML"
                                )
                            except Exception:
                                await callback.message.answer(
                                    message_text,
                                    reply_markup=get_back_to_main_menu_markup(current_lang, i18n),
                                    parse_mode="HTML"
                                )
                        await callback.answer()
                    else:
                        await callback.answer("❌ Failed to generate link", show_alert=True)
                else:
                    error_text = await response.text()
                    logging.error(f"Auth service returned status {response.status}: {error_text}")
                    await callback.answer("❌ Service temporarily unavailable", show_alert=True)

    except Exception as e:
        logging.error(f"Error generating personal cabinet link for user {user_id}: {e}", exc_info=True)
        await callback.answer("❌ Error generating link. Please try again later.", show_alert=True)


@router.callback_query(F.data.startswith("main_action:"))
async def main_action_callback_handler(
        callback: types.CallbackQuery, state: FSMContext, settings: Settings,
        i18n_data: dict, bot: Bot, subscription_service: SubscriptionService,
        referral_service: ReferralService, panel_service: PanelApiService,
        promo_code_service: PromoCodeService, session: AsyncSession):
    action = callback.data.split(":")[1]
    user_id = callback.from_user.id

    from . import subscription as user_subscription_handlers
    from . import referral as user_referral_handlers
    from . import promo_user as user_promo_handlers
    from . import trial_handler as user_trial_handlers

    if not callback.message:
        await callback.answer("Error: message context lost.", show_alert=True)
        return

    if action == "subscribe":
        await user_subscription_handlers.display_subscription_options(
            callback, i18n_data, settings, session)
    elif action == "my_subscription":

        await user_subscription_handlers.my_subscription_command_handler(
            callback, i18n_data, settings, panel_service, subscription_service,
            session, bot)
    elif action == "referral":
        await user_referral_handlers.referral_command_handler(
            callback, settings, i18n_data, referral_service, bot, session)
    elif action == "apply_promo":
        await user_promo_handlers.prompt_promo_code_input(
            callback, state, i18n_data, settings, session)
    elif action == "request_trial":
        await user_trial_handlers.request_trial_confirmation_handler(
            callback, settings, i18n_data, subscription_service, session)
    elif action == "language":

        await language_command_handler(callback, i18n_data, settings)
    elif action == "personal_cabinet":
        await handle_personal_cabinet(callback, i18n_data, settings, session, subscription_service)
    elif action == "back_to_main":
        await send_main_menu(callback,
                             settings,
                             i18n_data,
                             subscription_service,
                             session,
                             is_edit=True)
    else:
        i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
        _ = lambda key, **kwargs: i18n.gettext(
            i18n_data.get("current_language"), key, **kw) if i18n else key
        await callback.answer(_("main_menu_unknown_action"), show_alert=True)
