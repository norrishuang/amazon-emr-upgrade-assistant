#!/bin/bash

# Amazon EMR 版本升级助手启动脚本

echo "🚀 启动 Amazon EMR 版本升级助手..."

# 检查 Python 版本
python_version=$(python3 --version 2>&1)
echo "Python 版本: $python_version"

# 检查是否存在虚拟环境
if [ ! -d "venv" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
echo "🔧 激活虚拟环境..."
source venv/bin/activate

# 安装 Strands Agents
echo "🚀 安装 Strands Agents..."
pip install strands-agents
pip install strands-agents-tools
pip install strands-agents-builder

# 如果没有安装 uv，请先安装
pip install uv

# 安装其他依赖
echo "📚 安装其他依赖包..."
pip install -r requirements.txt

# 检查环境变量文件
if [ ! -f ".env" ]; then
    echo "⚠️  未找到 .env 文件，请复制 .env.example 并配置相关参数"
    echo "cp .env.example .env"
    echo "然后编辑 .env 文件配置您的 AWS 和 OpenSearch 参数"
    exit 1
fi

# 检查 AWS 凭证
echo "🔐 检查 AWS 配置..."
if ! aws sts get-caller-identity > /dev/null 2>&1; then
    echo "⚠️  AWS 凭证未配置或无效，请配置 AWS CLI 或设置环境变量"
    echo "aws configure"
    exit 1
fi

# 启动应用
echo "🌟 启动 EMR 升级助手..."
echo "访问地址: http://localhost:5001"
echo "按 Ctrl+C 停止服务"
echo ""

python app.py