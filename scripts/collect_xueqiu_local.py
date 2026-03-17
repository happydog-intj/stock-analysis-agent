#!/usr/bin/env python3
"""
scripts/collect_xueqiu_local.py — 雪球本机采集脚本

在本机定时运行（crontab），采集 1860.HK 相关帖子及行情，
以 Markdown + JSON 格式创建 GitHub Issue（label: xueqiu-data），
供 GitHub Action 读取做情绪分析。

使用方式：
  python scripts/collect_xueqiu_local.py [--token XQ_A_TOKEN] [--count 30]

环境变量（优先级低于命令行参数）：
  XUEQIU_COOKIES   xq_a_token 的值
  GH_REPO          目标仓库，默认 happydog-intj/stock-analysis-agent

定时任务示例（每天早8点、12点、收盘后16点各跑一次）：
  0 8,12,16 * * 1-5 cd /path/to/stock-analysis-agent && python scripts/collect_xueqiu_local.py
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime

# ── 依赖检查 ──────────────────────────────────────────────────────────
try:
    import pysnowball
    import requests
except ImportError:
    print("[ERROR] 缺少依赖，请先安装：pip install pysnowball requests")
    sys.exit(1)

# ── 配置 ──────────────────────────────────────────────────────────────
DEFAULT_SYMBOL    = "HK01860"
DEFAULT_TICKER    = "1860.HK"
DEFAULT_COUNT     = 30
GH_LABEL          = "xueqiu-data"
GH_LABEL_COLOR    = "#e6b800"
GH_LABEL_DESC     = "雪球自动采集数据"


# ── 工具函数 ──────────────────────────────────────────────────────────

def extract_token(raw: str) -> str:
    """从 cookie 字符串或纯 token 中提取 xq_a_token。"""
    raw = raw.strip()
    if "=" not in raw:
        return raw
    m = re.search(r"xq_a_token=([^;]+)", raw)
    return m.group(1).strip() if m else raw.split("=", 1)[1].strip()


def fetch_timeline(token: str, symbol: str, count: int) -> list[dict]:
    """获取股票讨论区 timeline 帖子。"""
    headers = {
        "Host": "xueqiu.com",
        "Cookie": f"xq_a_token={token}",
        "User-Agent": "Xueqiu iPhone 14.15.1",
        "Accept": "application/json",
        "Accept-Language": "zh-Hans-CN;q=1",
        "Accept-Encoding": "gzip, deflate",
        "Referer": f"https://xueqiu.com/S/{symbol}",
    }
    url = "https://xueqiu.com/v4/statuses/public_timeline_by_symbol.json"
    resp = requests.get(url, params={"count": count, "symbol": symbol},
                        headers=headers, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"timeline API 返回 {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    if not data.get("statuses"):
        # 尝试备用接口
        url2 = "https://xueqiu.com/query/v1/symbol/search/status.json"
        code = symbol.replace("HK", "").lstrip("0") or "01860"
        resp2 = requests.get(url2,
            params={"count": count, "symbol": code, "type": "11"},
            headers=headers, timeout=15)
        if resp2.status_code == 200:
            text = resp2.content.decode("utf-8", errors="replace")
            if text.strip().startswith("{"):
                data2 = resp2.json()
                return data2.get("list", [])
    return data.get("statuses", [])


def fetch_quote(symbol: str) -> dict:
    """获取实时行情（pysnowball）。"""
    try:
        result = pysnowball.quote_detail(symbol)
        return result.get("data", {}).get("quote", {})
    except Exception as e:
        print(f"[WARN] 行情获取失败: {e}")
        return {}


def parse_post(raw: dict, ticker: str) -> dict | None:
    """解析原始帖子为统一结构。"""
    text = raw.get("text") or raw.get("description") or raw.get("content") or ""
    text = re.sub(r"<[^>]+>", "", text).strip()
    if not text:
        return None

    user = raw.get("user") or {}
    created_ms = raw.get("created_at")
    captured_at = (
        datetime.fromtimestamp(created_ms / 1000, tz=UTC).isoformat()
        if created_ms else datetime.now(UTC).isoformat()
    )

    return {
        "id": str(raw.get("id", "")),
        "content": text[:800],
        "author": user.get("screen_name") or str(user.get("id", "")),
        "followers": user.get("followers_count", 0),
        "like_count": raw.get("like_count", 0),
        "reply_count": raw.get("reply_count", 0),
        "retweet_count": raw.get("retweet_count", 0),
        "captured_at": captured_at,
        "ticker": ticker,
        "platform": "xueqiu",
    }


def render_markdown(posts: list[dict], quote: dict, symbol: str,
                    ticker: str, collected_at: str) -> str:
    """将采集结果渲染为 Markdown Issue 内容。"""
    price = quote.get("current", "N/A")
    pct   = quote.get("percent", "N/A")
    vol   = quote.get("volume", "N/A")
    high  = quote.get("high", "N/A")
    low   = quote.get("low", "N/A")

    sign = "+" if isinstance(pct, (int, float)) and pct >= 0 else ""

    lines = [
        f"# 📊 雪球数据采集 — {ticker}",
        f"> 采集时间：{collected_at}  |  数据条数：{len(posts)}",
        "",
        "## 💹 实时行情",
        f"| 指标 | 数值 |",
        f"|------|------|",
        f"| 现价 | {price} HKD |",
        f"| 涨跌幅 | {sign}{pct}% |",
        f"| 最高 | {high} |",
        f"| 最低 | {low} |",
        f"| 成交量 | {vol} |",
        "",
        f"## 💬 讨论帖子（{len(posts)} 条）",
        "",
    ]

    for i, p in enumerate(posts[:20], 1):
        ts = p["captured_at"][:16].replace("T", " ")
        lines.append(f"**{i}. {p['author']}** `{ts}`  "
                     f"👍{p['like_count']} 💬{p['reply_count']}")
        lines.append(f"> {p['content'][:300]}")
        lines.append("")

    if len(posts) > 20:
        lines.append(f"*（另有 {len(posts)-20} 条帖子，见下方 JSON 数据块）*")
        lines.append("")

    # 嵌入完整 JSON（供 Action 解析）
    payload = {
        "collected_at": collected_at,
        "ticker": ticker,
        "symbol": symbol,
        "quote": quote,
        "posts": posts,
    }
    lines += [
        "## 📦 原始数据（JSON）",
        "",
        "```json",
        json.dumps(payload, ensure_ascii=False, indent=2),
        "```",
    ]

    return "\n".join(lines)


def ensure_label(repo: str) -> None:
    """确保 GitHub Issue label 存在。"""
    subprocess.run(
        ["gh", "label", "create", GH_LABEL,
         "--color", GH_LABEL_COLOR,
         "--description", GH_LABEL_DESC,
         "--repo", repo],
        capture_output=True,
    )


def create_issue(repo: str, title: str, body_file: str) -> str:
    """创建 GitHub Issue，返回 Issue URL。"""
    result = subprocess.run(
        ["gh", "issue", "create",
         "--title", title,
         "--body-file", body_file,
         "--label", GH_LABEL,
         "--repo", repo],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        # 尝试不带 label
        result = subprocess.run(
            ["gh", "issue", "create",
             "--title", title,
             "--body-file", body_file,
             "--repo", repo],
            capture_output=True, text=True,
        )
    return result.stdout.strip()


# ── 主流程 ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="雪球本机采集 → GitHub Issue")
    parser.add_argument("--token", help="xq_a_token 值（也可通过 XUEQIU_COOKIES 环境变量传入）")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT, help="采集帖子数量")
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL, help="雪球股票代码")
    parser.add_argument("--ticker", default=DEFAULT_TICKER, help="标准股票代码")
    parser.add_argument("--repo", default=os.getenv("GH_REPO", "happydog-intj/stock-analysis-agent"))
    args = parser.parse_args()

    # 获取 token
    raw_cookie = args.token or os.getenv("XUEQIU_COOKIES", "")
    if not raw_cookie:
        print("[ERROR] 请通过 --token 或 XUEQIU_COOKIES 环境变量提供 xq_a_token")
        sys.exit(1)

    token = extract_token(raw_cookie)
    pysnowball.set_token(token)
    print(f"[INFO] token 已配置（长度: {len(token)}）")

    # 采集帖子
    print(f"[INFO] 采集 {args.symbol} timeline ({args.count} 条)...")
    try:
        raw_posts = fetch_timeline(token, args.symbol, args.count)
    except Exception as e:
        print(f"[ERROR] timeline 采集失败: {e}")
        sys.exit(1)

    posts = [p for raw in raw_posts if (p := parse_post(raw, args.ticker)) is not None]
    print(f"[INFO] 解析完成，有效帖子 {len(posts)} 条")

    # 采集行情
    print(f"[INFO] 获取行情 {args.symbol}...")
    quote = fetch_quote(args.symbol)
    if quote:
        print(f"[INFO] 现价: {quote.get('current')}  涨跌: {quote.get('percent')}%")

    # 渲染 Markdown
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    hkt_date = datetime.now().strftime("%Y-%m-%d")
    md = render_markdown(posts, quote, args.symbol, args.ticker, now)

    # 写临时文件
    tmp_file = "/tmp/xueqiu_issue_body.md"
    with open(tmp_file, "w", encoding="utf-8") as f:
        f.write(md)

    # 创建 GitHub Issue
    title = f"📡 雪球数据 {args.ticker} {hkt_date} {datetime.now().strftime('%H:%M')}"
    print(f"[INFO] 创建 Issue: {title}")
    ensure_label(args.repo)
    issue_url = create_issue(args.repo, title, tmp_file)
    if issue_url:
        print(f"[OK] Issue 已创建: {issue_url}")
    else:
        print("[WARN] Issue 创建可能失败，请检查 gh 权限")


if __name__ == "__main__":
    main()
