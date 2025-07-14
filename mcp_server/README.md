# MCP Server (Model Context Protocol)

基于 OpenSearch 的 MCP Server，兼容大语言模型 Model Context Protocol（MCP）标准。

## 1. 环境准备

- Python 3.8+
- OpenSearch 实例（可本地或云端）

## 2. 安装依赖

```bash
cd mcp_server
pip install -r requirements.txt
```

## 3. 配置环境变量

可在 `.env` 文件中配置如下内容：

```
MCP_API_KEY=your-mcp-api-key
OPENSEARCH_HOST=localhost
OPENSEARCH_PORT=9200
OPENSEARCH_USER=admin
OPENSEARCH_PASS=admin
OPENSEARCH_INDEX=opensearch_kl_index
OPENSEARCH_EMBEDDING_MODEL_ID=-kB2sZUB0LCOh9zdNaiU
```

## 4. 启动 MCP Server

```bash
python app.py
```

默认监听 5100 端口。

## 5. API 说明

### POST /v1/mcp/context

- Header: `x-api-key: your-mcp-api-key`
- Content-Type: application/json
- Body 示例：
```
{
  "query": "EMR 升级步骤",
  "messages": [
    {"role": "user", "content": "EMR 升级步骤"},
    {"role": "assistant", "content": "请问你使用的 EMR 版本？"}
  ],
  "user_id": "user-xxx",
  "context": {}
}
```
- 返回示例：
```
{
  "context": {},
  "results": [
    {"text": "...", "score": 1.23}
  ],
  "answer": "..."
}
```

- `context`：原样返回，便于多轮对话
- `results`：检索结果列表
- `answer`：自动拼接前3条结果文本（可按需自定义）

## 6. 适配说明
本接口兼容 DeepSeek、百度文心等大模型 MCP 插件协议，可直接用于 LLM 检索增强。

### POST /search

- Header: `x-api-key: your-mcp-api-key`
- Body: `{ "query": "你的问题", "pipeline": "my-conversation-search-pipeline-deepseek-zh" }`
- 返回：检索结果列表

示例：

```bash
curl -X POST http://localhost:5100/search \
  -H 'Content-Type: application/json' \
  -H 'x-api-key: your-mcp-api-key' \
  -d '{"query": "EMR 升级步骤"}'
``` 