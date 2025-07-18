# Amazon EMR 版本升级助手

基于 AI 和 OpenSearch MCP Server 的智能 EMR 升级助手，帮助用户解决 Amazon EMR 版本升级过程中的各种问题。

## 🌟 功能特性

- 🤖 **智能对话**: 基于 AI Agent 的自然语言交互
- 📚 **知识库集成**: 直接调用你已实现的 MCP Server
- 🧠 **上下文记忆**: 使用 Mem0 存储和检索对话历史，提供个性化体验
- 🔄 **版本升级指导**: 提供详细的 EMR 版本升级建议
- 🛠️ **组件兼容性**: 分析 Hive、Spark、Flink、HBase 等组件的兼容性
- 💻 **Web 界面**: 用户友好的聊天界面
- 🔍 **智能检索**: 基于语义搜索和关键词搜索的混合检索

## 🏗️ 架构组件

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Web Frontend  │───▶│  Flask App      │───▶│ EMR Agent       │
│   (Chat UI)     │    │  (Web Server)   │    │ (Claude + MCP)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                            │                          │
                            │                          ▼
                            │                 ┌─────────────────┐
                            │                 │   MCP Server    │───┐
                            │                 │ (search_context)│   │
                            │                 └─────────────────┘   │
                            │                                       ▼
                            ▼                                ┌─────────────────┐
                     ┌─────────────────┐                     │   OpenSearch    │
                     │   Mem0 Memory   │◀────────────────────│  (Knowledge DB) │
                     │   (User Context)│                     └─────────────────┘
                     └─────────────────┘
```

### 核心组件说明

1. **Web Frontend**: 用户友好的聊天界面，支持显示工具使用情况和知识库内容
2. **Flask App**: Web 服务器，处理 HTTP 请求和会话管理
3. **EMR Agent**: 基于 Anthropic Claude 的智能 AI 代理，通过 MCP 协议调用工具
4. **MCP Server**: 你已实现的 OpenSearch 连接服务，提供 `search_context` 工具
5. **OpenSearch**: 存储 EMR 升级知识库的搜索引擎，支持混合搜索
6. **Mem0 Memory**: 基于 OpenSearch 的上下文记忆系统，存储用户对话历史并提供个性化体验

## 🚀 快速开始

### 环境要求

- Python 3.10+
- Strands Agents SDK API Key
- AWS 账户（用于 OpenSearch 和 Secrets Manager）
- OpenSearch 集群（已配置 EMR 知识库）

### ⚠️ 重要提示

**请先参考 [Strands Agents 官方文档](https://strandsagents.com/latest/user-guide/quickstart/) 调整代码中的 API 调用！**

当前代码中包含了需要根据官方文档调整的部分，已在代码注释中标明。

### 1. 克隆和安装

```bash
# 进入项目目录
cd emr_upgrade_assistant

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，配置以下参数：
```

**必需配置项：**

```env
# Anthropic API 配置
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# AWS 配置 (MCP Server 需要)
AWS_REGION=us-east-1
OPENSEARCH_HOST=your-opensearch-domain.us-east-1.es.amazonaws.com
OPENSEARCH_PORT=443
OPENSEARCH_SECRET_NAME=opensearch_credentials
OPENSEARCH_INDEX=opensearch_kl_index
OPENSEARCH_EMBEDDING_MODEL_ID=your_embedding_model_id

# Mem0 记忆系统配置
MEM0_ENABLED=true
MEM0_USER_ID=emr_assistant_user
MEM0_OPENSEARCH_HOST=your-opensearch-domain.us-east-1.es.amazonaws.com
MEM0_OPENSEARCH_PORT=443
MEM0_OPENSEARCH_USERNAME=admin
MEM0_OPENSEARCH_PASSWORD=your_password
MEM0_OPENSEARCH_USE_SSL=true
MEM0_OPENSEARCH_VERIFY_CERTS=true
MEM0_OPENSEARCH_INDEX=emr_assistant_memories
```

### 3. 启动服务

```bash
# 使用启动脚本（推荐）
./start.sh

# 或直接运行
python app.py
```

### 4. 访问应用

打开浏览器访问：`http://localhost:5001`

