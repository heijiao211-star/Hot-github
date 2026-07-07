from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

GITHUB_BASE_URL = "https://github.com"
PUSHPLUS_URL = os.getenv("PUSHPLUS_URL", "https://www.pushplus.plus/send")
PERIODS = [
    ("daily", "日榜", "最近一天突然变热的项目，适合看新鲜方向"),
    ("weekly", "周榜", "最近一周持续受关注的项目，热度更稳定"),
    ("monthly", "月榜", "最近一个月很多人收藏的项目，值得慢慢研究"),
]


@dataclass(frozen=True)
class RepoItem:
    full_name: str
    url: str
    description: str
    language: str
    stars: str
    period_stars: str


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Hot-github/2.0 (+https://github.com/heijiao211-star/Hot-github)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    return session


def parse_repo_article(article) -> RepoItem | None:
    title = article.select_one("h2 a")
    if title is None:
        return None
    href = title.get("href", "").strip()
    if not href:
        return None

    full_name = clean_text(title.get_text(" ", strip=True)).replace(" ", "").strip("/")
    description_node = article.select_one("p")
    language_node = article.select_one('[itemprop="programmingLanguage"]')
    description = clean_text(description_node.get_text(" ", strip=True) if description_node else "") or "作者没有写简介"
    language = clean_text(language_node.get_text(" ", strip=True) if language_node else "") or "未标明"

    stars = "未显示"
    for link in article.select('a[href$="/stargazers"]'):
        stars = clean_text(link.get_text(" ", strip=True)) or stars
        break

    period_stars = "未显示"
    for node in article.find_all("span"):
        text = clean_text(node.get_text(" ", strip=True))
        lower = text.lower()
        if "star" in lower and ("today" in lower or "week" in lower or "month" in lower):
            period_stars = text
            break

    return RepoItem(full_name, f"{GITHUB_BASE_URL}{href}", description, language, stars, period_stars)


def fetch_trending(session: requests.Session, period: str, limit: int) -> list[RepoItem]:
    # GitHub 官方 Trending 页面，非官方 API，按网页结构解析
    response = session.get(f"{GITHUB_BASE_URL}/trending?since={period}", timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    items = [item for article in soup.select("article.Box-row") if (item := parse_repo_article(article))]
    if not items:
        raise RuntimeError("没有从 GitHub Trending 页面解析到项目，可能是页面结构变了。")
    return items[:limit]


def ai_summarize(repos: list[RepoItem]) -> dict[str, str]:
    api_key = os.getenv("AI_API_KEY", "").strip()
    model = os.getenv("AI_MODEL", "").strip()
    base_url = os.getenv("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    if not api_key or not model:
        print("[WARN] AI_API_KEY / AI_MODEL 未配置，跳过 AI 摘要", file=sys.stderr)
        return {}

    prompt = (
        "你是中国小白用户的 GitHub 技术博主，请把下面每个项目转成地道中文介绍。"
        "严格要求：1.纯中文，不出现英文句子；2.每个项目 2-3 句话，40-60 个汉字；"
        "3.第一句说它是干什么的，第二句说适合谁或解决什么问题；"
        "4.自然多样，不要每句以‘就像’开头；"
        "5.输出严格 JSON，键是项目全名，值是中文介绍。"
    )

    summaries: dict[str, str] = {}
    # 分批生成，每批 10 个，避免模型输出不完整
    batch_size = 10
    for i in range(0, len(repos), batch_size):
        batch = repos[i:i + batch_size]
        payload_repos = [
            {"name": repo.full_name, "description": repo.description, "language": repo.language}
            for repo in batch
        ]
        try:
            response = requests.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "你是中文开源项目介绍助手，只输出纯中文 JSON。"},
                        {"role": "user", "content": f"{prompt}\n\n{json.dumps(payload_repos, ensure_ascii=False)}"},
                    ],
                    "temperature": 0.4,
                    "max_tokens": 4000,
                },
                timeout=180,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            print(f"[DEBUG] batch {i//batch_size + 1} raw length={len(content)}, preview={content[:200]}")
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.S)
            parsed = json.loads(content)
            batch_count = 0
            for k, v in parsed.items():
                if isinstance(v, str) and v.strip():
                    summaries[str(k)] = v.strip()
                    batch_count += 1
            print(f"[DEBUG] batch {i//batch_size + 1} parsed {batch_count} summaries")
        except Exception as exc:
            print(f"[WARN] AI 批次 {i//batch_size + 1} 生成失败：{exc}", file=sys.stderr)

    return summaries


def fallback_summary(repo: RepoItem) -> str:
    # AI 不可用时的极简回退，不出现英文原文
    return "本月热门开源项目，点击名字可以跳转到 GitHub 查看详情。"


def growth_number(text: str) -> str:
    m = re.search(r"([\d,]+)", text)
    return f"+{m.group(1)}" if m else text


