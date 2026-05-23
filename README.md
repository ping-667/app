# QQ群消息监控

面向学生群体的 QQ 群消息实时监控系统 — 自动抓取群聊消息、关键词匹配、桌面通知提醒、Web 数据看板。

**典型场景**：老师在 QQ 群布置作业 / 发布考试通知时，系统第一时间捕获并提醒，避免错过重要信息。

> ## 前提条件
>
> **本系统依赖 NapCatQQ 进行消息采集。使用前必须安装并启动 NapCatQQ！**
>
> 如果 NapCatQQ 未运行，系统将**无法获取任何 QQ 消息**。请务必按照下方的 [OneBot 模式配置](#onebot-模式配置) 完成设置。

## 功能特性

- **OneBot WebSocket 消息采集** — 对接 NapCatQQ，零延迟实时获取群消息
- **截图+OCR 采集** — MSS 截图 + PaddleOCR 文本识别（备选方案）
- **关键词匹配** — 精确匹配 + 正则匹配双模式，支持批量管理
- **桌面通知** — 命中关键词即时弹窗提醒
- **Web 管理面板** — 消息记录浏览、关键词管理、数据统计看板
- **多用户支持** — 注册/登录，数据按用户隔离
- **实时数据看板** — Chart.js 可视化关键词命中排行 & 发送者分布
- **CSV 导出** — 一键导出消息记录
- **Docker 部署** — 支持容器化运行
- **安全加固** — bcrypt 密码哈希、Session 认证、环境变量密钥

## 系统架构

```
┌──────────────────────────────────────────────────┐
│                   采集层                          │
│  ┌──────────────────────┐  ┌──────────────────┐  │
│  │   OneBot WebSocket   │  │    截图+OCR      │  │
│  │  (NapCatQQ — 推荐)   │  │  (mss+PaddleOCR) │  │
│  └──────────┬───────────┘  └────────┬─────────┘  │
│             │                       │             │
│  ┌──────────┴───────────────────────┴─────────┐  │
│  │           检测器 (Detector)                 │  │
│  │   发件人解析 + 关键词匹配 + 去重            │  │
│  └────────────────────┬───────────────────────┘  │
└───────────────────────┼──────────────────────────┘
                        │
┌───────────────────────┼──────────────────────────┐
│                   存储层                          │
│  ┌────────────────────┴─────────────────────┐   │
│  │         SQLite (WAL mode)                │   │
│  │   用户表 / 消息表 / 用户配置表            │   │
│  └────────────────────┬─────────────────────┘   │
└───────────────────────┼──────────────────────────┘
                        │
┌───────────────────────┼──────────────────────────┐
│                   展示层                          │
│  ┌────────────────────┴─────────────────────┐   │
│  │       Flask Web 服务 (端口 5000)          │   │
│  │  ┌──────────┐ ┌──────────┐ ┌─────────┐   │   │
│  │  │ 消息记录 │ │关键词管理│ │数据统计 │   │   │
│  │  └──────────┘ └──────────┘ └─────────┘   │   │
│  └───────────────────────────────────────────┘   │
│  ┌───────────────────────────────────────────┐   │
│  │          桌面通知 (plyer)                 │   │
│  └───────────────────────────────────────────┘   │
└──────────────────────────────────────────────────┘
```

## 快速开始

### 环境要求

- Windows 10/11 64-bit
- Python 3.9+
- QQ（必须安装）

### 第一步：安装并启动 NapCatQQ（必须）

**这是最关键的一步，跳过将无法获取任何消息！**

1. 下载 [NapCatQQ](https://github.com/NapNeko/NapCatQQ)（推荐 Framework 版）
2. 配置 WebSocket 服务（见下方 [OneBot 模式配置](#onebot-模式配置)）
3. 启动 QQ，然后启动 NapCatQQ

### 第二步：启动本系统

```bash
# 克隆仓库
git clone https://github.com/ping-667/app.git
cd app

# 安装依赖
pip install -r requirements.txt

# 启动 Web 服务
python app.py
```

浏览器打开 `http://127.0.0.1:5000`，注册账号后即可使用。

### Docker 部署

```bash
docker compose up -d
```

## 采集模式说明

| 模式 | 原理 | QQ 窗口要求 | 推荐场景 |
|------|------|------------|---------|
| OneBot WS | 对接 NapCatQQ WebSocket | 无需窗口 | **推荐首选，零延迟** |
| 截图+OCR | MSS 截图 → PaddleOCR → 文本匹配 | QQ 需可见 | 备选方案 |

### OneBot 模式配置（必须）

> **NapCatQQ 是本系统的核心依赖，未配置将无法采集消息！**

1. 安装 [NapCatQQ](https://github.com/NapNeko/NapCatQQ)（推荐 Framework 版：[Releases](https://github.com/NapNeko/NapCatQQ/releases)）
2. 启动一次 NapCatQQ，会在 NapCat 目录下生成 `config/` 文件夹
3. 修改 `config/onebot11_<你的QQ号>.json`：
```json
{
  "websocketServers": [{
    "name": "QQ-Monitor",
    "enable": true,
    "host": "0.0.0.0",
    "port": 3001,
    "token": ""
  }]
}
```
4. **先启动 QQ，再启动 NapCatQQ**（顺序不能乱）
5. 启动本系统的 `python app.py`
6. 在 Web 面板「设置」中将采集模式切换为「OneBot WS」

## 项目结构

```
├── app.py               # Flask Web 服务入口
├── config.py            # 配置管理 + 默认关键词
├── database.py          # SQLite 数据层 (bcrypt 认证)
├── detector.py          # 关键词检测 + 发送者解析 + 去重
├── monitor.py           # 监控引擎 (截图/OCR/OneBot 多模式)
├── onebot_client.py     # OneBot 11 WebSocket 客户端
├── utils.py             # DPI 感知 + 日志配置
├── loadNapCat.js        # NapCatQQ 快速启动脚本
├── Dockerfile           # Docker 镜像
├── docker-compose.yml   # Docker Compose 配置
├── requirements.txt     # Python 依赖
├── 启动.bat             # Windows 一键启动脚本
├── static/
│   ├── style.css        # 前端样式 (暗色监控控制台主题)
│   └── app.js           # 前端逻辑 (Chart.js 可视化)
└── templates/
    ├── index.html       # 主页面
    └── login.html       # 登录页
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | Flask |
| OCR 引擎 | PaddleOCR (PP-OCRv4) |
| 屏幕截图 | MSS |
| 消息协议 | OneBot 11 (WebSocket) |
| QQ 框架 | NapCatQQ |
| 数据库 | SQLite (WAL mode) |
| 密码哈希 | bcrypt |
| 前端可视化 | Chart.js 4.x |
| 前端样式 | 纯 CSS (暗色监控控制台主题) |
| 部署 | Docker / Docker Compose |

## 公网访问

如需让他人通过公网使用：

- **内网穿透**：使用 [frp](https://github.com/fatedier/frp) 或 [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
- **反向代理**：Nginx + HTTPS（推荐配合 Let's Encrypt）
- **环境变量**：设置 `QQ_MONITOR_SECRET` 为强随机字符串以保护 Session 安全

## License

MIT
