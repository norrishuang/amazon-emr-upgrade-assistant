#!/usr/bin/env python3
"""
简单测试脚本，验证版本号是否正确显示
"""

import sys
import os

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from app_conversational import APP_VERSION
    print(f"✅ 应用版本号: {APP_VERSION}")
    print("✅ 版本号常量导入成功")
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ 其他错误: {e}")
    sys.exit(1)

print("✅ 版本号功能测试通过")
