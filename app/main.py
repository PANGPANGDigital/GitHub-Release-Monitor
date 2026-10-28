#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Releases 监控 & 飞书 Webhook 推送
群晖 NAS docker-compose 部署
"""

__version__ = "1.0.3"

import os
import json
import time
import hmac
import hashlib
import base64
import re
import requests
from datetime import datetime, timezone, timedelta

# ========================
# 配置区（从环境变量读取）
# ========================
DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
GITHUB_REPOS = os.environ.get("GITHUB_REPOS", "").strip()
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "600"))
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "").strip()
FEISHU_SECRET = os.environ.get("FEISHU_SECRET", "").strip()
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()


def get_github_headers():
    """构造 GitHub API 请求头"""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "GitHub-Release-Monitor",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def get_proxies():
    """获取 HTTP 代理配置"""
    proxies = {}
    http_proxy = os.environ.get("HTTP_PROXY", "").strip()
    https_proxy = os.environ.get("HTTPS_PROXY", "").strip()
    if http_proxy:
        proxies["http"] = http_proxy
    if https_proxy:
        proxies["https"] = https_proxy
    return proxies or None


def get_latest_release(repo):
    """
    获取指定仓库最新发布的 Release。
    排除 draft，保留 alpha/beta/rc 及正式版，按 published_at 降序取最新。
    """
    url = f"https://api.github.com/repos/{repo}/releases?per_page=100"
    proxies = get_proxies()
    resp = requests.get(url, headers=get_github_headers(), proxies=proxies, timeout=30)
    resp.raise_for_status()
    releases = resp.json()

    if not releases:
        return None

    # 排除草稿
    releases = [r for r in releases if not r.get("draft", False)]

    if not releases:
        return None

    # 按发布时间降序
    releases.sort(key=lambda r: r.get("published_at", ""), reverse=True)
    return releases[0]


def load_state():
    """读取持久化状态"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    """保存持久化状态"""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def notify_on_start():
    """
    启动时对每个监控仓库推送当前最新版本信息。
    - state 中无记录：推送「✉️ 开始监控」
    - state 中有记录：推送「🔄 重启通知」
    推送后立即更新 state，避免与后续 monitor_once 重复。
    """
    if not GITHUB_REPOS:
        print("[ERROR] GITHUB_REPOS 为空，请配置要监控的仓库（逗号分隔）")
        return

    repos = [r.strip() for r in GITHUB_REPOS.split(",") if r.strip()]
    state = load_state()
    changed = False

    for repo in repos:
        print(f"[INFO] 启动检查: {repo}")
        try:
            release = get_latest_release(repo)
        except Exception as e:
            print(f"[ERROR] 获取 {repo} Releases 失败: {e}")
            continue

        if not release:
            print(f"[WARN] {repo} 没有找到任何 Release")
            continue

        tag = release.get("tag_name", "")
        published_at = release.get("published_at", "")
        name = release.get("name", tag)
        body = release.get("body", "") or ""
        url = release.get("html_url", "")

        title = "✉️ 开始监控"

        elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**仓库名称：** {repo}\n"
                        f"**Tag：** {tag}\n"
                        f"**更新时间：** {format_time(published_at)}\n"
                        f"**链接：** [查看 Release]({url})"
                    ),
                },
            },
        ]
        send_feishu_card(title, elements, color_template="blue")
        state[repo] = {
            "tag": tag,
            "published_at": published_at,
            "name": name,
            "body": body,
            "url": url,
        }
        changed = True

    if changed:
        save_state(state)


def gen_feishu_sign(timestamp, secret):
    """飞书 Webhook 签名校验"""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
    ).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def send_feishu_card(title, elements, color_template="blue"):
    """
    发送飞书富文本卡片消息
    :param title: 卡片标题
    :param elements: 卡片元素列表
    :param color_template: 卡片主题色，支持 blue/green/orange/red 等
    """
    if not FEISHU_WEBHOOK:
        print("[WARN] FEISHU_WEBHOOK 未配置，跳过推送")
        return

    timestamp = str(int(time.time()))
    sign = gen_feishu_sign(timestamp, FEISHU_SECRET) if FEISHU_SECRET else ""

    card = {
        "header": {
            "title": {
                "tag": "plain_text",
                "content": title
            },
            "template": color_template,
        },
        "elements": elements,
    }

    payload = {
        "timestamp": timestamp,
        "msg_type": "interactive",
        "card": card,
    }
    if sign:
        payload["sign"] = sign

    try:
        resp = requests.post(FEISHU_WEBHOOK, json=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") != 0:
            print(f"[ERROR] 飞书推送失败: {result}")
        else:
            print(f"[INFO] 飞书卡片推送成功: {title}")
    except Exception as e:
        print(f"[ERROR] 飞书推送异常: {e}")


def format_time(iso_str):
    """格式化 ISO 时间为 UTC+8 可读字符串"""
    if not iso_str:
        return "未知"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        dt = dt.astimezone(timezone(timedelta(hours=8)))
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC+8")
    except Exception:
        return iso_str


def truncate_text(text, max_length=3000):
    """截断过长的文本，防止飞书消息超长"""
    if not text:
        return "（无）"
    if len(text) <= max_length:
        return text
    return text[:max_length] + "\n\n...（已截断，请查看完整 Release  Notes）"


def filter_chinese(text):
    """只保留包含中文的行"""
    if not text:
        return ""
    lines = text.splitlines()
    chinese_lines = [line for line in lines if re.search(r'[\u4e00-\u9fff]', line)]
    filtered = "\n".join(chinese_lines).strip()
    return filtered or "（无中文更新日志）"


def monitor_once():
    """执行一次监控检查"""
    if not GITHUB_REPOS:
        print("[ERROR] GITHUB_REPOS 为空，请配置要监控的仓库（逗号分隔）")
        return

    repos = [r.strip() for r in GITHUB_REPOS.split(",") if r.strip()]
    state = load_state()
    changed = False

    for repo in repos:
        print(f"[INFO] 正在检查 {repo} ...")
        try:
            release = get_latest_release(repo)
        except Exception as e:
            print(f"[ERROR] 获取 {repo} Releases 失败: {e}")
            continue

        if not release:
            print(f"[WARN] {repo} 没有找到任何 Release")
            continue

        tag = release.get("tag_name", "")
        published_at = release.get("published_at", "")
        name = release.get("name", tag)
        body = release.get("body", "") or ""
        url = release.get("html_url", "")

        prev = state.get(repo)

        if not prev:
            # 首次运行或状态文件丢失，仅保存当前状态，不重复推送
            # 启动时的通知由 notify_on_start() 负责
            state[repo] = {
                "tag": tag,
                "published_at": published_at,
                "name": name,
                "body": body,
                "url": url,
            }
            changed = True

        elif prev.get("tag") != tag or prev.get("published_at") != published_at:
            # 发现新版本
            elements = [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**仓库名称：** {repo}\n"
                            f"**Tag：** {tag}\n"
                            f"**更新时间：** {format_time(published_at)}\n"
                            f"**链接：** [查看 Release]({url})"
                        ),
                    },
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**更新日志：**\n{truncate_text(filter_chinese(body))}",
                    },
                },
            ]
            send_feishu_card("📢 Release 更新通知", elements, color_template="orange")
            state[repo] = {
                "tag": tag,
                "published_at": published_at,
                "name": name,
                "body": body,
                "url": url,
            }
            changed = True

        else:
            print(f"[INFO] {repo} 已是最新版本: {tag}")

    if changed:
        save_state(state)


if __name__ == "__main__":
    print("=" * 50)
    print(f"GitHub Releases 监控启动 v{__version__}")
    print(f"监控仓库: {GITHUB_REPOS}")
    print(f"检查间隔: {CHECK_INTERVAL} 秒")
    print(f"数据目录: {DATA_DIR}")
    print("=" * 50)

    # 启动时立即推送当前最新版本（首次或重启均会触发）
    notify_on_start()

    # 立即执行一次检查（检测是否有新版本）
    monitor_once()

    # 循环检查
    while True:
        print(f"[INFO] 休眠 {CHECK_INTERVAL} 秒后进行下一次检查...")
        time.sleep(CHECK_INTERVAL)
        monitor_once()
