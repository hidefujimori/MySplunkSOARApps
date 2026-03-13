# MCP LLM Client - Splunk SOAR App (PoC)

A Splunk SOAR App that connects to an MCP Server (e.g. Splunk MCP Server) and routes user prompts to a configurable LLM provider.

## File Structure

```
mcp_llm_client/
├── __init__.py
├── mcp_llm_client.json          # App metadata (app JSON)
├── mcp_llm_client_connector.py  # Main Connector module
├── mcp_client.py                # MCP client (JSON-RPC 2.0)
├── llm_providers.py             # LLM provider abstraction layer
├── mcp_llm_client.svg           # Logo (light)
└── mcp_llm_client_dark.svg      # Logo (dark)
```

## Installation

```bash
# Create TAR.GZ archive
tar -zcvf mcp_llm_client.tgz mcp_llm_client/
```

Import the generated `.tgz` file from the **Apps** page in Splunk SOAR.

## Asset Configuration

| Parameter | Required | Description |
|---|---|---|
| mcp_server_url | ✅ | MCP Server URL (e.g. https://splunk-mcp:8000) |
| mcp_server_token | - | Bearer token for MCP Server authentication (if required) |
| llm_provider | ✅ | anthropic / openai / gemini / azure_openai |
| llm_api_key | ✅ | API key for the selected LLM provider |
| llm_model | ✅ | Model name (e.g. claude-sonnet-4-20250514) |
| llm_api_base_url | - | Custom base URL (required for Azure OpenAI) |
| max_tokens | - | Maximum tokens in LLM response (default: 1024) |
| request_timeout | - | HTTP timeout in seconds (default: 60) |
| verify_ssl_mcp | - | Verify SSL certificate for MCP Server (default: true) |
| verify_ssl_llm | - | Verify SSL certificate for LLM API (default: true) |

> **Note for PoC environments:** If your MCP Server uses a self-signed certificate, set `verify_ssl_mcp` to `false`.

## LLM Provider Examples

| Provider | llm_model example | llm_api_base_url |
|---|---|---|
| anthropic | claude-sonnet-4-20250514 | Not required |
| openai | gpt-4o | Not required |
| azure_openai | gpt-4o | https://\<your\>.openai.azure.com/openai/deployments/\<deploy\>/chat/completions?api-version=2024-02-15-preview |
| gemini | gemini-2.0-flash | Not required |

## Available Actions

### test connectivity
Tests the asset configuration. Verifies the MCP Server handshake and retrieves the list of available tools.

### send prompt
Sends a prompt to the LLM via the MCP Server and returns the response.

**Parameters:**
- `prompt` (required): User prompt text
- `system_prompt` (optional): System prompt to guide LLM behavior
- `use_mcp_tools` (optional): Include available MCP tool context in the prompt (default: true)

**Output fields:**
- `llm_response`: The LLM's response text
- `finish_reason`: Reason the LLM stopped generating (`STOP`, `MAX_TOKENS`, `SAFETY`, etc.)
- `provider`: LLM provider class name
- `model`: Model identifier used
- `mcp_tools_available`: Comma-separated list of MCP tools included in context

> **Tip:** If `finish_reason` is `MAX_TOKENS`, increase `max_tokens` in the Asset Config.

### list mcp tools
Retrieves the list of available tools from the MCP Server.

## Architecture

```
SOAR Playbook
    ↓ (prompt input)
MCPLLMClientConnector
    ├─ MCPClient ──→ MCP Server (initialize, tools/list)
    └─ LLMProvider → LLM API (Anthropic / OpenAI / Gemini / Azure OpenAI)
```

## Notes

- MCP tool information is appended to the **user message** (not the system prompt) to avoid `UNEXPECTED_TOOL_CALL` errors with Gemini models.
- SSL verification can be independently controlled for the MCP Server and LLM API.
- This app is intended as a Proof of Concept. For production use, review security settings and error handling.
