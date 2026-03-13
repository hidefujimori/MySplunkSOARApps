# MCP LLM Client - Splunk SOAR App (PoC)

MCPサーバー（例: Splunk MCP Server）に接続し、ユーザーのプロンプトを
設定可能なLLMプロバイダーにルーティングするSplunk SOAR Appです。

## ファイル構成

```
mcp_llm_client/
├── __init__.py
├── mcp_llm_client.json          # Appメタデータ (app JSON)
├── mcp_llm_client_connector.py  # メインConnectorモジュール
├── mcp_client.py                # MCPクライアント (JSON-RPC 2.0)
├── llm_providers.py             # LLMプロバイダー抽象化レイヤー
├── mcp_llm_client.svg           # ロゴ (ライト)
└── mcp_llm_client_dark.svg      # ロゴ (ダーク)
```

## インストール方法

```bash
# TAR.GZアーカイブを作成
tar -zcvf mcp_llm_client.tgz mcp_llm_client/
```

作成した `.tgz` ファイルをSOARの「Apps」ページからインポートします。

## Asset Configuration

| パラメータ | 必須 | 説明 |
|---|---|---|
| mcp_server_url | ✅ | MCPサーバーのURL (例: https://splunk-mcp:8000) |
| mcp_server_token | - | Bearer認証トークン（必要な場合） |
| llm_provider | ✅ | anthropic / openai / gemini / azure_openai |
| llm_api_key | ✅ | 選択したプロバイダーのAPIキー |
| llm_model | ✅ | モデル名 (例: claude-sonnet-4-20250514) |
| llm_api_base_url | - | Azure OpenAI使用時のベースURL |
| max_tokens | - | 最大トークン数 (デフォルト: 1024) |
| request_timeout | - | HTTPタイムアウト秒 (デフォルト: 60) |

## LLMプロバイダー別設定例

| Provider | llm_model の例 | llm_api_base_url |
|---|---|---|
| anthropic | claude-sonnet-4-20250514 | 不要 |
| openai | gpt-4o | 不要 |
| azure_openai | gpt-4o | https://<your>.openai.azure.com/openai/deployments/<deploy>/chat/completions?api-version=2024-02-15-preview |
| gemini | gemini-1.5-pro | 不要 |

## 利用可能なActions

### test connectivity
Asset Configの接続テスト。MCPサーバーへのハンドシェイクと
ツール一覧の取得を確認します。

### send prompt
プロンプトをLLM経由で送信し応答を取得します。

**パラメータ:**
- `prompt` (必須): ユーザープロンプト
- `system_prompt` (任意): システムプロンプト
- `use_mcp_tools` (任意): MCPツール情報をプロンプトに含める (デフォルト: true)

### list mcp tools
MCPサーバーから利用可能なツール一覧を取得します。

## アーキテクチャ

```
SOAR Playbook
    ↓ (prompt入力)
MCPLLMClientConnector
    ├─ MCPClient ──→ MCP Server (tools/list, initialize)
    └─ LLMProvider → LLM API (Anthropic / OpenAI / Gemini)
```