def html_escape(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def build_html(sections: list[tuple[str, str, list[RepoItem]]], summaries: dict[str, str]) -> str:
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime("%m-%d %H:%M")

    section_htmls = []
    for period_name, period_help, repos in sections:
        cards = []
        for idx, repo in enumerate(repos, 1):
            summary = html_escape(summaries.get(repo.full_name) or fallback_summary(repo))
            growth = html_escape(growth_number(repo.period_stars))
            cards.append(f"""
  <div class="card">
    <div class="rank">{idx}</div>
    <div class="content">
      <a href="{repo.url}" class="repo-name">{html_escape(repo.full_name)}</a>
      <div class="meta">
        <span class="lang">{html_escape(repo.language)}</span>
        <span class="stars">{html_escape(repo.stars)}</span>
        <span class="growth">{growth}</span>
      </div>
      <p class="desc">{summary}</p>
    </div>
  </div>""")
        section_htmls.append(f"""
  <div class="section">
    <div class="section-title">{period_name}</div>
    <div class="section-subtitle">{period_help}</div>
    {''.join(cards)}
  </div>""")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  body{{margin:0;padding:0;background:#0c0c0e;font-family:'Geist',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;-webkit-font-smoothing:antialiased;}}
  .wrap{{max-width:720px;margin:0 auto;padding:48px 24px;}}
  .hero{{position:relative;background:linear-gradient(160deg,#18181c 0%,#111114 60%,#0d0d0f 100%);border:1px solid rgba(255,255,255,0.06);border-radius:32px;padding:42px 36px;margin-bottom:32px;overflow:hidden;}}
  .hero::before{{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,rgba(255,255,255,0.12),transparent);}}
  .kicker{{font-size:11px;font-weight:700;letter-spacing:0.22em;color:#6b7280;text-transform:uppercase;margin-bottom:16px;}}
  .hero h1{{margin:0;font-size:42px;font-weight:800;color:#fafafa;letter-spacing:-0.04em;line-height:1.05;}}
  .hero p{{margin:14px 0 0 0;font-size:16px;color:#9ca3af;font-weight:500;max-width:520px;}}
  .section{{margin-bottom:42px;}}
  .section-title{{font-size:24px;font-weight:800;color:#fafafa;margin-bottom:6px;letter-spacing:-0.02em;}}
  .section-subtitle{{font-size:14px;color:#6b7280;margin-bottom:20px;}}
  .card{{position:relative;background:#141417;border:1px solid rgba(255,255,255,0.05);border-radius:24px;padding:24px;margin-bottom:14px;display:flex;gap:18px;align-items:flex-start;}}
  .card::after{{content:'';position:absolute;top:0;left:24px;right:24px;height:1px;background:linear-gradient(90deg,transparent,rgba(255,255,255,0.06),transparent);}}
  .rank{{font-size:34px;font-weight:800;color:#10b981;line-height:1;min-width:42px;text-align:left;letter-spacing:-0.05em;}}
  .content{{flex:1;min-width:0;}}
  .repo-name{{font-size:17px;font-weight:700;color:#f3f4f6;margin-bottom:8px;text-decoration:none;display:block;letter-spacing:-0.01em;}}
  .meta{{display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap;}}
  .lang{{font-size:12px;font-weight:600;color:#d1d5db;background:rgba(255,255,255,0.06);padding:4px 10px;border-radius:100px;}}
  .stars{{font-size:12px;font-weight:600;color:#6b7280;}}
  .growth{{font-size:12px;font-weight:700;color:#10b981;background:rgba(16,185,129,0.08);padding:4px 10px;border-radius:100px;border:1px solid rgba(16,185,129,0.14);}}
  .desc{{margin:0;font-size:14px;color:#d1d5db;line-height:1.75;}}
  .footer{{text-align:center;padding:24px 0 0 0;}}
  .footer a{{color:#52525b;font-size:13px;text-decoration:none;font-weight:500;}}
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <div class="kicker">GitHub Trending</div>
    <h1>GitHub 热榜精读</h1>
    <p>日榜 · 周榜 · 月榜 Top 10，每个项目一句中文精读。生成时间：{now} 北京时间</p>
  </div>
  {''.join(section_htmls)}
  <div class="footer">
    <a href="https://github.com/heijiao211-star/Hot-github">来源：heijiao211-star/Hot-github</a>
  </div>
</div>
</body>
</html>"""


def send_pushplus(title: str, content: str) -> None:
    token = os.getenv("PUSHPLUS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("缺少 PUSHPLUS_TOKEN。请在 GitHub 仓库 Settings -> Secrets and variables -> Actions 里添加。")
    payload = {"token": token, "title": title, "content": content, "template": "html"}
    if topic := os.getenv("PUSHPLUS_TOPIC", "").strip():
        payload["topic"] = topic
    response = requests.post(PUSHPLUS_URL, json=payload, timeout=30)
    response.raise_for_status()
    try:
        data = response.json()
    except ValueError:
        data = {}
    print(f"[INFO] pushplus response: {data}")
    if data.get("code") not in (None, 200):
        raise RuntimeError(f"pushplus 返回异常：{data}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Push a polished GitHub Trending report to pushplus.")
    parser.add_argument("--limit", type=int, default=10, help="每个榜单抓取多少个项目，默认 10。")
    parser.add_argument("--dry-run", action="store_true", help="只生成报告，不发送 pushplus。")
    parser.add_argument("--output", default="latest_report.html", help="报告保存路径，默认 latest_report.html。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    session = get_session()
    sections = [(name, help_text, fetch_trending(session, period, args.limit)) for period, name, help_text in PERIODS]

    all_repos = [repo for _, _, repos in sections for repo in repos]
    print(f"[INFO] fetched {len(all_repos)} repos from {len(PERIODS)} periods")

    summaries = ai_summarize(all_repos)
    print(f"[INFO] generated {len(summaries)} AI summaries")

    html = build_html(sections, summaries)
    with open(args.output, "w", encoding="utf-8") as file:
        file.write(html)

    title = f"GitHub 热榜精读 {dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime('%m-%d')}"
    if args.dry_run:
        print(html[:600])
        print(f"\n已生成报告：{args.output}")
        return 0

    send_pushplus(title, html)
    print(f"已推送到 pushplus，并保存报告：{args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
