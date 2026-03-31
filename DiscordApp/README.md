# DiscordApp

Splunk SOAR app for Discord: validates a bot token against the Discord API and sends messages to channels.

## Setup

1. Create an application and bot in the [Discord Developer Portal](https://discord.com/developers/applications).
2. Under **Bot**, click **Reset Token** / **Copy** and paste **only the bot token** into the SOAR asset (`bot_token`). Do not use the **OAuth2 Client Secret** (that is not the bot token). Do not commit tokens to git.
3. In the asset, paste the token **without** a `Bot ` prefix; the app sends `Authorization: Bot <token>` automatically. If you previously pasted `Bot xxxxx`, that caused `Bot Bot xxxxx` and Discord returns **401 Unauthorized**.
4. Invite the bot to your server with the `applications.commands` scope and message permissions for target channels as needed.

### Connectivity test returns 401

- Confirm the value is the **Bot** token from the **Bot** tab, not **OAuth2 → Client Secret**.
- Re-copy the token after **Reset Token** if it may have been rotated or typo’d.
- Ensure the asset field has no extra spaces, line breaks, or surrounding quotes (the connector strips common cases, but a wrong secret will still 401).

## Actions

- **test connectivity** — `GET /users/@me` using the configured token.
- **send message** — `POST /channels/{channel_id}/messages` with the given text.
- **get channel id** — `GET /guilds/{guild_id}/channels`. Requires **guild_id** (server ID). Optional **channel_name** (case-insensitive exact match) and optional **channel_type** (e.g. `GUILD_TEXT`, `GUILD_VOICE`, `GUILD_CATEGORY`, or a numeric API type). Omit both filters to list all channels; use only **channel_type** to list every channel of that type. If there is no match, or **channel_type** is not a known label/number, the action still succeeds and returns **one data row** with `channel_id`, `channel_name`, `channel_type`, and `parent_id` set to **null** (`None`). Summary includes `matched` (`true` / `false`) and `channel_type_filter` when a type filter was applied.

Server and channel IDs: enable **Developer Mode** in the Discord client (Advanced settings), then right-click the server or channel and **Copy Server ID** / **Copy Channel ID**.

## Files

- `discord_app.json` — app metadata and action definitions.
- `discord_app_connector.py` — connector implementation (stdlib HTTP only).
