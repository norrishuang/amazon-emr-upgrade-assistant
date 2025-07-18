from quart import Quart, render_template, request, jsonify, Response, session
import os, sys
import json
import asyncio
from typing import Dict, Any
from dotenv import load_dotenv
import uuid
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler

# 根据官方文档导入 Strands Agents 和 MCP 相关模块
from mcp import stdio_client, StdioServerParameters
from strands import Agent
from strands.tools.mcp import MCPClient
from mem0_integration import create_mem0_integration
from mem0_tools import mem0_tools
from strands.models import BedrockModel

# 创建日志目录
log_dir = 'logs'
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# 配置日志记录器
def setup_logger():
    logger = logging.getLogger('emr_assistant')
    logger.setLevel(logging.DEBUG)
    
    # 创建格式化器
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 创建文件处理器（带滚动）
    file_handler = RotatingFileHandler(
        filename=os.path.join(log_dir, 'emr_assistant.log'),
        maxBytes=100*1024*1024,  # 100MB
        backupCount=30,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger

# 初始化日志记录器
logger = setup_logger()

load_dotenv()

app = Quart(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'emr-upgrade-assistant-secret-key')

# 禁用 Quart 的缓冲，确保流式响应立即发送
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['RESPONSE_TIMEOUT'] = 300  # 增加响应超时时间到300秒
app.config['BODY_TIMEOUT'] = 300  # 增加请求体超时时间到300秒

class EMRUpgradeAssistant:
    """Amazon EMR 版本升级助手 - 基于 Strands Agents"""
    
    def __init__(self):
        try:
            # 不在初始化时创建 mem0 实例，而是在每次请求时创建
            self.mem0 = None
            
            logger.info("🚀 开始初始化 EMR 升级助手...")
            
            # 根据官方文档配置 MCP 客户端
            # 参考: https://strandsagents.com/latest/user-guide/concepts/tools/mcp-tools/
            
            # 获取项目根目录和 MCP Server 目录
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
            mcp_server_dir = os.path.join(project_root, 'mcp_server')
            
            # 创建多个 MCP 客户端
            # 1. 主 MCP 服务器
            self.mcp_client = MCPClient(lambda: stdio_client(
                StdioServerParameters(
                    command="uv",
                    args=["--directory", mcp_server_dir, "run", "app.py"]
                )
            ))
            
            # 2. langgraph-crawler MCP 服务器 - 用于网页搜索和内容抓取
            self.langgraph_crawler_client = MCPClient(lambda: stdio_client(
                StdioServerParameters(
                    command="npx",
                    args=["-y", "@langgraph-js/crawler-mcp@latest"]
                )
            ))
            
            logger.info("✅ MCP 客户端初始化成功")
            logger.debug(f"📡 MCP Server 目录: {mcp_server_dir}")
            
            # 注意：根据官方文档，Agent 必须在 MCP 客户端的上下文管理器中创建和使用
            self.agent = None  # 将在 process_query 中创建
            
            logger.info("🚀 EMR 升级助手 (Strands Agents) 初始化完成")
            
        except ImportError as e:
            logger.error(f"❌ Strands Agents 导入失败: {str(e)}")
            logger.error("请确保已正确安装 Strands Agents:")
            logger.error("pip install strands-agents")
            logger.error("pip install strands-agents-tools")
            logger.error("pip install strands-agents-builder")
            self.agent = None
        except Exception as e:
            logger.error(f"❌ Agent 初始化失败: {str(e)}")
            self.agent = None
    
    def _get_instructions(self) -> str:
        """获取 Agent 指令"""
        return """
你是一个专业的 Amazon EMR 版本升级助手。你的主要职责是：

1. 帮助用户了解不同 EMR 版本之间的差异和升级注意事项
2. 提供各个组件（Hive、Spark、Flink、HBase等）的版本兼容性信息
3. 解答升级过程中可能遇到的技术问题
4. 提供最佳实践建议

请始终：
- 提供准确、详细的技术信息
- 基于知识库内容回答问题
- 给出具体的操作建议
- 突出重要的注意事项和风险点
- 使用中文回答
- 结构化回答，使用标题和要点

当用户询问 EMR 升级相关问题时：
1. 如果需要最新的信息，请使用 mcp_langgraph_crawler_web_search_tool 工具搜索互联网上的最新信息
2. 如果需要查看特定网页的内容，请使用 mcp_langgraph_crawler_crawl_tool 工具抓取网页内容
3. 如果需要本地知识库信息，请使用 search_context 工具检索相关信息

然后基于检索结果提供专业的回答。

回答格式建议：
## 问题分析
## 主要建议
## 实施步骤
## 注意事项
## 相关文档
"""
    
    def _extract_content_from_chunk(self, chunk) -> str:
        """从流式响应块中提取内容"""
        if hasattr(chunk, 'content'):
            return chunk.content
        elif hasattr(chunk, 'text'):
            return chunk.text
        elif isinstance(chunk, str):
            return chunk
        elif hasattr(chunk, 'delta') and hasattr(chunk.delta, 'content'):
            return chunk.delta.content
        elif hasattr(chunk, 'choices') and len(chunk.choices) > 0:
            # OpenAI 格式
            choice = chunk.choices[0]
            if hasattr(choice, 'delta') and hasattr(choice.delta, 'content'):
                return choice.delta.content or ""
        else:
            # 尝试转换为字符串
            try:
                return str(chunk)
            except:
                return ""
    
    def _format_streaming_content(self, content: str) -> str:
        """格式化流式内容，添加适当的换行"""
        import re
        
        # 定义需要换行的关键词和模式
        thinking_patterns = [
            r'让我为您检索',
            r'基于获取的信息',
            r'我需要进一步了解',
            r'需要更多关于',
            r'让我再查询',
            r'根据检索结果',
            r'## 问题分析',
            r'## 主要建议',
            r'## 实施步骤',
            r'## 注意事项',
            r'## 相关文档'
        ]
        
        # 为思考过程添加换行
        formatted_content = content
        for pattern in thinking_patterns:
            # 在匹配的模式前添加换行（如果前面不是换行的话）
            formatted_content = re.sub(
                f'([^\\n])({pattern})', 
                r'\1\n\n\2', 
                formatted_content
            )
        
        # 在冒号后添加换行（用于"内容："这样的模式）
        formatted_content = re.sub(r'：([^\\n])', r'：\n\1', formatted_content)
        
        return formatted_content
    
    def _stream_text_output(self, text):
        """将文本按词语流式输出 - 优化版本"""
        import re
        import time
        
        logger.debug(f"📝 开始模拟流式输出，内容长度: {len(text)}")
        
        # 按词语和标点符号分割，但是以更大的块为单位
        # 这样可以看到流式效果，但不会太慢
        chunks = []
        words = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+|\d+|[^\w\s]|\s+', text)
        
        # 将单词组合成更大的块（每3-5个词为一块）
        current_chunk = ""
        for i, word in enumerate(words):
            current_chunk += word
            
            # 每3-5个词或遇到句号、换行符时创建一个块
            if (i + 1) % 4 == 0 or word in ['.', '。', '\n', '!', '！', '?', '？']:
                if current_chunk.strip():
                    chunks.append(current_chunk)
                    current_chunk = ""
        
        # 添加剩余的内容
        if current_chunk.strip():
            chunks.append(current_chunk)
        
        accumulated = ""
        
        for chunk in chunks:
            accumulated += chunk
            
            yield {
                "type": "content",
                "content": chunk,
                "accumulated": accumulated,
                "timestamp": datetime.now().isoformat()
            }
            
            # 添加适当的延迟来模拟流式效果
            time.sleep(0.1)  # 100ms 延迟，足够看到流式效果但不会太慢
    


    
    def process_query_stream_simple(self, user_query: str, user_id: str = None):
        """
        简化版流式处理 - 用于调试
        """
        try:
            logger.debug(f"🔧 [简化版] 开始处理查询: {user_query}")
            logger.debug(f"🔧 [简化版] MCP Client 状态: {self.mcp_client is not None}")
            
            # 直接返回一个测试响应
            test_response = f"收到您的问题：{user_query}\n\n这是一个测试响应，用于验证流式输出是否正常工作。"
            
            logger.debug(f"🔧 [简化版] 开始模拟流式输出，内容长度: {len(test_response)}")
            
            # 模拟流式输出
            chunk_count = 0
            for chunk in self._stream_text_output(test_response):
                chunk_count += 1
                print(f"🔧 [简化版] 生成第 {chunk_count} 个数据块: {chunk}")
                yield chunk
            
            logger.debug(f"✅ [简化版] 流式输出完成，共生成 {chunk_count} 个数据块")
                
        except Exception as e:
            print(f"❌ [简化版] 处理失败: {str(e)}")
            import traceback
            print(f"❌ [简化版] 错误堆栈: {traceback.format_exc()}")
            yield {
                "type": "error",
                "error": f"简化版处理失败: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }

    async def process_query_stream(self, user_query: str, user_id: str = None):
        """
        流式处理用户查询 - 使用 Strands Agent 真正的流式响应
        保证 LLM 内容和 MCP Server 工具内容都能流式返回到页面，并在后台打印。
        """
        if not self.mcp_client:
            yield {
                "type": "error",
                "error": "MCP 客户端未正确初始化，请检查安装和配置",
                "timestamp": datetime.now().isoformat()
            }
            return

        try:
            logger.debug(f"📝 开始流式处理用户查询: {user_query}")
            
            # 获取主MCP服务器的工具
            with self.mcp_client:
                mcp_tools = self.mcp_client.list_tools_sync()
                logger.debug(f"🔧 获取到 {len(mcp_tools)} 个主MCP工具")
            
            # 获取langgraph-crawler MCP服务器的工具
            crawler_tools = []
            try:
                with self.langgraph_crawler_client:
                    crawler_tools = self.langgraph_crawler_client.list_tools_sync()
                    logger.debug(f"🔧 获取到 {len(crawler_tools)} 个langgraph-crawler工具")
            except Exception as crawler_error:
                logger.error(f"⚠️ 获取langgraph-crawler工具失败: {str(crawler_error)}")
            
            # 合并所有工具
            all_tools = mcp_tools + mem0_tools + crawler_tools
            logger.debug(f"🔧 总共获取到 {len(all_tools)} 个工具: {len(mcp_tools)}个主MCP工具 + {len(mem0_tools)}个mem0工具 + {len(crawler_tools)}个crawler工具")
            
            # 使用主MCP客户端的上下文管理器
            with self.mcp_client:
                try:
                    bedrock_model = BedrockModel(
                        model_id="us.anthropic.claude-sonnet-4-20250514-v1:0",
                        region_name="us-east-1",
                        temperature=0.3,
                    )
                    agent = Agent(
                        tools=all_tools,
                        callback_handler=None
                    )
                    logger.debug("✅ 成功创建使用 Agent")
                except Exception as model_error:
                    logger.error(f"⚠️ 使用 Claude 4.0 Sonnet 创建 Agent 失败: {str(model_error)}")
                    logger.error("尝试使用默认模型创建 Agent")
                    agent = Agent(tools=all_tools, callback_handler=None)
                if hasattr(agent, 'model') and hasattr(agent.model, 'config'):
                    logger.debug(f"🔧 使用模型配置: {agent.model.config}")
                else:
                    logger.warn("⚠️ 无法获取模型配置信息")
                user_mem0 = create_mem0_integration(user_id)
                from mem0_tools import set_current_user_mem0
                set_current_user_mem0(user_mem0)
                historical_context = user_mem0.get_context_for_query(user_query)
                system_instructions = self._get_instructions()
                if historical_context:
                    full_query = f"{system_instructions}\n\n{historical_context}\n\n用户问题: {user_query}"
                    logger.debug(f"📚 添加了历史上下文，长度: {len(historical_context)}")
                else:
                    full_query = f"{system_instructions}\n\n用户问题: {user_query}"
                logger.debug(f"🔧 开始 Strands Agent 流式调用...")
                accumulated_response = ""
                async def async_stream():
                    nonlocal accumulated_response
                    try:
                        # 设置超时时间（秒）
                        timeout_seconds = 240  # 增加到240秒
                        
                        # 获取流式响应迭代器
                        stream_iterator = agent.stream_async(full_query)
                        
                        # 初始化心跳计数器
                        heartbeat_counter = 0
                        last_heartbeat_time = datetime.now()
                        
                        # 处理流式响应
                        while True:
                            # 每5秒发送一次心跳，保持连接活跃
                            current_time = datetime.now()
                            if (current_time - last_heartbeat_time).total_seconds() >= 5:
                                yield {
                                    "type": "heartbeat",
                                    "timestamp": current_time.isoformat()
                                }
                                last_heartbeat_time = current_time
                                heartbeat_counter += 1
                            
                            # 等待流式响应或超时
                            try:
                                # 使用asyncio.wait_for设置超时，但增加超时时间
                                event = await asyncio.wait_for(stream_iterator.__anext__(), timeout=10.0)
                                
                                # 处理事件
                                # LLM 内容流式返回
                                if "data" in event:
                                    content = event["data"]
                                    if content:
                                        accumulated_response += content
                                        logger.debug(f"📝 LLM流式内容: {content}")
                                        yield {
                                            "type": "content",
                                            "content": content,
                                            "accumulated": accumulated_response,
                                            "timestamp": datetime.now().isoformat()
                                        }
                                
                                # 工具调用事件
                                if "current_tool_use" in event and event["current_tool_use"].get("name"):
                                    tool_name = event["current_tool_use"]["name"]
                                    tool_input = event["current_tool_use"].get("input", {})
                                    logger.debug(f"🔧 工具调用: {tool_name}, 输入: {tool_input}")
                                    
                                    # 对网络搜索工具添加特殊处理
                                    if "web_search" in tool_name.lower() or "crawl" in tool_name.lower():
                                        yield {
                                            "type": "status",
                                            "message": f"[正在搜索网络信息: {tool_input.get('query', '')}]",
                                            "timestamp": datetime.now().isoformat()
                                        }
                                    else:
                                        yield {
                                            "type": "status",
                                            "message": f"[使用工具: {tool_name}]",
                                            "timestamp": datetime.now().isoformat()
                                        }
                                
                                # MCP Server 工具返回内容
                                if "tool_response" in event and event["tool_response"]:
                                    tool_name = event.get("current_tool_use", {}).get("name", "未知工具")
                                    logger.debug(f"🟢 工具 {tool_name} 返回结果")
                                    
                                    # 对于网络搜索工具，通知前端搜索完成
                                    if "web_search" in tool_name.lower() or "crawl" in tool_name.lower():
                                        yield {
                                            "type": "status",
                                            "message": f"[网络搜索完成，正在分析结果]",
                                            "timestamp": datetime.now().isoformat()
                                        }
                                
                            except StopAsyncIteration:
                                # 流结束
                                logger.debug("✅ 流式响应完成")
                                break
                                
                            except asyncio.TimeoutError:
                                # 超时但不中断流程，继续等待
                                logger.debug(f"⏱️ 等待流式响应中... ({heartbeat_counter * 10}秒)")
                                
                                # 如果超过总超时时间，发送状态消息但不中断
                                if heartbeat_counter * 10 > timeout_seconds:
                                    logger.warning(f"⚠️ 流式响应处理时间较长 ({timeout_seconds}秒)")
                                    yield {
                                        "type": "status",
                                        "message": f"[处理时间较长，可能是网络搜索或分析复杂问题导致，请耐心等待...]",
                                        "timestamp": datetime.now().isoformat()
                                    }
                            
                            except Exception as event_error:
                                # 处理单个事件的错误，但不中断整个流程
                                logger.error(f"❌ 处理事件时出错: {str(event_error)}")
                                yield {
                                    "type": "status",
                                    "message": f"[处理过程中遇到问题，但仍在继续...]",
                                    "timestamp": datetime.now().isoformat()
                                }
                    except Exception as e:
                        logger.error(f"❌ 异步流式调用失败: {str(e)}")
                        import traceback
                        logger.error(f"错误堆栈: {traceback.format_exc()}")
                        yield {
                            "type": "error",
                            "error": f"处理查询时出错: {str(e)}",
                            "timestamp": datetime.now().isoformat()
                        }
                async for chunk in async_stream():
                    yield chunk
                if accumulated_response:
                    try:
                        user_mem0.add_memory(
                            message="EMR升级咨询对话",
                            user_query=user_query,
                            response=accumulated_response,
                            metadata={
                                "user_id": user_id,
                                "response_length": len(accumulated_response)
                            }
                        )
                        logger.debug(f"💾 对话记忆已保存到 mem0 {user_id}")
                    except Exception as mem_error:
                        logger.error(f"⚠️ 保存记忆失败: {str(mem_error)}")
        except Exception as e:
            logger.error(f"❌ 流式处理查询时出错: {str(e)}")
            yield {
                "type": "error",
                "error": f"处理查询时出错: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }

    async def process_query(self, user_query: str, user_id: str = None) -> Dict[str, Any]:
        """
        处理用户查询
        
        Args:
            user_query: 用户查询内容
            user_id: 用户ID
            
        Returns:
            包含回答和相关信息的字典
        """
        if not self.mcp_client:
            return {
                "success": False,
                "error": "MCP 客户端未正确初始化，请检查安装和配置",
                "timestamp": datetime.now().isoformat()
            }
        
        try:
            logger.info(f"📝 处理用户查询: {user_query}")
            
            # 根据官方文档，必须在 MCP 客户端的上下文管理器中使用 Agent
            with self.mcp_client:
                # 获取 MCP 服务器提供的工具
                tools = self.mcp_client.list_tools_sync()
                logger.debug(f"🔧 获取到 {len(tools)} 个 MCP 工具")
                
                # 在上下文管理器中创建 Agent
                # 根据 Strands Agents API，Agent 初始化不接受 instructions 参数
                agent = Agent(tools=tools)
                
                # 构建包含系统指令的完整查询
                system_instructions = self._get_instructions()
                full_query = f"{system_instructions}\n\n用户问题: {user_query}"
                
                # 使用 Agent 处理查询
                response = agent(full_query)
                
                logger.debug("✅ Strands Agent 处理完成")
                
                # 根据官方文档，响应格式可能是字符串或对象
                if isinstance(response, str):
                    answer = response
                    tools_used = []
                else:
                    answer = getattr(response, 'content', str(response))
                    tools_used = getattr(response, 'tools_used', [])
                
                return {
                    "success": True,
                    "answer": answer,
                    "tools_used": tools_used,
                    "query": user_query,
                    "timestamp": datetime.now().isoformat()
                }
            
        except Exception as e:
            logger.error(f"❌ 处理查询时出错: {str(e)}")
            return {
                "success": False,
                "error": f"处理查询时出错: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }

# 初始化助手
emr_assistant = EMRUpgradeAssistant()

@app.route('/')
async def index():
    """主页 - 生成并存储用户ID"""
    # 检查会话中是否已有用户ID，如果没有则创建一个新的
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
        logger.info(f"创建新的用户会话ID: {session['user_id']}")
    else:
        logger.info(f"使用现有用户会话ID: {session['user_id']}")
    
    return await render_template('index.html')

@app.route('/chat', methods=['POST'])
async def chat_stream():
    """处理聊天请求 - 流式响应"""
    try:
        data = await request.get_json()
        user_query = data.get('query', '').strip()
        
        if not user_query:
            return jsonify({
                'success': False,
                'error': '请输入您的问题'
            }), 400
        
        # 从会话中获取用户ID，如果不存在则创建一个新的
        user_id = session.get('user_id')
        if not user_id:
            user_id = str(uuid.uuid4())
            session['user_id'] = user_id
            logger.info(f"在聊天请求中创建新的用户会话ID: {user_id}")
        else:
            logger.debug(f"使用现有用户会话ID: {user_id}")
        
        # 返回流式响应 - 强制实时传输，添加填充数据
        async def generate_stream():
            import sys
            import os
            
            # 强制禁用 Python 的输出缓冲
            os.environ['PYTHONUNBUFFERED'] = '1'
            
            try:
                logger.debug("🔄 开始生成流式响应...")
                
                # 立即发送心跳和填充数据，强制建立连接
                heartbeat = json.dumps({'type': 'heartbeat'})
                yield f"data: {heartbeat}\n\n"
                
                # 发送填充数据，强制 Flask 立即发送响应头
                padding = " " * 1024  # 1KB 填充数据
                yield f": padding {padding}\n\n"
                
                logger.debug("📡 心跳和填充数据已发送，开始处理查询...")
                
                # 先发送一个初始内容，确保前端能立即显示
                initial_content = {
                    "type": "content",
                    "content": "正在思考您的问题...\n\n",
                    "accumulated": "正在思考您的问题...\n\n",
                    "timestamp": datetime.now().isoformat()
                }
                yield f"data: {json.dumps(initial_content, ensure_ascii=False)}\n\n"
                yield f": initial-content\n\n"
                
                # 使用完整的 Strands Agent 流式处理
                chunk_count = 0
                async for chunk in emr_assistant.process_query_stream(user_query, user_id):
                    chunk_count += 1
                    logger.debug(f"生成第 {chunk_count} 个数据块: {chunk}")
                    
                    # 确保 JSON 序列化不会失败
                    try:
                        chunk_data = json.dumps(chunk, ensure_ascii=False)
                    except Exception as json_err:
                        print(f"JSON 序列化失败: {str(json_err)}, 尝试简化数据")
                        # 如果序列化失败，尝试简化数据
                        simplified_chunk = {
                            "type": chunk.get("type", "content"),
                            "content": str(chunk.get("content", "")),
                            "timestamp": datetime.now().isoformat()
                        }
                        chunk_data = json.dumps(simplified_chunk, ensure_ascii=False)
                    
                    # 立即发送数据，确保每个块都有完整的 SSE 格式
                    yield f"data: {chunk_data}\n\n"
                    
                    # 添加小的填充数据确保立即传输
                    yield f": chunk-{chunk_count}\n\n"
                    
                    # 强制刷新缓冲区
                    sys.stdout.flush()
                    sys.stderr.flush()
                
                # 发送结束信号
                end_data = json.dumps({'type': 'end'})
                yield f"data: {end_data}\n\n"
                
                print(f"✅ 流式响应完成，共发送 {chunk_count} 个数据块")
                
            except Exception as e:
                import traceback
                logger.error(f"❌ 流式响应错误: {str(e)}")
                print(f"错误堆栈: {traceback.format_exc()}")
                error_data = json.dumps({'type': 'error', 'error': str(e)})
                yield f"data: {error_data}\n\n"
        
        return Response(
            generate_stream(), 
            content_type='text/event-stream',
            headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no',  # 禁用Nginx缓冲
                'Transfer-Encoding': 'chunked'  # 使用分块传输编码
            }
        )
        
    except Exception as e:
        import traceback
        logger.error(f"❌ 处理聊天请求失败: {str(e)}")
        logger.error(f"错误堆栈: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': f'服务器错误: {str(e)}'
        }), 500

@app.route('/chat-sync', methods=['POST'])
async def chat_sync():
    """处理聊天请求 - 同步响应（备用）"""
    try:
        data = await request.get_json()
        user_query = data.get('query', '').strip()
        
        if not user_query:
            return jsonify({
                'success': False,
                'error': '请输入您的问题'
            }), 400
        
        # 从会话中获取用户ID，如果不存在则创建一个新的
        user_id = session.get('user_id')
        if not user_id:
            user_id = str(uuid.uuid4())
            session['user_id'] = user_id
            logger.info(f"在chat-sync请求中创建新的用户会话ID: {user_id}")
        else:
            logger.debug(f"使用现有用户会话ID: {user_id}")
        
        # 处理查询
        result = await emr_assistant.process_query(user_query, user_id)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'服务器错误: {str(e)}'
        }), 500

