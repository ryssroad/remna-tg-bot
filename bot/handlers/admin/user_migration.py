import logging
import asyncio
from aiogram import Router, types, F
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.i18n import JsonI18n
from bot.services.user_migration_service import UserMigrationService
from bot.services.panel_api_service import PanelApiService
from config.settings import Settings

router = Router(name="admin_user_migration_router")


@router.message(Command("migrate_usernames"))
async def migrate_usernames_command(message: types.Message,
                                  session: AsyncSession,
                                  panel_service: PanelApiService,
                                  settings: Settings,
                                  i18n_data: dict):
    """Admin command to migrate users from tg_userId to userName_userId format"""

    i18n: JsonI18n = i18n_data.get("i18n_instance")
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)

    # Check if command has dry-run parameter
    command_args = message.text.split()[1:] if len(message.text.split()) > 1 else []
    dry_run = "dry-run" in command_args or "--dry-run" in command_args

    await message.reply(
        f"🔄 <b>{'[DRY RUN] ' if dry_run else ''}Username Migration Started</b>\n\n"
        f"{'⚠️ This is a dry run - no changes will be made.' if dry_run else '⚠️ This will modify usernames in the panel.'}\n"
        f"Please wait...",
        parse_mode="HTML"
    )

    try:
        migration_service = UserMigrationService(panel_service)

        # Step 1: Find candidates
        await message.reply("🔍 <b>Step 1:</b> Finding migration candidates...", parse_mode="HTML")
        candidates = await migration_service.find_candidates_for_migration(session, limit=50)

        if not candidates:
            await message.reply("✅ No users found that need migration.")
            return

        await message.reply(
            f"📊 Found <b>{len(candidates)}</b> candidates for migration:\n\n" +
            "\n".join([
                f"• @{candidate['telegram_username']} (ID: {candidate['user_id']})\n"
                f"  <code>{candidate['old_username']}</code> → <code>{candidate['new_username']}</code>"
                for candidate in candidates[:5]
            ]) +
            (f"\n... and {len(candidates) - 5} more" if len(candidates) > 5 else ""),
            parse_mode="HTML"
        )

        # Step 2: Check feasibility
        await message.reply("🔍 <b>Step 2:</b> Checking migration feasibility...", parse_mode="HTML")
        feasibility = await migration_service.check_migration_feasibility(candidates)

        summary = feasibility['summary']
        await message.reply(
            f"📋 <b>Migration Feasibility Check Results:</b>\n\n"
            f"✅ Safe to migrate: <b>{summary['safe_count']}</b>\n"
            f"❌ Unsafe/conflicts: <b>{summary['unsafe_count']}</b>\n"
            f"⚠️ Errors: <b>{summary['error_count']}</b>\n\n"
            f"{'🧪 Ready for dry run migration' if dry_run else '🚀 Ready for actual migration'}",
            parse_mode="HTML"
        )

        if summary['safe_count'] == 0:
            await message.reply("❌ No users are safe to migrate at this time.")
            return

        # Show some unsafe examples if any
        if feasibility['unsafe_to_migrate']:
            unsafe_examples = feasibility['unsafe_to_migrate'][:3]
            unsafe_text = "⚠️ <b>Some users cannot be migrated:</b>\n\n"
            for user in unsafe_examples:
                error = user.get('migration_check', {}).get('error', 'Unknown error')
                unsafe_text += f"• @{user['telegram_username']}: {error}\n"
            if len(feasibility['unsafe_to_migrate']) > 3:
                unsafe_text += f"... and {len(feasibility['unsafe_to_migrate']) - 3} more"
            await message.reply(unsafe_text, parse_mode="HTML")

        # Step 3: Perform migration (or dry run)
        safe_candidates = feasibility['safe_to_migrate']
        if not safe_candidates:
            await message.reply("❌ No safe candidates found for migration.")
            return

        await message.reply(
            f"🚀 <b>Step 3:</b> {'Performing dry run' if dry_run else 'Performing migration'} "
            f"for <b>{len(safe_candidates)}</b> users...",
            parse_mode="HTML"
        )

        if not dry_run:
            # Actual migration
            migration_results = await migration_service.migrate_users_batch(
                safe_candidates,
                max_concurrent=2,  # Conservative for safety
                delay_between_batches=2.0
            )

            results_summary = migration_results['summary']
            await message.reply(
                f"🎉 <b>Migration Complete!</b>\n\n"
                f"✅ Successful: <b>{results_summary['success_count']}</b>\n"
                f"❌ Failed: <b>{results_summary['failure_count']}</b>\n\n"
                f"{'🎯 All migrations successful!' if results_summary['failure_count'] == 0 else '⚠️ Some migrations failed - check logs.'}",
                parse_mode="HTML"
            )

            # Show successful migrations
            if migration_results['successful']:
                success_text = "✅ <b>Successfully migrated:</b>\n\n"
                for user in migration_results['successful'][:5]:
                    success_text += f"• @{user['telegram_username']}: <code>{user['old_username']}</code> → <code>{user['new_username']}</code>\n"
                if len(migration_results['successful']) > 5:
                    success_text += f"... and {len(migration_results['successful']) - 5} more"
                await message.reply(success_text, parse_mode="HTML")

            # Show failed migrations
            if migration_results['failed']:
                failed_text = "❌ <b>Failed migrations:</b>\n\n"
                for user in migration_results['failed'][:3]:
                    error = user.get('migration_result', {}).get('error', user.get('error', 'Unknown error'))
                    failed_text += f"• @{user['telegram_username']}: {error}\n"
                if len(migration_results['failed']) > 3:
                    failed_text += f"... and {len(migration_results['failed']) - 3} more"
                await message.reply(failed_text, parse_mode="HTML")
        else:
            # Dry run complete
            await message.reply(
                f"🧪 <b>Dry Run Complete!</b>\n\n"
                f"✅ <b>{len(safe_candidates)}</b> users are ready for migration.\n\n"
                f"To perform actual migration, run:\n"
                f"<code>/migrate_usernames</code> (without dry-run flag)",
                parse_mode="HTML"
            )

    except Exception as e:
        logging.error(f"Error in username migration: {e}", exc_info=True)
        await message.reply(
            f"❌ <b>Migration Error:</b>\n\n"
            f"<code>{str(e)}</code>\n\n"
            f"Check logs for details.",
            parse_mode="HTML"
        )


