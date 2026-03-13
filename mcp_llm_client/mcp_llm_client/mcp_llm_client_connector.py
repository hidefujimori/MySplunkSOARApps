"""
MCP LLM Client - Splunk SOAR Connector

Connects to an MCP Server (e.g. Splunk MCP Server) and routes
user prompts to a configurable LLM provider.

Supported LLM providers:
  - Anthropic Claude
  - OpenAI (including Azure OpenAI)
  - Google Gemini
"""

import phantom.app as phantom
from phantom.app import BaseConnector
from phantom.app import ActionResult

import json

from llm_providers import get_llm_provider, LLMProviderError
from mcp_client import MCPClient, MCPClientError


class MCPLLMClientConnector(BaseConnector):

    def __init__(self):
        super(MCPLLMClientConnector, self).__init__()
        self._mcp_client = None
        self._llm_provider = None

    def initialize(self):
        config = self.get_config()

        verify_ssl_mcp = config.get("verify_ssl_mcp", True)
        verify_ssl_llm = config.get("verify_ssl_llm", True)

        # -- MCP client --------------------------------------------------
        mcp_url = config.get("mcp_server_url", "").strip()
        if not mcp_url:
            return self.set_status(phantom.APP_ERROR, "mcp_server_url is required")

        self._mcp_client = MCPClient(
            server_url=mcp_url,
            token=config.get("mcp_server_token"),
            timeout=config.get("request_timeout", 30),
            verify_ssl=verify_ssl_mcp,
        )

        # -- LLM provider ------------------------------------------------
        provider_name = config.get("llm_provider", "anthropic").strip().lower()
        api_key = config.get("llm_api_key", "").strip()
        model = config.get("llm_model", "").strip()

        if not api_key:
            return self.set_status(phantom.APP_ERROR, "llm_api_key is required")
        if not model:
            return self.set_status(phantom.APP_ERROR, "llm_model is required")

        try:
            self._llm_provider = get_llm_provider(
                provider_name=provider_name,
                api_key=api_key,
                model=model,
                max_tokens=config.get("max_tokens", 1024),
                base_url=config.get("llm_api_base_url") or None,
                timeout=config.get("request_timeout", 60),
                verify_ssl=verify_ssl_llm,
            )
        except ValueError as e:
            return self.set_status(phantom.APP_ERROR, str(e))

        return phantom.APP_SUCCESS

    # ------------------------------------------------------------------
    # Action routing
    # ------------------------------------------------------------------

    def handle_action(self, param):
        action_id = self.get_action_identifier()
        self.debug_print("Action: {}".format(action_id))

        if action_id == "test_asset_connectivity":
            return self._handle_test_connectivity(param)
        elif action_id == "send_prompt":
            return self._handle_send_prompt(param)
        elif action_id == "list_mcp_tools":
            return self._handle_list_mcp_tools(param)

        return phantom.APP_SUCCESS

    # ------------------------------------------------------------------
    # test connectivity
    # ------------------------------------------------------------------

    def _handle_test_connectivity(self, param):
        config = self.get_config()
        verify_ssl_mcp = config.get("verify_ssl_mcp", True)
        verify_ssl_llm = config.get("verify_ssl_llm", True)

        self.save_progress("SSL verification - MCP: {}, LLM: {}".format(
            verify_ssl_mcp, verify_ssl_llm))
        self.save_progress("Testing connectivity to MCP Server...")

        try:
            init_result = self._mcp_client.initialize()
            protocol_version = init_result.get("protocolVersion", "unknown")
            self.save_progress("MCP Server initialized (protocol: {})".format(protocol_version))
        except MCPClientError as e:
            self.save_progress("MCP Server connection failed: {}".format(str(e)))
            return self.set_status(
                phantom.APP_ERROR,
                "Failed to connect to MCP Server: {}".format(str(e))
            )

        try:
            tools = self._mcp_client.list_tools()
            self.save_progress("MCP Server has {} available tool(s)".format(len(tools)))
        except MCPClientError as e:
            self.save_progress("Warning: Could not retrieve tool list: {}".format(str(e)))
            tools = []

        self.save_progress("LLM Provider: {} / Model: {}".format(
            self._llm_provider.__class__.__name__, self._llm_provider.model))
        self.save_progress("Connectivity test passed!")
        return self.set_status(phantom.APP_SUCCESS, "Connectivity test passed")

    # ------------------------------------------------------------------
    # send prompt
    # ------------------------------------------------------------------

    def _handle_send_prompt(self, param):
        action_result = self.add_action_result(ActionResult(dict(param)))

        user_prompt = param.get("prompt", "").strip()
        system_prompt = param.get("system_prompt", "").strip()
        use_mcp_tools = param.get("use_mcp_tools", True)

        if not user_prompt:
            return action_result.set_status(phantom.APP_ERROR, "prompt parameter is required")

        mcp_tools = []
        try:
            self._mcp_client.initialize()
            if use_mcp_tools:
                mcp_tools = self._mcp_client.list_tools()
        except MCPClientError as e:
            self.debug_print("MCP tools unavailable: {}".format(str(e)))

        # システムプロンプト（ベースのみ、ツール情報は含めない）
        effective_system = self._build_system_prompt(system_prompt, mcp_tools)

        # MCPツール情報はユーザーメッセージに付加
        # → systemInstructionに含めるとGeminiがUNEXPECTED_TOOL_CALLを起こすため
        effective_user_prompt = self._build_user_message_with_tools(user_prompt, mcp_tools)

        messages = [{"role": "user", "content": effective_user_prompt}]
        try:
            llm_resp = self._llm_provider.create_message(
                messages=messages,
                system_prompt=effective_system or None,
            )
        except LLMProviderError as e:
            return action_result.set_status(phantom.APP_ERROR, "LLM provider error: {}".format(str(e)))
        except Exception as e:
            return action_result.set_status(phantom.APP_ERROR, "Unexpected error: {}".format(str(e)))

        tool_names = [t.get("name", "") for t in mcp_tools]
        finish_reason = llm_resp.get("finish_reason", "unknown")
        action_result.add_data({
            "llm_response": llm_resp["content"],
            "finish_reason": finish_reason,
            "provider": self._llm_provider.__class__.__name__,
            "model": self._llm_provider.model,
            "mcp_tools_available": ", ".join(tool_names) if tool_names else "none",
        })
        action_result.update_summary({
            "llm_provider": self._llm_provider.__class__.__name__,
            "mcp_tools_count": len(mcp_tools),
            "finish_reason": finish_reason,
        })
        return action_result.set_status(phantom.APP_SUCCESS, "Prompt processed successfully")

    # ------------------------------------------------------------------
    # list mcp tools
    # ------------------------------------------------------------------

    def _handle_list_mcp_tools(self, param):
        action_result = self.add_action_result(ActionResult(dict(param)))
        try:
            self._mcp_client.initialize()
            tools = self._mcp_client.list_tools()
        except MCPClientError as e:
            return action_result.set_status(
                phantom.APP_ERROR, "Failed to retrieve MCP tools: {}".format(str(e)))

        for tool in tools:
            action_result.add_data({
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "input_schema": json.dumps(tool.get("inputSchema", {})),
            })

        action_result.update_summary({"tool_count": len(tools)})
        return action_result.set_status(
            phantom.APP_SUCCESS, "Retrieved {} tool(s) from MCP Server".format(len(tools)))

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _build_system_prompt(self, base_prompt, mcp_tools):
        """システムプロンプトはベースのみ返す。ツール情報はユーザーメッセージに付加する。"""
        return base_prompt.strip() if base_prompt else ""

    def _build_user_message_with_tools(self, user_prompt, mcp_tools):
        """
        MCPツール情報をユーザーメッセージの末尾に付加する。
        systemInstructionではなくユーザーメッセージに含めることで
        GeminiのUNEXPECTED_TOOL_CALLを回避する。
        """
        if not mcp_tools:
            return user_prompt
        tool_lines = ["- {}: {}".format(t.get("name", ""), t.get("description", "")) for t in mcp_tools]
        tools_section = (
            "\n\n---\n"
            "参考情報: 以下のMCPツールが利用可能です（情報として参照してください）:\n"
            + "\n".join(tool_lines)
        )
        return user_prompt + tools_section


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python mcp_llm_client_connector.py <action_json_file>")
        sys.exit(1)
    with open(sys.argv[1]) as f:
        in_json = f.read()
    connector = MCPLLMClientConnector()
    connector.print_progress_message = True
    ret_val = connector._handle_action(in_json, None)
    print(json.dumps(json.loads(ret_val), indent=4))
    sys.exit(0 if phantom.is_success(ret_val) else 1)
