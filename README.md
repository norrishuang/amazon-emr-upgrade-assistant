# OpenSearch RAG 问答应用

这个应用程序是一个基于 OpenSearch 的检索增强生成（RAG）问答系统，支持文档上传、语义搜索和基于对话历史的多轮对话。

## 功能特点

- 文档上传和处理（支持 PDF、DOCX、TXT 格式）
- 文本分块和向量化存储
- 基于神经搜索的语义检索
- 生成式问答（RAG）
- 多轮对话支持（会话记忆）

## 应用版本

本项目包含两个版本的应用：

1. **app.py** - 基础版本，支持文档上传和单轮问答
2. **app_conversational.py** - 增强版本，支持多轮对话和会话记忆

## 环境要求

- Python 3.8+
- Flask
- OpenSearch Python 客户端
- 其他依赖项（见 requirements.txt）

## 配置

应用通过 `.env` 文件进行配置，主要配置项包括：

```
OPENSEARCH_HOST=localhost
OPENSEARCH_PORT=9200
OPENSEARCH_USER=admin
OPENSEARCH_PASSWORD=admin
OPENSEARCH_INDEX=opensearch_kl_index
OPENSEARCH_EMBEDDING_MODEL_ID=-kB2sZUB0LCOh9zdNaiU
SECRET_KEY=your-secret-key
```

## 安装和运行

1. 安装依赖：
   ```shell
   python3 -m venv .venv
  source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. 运行基础版本：
   ```shell
   python app.py
   ```

3. 运行支持多轮对话的版本：
   ```shell
   python app_conversational.py
   ```

## 使用方法

1. 访问 http://localhost:5000 (基础版本) 或 http://localhost:5001 (对话版本)
2. 上传文档进行知识库构建
3. 在搜索框中输入问题进行查询
4. 对话版本会自动保存会话历史，支持上下文相关的多轮对话

## 会话管理 API (仅对话版本)

- **清除会话历史**：
  ```
  POST /conversation/clear
  Content-Type: application/json
  
  {
    "conversation_id": "your-conversation-id"
  }
  ```

- **获取会话历史**：
  ```
  GET /conversation/history?conversation_id=your-conversation-id
  ```

## 技术实现

- 使用 OpenSearch 的文本嵌入和神经搜索功能
- 利用 OpenSearch 的生成式 AI 管道进行 RAG
- 通过会话 ID 和消息历史实现多轮对话
- 自动清理过期会话（24小时）