@router.message(Command("migration_status"))
async def migration_status_command(message: types.Message,
                                 session: AsyncSession,
                                 panel_service: PanelApiService,
                                 settings: Settings):
    """Check migration status and show statistics"""

    try:
        migration_service = UserMigrationService(panel_service)

        await message.reply("🔍 Checking migration status...", parse_mode="HTML")

        # Find candidates
        candidates = await migration_service.find_candidates_for_migration(session, limit=100)

        # Count different types
        tg_format_count = 0
        new_format_count = 0

        for candidate in candidates:
            if candidate['old_username'].startswith('tg_'):
                tg_format_count += 1
            else:
                new_format_count += 1

        total_candidates = len(candidates)

        await message.reply(
            f"📊 <b>Username Migration Status</b>\n\n"
            f"🔄 Candidates for migration: <b>{total_candidates}</b>\n"
            f"📛 Still using tg_format: <b>{tg_format_count}</b>\n"
            f"✅ Already new format: <b>{new_format_count}</b>\n\n"
            f"{'🎯 No migration needed!' if total_candidates == 0 else '⚠️ Migration available'}\n\n"
            f"Use <code>/migrate_usernames dry-run</code> to test migration\n"
            f"Use <code>/migrate_usernames</code> to perform migration",
            parse_mode="HTML"
        )

    except Exception as e:
        logging.error(f"Error checking migration status: {e}", exc_info=True)
        await message.reply(f"❌ Error checking status: {str(e)}")


