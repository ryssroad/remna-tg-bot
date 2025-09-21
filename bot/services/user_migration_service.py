import logging
import asyncio
from typing import Dict, List, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from db.dal import user_dal
from bot.services.panel_api_service import PanelApiService


class UserMigrationService:
    """Service for migrating users from tg_userId to userName_userId format"""

    def __init__(self, panel_service: PanelApiService):
        self.panel_service = panel_service

    def _generate_new_username(self, user_data: Dict[str, Any], user_id: int) -> str:
        """Generate new username in userName_userId format"""
        username = user_data.get('username')

        if username:
            # Clean username: remove @ symbol, keep only alphanumeric and underscores
            clean_username = username.lstrip('@').replace('-', '_')
            clean_username = ''.join(c for c in clean_username if c.isalnum() or c == '_')

            # Limit length to avoid exceeding panel requirements (max 34 chars total)
            max_username_length = 30 - len(str(user_id))  # Reserve space for _userId
            if max_username_length > 0 and clean_username:
                clean_username = clean_username[:max_username_length]
                return f"{clean_username}_{user_id}"

        # Fallback to old format if no username
        return f"tg_{user_id}"

    async def find_candidates_for_migration(self, session: AsyncSession,
                                          limit: int = 100) -> List[Dict[str, Any]]:
        """
        Find users who are candidates for migration from tg_userId to userName_userId format.

        Returns list of user data with migration information.
        """
        candidates = []

        try:
            # Get users who have panel_user_uuid and username
            users = await user_dal.get_users_with_panel_uuid_and_username(session, limit=limit)

            for user in users:
                if not user.panel_user_uuid or not user.username:
                    continue

                # Generate what the new username should be
                user_dict = {
                    'username': user.username,
                    'first_name': user.first_name,
                    'last_name': user.last_name
                }
                new_username = self._generate_new_username(user_dict, user.user_id)
                old_username = f"tg_{user.user_id}"

                # Only include if the new username would be different and follows new format
                if (new_username != old_username and
                    not new_username.startswith('tg_') and
                    '_' in new_username and
                    new_username.split('_')[-1].isdigit()):

                    candidates.append({
                        'user_id': user.user_id,
                        'panel_uuid': user.panel_user_uuid,
                        'telegram_username': user.username,
                        'first_name': user.first_name,
                        'last_name': user.last_name,
                        'old_username': old_username,
                        'new_username': new_username,
                        'language_code': user.language_code
                    })

            logging.info(f"Found {len(candidates)} candidates for username migration")
            return candidates

        except Exception as e:
            logging.error(f"Error finding migration candidates: {e}", exc_info=True)
            return []

    async def check_migration_feasibility(self, candidates: List[Dict[str, Any]],
                                        max_concurrent: int = 5) -> Dict[str, Any]:
        """
        Check which users can be safely migrated (dry run for all candidates).

        Args:
            candidates: List of user migration candidates
            max_concurrent: Maximum concurrent API calls

        Returns:
            Dict with migration feasibility results
        """
        results = {
            'total_candidates': len(candidates),
            'safe_to_migrate': [],
            'unsafe_to_migrate': [],
            'errors': [],
            'summary': {
                'safe_count': 0,
                'unsafe_count': 0,
                'error_count': 0
            }
        }

        semaphore = asyncio.Semaphore(max_concurrent)

        async def check_single_user(candidate: Dict[str, Any]) -> Dict[str, Any]:
            async with semaphore:
                try:
                    result = await self.panel_service.migrate_user_to_new_username_format(
                        panel_uuid=candidate['panel_uuid'],
                        old_username=candidate['old_username'],
                        new_username=candidate['new_username'],
                        dry_run=True
                    )

                    candidate_result = {**candidate, 'migration_check': result}

                    if result['success'] and result['checks']['safe_to_migrate']:
                        results['safe_to_migrate'].append(candidate_result)
                        results['summary']['safe_count'] += 1
                    else:
                        results['unsafe_to_migrate'].append(candidate_result)
                        results['summary']['unsafe_count'] += 1

                    return candidate_result

                except Exception as e:
                    error_result = {**candidate, 'error': str(e)}
                    results['errors'].append(error_result)
                    results['summary']['error_count'] += 1
                    logging.error(f"Error checking user {candidate['user_id']}: {e}")
                    return error_result

        # Process all candidates concurrently
        await asyncio.gather(*[check_single_user(candidate) for candidate in candidates])

        logging.info(f"Migration feasibility check complete: {results['summary']}")
        return results

    async def migrate_users_batch(self, safe_candidates: List[Dict[str, Any]],
                                 max_concurrent: int = 3,
                                 delay_between_batches: float = 1.0) -> Dict[str, Any]:
        """
        Perform actual migration for a batch of users.

        Args:
            safe_candidates: List of users that passed safety checks
            max_concurrent: Maximum concurrent migrations
            delay_between_batches: Delay between batches in seconds

        Returns:
            Dict with migration results
        """
        results = {
            'total_migrations': len(safe_candidates),
            'successful': [],
            'failed': [],
            'summary': {
                'success_count': 0,
                'failure_count': 0
            }
        }

        semaphore = asyncio.Semaphore(max_concurrent)

        async def migrate_single_user(candidate: Dict[str, Any]) -> Dict[str, Any]:
            async with semaphore:
                try:
                    logging.info(f"Migrating user {candidate['user_id']}: "
                               f"'{candidate['old_username']}' -> '{candidate['new_username']}'")

                    result = await self.panel_service.migrate_user_to_new_username_format(
                        panel_uuid=candidate['panel_uuid'],
                        old_username=candidate['old_username'],
                        new_username=candidate['new_username'],
                        dry_run=False
                    )

                    candidate_result = {**candidate, 'migration_result': result}

                    if result['success']:
                        results['successful'].append(candidate_result)
                        results['summary']['success_count'] += 1
                        logging.info(f"✓ Successfully migrated user {candidate['user_id']}")
                    else:
                        results['failed'].append(candidate_result)
                        results['summary']['failure_count'] += 1
                        logging.error(f"✗ Failed to migrate user {candidate['user_id']}: {result.get('error', 'Unknown error')}")

                    # Small delay between migrations
                    await asyncio.sleep(delay_between_batches)
                    return candidate_result

                except Exception as e:
                    error_result = {**candidate, 'error': str(e)}
                    results['failed'].append(error_result)
                    results['summary']['failure_count'] += 1
                    logging.error(f"✗ Exception migrating user {candidate['user_id']}: {e}")
                    return error_result

        # Process migrations
        await asyncio.gather(*[migrate_single_user(candidate) for candidate in safe_candidates])

        logging.info(f"Batch migration complete: {results['summary']}")
        return results