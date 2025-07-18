from quart import Quart, render_template, request, jsonify, Response
import os
import json
import asyncio
from typing import Dict, Any
from dotenv import load_dotenv
import uuid
from datetime import datetime

# 根据官方文档导入 Strands Agents 和 MCP 相关模块
from mcp import stdio_client, StdioServerParameters
from strands import Agent
from strands.tools.mcp import MCPClient
from mem0_integration import create_mem0_integration
from mem0_tools import mem0_tools
from strands.models import BedrockModel

load_dotenv()

app = Quart(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'emr-upgrade-assistant-secret-key')

# 禁用 Quart 的缓冲，确保流式响应立即发送
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['TEMPLATES_AUTO_RELOAD'] = True

class EMRUpgradeAssistant:
    """Amazon EMR 版本升级助手 - 基于 Strands Agents"""
    
    def __init__(self):
        try:
            # 不在初始化时创建 mem0 实例，而是在每次请求时创建
            self.mem0 = None
            
            print("🚀 开始初始化 EMR 升级助手...")
            
            # 根据官方文档配置 MCP 客户端
            # 参考: https://strandsagents.com/latest/user-guide/concepts/tools/mcp-tools/
            
            # 获取项目根目录和 MCP Server 目录
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
            mcp_server_dir = os.path.join(project_root, 'mcp_server')
            
            # 根据你提供的配置，使用 uv 命令创建 MCP 客户端
            # 配置格式: {"mcpServers": {"opensearch_mcp_server": {"command": "uv","args": ["--directory","/path/to/mcp_server","run","app.py"]}}}
            self.mcp_client = MCPClient(lambda: stdio_client(
                StdioServerParameters(
                    command="uv",
                    args=["--directory", mcp_server_dir, "run", "app.py"]
                )
            ))
            
            print("✅ MCP 客户端初始化成功")
            print(f"📡 MCP Server 目录: {mcp_server_dir}")
            
            # 注意：根据官方文档，Agent 必须在 MCP 客户端的上下文管理器中创建和使用
            self.agent = None  # 将在 process_query 中创建
            
            print("🚀 EMR 升级助手 (Strands Agents) 初始化完成")
            
        except ImportError as e:
            print(f"❌ Strands Agents 导入失败: {str(e)}")
            print("请确保已正确安装 Strands Agents:")
            print("pip install strands-agents")
            print("pip install strands-agents-tools")
            print("pip install strands-agents-builder")
            self.agent = None
        except Exception as e:
            print(f"❌ Agent 初始化失败: {str(e)}")
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

