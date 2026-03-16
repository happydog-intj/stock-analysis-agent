# 股票分析 Agent — 汇量科技 1860.HK

> 基于 Claude AI 的多源数据采集、情绪分析与自动化报告系统，以汇量科技（汇量科技集团，1860.HK）为核心案例。

---

## 项目简介

本项目通过多个数据采集器（雪球、Reddit、港交所披露易、Yahoo Finance）持续收集与汇量科技相关的舆情与市场数据，利用 Claude API 进行情绪打分与主题提炼，并在每天固定时间（09:00 / 12:00 / 15:00）通过飞书 Webhook 自动推送晨报、午报、收盘报。

---

## 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                       Orchestrator Agent                        │
│              (协调采集 → 分析 → 报告整个流程)                        │
└───────┬────────────────┬────────────────┬───────────────────────┘
        │                │                │
   ┌────▼────┐      ┌────▼────┐     ┌─────▼─────┐
   │Sentiment│      │Industry │     │ Financial │
   │  Agent  │      │  Agent  │     │   Agent   │
   └────┬────┘      └────┬────┘     └─────┬─────┘
        │                │                │
┌───────▼────────────────▼────────────────▼────────────┐
│                    Collectors Layer                    │
│  ┌──────────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌────────┐  │
│  │  Xueqiu  │ │Reddit│ │ HKEX │ │Yahoo │ │Futu/   │  │
│  │(Playwright│ │(PRAW)│ │(HTTP)│ │Fin.  │ │Tiger   │  │
│  └────┬─────┘ └──┬───┘ └──┬───┘ └──┬───┘ └───┬────┘  │
└───────┼──────────┼────────┼────────┼──────────┼───────┘
        └──────────┴────────┴────────┴──────────┘
                            │
              ┌─────────────▼──────────────┐
              │     PostgreSQL + Redis      │
              │  (持久化存储 + 增量状态缓存)  │
              └─────────────┬──────────────┘
                            │
              ┌─────────────▼──────────────┐
              │      Analysis Layer         │
              │  Claude API · 情绪分析       │
              │  竞对比较 · 财务指标          │
              └─────────────┬──────────────┘
                            │
              ┌─────────────▼──────────────┐
              │      Reporter Layer         │
              │  飞书富文本卡片 · 晨/午/收盘报 │
              └────────────────────────────┘
```

---

## 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <repo-url>
cd stock-analysis-agent

# 创建虚拟环境（推荐 Python 3.11+）
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入各平台密钥
```

### 3. 启动基础服务

```bash
docker-compose up -d   # 启动 PostgreSQL + Redis
```

### 4. 初始化数据库

```bash
python scripts/run.py --init-db
```

### 5. 启动调度器

```bash
python scripts/run.py
```

### 6. 历史数据回填

```bash
python scripts/backfill.py --ticker 1860.HK --days 30
```

---

## 配置说明

| 变量 | 说明 | 示例 |
|------|------|------|
| `DB_URL` | PostgreSQL 连接串 | `postgresql+asyncpg://user:pass@localhost:5432/stockdb` |
| `REDIS_URL` | Redis 连接串 | `redis://localhost:6379/0` |
| `CLAUDE_API_KEY` | Anthropic Claude API 密钥 | `sk-ant-...` |
| `FEISHU_WEBHOOK` | 飞书机器人 Webhook URL | `https://open.feishu.cn/open-apis/bot/v2/hook/xxx` |
| `REDDIT_CLIENT_ID` | Reddit App Client ID | — |
| `REDDIT_CLIENT_SECRET` | Reddit App Secret | — |
| `REDDIT_USER_AGENT` | Reddit 请求 UA | `StockBot/1.0` |
| `FUTU_HOST` | FutuOpenD 服务地址 | `127.0.0.1` |
| `FUTU_PORT` | FutuOpenD 服务端口 | `11111` |
| `TIGER_TIGER_ID` | Tiger Broker Tiger ID | — |
| `TIGER_PRIVATE_KEY` | Tiger RSA 私钥 | — |

---

## 目录结构

```
stock-analysis-agent/
├── config/            # 全局配置（pydantic-settings）
├── src/
│   ├── agents/        # Agent 编排层
│   ├── collectors/    # 数据采集层
│   ├── analysis/      # 分析层（Claude / 财务 / 竞对）
│   ├── scheduler/     # APScheduler 定时任务
│   ├── reporters/     # 飞书报告推送
│   └── db/            # ORM 模型 & 数据库连接
├── tests/             # 单元测试
├── scripts/           # 入口脚本
└── docker-compose.yml # 本地基础设施
```

---

## 监控指标（汇量科技 1860.HK）

- **主要竞对**：AppLovin（APP）、Unity Ads（U）、Digital Turbine（APPS）
- **核心业务**：程序化广告（Mintegral DSP/SSP）、移动应用发行
- **关键词**：Mobvista, Mintegral, 汇量科技, 1860.HK
- **港交所公告分类**：业绩公告（P3）、回购（P2）、股权变动（P2）、一般公告（P1）

---

## License

MIT
