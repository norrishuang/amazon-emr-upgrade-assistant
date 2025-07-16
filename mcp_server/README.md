# MCP Server (Model Context Protocol)

基于 OpenSearch 的 MCP Server，兼容大语言模型 Model Context Protocol（MCP）标准。

## 1. 环境准备

- Python 3.10+
- OpenSearch 实例（可本地或云端）
- Node.js 和 npm

## 2. 安装依赖

```bash
pip install "mcp[cli]" httpx opensearch-py python-dotenv
sudo dnf install nodejs npm -y
```

## 3. 环境变量（.env）配置

请在 `mcp_server` 目录下创建 `.env` 文件，内容示例：

```
# OpenSearch 连接配置
OPENSEARCH_HOST=your-opensearch-host
OPENSEARCH_PORT=9200
OPENSEARCH_INDEX=opensearch_kl_index
OPENSEARCH_EMBEDDING_MODEL_ID=-kB2sZUB0LCOh9zdNaiU

# AWS Secrets Manager 配置
OPENSEARCH_SECRET_NAME=opensearch_credentials   # 存储 OpenSearch 用户名密码的 secret 名称
AWS_REGION=us-east-1                           # secret 所在的 AWS 区域
```

> OpenSearch 用户名和密码需存储在 AWS Secrets Manager 中，secret 内容格式如下：
> ```json
> {"username": "your-username", "password": "your-password"}
> ```

## 4. 启动 MCP Inspector 进行测试

```bash
uv run mcp dev /home/ec2-user/amazon-emr-upgrade-assistant/mcp_server/app.py
```

启动后访问 [http://127.0.0.1:6274](http://127.0.0.1:6274) 打开 UI 测试 MCP Server。

## 5. 服务说明

本服务为 Amazon EMR 版本升级知识库检索，支持 EMR 组件（hive、spark、flink、hbase）在各版本中的新增特性和 BUG 修复内容的查询。

## 6. 其他说明

- 本 MCP Server 通过 MCP 协议与客户端通信，无需监听 HTTP 端口。
- 其他原有内容保留。 