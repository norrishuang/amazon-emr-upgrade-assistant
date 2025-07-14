# MCP Web

基于 Flask 的知识库 Web 页面，所有检索请求通过 MCP Server 转发。

## 1. 环境准备

- Python 3.8+
- 需先启动 MCP Server

## 2. 安装依赖

```bash
cd mcp_web
pip install -r requirements.txt
```

## 3. 配置环境变量

可在 `.env` 文件中配置如下内容：

```
MCP_SERVER_URL=http://localhost:5100
MCP_API_KEY=your-mcp-api-key
WEB_SECRET_KEY=mcp-web-secret-key
```

## 4. 启动 Web

```bash
python app.py
```

默认监听 5200 端口。

## 5. 功能说明

- 访问 `/login`，输入邀请码登录
- 登录后可在主页面输入问题，检索结果由 MCP Server 返回
- 可通过 `/generate_invite_code` 生成测试邀请码 