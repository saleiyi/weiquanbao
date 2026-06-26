# 🛡️ 维权宝 - 聊天记录取证与 AI 智能分析

一站式导出钉钉、微信、QQ、飞书的聊天记录，AI 智能分析维权要素，生成专业维权方案。

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| 📱 多平台支持 | 钉钉、微信、QQ、飞书四大平台 |
| 🤖 AI 智能分析 | 接入 OpenAI / DeepSeek / 智谱，自动识别案件类型 |
| 📊 证据评估 | 自动评估证据强度，识别证据缺口 |
| ⚖️ 法律依据 | 根据案件类型匹配相关法律条文 |
| 📅 时间线 | 从聊天记录中提取关键时间节点 |
| 💰 赔偿计算 | 智能计算赔偿/补偿预期 |
| 📝 维权步骤 | 生成带费用和时效的具体行动方案 |
| 🔍 跨平台搜索 | 跨平台关键词搜索 |

## 📱 平台支持

| 平台 | 使用方式 | 状态 |
|------|----------|------|
| 钉钉 | 自动检测本地数据 | ✅ 最简单 |
| 微信 | 自动从内存提取密钥 | ✅ 简单 |
| 飞书 | 开放平台 API | ⚠️ 需配置 |
| QQ | 借助 qq-chat-exporter | ⚠️ 需先导出 |

## ⚡ 快速开始

### 方式一：下载 EXE（推荐）

1. 从 [Releases](https://github.com/saleiyi/weiquanbao/releases) 下载最新版本
2. 双击 `weiquanbao.exe` 运行
3. 浏览器访问 `http://localhost:8090`

### 方式二：Python 源码

```bash
# 安装依赖
pip install fastapi uvicorn apscheduler pymem cryptography zstandard

# 启动
python main.py

# 浏览器访问
http://localhost:8090
```

### 方式三：Docker 部署

```bash
# 构建并启动
docker compose up -d

# 或手动构建
docker build -t weiquanbao .
docker run -p 8090:8090 -e OPENAI_API_KEY=sk-xxx weiquanbao
```

## 🤖 AI 分析配置

在网页端点击 ⚙️ 按钮配置 API Key，支持：

| 服务 | API Base | 模型 |
|------|----------|------|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 智谱 | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` |

也可通过环境变量配置：

```bash
export OPENAI_API_KEY=sk-xxx
export OPENAI_API_BASE=https://api.openai.com/v1
export OPENAI_MODEL=gpt-4o-mini
```

未配置 API Key 时自动使用增强规则引擎。

## 📁 项目结构

```
weiquanbao/
├── main.py              # 入口
├── config.py            # 配置
├── ai_analyzer.py       # AI 分析引擎
├── web/
│   ├── api.py           # 后端 API
│   └── static/          # 前端页面
├── platforms/
│   ├── base.py          # 平台基类
│   ├── dingtalk.py      # 钉钉
│   ├── wechat.py        # 微信
│   ├── qq.py            # QQ
│   └── feishu.py        # 飞书
├── tools/               # 辅助工具
├── Dockerfile           # Docker 构建
└── docker-compose.yml   # Docker Compose
```

## 🔧 各平台使用指南

### 钉钉（最简单）

确保电脑上安装了钉钉并登录过，启动维权宝后自动检测。

### 微信（简单）

确保微信正在运行并已登录，需管理员权限运行维权宝。

### 飞书（需配置）

```bash
python tools/feishu_setup.py
```

按提示完成飞书开放平台应用创建和授权。

### QQ（需先导出）

使用 [qq-chat-exporter](https://github.com/shuakami/qq-chat-exporter/releases) 先导出 JSON，再在维权宝中导入。

## 📄 法律声明

- 本工具仅用于**合法维权取证**，请勿用于非法用途
- 导出的数据包含个人隐私，请妥善保管
- 使用本工具前请确保已获得相关方授权

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📝 License

MIT
