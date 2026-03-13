"""
LLM Provider abstraction layer for MCP LLM Client SOAR App.

Supports: Anthropic Claude, OpenAI, Google Gemini, Azure OpenAI
"""

import urllib3

try:
    import requests
except ImportError:
    pass


class LLMProviderError(Exception):
    """Raised when an LLM provider call fails."""
    pass


class BaseLLMProvider:
    """Abstract base class for all LLM providers."""

    def __init__(self, api_key, model, max_tokens=1024, base_url=None, timeout=60, verify_ssl=True):
        self.api_key = api_key
        self.model = model
        self.max_tokens = int(max_tokens)
        self.base_url = base_url
        self.timeout = int(timeout)
        self.verify_ssl = verify_ssl

        if not self.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def create_message(self, messages, system_prompt=None):
        raise NotImplementedError

    def _format_response(self, text, finish_reason=None):
        return {
            "role": "assistant",
            "content": text,
            "finish_reason": finish_reason or "unknown",
        }

    def _raise_for_response(self, resp):
        if resp.status_code != 200:
            raise LLMProviderError("HTTP {}: {}".format(resp.status_code, resp.text[:500]))


# ---------------------------------------------------------------------------
# Anthropic Claude
# ---------------------------------------------------------------------------
class AnthropicProvider(BaseLLMProvider):
    DEFAULT_BASE_URL = "https://api.anthropic.com/v1/messages"

    def create_message(self, messages, system_prompt=None):
        url = self.base_url or self.DEFAULT_BASE_URL
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {"model": self.model, "max_tokens": self.max_tokens, "messages": messages}
        if system_prompt:
            payload["system"] = system_prompt
        try:
            resp = requests.post(url, headers=headers, json=payload,
                                 timeout=self.timeout, verify=self.verify_ssl)
            self._raise_for_response(resp)
            data = resp.json()

            # レスポンス構造の安全な解析
            content_blocks = data.get("content", [])
            if not content_blocks:
                raise LLMProviderError(
                    "Anthropic returned empty content. Full response: {}".format(str(data))
                )
            text = content_blocks[0].get("text", "")
            finish_reason = data.get("stop_reason", "unknown")
            return self._format_response(text, finish_reason)

        except LLMProviderError:
            raise
        except requests.exceptions.SSLError as e:
            raise LLMProviderError(
                "SSL error calling Anthropic API: {}. "
                "Asset Config の 'Verify SSL for LLM API' を False に設定してください。".format(str(e))
            )
        except Exception as e:
            raise LLMProviderError("Anthropic API error: {}".format(str(e)))


# ---------------------------------------------------------------------------
# OpenAI / Azure OpenAI
# ---------------------------------------------------------------------------
class OpenAIProvider(BaseLLMProvider):
    DEFAULT_BASE_URL = "https://api.openai.com/v1/chat/completions"

    def create_message(self, messages, system_prompt=None):
        url = self.base_url or self.DEFAULT_BASE_URL
        headers = {
            "Authorization": "Bearer {}".format(self.api_key),
            "Content-Type": "application/json",
        }
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)
        payload = {"model": self.model, "max_tokens": self.max_tokens, "messages": full_messages}
        try:
            resp = requests.post(url, headers=headers, json=payload,
                                 timeout=self.timeout, verify=self.verify_ssl)
            self._raise_for_response(resp)
            data = resp.json()

            # レスポンス構造の安全な解析
            choices = data.get("choices", [])
            if not choices:
                raise LLMProviderError(
                    "OpenAI returned empty choices. Full response: {}".format(str(data))
                )
            text = choices[0].get("message", {}).get("content", "")
            finish_reason = choices[0].get("finish_reason", "unknown")
            return self._format_response(text, finish_reason)

        except LLMProviderError:
            raise
        except requests.exceptions.SSLError as e:
            raise LLMProviderError("SSL error calling OpenAI API: {}".format(str(e)))
        except Exception as e:
            raise LLMProviderError("OpenAI API error: {}".format(str(e)))


# ---------------------------------------------------------------------------
# Google Gemini
# ---------------------------------------------------------------------------
class GeminiProvider(BaseLLMProvider):
    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def create_message(self, messages, system_prompt=None):
        base = self.base_url or self.DEFAULT_BASE_URL
        url = "{}/{}:generateContent?key={}".format(base, self.model, self.api_key)
        contents = [
            {
                "role": "user" if m["role"] == "user" else "model",
                "parts": [{"text": m["content"]}],
            }
            for m in messages
        ]
        payload = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": self.max_tokens},
        }
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        try:
            resp = requests.post(url, json=payload, timeout=self.timeout, verify=self.verify_ssl)
            self._raise_for_response(resp)
            data = resp.json()

            # --- 安全なレスポンス解析 ---
            candidates = data.get("candidates", [])

            # candidatesが空 → Safety filterブロックの可能性
            if not candidates:
                prompt_feedback = data.get("promptFeedback", {})
                block_reason = prompt_feedback.get("blockReason", "unknown")
                raise LLMProviderError(
                    "Gemini returned no candidates. "
                    "Possible safety filter block. blockReason: {}. "
                    "Full response: {}".format(block_reason, str(data))
                )

            candidate = candidates[0]
            finish_reason = candidate.get("finishReason", "unknown")

            # content キーが存在しない場合
            if "content" not in candidate:
                raise LLMProviderError(
                    "Gemini candidate has no 'content' key. "
                    "finishReason: {}. Full candidate: {}".format(finish_reason, str(candidate))
                )

            parts = candidate["content"].get("parts", [])
            if not parts:
                raise LLMProviderError(
                    "Gemini content has no 'parts'. "
                    "finishReason: {}. Full candidate: {}".format(finish_reason, str(candidate))
                )

            text = parts[0].get("text", "")

            # MAX_TOKENS で途中終了の警告
            if finish_reason == "MAX_TOKENS":
                text += "\n\n[WARNING: Response was truncated due to max_tokens limit. " \
                        "Asset Config の max_tokens を増やしてください。]"

            return self._format_response(text, finish_reason)

        except LLMProviderError:
            raise
        except requests.exceptions.SSLError as e:
            raise LLMProviderError(
                "SSL error calling Gemini API: {}. "
                "Asset Config の 'Verify SSL for LLM API' を False に設定してください。".format(str(e))
            )
        except Exception as e:
            raise LLMProviderError("Gemini API error: {}".format(str(e)))


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
PROVIDER_MAP = {
    "anthropic":    AnthropicProvider,
    "openai":       OpenAIProvider,
    "azure_openai": OpenAIProvider,
    "gemini":       GeminiProvider,
}


def get_llm_provider(provider_name, api_key, model,
                     max_tokens=1024, base_url=None, timeout=60, verify_ssl=True):
    cls = PROVIDER_MAP.get(provider_name)
    if cls is None:
        raise ValueError(
            "Unsupported LLM provider '{}'. Supported: {}".format(
                provider_name, ", ".join(PROVIDER_MAP.keys())
            )
        )
    return cls(
        api_key=api_key,
        model=model,
        max_tokens=max_tokens,
        base_url=base_url,
        timeout=timeout,
        verify_ssl=verify_ssl,
    )
