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

# Discord channel types (subset; see API docs for full list)
_CHANNEL_TYPE_LABELS = {
    0: "GUILD_TEXT",
    1: "DM",
    2: "GUILD_VOICE",
    3: "GROUP_DM",
    4: "GUILD_CATEGORY",
    5: "GUILD_ANNOUNCEMENT",
    10: "GUILD_NEWS_THREAD",
    11: "GUILD_PUBLIC_THREAD",
    12: "GUILD_PRIVATE_THREAD",
    13: "GUILD_STAGE_VOICE",
    15: "GUILD_FORUM",
    16: "GUILD_MEDIA",
}


def _channel_type_label(type_id):
    try:
        tid = int(type_id)
    except (TypeError, ValueError):
        return "UNKNOWN"
    return _CHANNEL_TYPE_LABELS.get(tid, "TYPE_{}".format(tid))


def _normalize_bot_token(raw):
    """
    Prepare token for Authorization: Bot <token>.

    Common SOAR / copy-paste issues:
    - Leading/trailing whitespace or newlines
    - Wrapping quotes
    - Pasting "Bot <token>" when the connector already adds the Bot prefix
    """
    if raw is None:
        return ""
    t = str(raw).strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in ('"', "'"):
        t = t[1:-1].strip()
    low = t.lower()
    if low.startswith("bot "):
        t = t[4:].lstrip()
    return t


class DiscordAppConnector(BaseConnector):

    def __init__(self):
        super(DiscordAppConnector, self).__init__()
        self._bot_token = None
        self._api_base = None
        self._timeout = 30
        self._ssl_context = None

    def initialize(self):
        config = self.get_config()
        token = _normalize_bot_token(config.get("bot_token"))
        if not token:
            return self.set_status(phantom.APP_ERROR, "bot_token is required")

        self._bot_token = token
        self.debug_print("Bot token length (chars): {}".format(len(token)))
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
        if action_id == "get_channel_id":
            return self._handle_get_channel_id(param)

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

    def _handle_get_channel_id(self, param):
        action_result = self.add_action_result(ActionResult(dict(param)))
        guild_id = (param.get("guild_id") or "").strip()
        if not guild_id:
            return action_result.set_status(phantom.APP_ERROR, "guild_id is required")

        name_filter = param.get("channel_name")
        if name_filter is None:
            name_filter = ""
        else:
            name_filter = str(name_filter).strip()
        filter_lower = name_filter.lower() if name_filter else None

        path = "/guilds/{}/channels".format(guild_id)
        try:
            channels = self._request_json("GET", path)
        except (HTTPError, URLError, ValueError) as e:
            return action_result.set_status(
                phantom.APP_ERROR,
                "Failed to list guild channels: {}".format(self._request_error_message(e)),
            )

        if not isinstance(channels, list):
            return action_result.set_status(
                phantom.APP_ERROR,
                "Unexpected API response when listing channels",
            )

        rows = []
        for ch in channels:
            cid = ch.get("id")
            cname = ch.get("name")
            if cid is None:
                continue
            name_str = cname if cname is not None else ""
            if filter_lower is not None:
                if name_str.lower() != filter_lower:
                    continue
            ctype = ch.get("type")
            parent = ch.get("parent_id")
            rows.append({
                "channel_id": str(cid),
                "channel_name": name_str,
                "channel_type": _channel_type_label(ctype),
                "parent_id": str(parent) if parent is not None else "",
            })

        rows.sort(key=lambda r: (r["channel_type"], r["channel_name"].lower(), r["channel_id"]))

        for r in rows:
            action_result.add_data(r)

        action_result.update_summary({
            "channel_count": len(rows),
            "guild_id": guild_id,
        })

        if filter_lower is not None:
            msg = "Found {} channel(s) matching name".format(len(rows))
        else:
            msg = "Retrieved {} channel(s)".format(len(rows))
        return action_result.set_status(phantom.APP_SUCCESS, msg)


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
