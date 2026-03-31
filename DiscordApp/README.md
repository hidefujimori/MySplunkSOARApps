# DiscordApp

Splunk SOAR app for Discord: validates a bot token against the Discord API and sends messages to channels.

## Setup

1. Create an application and bot in the [Discord Developer Portal](https://discord.com/developers/applications).
2. Copy the bot token into the SOAR asset (password field). Do not commit tokens to git.
3. Invite the bot to your server with the `applications.commands` scope and message permissions for target channels as needed.

## Actions

- **test connectivity** — `GET /users/@me` using the configured token.
- **send message** — `POST /channels/{channel_id}/messages` with the given text.

## Files

- `discord_app.json` — app metadata and action definitions.
- `discord_app_connector.py` — connector implementation (stdlib HTTP only).