@app.route('/memory/stats')
async def memory_stats():
    """获取记忆统计信息"""
    try:
        # 从会话中获取用户ID，如果不存在则创建一个新的
        user_id = session.get('user_id')
        if not user_id:
            user_id = str(uuid.uuid4())
            session['user_id'] = user_id
            logger.info(f"在memory/stats请求中创建新的用户会话ID: {user_id}")
        else:
            logger.debug(f"使用现有用户会话ID: {user_id}")
        
        # 为当前用户创建 mem0 实例
        user_mem0 = create_mem0_integration(user_id)
        stats = user_mem0.get_memory_stats()
        
        return jsonify({
            'success': True,
            'stats': stats,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'获取记忆统计失败: {str(e)}'
        }), 500

@app.route('/memory/search', methods=['POST'])
async def search_memories():
    """搜索历史记忆"""
    try:
        data = await request.get_json()
        query = data.get('query', '').strip()
        limit = data.get('limit', 5)
        
        if not query:
            return jsonify({
                'success': False,
                'error': '请输入搜索查询'
            }), 400
        
        # 从会话中获取用户ID，如果不存在则创建一个新的
        user_id = session.get('user_id')
        if not user_id:
            user_id = str(uuid.uuid4())
            session['user_id'] = user_id
            logger.info(f"在memory/search请求中创建新的用户会话ID: {user_id}")
        else:
            logger.debug(f"使用现有用户会话ID: {user_id}")
        
        # 为当前用户创建 mem0 实例
        user_mem0 = create_mem0_integration(user_id)
        memories = user_mem0.search_memories(query, limit)
        
        return jsonify({
            'success': True,
            'memories': memories,
            'query': query,
            'count': len(memories),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'搜索记忆失败: {str(e)}'
        }), 500

