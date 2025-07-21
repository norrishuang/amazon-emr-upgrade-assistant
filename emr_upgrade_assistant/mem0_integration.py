"""
Mem0 集成模块 - 实现上下文记忆存储和查询
"""

import os, sys
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler

# 创建日志目录
log_dir = 'logs'
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# 配置日志记录器
def setup_logger():
    logger = logging.getLogger('emr_assistant')
    
    # 如果logger已经有handlers，说明已经初始化过了，直接返回
    if logger.handlers:
        return logger
        
    logger.setLevel(logging.DEBUG)
    # 防止日志传播到根logger，避免重复输出
    logger.propagate = False
    
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

# 确保加载环境变量
load_dotenv()

try:
    from mem0 import Memory
    from opensearchpy import OpenSearch
    MEM0_AVAILABLE = True
except ImportError:
    MEM0_AVAILABLE = False
    Memory = None
    OpenSearch = None

# logger = logging.getLogger(__name__)


class Mem0Integration:
    """Mem0 记忆存储集成类"""
    
    def __init__(self, user_id: Optional[str] = None):
        """初始化 Mem0 集成"""
        self.enabled = os.getenv('MEM0_ENABLED', 'false').lower() == 'true'
        
        # 如果提供了用户ID，使用它；否则生成随机ID
        if user_id:
            self.user_id = user_id
        else:
            import uuid
            self.user_id = f"emr_user_{uuid.uuid4().hex[:8]}"
        
        self.memory = None
        self.opensearch_client = None
        
        if not MEM0_AVAILABLE:
            logger.warning("Mem0 或 OpenSearch 库未安装，记忆功能将被禁用")
            self.enabled = False
            return
        
        if self.enabled:
            self._initialize_mem0()
            self._initialize_opensearch()
    
    def _initialize_mem0(self):
        """初始化 Mem0 记忆系统"""
        try:
            config = {
                "llm": {
                    "provider": "aws_bedrock",
                    "config": {
                        "model": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",  # 使用 Claude 4.0 (Sonnet)
                        "temperature": 0.1,
                        "max_tokens": 2000,
                        # "aws_access_key_id": os.environ.get("AWS_ACCESS_KEY_ID"),
                        # "aws_secret_access_key": os.environ.get("AWS_SECRET_ACCESS_KEY"),
                    }
                },
                "embedder": {
                    "provider": "aws_bedrock", 
                    "config": {
                        "model": "amazon.titan-embed-text-v2:0",
                        # "aws_access_key_id": os.environ.get("AWS_ACCESS_KEY_ID"),
                        # "aws_secret_access_key": os.environ.get("AWS_SECRET_ACCESS_KEY")
                    }
                },
                "vector_store": {
                    "provider": "opensearch",
                    "config": {
                        "host": os.getenv('MEM0_OPENSEARCH_HOST', 'localhost'),
                        "port": int(os.getenv('MEM0_OPENSEARCH_PORT', '9200')),
                        "http_auth": (
                            os.getenv('MEM0_OPENSEARCH_USERNAME', 'admin'), 
                            os.getenv('MEM0_OPENSEARCH_PASSWORD', 'admin')
                        ),
                        "use_ssl": os.getenv('MEM0_OPENSEARCH_USE_SSL', 'false').lower() == 'true',
                        "verify_certs": os.getenv('MEM0_OPENSEARCH_VERIFY_CERTS', 'false').lower() == 'true',
                        "collection_name": os.getenv('MEM0_OPENSEARCH_INDEX', 'emr_assistant_memories'),
                        "embedding_model_dims": 1024
                    }
                },
                "version": "v1.1"
            }
            
            self.memory = Memory.from_config(config)
            logger.info("Mem0 记忆系统初始化成功")
            
        except Exception as e:
            logger.error(f"Mem0 初始化失败: {str(e)}")
            self.enabled = False
    
    def _initialize_opensearch(self):
        """初始化 OpenSearch 客户端（用于直接查询）"""
        try:
            self.opensearch_client = OpenSearch(
                hosts=[{
                    'host': os.getenv('MEM0_OPENSEARCH_HOST', 'localhost'),
                    'port': int(os.getenv('MEM0_OPENSEARCH_PORT', '9200'))
                }],
                http_auth=(
                    os.getenv('MEM0_OPENSEARCH_USERNAME', 'admin'),
                    os.getenv('MEM0_OPENSEARCH_PASSWORD', 'admin')
                ),
                use_ssl=os.getenv('MEM0_OPENSEARCH_USE_SSL', 'false').lower() == 'true',
                verify_certs=os.getenv('MEM0_OPENSEARCH_VERIFY_CERTS', 'false').lower() == 'true',
                ssl_show_warn=False
            )
            
            # 测试连接
            info = self.opensearch_client.info()
            logger.info(f"✅ OpenSearch 连接成功: {info['version']['number']}")
            
        except Exception as e:
            logger.error(f"❌ OpenSearch 连接失败: {str(e)}")
            self.opensearch_client = None
    

    
    def add_memory(self, message: str, user_query: str, response: str, metadata: Optional[Dict] = None) -> bool:
        """添加记忆到存储"""
        if not self.enabled or not self.memory:
            return False
        
        try:
            # 清理用户查询和响应，移除换行符
            clean_user_query = user_query[:100].replace('\n', ' ').replace('\r', ' ')
            clean_response = response[:200].replace('\n', ' ').replace('\r', ' ')
            
            # 构建两轮对话格式
            messages = [
                {"role": "user", "content": f"I need help with Amazon EMR upgrade. {clean_user_query}"},
                {"role": "assistant", "content": f"I can help you with EMR upgrade. {clean_response}"},
                {"role": "user", "content": "Thank you for the information. This is very helpful."},
                {"role": "assistant", "content": "You're welcome! I'll remember your EMR upgrade requirements for future assistance."}
            ]
            
            result = self.memory.add(messages, user_id=self.user_id)
            
            # 检查结果是否有效
            if isinstance(result, dict) and result.get('results') and len(result['results']) > 0:
                print(f"{self.user_id} 记忆添加成功，提取了 {len(result['results'])} 条记忆")
                return True
            else:
                print(f"{self.user_id} 记忆添加返回空结果")
                return False
            
        except Exception as e:
            logger.error(f"{self.user_id} 添加记忆失败: {str(e)}")
            return False
    
    def search_memories(self, query: str, limit: int = 5) -> List[Dict]:
        """搜索相关记忆"""
        if not self.enabled or not self.memory:
            return []
        
        try:
            memories = self.memory.search(query, user_id=self.user_id, limit=limit)
            logger.info(f"找到 {len(memories)} 条相关记忆")
            return memories
            
        except Exception as e:
            logger.error(f"搜索记忆失败: {str(e)}")
            return []
    
    def get_recent_memories(self, limit: int = 10) -> List[Dict]:
        """获取最近的记忆"""
        if not self.enabled or not self.memory:
            return []
        
        try:
            # 根据官方文档，使用正确的 API
            all_memories = self.memory.get_all(user_id=self.user_id)
            
            # 确保返回的是列表格式
            if not isinstance(all_memories, list):
                logger.warning(f"get_all 返回的不是列表格式: {type(all_memories)}")
                return []
            
            # 按时间戳排序，获取最近的记忆
            def get_timestamp(x):
                if isinstance(x, dict):
                    # 尝试不同的时间戳字段
                    if 'created_at' in x:
                        return x['created_at']
                    elif 'updated_at' in x:
                        return x['updated_at']
                    elif 'metadata' in x and isinstance(x['metadata'], dict):
                        return x['metadata'].get('timestamp', '')
                return ''
            
            sorted_memories = sorted(
                all_memories,
                key=get_timestamp,
                reverse=True
            )
            
            return sorted_memories[:limit]
            
        except Exception as e:
            logger.error(f"❌ 获取最近记忆失败: {str(e)}")
            return []
    
    def get_context_for_query(self, user_query: str) -> str:
        """为查询获取相关上下文"""
        if not self.enabled:
            return ""
        
        try:
            # 搜索相关记忆
            relevant_memories = self.search_memories(user_query, limit=3)
            
            if not relevant_memories:
                return ""
            
            # 构建上下文字符串
            context_parts = ["## 相关历史对话上下文"]
            
            for i, memory in enumerate(relevant_memories, 1):
                # 处理不同的记忆数据格式
                if isinstance(memory, dict):
                    # 如果是字典格式
                    memory_text = memory.get('memory', '') or memory.get('text', '') or str(memory)
                    metadata = memory.get('metadata', {})
                    timestamp = metadata.get('timestamp', '') if isinstance(metadata, dict) else ''
                elif isinstance(memory, str):
                    # 如果是字符串格式
                    memory_text = memory
                    timestamp = ''
                else:
                    # 其他格式，转换为字符串
                    memory_text = str(memory)
                    timestamp = ''
                
                context_parts.append(f"""
### 历史对话 {i} ({timestamp[:10] if timestamp else '未知时间'})
{memory_text}
""")
            
            context = "\n".join(context_parts)
            logger.info(f"📝 为查询构建了包含 {len(relevant_memories)} 条记忆的上下文")
            
            return context
            
        except Exception as e:
            logger.error(f"❌ 构建上下文失败: {str(e)}")
            return ""
    
    def clear_user_memories(self) -> bool:
        """清除用户的所有记忆"""
        if not self.enabled or not self.memory:
            return False
        
        try:
            # 获取所有记忆并删除
            all_memories = self.memory.get_all(user_id=self.user_id)
            
            for memory in all_memories:
                if isinstance(memory, dict):
                    memory_id = memory.get('id')
                    if memory_id:
                        self.memory.delete(memory_id=memory_id)
            
            logger.info(f"🗑️ 清除了 {len(all_memories)} 条用户记忆")
            return True
            
        except Exception as e:
            logger.error(f"❌ 清除记忆失败: {str(e)}")
            return False
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """获取记忆统计信息"""
        if not self.enabled:
            return {"enabled": False, "total_memories": 0}
        
        try:
            all_memories = self.memory.get_all(user_id=self.user_id) if self.memory else []
            
            # 处理不同的返回格式
            if isinstance(all_memories, list):
                memory_count = len(all_memories)
            else:
                memory_count = 0
            
            stats = {
                "enabled": True,
                "total_memories": memory_count,
                "user_id": self.user_id,
                "opensearch_connected": self.opensearch_client is not None
            }
            
            # 如果有记忆数据且是列表格式，尝试提取时间戳
            if isinstance(all_memories, list) and all_memories:
                timestamps = []
                for m in all_memories:
                    if isinstance(m, dict):
                        # 尝试不同的时间戳字段
                        timestamp = None
                        if 'created_at' in m:
                            timestamp = m['created_at']
                        elif 'updated_at' in m:
                            timestamp = m['updated_at']
                        elif 'metadata' in m and isinstance(m['metadata'], dict):
                            timestamp = m['metadata'].get('timestamp', '')
                        
                        if timestamp:
                            timestamps.append(timestamp)
                
                if timestamps:
                    timestamps.sort()
                    stats["earliest_memory"] = timestamps[0]
                    stats["latest_memory"] = timestamps[-1]
            
            return stats
            
        except Exception as e:
            logger.error(f"获取记忆统计失败: {str(e)}")
            return {"enabled": False, "error": str(e)}


# 工厂函数：为每次浏览器会话创建新的 Mem0 实例
def create_mem0_integration(user_id: Optional[str] = None) -> Mem0Integration:
    """
    创建新的 Mem0 集成实例
    
    Args:
        user_id: 可选的用户ID，如果不提供则自动生成随机ID
        
    Returns:
        Mem0Integration 实例
    """
    return Mem0Integration(user_id=user_id)

# 默认全局实例（向后兼容）
mem0_integration = create_mem0_integration()