当用户询问 EMR 升级相关问题时，请先使用 search_context 工具检索相关信息，然后基于检索结果提供专业的回答。

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
        
        print(f"📝 开始模拟流式输出，内容长度: {len(text)}")
        
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
            print(f"🔧 [简化版] 开始处理查询: {user_query}")
            print(f"🔧 [简化版] MCP Client 状态: {self.mcp_client is not None}")
            
            # 直接返回一个测试响应
            test_response = f"收到您的问题：{user_query}\n\n这是一个测试响应，用于验证流式输出是否正常工作。"
            
            print(f"🔧 [简化版] 开始模拟流式输出，内容长度: {len(test_response)}")
            
            # 模拟流式输出
            chunk_count = 0
            for chunk in self._stream_text_output(test_response):
                chunk_count += 1
                print(f"🔧 [简化版] 生成第 {chunk_count} 个数据块: {chunk}")
                yield chunk
            
            print(f"✅ [简化版] 流式输出完成，共生成 {chunk_count} 个数据块")
                
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
            print(f"📝 开始流式处理用户查询: {user_query}")
            with self.mcp_client:
                mcp_tools = self.mcp_client.list_tools_sync()
                all_tools = mcp_tools + mem0_tools
                print(f"🔧 获取到 {len(mcp_tools)} 个 MCP 工具，{len(mem0_tools)} 个 mem0 工具")
                try:
                    bedrock_model = BedrockModel(
                        model_id="us.anthropic.claude-3-5-sonnet-20241022-v2:0",
                        region_name="us-east-1",
                        temperature=0.3,
                    )
                    agent = Agent(
                        tools=all_tools,
                        callback_handler=None,
                        model=bedrock_model
                    )
                    print("✅ 成功创建使用 Claude 4.0 Sonnet 的 Agent")
                except Exception as model_error:
                    print(f"⚠️ 使用 Claude 4.0 Sonnet 创建 Agent 失败: {str(model_error)}")
                    print("尝试使用默认模型创建 Agent")
                    agent = Agent(tools=all_tools, callback_handler=None)
                if hasattr(agent, 'model') and hasattr(agent.model, 'config'):
                    print(f"🔧 使用模型配置: {agent.model.config}")
                else:
                    print("⚠️ 无法获取模型配置信息")
                user_mem0 = create_mem0_integration(user_id)
                from mem0_tools import set_current_user_mem0
                set_current_user_mem0(user_mem0)
                historical_context = user_mem0.get_context_for_query(user_query)
                system_instructions = self._get_instructions()
                if historical_context:
                    full_query = f"{system_instructions}\n\n{historical_context}\n\n用户问题: {user_query}"
                    print(f"📚 添加了历史上下文，长度: {len(historical_context)}")
                else:
                    full_query = f"{system_instructions}\n\n用户问题: {user_query}"
                print(f"🔧 开始 Strands Agent 流式调用...")
                accumulated_response = ""
                async def async_stream():
                    nonlocal accumulated_response
                    try:
                        async for event in agent.stream_async(full_query):
                            # 注释掉 MCP Server 查询返回的日志打印
                            # print("Agent event:", event)  # 打印所有 event
                            # LLM 内容流式返回
                            if "data" in event:
                                content = event["data"]
                                if content:
                                    accumulated_response += content
                                    print(f"📝 LLM流式内容: {content}")
                                    yield {
                                        "type": "content",
                                        "content": content,
                                        "accumulated": accumulated_response,
                                        "timestamp": datetime.now().isoformat()
                                    }
                            # 工具调用事件
                            if "current_tool_use" in event and event["current_tool_use"].get("name"):
                                tool_name = event["current_tool_use"]["name"]
                                print(f"🔧 工具调用: {tool_name}")
                                yield {
                                    "type": "status",
                                    "message": f"[使用工具: {tool_name}]",
                                    "timestamp": datetime.now().isoformat()
                                }
                            # MCP Server 工具返回内容 - 关闭日志打印
                            if "tool_response" in event and event["tool_response"]:
                                # print(f"🟢 MCP Server 工具返回内容: {event['tool_response']}")
                                pass
                    except Exception as e:
                        print(f"❌ 异步流式调用失败: {str(e)}")
                        yield {
                            "type": "error",
                            "error": str(e),
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
                        print("💾 对话记忆已保存到 mem0")
                    except Exception as mem_error:
                        print(f"⚠️ 保存记忆失败: {str(mem_error)}")
        except Exception as e:
            print(f"❌ 流式处理查询时出错: {str(e)}")
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
            print(f"📝 处理用户查询: {user_query}")
            
            # 根据官方文档，必须在 MCP 客户端的上下文管理器中使用 Agent
            with self.mcp_client:
                # 获取 MCP 服务器提供的工具
                tools = self.mcp_client.list_tools_sync()
                print(f"🔧 获取到 {len(tools)} 个 MCP 工具")
                
                # 在上下文管理器中创建 Agent
                # 根据 Strands Agents API，Agent 初始化不接受 instructions 参数
                agent = Agent(tools=tools)
                
                # 构建包含系统指令的完整查询
                system_instructions = self._get_instructions()
                full_query = f"{system_instructions}\n\n用户问题: {user_query}"
                
                # 使用 Agent 处理查询
                response = agent(full_query)
                
                print("✅ Strands Agent 处理完成")
                
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
            print(f"❌ 处理查询时出错: {str(e)}")
            return {
                "success": False,
                "error": f"处理查询时出错: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }

# 初始化助手
emr_assistant = EMRUpgradeAssistant()

@app.route('/')
async def index():
    """主页"""
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
        
        # 临时去掉 session，直接用随机 user_id
        import uuid
        user_id = str(uuid.uuid4())
        
        # 返回流式响应 - 强制实时传输，添加填充数据
        async def generate_stream():
            import sys
            import os
            
            # 强制禁用 Python 的输出缓冲
            os.environ['PYTHONUNBUFFERED'] = '1'
            
            try:
                print("🔄 开始生成流式响应...")
                
                # 立即发送心跳和填充数据，强制建立连接
                heartbeat = json.dumps({'type': 'heartbeat'})
                yield f"data: {heartbeat}\n\n"
                
                # 发送填充数据，强制 Flask 立即发送响应头
                padding = " " * 1024  # 1KB 填充数据
                yield f": padding {padding}\n\n"
                
                print("📡 心跳和填充数据已发送，开始处理查询...")
                
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
                    print(f"生成第 {chunk_count} 个数据块: {chunk}")
                    
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
                print(f"❌ 流式响应错误: {str(e)}")
                print(f"错误堆栈: {traceback.format_exc()}")
                error_data = json.dumps({'type': 'error', 'error': str(e)})
                yield f"data: {error_data}\n\n"
        
        return Response(generate_stream(), content_type='text/event-stream')
        
    except Exception as e:
        import traceback
        print(f"❌ 处理聊天请求失败: {str(e)}")
        print(f"错误堆栈: {traceback.format_exc()}")
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
        
        # 获取或创建用户会话ID
        user_id = str(uuid.uuid4())
        
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
        # 获取或创建用户会话ID
        user_id = str(uuid.uuid4())
        
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
        
        # 获取或创建用户会话ID
        user_id = str(uuid.uuid4())
        
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
        
        # 获取或创建用户会话ID
        user_id = str(uuid.uuid4())
        
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
        # 获取或创建用户会话ID
        user_id = str(uuid.uuid4())
        
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

@app.route('/test-stream')
async def test_stream():
    """测试流式响应 - 最简单的版本"""
    async def generate_test_stream():
        import asyncio
        yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        test_messages = [
            "这是第一条测试消息",
            "这是第二条测试消息",
            "这是第三条测试消息",
            "流式响应测试完成！"
        ]
        for i, msg in enumerate(test_messages):
            chunk_data = {
                "type": "content",
                "content": msg,
                "accumulated": " ".join(test_messages[:i+1]),
                "timestamp": datetime.now().isoformat()
            }
            yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.5)
        yield f"data: {json.dumps({'type': 'end'})}\n\n"
    return Response(generate_test_stream(), content_type='text/event-stream')

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
    print('请使用 hypercorn 启动此应用，例如:')
    print('hypercorn emr_upgrade_assistant.app:app --bind 0.0.0.0:5001')