@app.route('/memory/recent')
async def get_recent_memories():
    """获取最近的记忆"""
    try:
        limit = int(request.args.get('limit', 10))
        
        # 从会话中获取用户ID，如果不存在则创建一个新的
        user_id = session.get('user_id')
        if not user_id:
            user_id = str(uuid.uuid4())
            session['user_id'] = user_id
            logger.info(f"在memory/recent请求中创建新的用户会话ID: {user_id}")
        else:
            logger.debug(f"使用现有用户会话ID: {user_id}")
        
        # 为当前用户创建 mem0 实例
        user_mem0 = create_mem0_integration(user_id)
        memories = user_mem0.get_recent_memories(limit)
        
        return jsonify({
            'success': True,
            'memories': memories,
            'count': len(memories),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'获取最近记忆失败: {str(e)}'
        }), 500

@app.route('/memory/clear', methods=['POST'])
async def clear_memories():
    """清除所有记忆"""
    try:
        # 从会话中获取用户ID，如果不存在则创建一个新的
        user_id = session.get('user_id')
        if not user_id:
            user_id = str(uuid.uuid4())
            session['user_id'] = user_id
            logger.info(f"在memory/clear请求中创建新的用户会话ID: {user_id}")
        else:
            logger.debug(f"使用现有用户会话ID: {user_id}")
        
        # 为当前用户创建 mem0 实例
        user_mem0 = create_mem0_integration(user_id)
        success = user_mem0.clear_user_memories()
        
        if success:
            return jsonify({
                'success': True,
                'message': '所有记忆已成功清除',
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({
                'success': False,
                'error': '清除记忆失败，请检查系统配置'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'清除记忆失败: {str(e)}'
        }), 500

# 测试流式响应路由已移除

@app.route('/health')
async def health():
    """健康检查"""
    try:
        # 创建一个临时的 mem0 实例来检查状态
        temp_mem0 = create_mem0_integration()
        mem0_enabled = temp_mem0.enabled
    except:
        mem0_enabled = False
    
    return jsonify({
        'status': 'healthy',
        'service': 'EMR Upgrade Assistant',
        'mem0_enabled': mem0_enabled,
        'timestamp': datetime.now().isoformat()
    })

@app.errorhandler(404)
async def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
async def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

# 启动方式提示
if __name__ == '__main__':
    logger.info('请使用 hypercorn 启动此应用，例如:')
    logger.info('hypercorn emr_upgrade_assistant.app:app --bind 0.0.0.0:5001')