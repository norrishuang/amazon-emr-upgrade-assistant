#!/usr/bin/env python3
"""
使用 gunicorn 运行 EMR 升级助手，支持真正的流式响应
"""

import os
import sys

def main():
    """启动支持流式响应的服务器"""
    
    # 强制禁用缓冲
    os.environ['PYTHONUNBUFFERED'] = '1'
    
    port = int(os.getenv('PORT', 5001))
    
    print(f"🚀 启动 EMR 升级助手服务（流式响应模式）...")
    print(f"📡 访问地址: http://localhost:{port}")
    print(f"🔧 使用 gunicorn 服务器确保真正的流式响应")
    
    try:
        # 尝试使用 gunicorn
        import gunicorn.app.wsgiapp as wsgi
        
        # gunicorn 配置
        sys.argv = [
            'gunicorn',
            '--bind', f'0.0.0.0:{port}',
            '--workers', '1',  # 单进程确保流式响应
            '--worker-class', 'sync',  # 同步工作模式
            '--timeout', '300',  # 5分钟超时
            '--keep-alive', '2',
            '--max-requests', '1000',
            '--preload',  # 预加载应用
            '--access-logfile', '-',  # 输出访问日志
            '--error-logfile', '-',   # 输出错误日志
            '--log-level', 'info',
            'app:app'  # 应用模块
        ]
        
        wsgi.run()
        
    except ImportError:
        print("⚠️ gunicorn 不可用，尝试使用 waitress...")
        
        try:
            from waitress import serve
            from app import app
            
            print("🚀 使用 waitress 服务器")
            serve(
                app,
                host='0.0.0.0',
                port=port,
                threads=4,
                connection_limit=1000,
                cleanup_interval=30,
                channel_timeout=120
            )
            
        except ImportError:
            print("❌ 无法找到合适的 WSGI 服务器")
            print("请安装 gunicorn 或 waitress:")
            print("pip install gunicorn")
            print("或")
            print("pip install waitress")
            sys.exit(1)

if __name__ == '__main__':
    main()