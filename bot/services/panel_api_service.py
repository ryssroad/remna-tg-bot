import aiohttp
import logging
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
import asyncio
from urllib.parse import urlencode

from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import Settings
from db.dal import panel_sync_dal
from db.models import PanelSyncStatus


class PanelApiService:

    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.PANEL_API_URL
        self.api_key = settings.PANEL_API_KEY
        self._session: Optional[aiohttp.ClientSession] = None
        self.default_client_ip = "127.0.0.1"
    
    async def __aenter__(self):
        """Context manager entry"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - automatically close session"""
        await self.close_session()

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close_session(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            logging.debug("Panel API service HTTP session closed.")

    async def close(self):
        """Alias for close_session for API consistency."""
        await self.close_session()

    async def _prepare_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-For": self.default_client_ip,
            "X-Real-IP": self.default_client_ip,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def _request(self,
                       method: str,
                       endpoint: str,
                       log_full_response: bool = False,
                       **kwargs) -> Optional[Dict[str, Any]]:
        if not self.base_url:
            logging.error(
                "Panel API URL (PANEL_API_URL) not configured in settings.")
            return {
                "error": True,
                "status_code": 0,
                "message": "Panel API URL not configured."
            }

        aiohttp_session = await self._get_session()
        headers = await self._prepare_headers()

        url_for_request = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"

        current_params = kwargs.get("params")
        url_with_params_for_log = url_for_request
        if current_params:
            try:
                url_with_params_for_log += "?" + urlencode(current_params)
            except Exception:
                pass

        json_payload_for_log = kwargs.get('json') if method.upper() in [
            "POST", "PATCH", "PUT"
        ] else None
        log_prefix = f"Panel API Req: {method.upper()} {url_with_params_for_log}"
        if json_payload_for_log:
            try:
                payload_str = json.dumps(json_payload_for_log)
                log_prefix += f" | Payload: {payload_str[:300]}{'...' if len(payload_str) > 300 else ''}"
            except Exception:
                log_prefix += f" | Payload: {str(json_payload_for_log)[:300]}..."
        try:
            async with aiohttp_session.request(method.upper(),
                                               url_for_request,
                                               headers=headers,
                                               **kwargs) as response:
                response_status = response.status
                response_text = await response.text()

                log_suffix = f"| Status: {response_status}"

                if log_full_response or not (200 <= response_status < 300):
                    try:
                        parsed_json_for_log = json.loads(response_text)
                        pretty_response_text = json.dumps(parsed_json_for_log,
                                                          indent=2,
                                                          ensure_ascii=False)
                        logging.info(
                            f"{log_prefix} {log_suffix} | Full Response Body:\n{pretty_response_text}"
                        )
                    except json.JSONDecodeError:
                        logging.info(
                            f"{log_prefix} {log_suffix} | Full Response Text (not JSON):\n{response_text[:2000]}{'...' if len(response_text) > 2000 else ''}"
                        )
                else:
                    logging.debug(
                        f"{log_prefix} {log_suffix} | OK. Response Body Preview: {response_text[:200]}{'...' if len(response_text) > 200 else ''}"
                    )

                if 200 <= response_status < 300:
                    try:
                        if 'application/json' in response.headers.get(
                                'Content-Type', '').lower():
                            data = json.loads(response_text)
                            return data
                        else:
                            return {
                                "status": "success",
                                "code": response_status,
                                "data_text": response_text
                            }
                    except json.JSONDecodeError as e_json_ok:
                        logging.error(
                            f"{log_prefix} {log_suffix} | OK but JSON Parse Error. Error: {e_json_ok}. Body was logged above."
                        )
                        return {
                            "status": "success_parse_error",
                            "code": response_status,
                            "data_text": response_text,
                            "parse_error": str(e_json_ok)
                        }
                else:
                    error_details = {
                        "message":
                        f"Request failed with status {response_status}",
                        "raw_response_text": response_text
                    }
                    try:
                        if 'application/json' in response.headers.get(
                                'Content-Type', '').lower():
                            error_json_data = json.loads(response_text)
                            error_details.update(error_json_data)
                    except json.JSONDecodeError:
                        pass
                    return {
                        "error": True,
                        "status_code": response_status,
                        "details": error_details
                    }

        except aiohttp.ClientConnectorError as e:
            logging.error(
                f"Panel API ClientConnectorError to {url_for_request}: {e}")
            return {
                "error": True,
                "status_code": -1,
                "message": f"Connection error: {str(e)}"
            }
        except aiohttp.ClientError as e:
            logging.error(f"Panel API ClientError to {url_for_request}: {e}")
            return {
                "error": True,
                "status_code": -2,
                "message": f"Client error: {str(e)}"
            }
        except asyncio.TimeoutError:
            logging.error(f"Panel API request to {url_for_request} timed out.")
            return {
                "error": True,
                "status_code": -3,
                "message": "Request timed out"
            }
        except Exception as e:
            logging.error(
                f"Unexpected Panel API request error to {url_for_request}: {e}",
                exc_info=True)
            return {
                "error": True,
                "status_code": -4,
                "message": f"Unexpected error: {str(e)}"
            }

    async def get_all_panel_users(
            self,
            page_size: int = 100,
            log_responses: bool = False) -> Optional[List[Dict[str, Any]]]:
        all_users = []
        start_offset = 0
        while True:
            params = {"size": page_size, "start": start_offset}
            response_data = await self._request(
                "GET",
                "/users",
                params=params,
                log_full_response=log_responses)

            if not response_data or response_data.get("error"):
                logging.error(
                    f"Failed to fetch panel users batch (start: {start_offset}). Response: {response_data}"
                )
                return None
            users_batch = response_data.get("response", {}).get("users", [])
            if not users_batch: break
            all_users.extend(users_batch)
            if len(users_batch) < page_size: break
            start_offset += page_size
            await asyncio.sleep(0.1)
        logging.info(f"Fetched {len(all_users)} users from panel API.")
        return all_users

    async def get_user_by_uuid(
            self,
            user_uuid: str,
            log_response: bool = True) -> Optional[Dict[str, Any]]:
        endpoint = f"/users/{user_uuid}"
        full_response = await self._request("GET",
                                            endpoint,
                                            log_full_response=log_response)
        if full_response and not full_response.get(
                "error") and "response" in full_response:
            return full_response.get("response")

        return None

    async def get_user(
        self,
        *,
        uuid: Optional[str] = None,
        telegram_id: Optional[int] = None,
        username: Optional[str] = None,
        email: Optional[str] = None,
        log_response: bool = True,
    ) -> Optional[Dict[str, Any]]:
        if uuid:
            return await self.get_user_by_uuid(uuid, log_response=log_response)

        users = await self.get_users_by_filter(
            telegram_id=telegram_id,
            username=username,
            email=email,
            log_response=log_response,
        )
        if users:
            return users[0]
        return None

    async def get_users_by_filter(
            self,
            telegram_id: Optional[int] = None,
            username: Optional[str] = None,
            email: Optional[str] = None,
            log_response: bool = True) -> Optional[List[Dict[str, Any]]]:

        response_data = None
        filter_used_log = "No filter specified"

        if telegram_id is not None:
            filter_used_log = f"telegramId={telegram_id}"
            endpoint = f"/users/by-telegram-id/{telegram_id}"
            response_data = await self._request("GET",
                                                endpoint,
                                                log_full_response=log_response)

            if response_data and not response_data.get(
                    "error") and "response" in response_data and isinstance(
                        response_data["response"], list):
                return response_data["response"]
            elif response_data and response_data.get("errorCode") == "A062":
                logging.info(
                    f"Panel API: Users not found for {filter_used_log}")
                return []

        elif username is not None:
            filter_used_log = f"username={username}"
            endpoint = f"/users/by-username/{username}"
            response_data = await self._request("GET",
                                                endpoint,
                                                log_full_response=log_response)

            if response_data and not response_data.get(
                    "error") and "response" in response_data and isinstance(
                        response_data["response"], dict):
                return [response_data["response"]]
            elif response_data and response_data.get("errorCode") == "A062":
                logging.info(
                    f"Panel API: User not found for {filter_used_log}")
                return []

        elif email is not None:
            filter_used_log = f"email={email}"
            endpoint = f"/users/by-email/{email}"
            response_data = await self._request("GET",
                                                endpoint,
                                                log_full_response=log_response)

            if response_data and not response_data.get(
                    "error") and "response" in response_data and isinstance(
                        response_data["response"], list):
                return response_data["response"]
            elif response_data and response_data.get("errorCode") == "A062":
                logging.info(
                    f"Panel API: Users not found for {filter_used_log}")
                return []

        if not telegram_id and not username and not email:
            logging.warning(
                "get_users_by_filter called without any specific filter criteria."
            )
            return []

        logging.error(
            f"Failed to fetch panel users with filter ({filter_used_log}). Last API response: {response_data if not log_response else '(logged above)'}"
        )
        return None

    async def create_panel_user(
            self,
            username_on_panel: str,
            telegram_id: Optional[int] = None,
            email: Optional[str] = None,
            default_expire_days: int = 1,
            default_traffic_limit_bytes: int = 0,
            default_traffic_limit_strategy: str = "NO_RESET",
            specific_squad_uuids: Optional[List[str]] = None,
            description: Optional[str] = None,
            tag: Optional[str] = None,
            status: str = "ACTIVE",
            log_response: bool = True) -> Optional[Dict[str, Any]]:

        # Check basic length and character requirements first
        if not (6 <= len(username_on_panel) <= 34):
            msg = f"Panel username '{username_on_panel}' length must be between 6 and 34 characters."
            logging.error(msg)
            return {
                "error": True,
                "status_code": 400,
                "error_message": msg,
                "error_code": "INVALID_USERNAME_LENGTH"
            }

        # Check if username contains only valid characters (alphanumeric, underscore, hyphen)
        if not username_on_panel.replace('_', '').replace('-', '').isalnum():
            msg = f"Panel username '{username_on_panel}' contains invalid characters."
            logging.error(msg)
            return {
                "error": True,
                "status_code": 400,
                "error_message": msg,
                "error_code": "INVALID_USERNAME_CHARS"
            }

        # Allow both formats: tg_userId and userName_userId
        is_valid_tg_format = (username_on_panel.startswith("tg_")
                            and username_on_panel.split("tg_")[-1].isdigit())
        is_valid_username_format = ('_' in username_on_panel
                                  and username_on_panel.split('_')[-1].isdigit())

        if not (is_valid_tg_format or is_valid_username_format):
                msg = f"Panel username '{username_on_panel}' does not meet panel requirements."
                logging.error(msg)
                return {
                    "error": True,
                    "status_code": 400,
                    "message": msg,
                    "errorCode": "VALIDATION_ERROR_USERNAME"
                }

        now = datetime.now(timezone.utc)
        expire_at_dt = now + timedelta(days=default_expire_days)
        expire_at_iso = expire_at_dt.isoformat(
            timespec='milliseconds').replace('+00:00', 'Z')

        payload: Dict[str, Any] = {
            "username": username_on_panel,
            "status": status.upper(),
            "expireAt": expire_at_iso,
            "trafficLimitStrategy": default_traffic_limit_strategy.upper(),
            "trafficLimitBytes": default_traffic_limit_bytes,
        }
        if specific_squad_uuids:
            payload["activeInternalSquads"] = specific_squad_uuids
        if telegram_id is not None: payload["telegramId"] = telegram_id
        if email: payload["email"] = email
        if description: payload["description"] = description
        if tag: payload["tag"] = tag

        response = await self._request("POST",
                                       "/users",
                                       json=payload,
                                       log_full_response=log_response)
        if response and not response.get("error") and "response" in response:
            logging.info(
                f"Panel user '{username_on_panel}' created successfully (UUID: {response.get('response',{}).get('uuid')})."
            )
            return response

        logging.error(
            f"Failed to create panel user '{username_on_panel}'. Payload: {payload}, Response: {response if not log_response else '(full response logged above)'}"
        )
        return response

    async def update_user_details_on_panel(
            self,
            user_uuid: str,
            update_payload: Dict[str, Any],
            log_response: bool = True) -> Optional[Dict[str, Any]]:
        if 'uuid' not in update_payload:
            update_payload['uuid'] = user_uuid

        full_response = await self._request("PATCH",
                                            "/users",
                                            json=update_payload,
                                            log_full_response=log_response)
        if full_response and not full_response.get(
                "error") and "response" in full_response:
            logging.info(f"User {user_uuid} details updated on panel.")
            return full_response.get("response")

        logging.error(
            f"Failed to update user {user_uuid} details on panel. Payload: {update_payload}, Response: {full_response if not log_response else '(logged above)'}"
        )
        return None

    async def update_user_status_on_panel(self,
                                          user_uuid: str,
                                          enable: bool,
                                          log_response: bool = True) -> bool:
        action = "enable" if enable else "disable"
        endpoint = f"/users/{user_uuid}/actions/{action}"
        response_data = await self._request("POST",
                                            endpoint,
                                            log_full_response=log_response)

        if response_data and not response_data.get(
                "error") and "response" in response_data:
            actual_status = response_data.get("response", {}).get("status")
            expected_status = "ACTIVE" if enable else "DISABLED"
            if actual_status == expected_status:
                logging.info(
                    f"User {user_uuid} status on panel successfully set to {action} (Actual: {actual_status})."
                )
                return True
            else:
                logging.warning(
                    f"User {user_uuid} status on panel action '{action}' called, but final status is '{actual_status}'."
                )
                return False

        logging.error(
            f"Failed to {action} user {user_uuid} on panel. Response: {response_data if not log_response else '(logged above)'}"
        )
        return False

    async def get_subscription_link(
            self,
            short_uuid_or_sub_uuid: str,
            client_type: Optional[str] = None) -> Optional[str]:
        if not self.settings.PANEL_API_URL:
            logging.error(
                "PANEL_API_URL not set, cannot generate subscription link.")
            return None
        base_sub_url = f"{self.settings.PANEL_API_URL.rstrip('/')}/sub/{short_uuid_or_sub_uuid}"
        if client_type:
            return f"{base_sub_url}/{client_type.lower()}"
        return base_sub_url

    async def update_bot_db_sync_status(self,
                                        session: AsyncSession,
                                        status: str,
                                        details: str,
                                        users_processed: int = 0,
                                        subs_synced: int = 0):
        await panel_sync_dal.update_panel_sync_status(session, status, details,
                                                      users_processed,
                                                      subs_synced)

    async def get_bot_db_last_sync_status(
            self, session: AsyncSession) -> Optional[PanelSyncStatus]:
        return await panel_sync_dal.get_panel_sync_status(session)

    async def delete_user_by_uuid(self, user_uuid: str) -> bool:
        """Delete user from panel by UUID"""
        try:
            response_data = await self._request("DELETE", f"/users/{user_uuid}")
            if response_data and not response_data.get("error"):
                logging.info(f"User {user_uuid} deleted from panel successfully")
                return True
            else:
                logging.error(f"Failed to delete user {user_uuid} from panel: {response_data}")
                return False
        except Exception as e:
            logging.error(f"Error deleting user {user_uuid} from panel: {e}")
            return False


    async def get_system_stats(self) -> Optional[Dict[str, Any]]:
        """Get system statistics (CPU, memory, users counts)"""
        response_data = await self._request("GET", "/system/stats", log_full_response=False)
        if response_data and not response_data.get("error") and "response" in response_data:
            return response_data.get("response")
        return None
    
    async def get_bandwidth_stats(self) -> Optional[Dict[str, Any]]:
        """Get bandwidth statistics"""
        response_data = await self._request("GET", "/system/stats/bandwidth", log_full_response=False)
        if response_data and not response_data.get("error") and "response" in response_data:
            return response_data.get("response")
        return None
    
    async def get_nodes_statistics(self) -> Optional[Dict[str, Any]]:
        """Get nodes statistics"""
        response_data = await self._request("GET", "/system/stats/nodes", log_full_response=False)
        if response_data and not response_data.get("error") and "response" in response_data:
            return response_data.get("response")
        return None

    async def migrate_user_to_new_username_format(self, panel_uuid: str, old_username: str, new_username: str,
                                                   dry_run: bool = True) -> Dict[str, Any]:
        """
        Safely migrate a user from old format (tg_userId) to new format (userName_userId).

        Args:
            panel_uuid: Panel user UUID
            old_username: Current username (e.g., "tg_123456")
            new_username: New username (e.g., "john_doe_123456")
            dry_run: If True, only check if migration is possible without making changes

        Returns:
            Dict with migration status and details
        """
        result = {
            "success": False,
            "dry_run": dry_run,
            "old_username": old_username,
            "new_username": new_username,
            "panel_uuid": panel_uuid,
            "error": None,
            "checks": {
                "user_exists": False,
                "username_available": False,
                "format_valid": False,
                "safe_to_migrate": False
            }
        }

        try:
            # 1. Verify user exists by UUID
            user_data = await self.get_user_by_uuid(panel_uuid)
            if not user_data:
                result["error"] = f"User with UUID {panel_uuid} not found on panel"
                return result

            result["checks"]["user_exists"] = True
            current_panel_username = user_data.get("username", "")

            # 2. Verify current username matches expected old username
            if current_panel_username != old_username:
                result["error"] = f"Current username '{current_panel_username}' does not match expected '{old_username}'"
                return result

            # 3. Validate new username format
            if not new_username or len(new_username) < 6 or len(new_username) > 34:
                result["error"] = f"New username '{new_username}' does not meet length requirements (6-34 chars)"
                return result

            if not new_username.replace('_', '').replace('-', '').isalnum():
                result["error"] = f"New username '{new_username}' contains invalid characters"
                return result

            # Check if it ends with _userId format
            if '_' not in new_username or not new_username.split('_')[-1].isdigit():
                result["error"] = f"New username '{new_username}' does not follow userName_userId format"
                return result

            result["checks"]["format_valid"] = True

            # 4. Check if new username is available
            try:
                # Don't log responses for availability check to avoid 404 error logs
                existing_users = await self.get_users_by_filter(username=new_username, log_response=False)
                if existing_users and len(existing_users) > 0:
                    result["error"] = f"Username '{new_username}' is already taken"
                    return result
                # If existing_users is None or empty list, username is available
                result["checks"]["username_available"] = True
            except Exception as e:
                # If we get an error (like 404), it means username doesn't exist = available
                logging.info(f"Username '{new_username}' appears to be available (got expected 404)")
                result["checks"]["username_available"] = True

            # 5. Additional safety checks
            # Check if user has active subscriptions
            if user_data.get("is_active", False):
                logging.warning(f"User {panel_uuid} is currently active - migration may affect service")

            result["checks"]["safe_to_migrate"] = True

            # 6. Perform migration if not dry run
            if not dry_run:
                # Use existing update_user_details_on_panel method
                update_payload = {"username": new_username}

                response_data = await self.update_user_details_on_panel(
                    user_uuid=panel_uuid,
                    update_payload=update_payload,
                    log_response=True
                )

                if response_data:
                    result["success"] = True
                    result["migration_response"] = response_data
                    logging.info(f"Successfully migrated user {panel_uuid}: '{old_username}' -> '{new_username}'")
                else:
                    error_msg = response_data.get('error_message', 'Unknown error') if isinstance(response_data, dict) else 'Update failed'
                    result["error"] = f"Panel API error: {error_msg}"
                    logging.error(f"Failed to migrate user {panel_uuid}: {result['error']}")
            else:
                result["success"] = True  # Dry run successful
                logging.info(f"Dry run successful for user {panel_uuid}: '{old_username}' -> '{new_username}'")

        except Exception as e:
            result["error"] = f"Exception during migration: {str(e)}"
            logging.error(f"Exception during user migration {panel_uuid}: {e}", exc_info=True)

        return result