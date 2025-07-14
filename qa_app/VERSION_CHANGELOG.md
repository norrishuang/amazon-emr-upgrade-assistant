# 版本更新日志

## v0.1 (2025-06-17)

### 新增功能
- 在页面头部添加版本号显示
- 版本号以蓝色徽章形式显示在应用标题旁边
- 在后端代码中添加 `APP_VERSION` 常量，便于版本管理

### 技术实现
- 在 `app_conversational.py` 中定义 `APP_VERSION = "v0.1"`
- 修改 `index()` 路由，将版本号传递给模板
- 在 `index_conversational.html` 中添加版本号显示和相关CSS样式
- 版本号样式：蓝色背景，白色文字，圆角徽章设计

### 文件修改
- `app_conversational.py`: 添加版本号常量和模板变量传递
- `templates/index_conversational.html`: 添加版本号显示和CSS样式

### 使用说明
- 版本号会自动显示在页面标题"Amazon EMR 升级助手"旁边
- 要更新版本号，只需修改 `app_conversational.py` 中的 `APP_VERSION` 常量
