"""
MCP (Model Context Protocol) client utilities for SOAR App.

Handles JSON-RPC 2.0 communication with MCP servers.
"""

import json
import urllib3

try:
    import requests
except ImportError:
    pass


class MCPClientError(Exception):
    """Raised when an MCP server call fails."""
    pass


class MCPClient:
    """
    Lightweight synchronous MCP client using HTTP/JSON-RPC 2.0.

    Supports:
      - initialize / initialized handshake
      - tools/list
      - tools/call
    """

    MCP_ENDPOINT = "/mcp"

    def __init__(self, server_url, token=None, timeout=30, verify_ssl=True):
        """
        Args:
            server_url (str): Base URL of the MCP server (no trailing slash)
            token (str): Optional Bearer token for authentication
            timeout (int): HTTP request timeout in seconds
            verify_ssl (bool): Verify SSL certificate (set False for self-signed certs)
        """
        self.server_url = server_url.rstrip("/")
        self.token = token
        self.timeout = int(timeout)
        self.verify_ssl = verify_ssl
        self._request_id = 0

        # SSL検証を無効にした場合は警告を抑制
        if not self.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def _next_id(self):
        self._request_id += 1
        return self._request_id

    def _build_headers(self):
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer {}".format(self.token)
        return headers

    def _post(self, payload):
        """Send a JSON-RPC request and return the parsed response dict."""
        url = "{}{}".format(self.server_url, self.MCP_ENDPOINT)
        try:
            resp = requests.post(
                url,
                headers=self._build_headers(),
                json=payload,
                timeout=self.timeout,
                verify=self.verify_ssl,
            )
        except requests.exceptions.SSLError as e:
            raise MCPClientError(
                "SSL certificate verification failed: {}. "
                "Asset Config の 'Verify SSL for MCP Server' を False に設定してください。".format(str(e))
            )
        except requests.exceptions.ConnectionError as e:
            raise MCPClientError("Connection error to MCP server: {}".format(str(e)))
        except requests.exceptions.Timeout:
            raise MCPClientError("Request to MCP server timed out after {}s".format(self.timeout))
        except Exception as e:
            raise MCPClientError("HTTP error: {}".format(str(e)))

        if resp.status_code != 200:
            raise MCPClientError(
                "MCP server returned HTTP {}: {}".format(resp.status_code, resp.text[:500])
            )
        try:
            data = resp.json()
        except Exception:
            raise MCPClientError("Invalid JSON response from MCP server: {}".format(resp.text[:200]))

        if "error" in data:
            err = data["error"]
            raise MCPClientError(
                "JSON-RPC error {}: {}".format(err.get("code", "?"), err.get("message", str(err)))
            )
        return data

    def initialize(self):
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "splunk-soar-mcp-client", "version": "1.0.0"},
            },
        }
        result = self._post(payload)

        # initialized notification (no response expected)
        try:
            requests.post(
                "{}{}".format(self.server_url, self.MCP_ENDPOINT),
                headers=self._build_headers(),
                json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                timeout=self.timeout,
                verify=self.verify_ssl,
            )
        except Exception:
            pass

        return result.get("result", {})

    def list_tools(self):
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/list",
            "params": {},
        }
        result = self._post(payload)
        return result.get("result", {}).get("tools", [])

    def call_tool(self, tool_name, arguments=None):
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments or {}},
        }
        result = self._post(payload)
        return result.get("result", {})
