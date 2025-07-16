# Amazon EMR 升级助手部署指南

## 📋 前置要求

- Python 3.8+
- 你已实现的 MCP Server (`mcp_server/app.py`)
- OpenSearch 集群（已配置 EMR 知识库）
- Strands Agents API Key 或相关凭证

## 🔧 安装步骤

### 1. 安装 Strands Agents SDK

```bash
# 进入项目目录
cd emr_upgrade_assistant

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装 Strands Agents
pip install strands-agents
pip install strands-agents-tools
pip install strands-agents-builder

# 安装其他依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件
nano .env  # 或使用你喜欢的编辑器
```

**必需配置项：**

```env
# Flask 应用配置
SECRET_KEY=your-secret-key-here
FLASK_ENV=development
PORT=5001

# Strands Agents 配置（请根据官方文档调整）
OPENAI_API_KEY=your_openai_api_key_here
# 或者如果使用其他模型提供商
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# AWS 配置 (MCP Server 需要)
AWS_REGION=us-east-1
OPENSEARCH_HOST=your-opensearch-domain.us-east-1.es.amazonaws.com
OPENSEARCH_PORT=443
OPENSEARCH_SECRET_NAME=opensearch_credentials
OPENSEARCH_INDEX=opensearch_kl_index
OPENSEARCH_EMBEDDING_MODEL_ID=your_embedding_model_id
```

### 3. 根据官方文档调整代码

**重要**: 请参考 https://strandsagents.com/latest/user-guide/quickstart/ 调整以下文件中的代码：

#### `app.py` 中需要调整的部分：

1. **导入语句** (第23-24行):
```python
from strands_agents import Agent
from strands_agents.tools import MCPTool
```

2. **Agent 初始化** (第27-34行):
```python
self.agent = Agent(
    name="EMR升级助手",
    description="专业的Amazon EMR版本升级助手",
    instructions=self._get_instructions(),
    model="gpt-4",  # 请根据官方文档调整
    temperature=0.1
)
```

3. **MCP 工具创建** (第75-83行):
```python
search_tool = MCPTool(
    name="search_context",
    description="检索知识库中关于 Amazon EMR 版本升级的相关内容",
    server_config={
        "command": ["python", mcp_server_path],
        "transport": "stdio"
    }
)
```

4. **添加工具到 Agent** (第86行):
```python
self.agent.add_tool(search_tool)
```

5. **Agent 运行** (第108-111行):
```python
response = await self.agent.run(
    message=user_query,
    user_id=user_id or str(uuid.uuid4())
)
```

6. **响应对象属性访问** (第116-122行):
```python
return {
    "success": True,
    "answer": getattr(response, 'content', str(response)),
    "thinking": getattr(response, 'thinking', ''),
    "tools_used": getattr(response, 'tools_used', []),
    "context": getattr(response, 'context', ''),
    # ...
}
```

### 4. 启动服务

```bash
# 使用启动脚本（推荐）
./start.sh

# 或直接运行
python app.py
```

### 5. 访问应用

打开浏览器访问：`http://localhost:5001`

## 🔍 调试步骤

如果遇到问题，请按以下步骤调试：

### 1. 检查 Strands Agents 安装
```bash
python -c "import strands_agents; print('Strands Agents 安装成功')"
```

### 2. 检查 MCP Server
```bash
cd ../mcp_server
python app.py
# 测试 MCP Server 是否正常工作
```

### 3. 检查环境变量
```bash
python -c "from dotenv import load_dotenv; load_dotenv(); import os; print('API Keys:', bool(os.getenv('OPENAI_API_KEY') or os.getenv('ANTHROPIC_API_KEY')))"
```

### 4. 查看日志
启动应用时注意控制台输出，特别关注：
- "🚀 EMR 升级助手 (Strands Agents) 初始化完成"
- "✅ MCP 工具注册成功"

## 📚 参考资源

- [Strands Agents 官方文档](https://strandsagents.com/latest/user-guide/quickstart/)
- [MCP 协议规范](https://modelcontextprotocol.io/)
- [你的 MCP Server](../mcp_server/app.py)

## ❓ 常见问题

### Q: Strands Agents 导入失败
A: 确保使用正确的安装命令：
```bash
pip install strands-agents
pip install strands-agents-tools
pip install strands-agents-builder
```

### Q: MCP 工具注册失败
A: 检查 MCP Server 路径是否正确，确保 `../mcp_server/app.py` 存在且可执行。

### Q: Agent 初始化失败
A: 检查 API Key 配置，确保模型名称和参数符合 Strands Agents 的要求。

## 🔄 下一步

1. 根据官方文档调整代码中标注的部分
2. 测试与你的 MCP Server 的连接
3. 验证 EMR 升级助手的功能
4. 根据需要调整 Agent 的指令和行为