## 💬 使用说明

### 基本使用

1. 在聊天界面输入您的 EMR 升级相关问题
2. AI 助手会自动搜索知识库并生成专业回答
3. 可以查看相关的知识库内容作为参考

### 示例查询

**版本升级相关：**
- "从 EMR 5.36 升级到 6.10 需要注意什么？"
- "EMR 6.x 相比 5.x 有哪些重大变化？"

**组件兼容性：**
- "EMR 6.10.0 升级到 6.11.0 后，Hive 有哪些新特性？"
- "Spark 3.x 在 EMR 6.x 中的配置变更"
- "HBase 在新版本中的兼容性问题"

**故障排除：**
- "EMR 升级后 Spark 作业失败如何解决？"
- "Hive 元数据迁移的最佳实践"

## 🔧 配置说明

### AWS 权限要求

确保您的 AWS 凭证具有以下权限：

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel",
                "es:ESHttpGet",
                "es:ESHttpPost",
                "secretsmanager:GetSecretValue"
            ],
            "Resource": "*"
        }
    ]
}
```

### OpenSearch 配置

确保您的 OpenSearch 集群：
1. 已安装并配置了嵌入模型
2. 已创建混合搜索管道
3. 已导入 EMR 相关知识库数据

## 🐛 故障排除

### 常见问题

**1. OpenSearch 连接失败**
```bash
# 检查网络连接和凭证
curl -X GET "https://your-domain.us-east-1.es.amazonaws.com/_cluster/health"
```

**2. Bedrock 调用失败**
```bash
# 检查 AWS 凭证和权限
aws bedrock list-foundation-models --region us-east-1
```

**3. 依赖安装问题**
```bash
# 升级 pip 并重新安装
pip install --upgrade pip
pip install -r requirements.txt --force-reinstall
```

### 日志查看

应用日志会显示在控制台，包括：
- OpenSearch 连接状态
- MCP 客户端初始化
- 查询处理过程
- 错误信息

## 🧠 Mem0 记忆系统

### 功能特点

- **用户隔离**: 每个浏览器会话拥有独立的记忆空间，通过随机生成的用户ID实现
- **上下文感知**: 自动检索与当前问题相关的历史对话，提供更连贯的回答
- **长期记忆**: 将重要信息存储在 OpenSearch 中，支持跨会话的知识累积
- **实时更新**: 每次对话后自动更新记忆，无需手动操作
- **记忆管理**: 提供记忆统计、搜索和清除功能

### 记忆 API

- **获取记忆统计**:
  ```
  GET /memory/stats
  ```

- **搜索相关记忆**:
  ```
  POST /memory/search
  Content-Type: application/json
  
  {
    "query": "EMR 升级",
    "limit": 5
  }
  ```

- **获取最近记忆**:
  ```
  GET /memory/recent?limit=10
  ```

- **清除所有记忆**:
  ```
  POST /memory/clear
  ```

### 记忆工具

EMR Agent 可以使用以下工具来访问记忆系统:

- `search_conversation_history`: 搜索相关的历史对话
- `get_recent_conversations`: 获取最近的对话记录
- `get_memory_statistics`: 获取记忆系统统计信息
- `clear_conversation_history`: 清除所有历史对话记录

## 🔄 开发和扩展

### 项目结构

```
emr_upgrade_assistant/
├── app.py              # 主应用文件
├── mem0_integration.py # Mem0 记忆系统集成
├── mem0_tools.py       # Mem0 工具集
├── requirements.txt    # Python 依赖
├── .env.example        # 环境变量模板
├── start.sh            # 启动脚本
├── templates/          # HTML 模板
│   └── index.html
└── static/             # 静态文件
    └── style.css
```

### 自定义扩展

1. **添加新的搜索功能**: 修改 `mcp_client.py` 中的搜索逻辑
2. **自定义 UI**: 编辑 `templates/index.html` 和 `static/style.css`
3. **集成其他 LLM**: 修改 `app.py` 中的 `call_llm` 方法

## 📝 许可证

本项目基于 MIT 许可证开源。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request 来改进这个项目！