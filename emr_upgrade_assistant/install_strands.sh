#!/bin/bash

# Strands Agent SDK 安装脚本

echo "🚀 开始安装 Strands Agent SDK..."

# 安装 Strands Agents 相关包
echo "📦 安装 strands-agents..."
pip install strands-agents

if [ $? -ne 0 ]; then
    echo "❌ strands-agents 安装失败"
    exit 1
fi

echo "📦 安装 strands-agents-tools..."
pip install strands-agents-tools

if [ $? -ne 0 ]; then
    echo "❌ strands-agents-tools 安装失败"
    exit 1
fi

echo "📦 安装 strands-agents-builder..."
pip install strands-agents-builder

if [ $? -ne 0 ]; then
    echo "❌ strands-agents-builder 安装失败"
    exit 1
fi

echo "✅ Strands Agent SDK 安装完成！"
echo ""
echo "📚 请参考官方文档: https://strandsagents.com/latest/user-guide/quickstart/"
echo "� 现在从可以开始使用 Strands Agents 了"