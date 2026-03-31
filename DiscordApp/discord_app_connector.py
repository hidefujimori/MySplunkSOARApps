"""
Discord App - Splunk SOAR Connector

Uses the Discord REST API (Bot token) for connectivity checks and sending
channel messages. Credentials must be supplied via asset configuration only.
"""

import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import phantom.app as phantom
from phantom.app import ActionResult
from phantom.app import BaseConnector


DEFAULT_API_BASE = "https://discord.com/api/v10"


class DiscordAppConnector(BaseConnector):

    def __init__(self):
        super(DiscordAppConnector, self).__init__()
        self._bot_token = None
        self._api_base = None
        self._timeout = 30
        self._ssl_context = None

    def initialize(self):
        config = self.get_config()
        token = (config.get("bot_token") or "").strip()
        if not token:
            return self.set_status(phantom.APP_ERROR, "bot_token is required")

        self._bot_token = token
        base = (config.get("api_base_url") or DEFAULT_API_BASE).strip().rstrip("/")
        self._api_base = base or DEFAULT_API_BASE
        self._timeout = int(config.get("request_timeout", 30) or 30)

        verify = config.get("verify_ssl", True)
        if verify:
            self._ssl_context = ssl.create_default_context()
        else:
            self._ssl_context = ssl._create_unverified_context()

        return phantom.APP_SUCCESS

    def handle_action(self, param):
        action_id = self.get_action_identifier()
        self.debug_print("Action: {}".format(action_id))

        if action_id == "test_asset_connectivity":
            return self._handle_test_connectivity(param)
        if action_id == "send_message":
            return self._handle_send_message(param)

        return phantom.APP_SUCCESS

    def _auth_headers(self):
        return {
            "Authorization": "Bot {}".format(self._bot_token),
            "Content-Type": "application/json",
            "User-Agent": "SplunkSOAR-DiscordApp (https://splunk.com)",
        }

    def _request_json(self, method, path, body=None):
        url = "{}{}".format(self._api_base, path)
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, method=method, headers=self._auth_headers())
        with urlopen(req, timeout=self._timeout, context=self._ssl_context) as resp:
            raw = resp.read().decode("utf-8")
            if not raw:
                return {}
            return json.loads(raw)

    def _request_error_message(self, err):
        if isinstance(err, HTTPError):
            try:
                payload = err.read().decode("utf-8")
                parsed = json.loads(payload) if payload else {}
                msg = parsed.get("message") or parsed.get("code") or str(err)
                return "HTTP {}: {}".format(err.code, msg)
            except Exception:
                return "HTTP error: {}".format(err)
        if isinstance(err, URLError):
            return "URL error: {}".format(err.reason)
        return str(err)

    def _handle_test_connectivity(self, param):
        self.save_progress("Testing Discord API (GET /users/@me)...")
        try:
            me = self._request_json("GET", "/users/@me")
        except (HTTPError, URLError, ValueError) as e:
            self.save_progress("Discord API failed: {}".format(self._request_error_message(e)))
            return self.set_status(
                phantom.APP_ERROR,
                "Connectivity test failed: {}".format(self._request_error_message(e)),
            )

        username = me.get("username", "unknown")
        user_id = me.get("id", "unknown")
        self.save_progress("Authenticated as bot user {} (id {})".format(username, user_id))
        return self.set_status(phantom.APP_SUCCESS, "Connectivity test passed")

    def _handle_send_message(self, param):
        action_result = self.add_action_result(ActionResult(dict(param)))
        channel_id = (param.get("channel_id") or "").strip()
        content = param.get("content")
        if content is None:
            content = ""
        else:
            content = str(content).strip()

        if not channel_id:
            return action_result.set_status(phantom.APP_ERROR, "channel_id is required")
        if not content:
            return action_result.set_status(phantom.APP_ERROR, "content is required")
        if len(content) > 2000:
            return action_result.set_status(
                phantom.APP_ERROR,
                "content exceeds Discord limit of 2000 characters",
            )

        path = "/channels/{}/messages".format(channel_id)
        try:
            msg = self._request_json("POST", path, {"content": content})
        except (HTTPError, URLError, ValueError) as e:
            return action_result.set_status(
                phantom.APP_ERROR,
                "Failed to send message: {}".format(self._request_error_message(e)),
            )

        action_result.add_data({
            "message_id": str(msg.get("id", "")),
            "channel_id": str(msg.get("channel_id", channel_id)),
        })
        return action_result.set_status(phantom.APP_SUCCESS, "Message sent")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python discord_app_connector.py <action_json_file>")
        sys.exit(1)
    with open(sys.argv[1]) as f:
        in_json = f.read()
    connector = DiscordAppConnector()
    connector.print_progress_message = True
    ret_val = connector._handle_action(in_json, None)
    print(json.dumps(json.loads(ret_val), indent=4))
    sys.exit(0 if phantom.is_success(ret_val) else 1)
