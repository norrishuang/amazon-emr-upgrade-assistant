"""
Mem0 工具集 - 为 Strands Agent 提供记忆功能
"""

from strands import tool
from typing import List, Dict, Any
from mem0_integration import create_mem0_integration
import threading

# 线程本地存储，用于存储当前用户的 mem0 实例
_thread_local = threading.local()

def set_current_user_mem0(user_mem0):
    """设置当前线程的用户 mem0 实例"""
    _thread_local.user_mem0 = user_mem0

def get_current_user_mem0():
    """获取当前线程的用户 mem0 实例"""
    return getattr(_thread_local, 'user_mem0', None)
import logging

logger = logging.getLogger(__name__)


@tool
def search_conversation_history(query: str, limit: int = 5) -> str:
    """
    搜索历史对话记录，找到与当前问题相关的上下文信息
    
    Args:
        query (str): 搜索查询，用于找到相关的历史对话
        limit (int): 返回结果的最大数量，默认为5
    
    Returns:
        str: 相关的历史对话上下文，如果没有找到则返回空字符串
    """
    try:
        user_mem0 = get_current_user_mem0()
        if not user_mem0:
            return "记忆系统未正确初始化。"
        
        memories = user_mem0.search_memories(query, limit)
        
        if not memories:
            return "没有找到相关的历史对话记录。"
        
        context_parts = ["找到以下相关的历史对话：\n"]
        
        for i, memory in enumerate(memories, 1):
            memory_text = memory.get('memory', '')
            metadata = memory.get('metadata', {})
            timestamp = metadata.get('timestamp', '')
            
            context_parts.append(f"""
{i}. 时间: {timestamp[:19] if timestamp else '未知'}
内容: {memory_text[:200]}{'...' if len(memory_text) > 200 else ''}
""")
        
        return "\n".join(context_parts)
        
    except Exception as e:
        logger.error(f"搜索历史对话失败: {str(e)}")
        return f"搜索历史对话时出错: {str(e)}"


@tool
def get_recent_conversations(limit: int = 5) -> str:
    """
    获取最近的对话记录
    
    Args:
        limit (int): 返回结果的最大数量，默认为5
    
    Returns:
        str: 最近的对话记录
    """
    try:
        user_mem0 = get_current_user_mem0()
        if not user_mem0:
            return "记忆系统未正确初始化。"
        
        memories = user_mem0.get_recent_memories(limit)
        
        if not memories:
            return "没有找到最近的对话记录。"
        
        context_parts = ["最近的对话记录：\n"]
        
        for i, memory in enumerate(memories, 1):
            memory_text = memory.get('memory', '')
            metadata = memory.get('metadata', {})
            timestamp = metadata.get('timestamp', '')
            
            context_parts.append(f"""
{i}. 时间: {timestamp[:19] if timestamp else '未知'}
内容: {memory_text[:150]}{'...' if len(memory_text) > 150 else ''}
""")
        
        return "\n".join(context_parts)
        
    except Exception as e:
        logger.error(f"获取最近对话失败: {str(e)}")
        return f"获取最近对话时出错: {str(e)}"


@tool
def get_memory_statistics() -> str:
    """
    获取记忆系统的统计信息
    
    Returns:
        str: 记忆系统的统计信息
    """
    try:
        user_mem0 = get_current_user_mem0()
        if not user_mem0:
            return "记忆系统未正确初始化。"
        
        stats = user_mem0.get_memory_stats()
        
        if not stats.get('enabled', False):
            return "记忆系统未启用或配置错误。"
        
        info_parts = [
            f"记忆系统状态: {'正常' if stats['enabled'] else '异常'}",
            f"总记忆数量: {stats.get('total_memories', 0)}",
            f"用户ID: {stats.get('user_id', '未知')}",
            f"OpenSearch连接: {'正常' if stats.get('opensearch_connected', False) else '异常'}"
        ]
        
        if stats.get('earliest_memory'):
            info_parts.append(f"最早记忆: {stats['earliest_memory'][:19]}")
        
        if stats.get('latest_memory'):
            info_parts.append(f"最新记忆: {stats['latest_memory'][:19]}")
        
        return "\n".join(info_parts)
        
    except Exception as e:
        logger.error(f"获取记忆统计失败: {str(e)}")
        return f"获取记忆统计时出错: {str(e)}"


@tool
def clear_conversation_history() -> str:
    """
    清除所有历史对话记录
    
    Returns:
        str: 操作结果
    """
    try:
        user_mem0 = get_current_user_mem0()
        if not user_mem0:
            return "记忆系统未正确初始化。"
        
        success = user_mem0.clear_user_memories()
        
        if success:
            return "✅ 已成功清除所有历史对话记录。"
        else:
            return "❌ 清除历史对话记录失败，请检查系统配置。"
        
    except Exception as e:
        logger.error(f"清除历史对话失败: {str(e)}")
        return f"清除历史对话时出错: {str(e)}"


# 导出所有工具
mem0_tools = [
    search_conversation_history,
    get_recent_conversations,
    get_memory_statistics,
    clear_conversation_history
]