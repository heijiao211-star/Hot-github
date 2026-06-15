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
    ("daily", "日榜", "最近一天突然变热的项目，适合看新鲜东西"),
    ("weekly", "周榜", "最近一周持续有人关注的项目，热度更稳一点"),
    ("monthly", "月榜", "最近一个月很多人收藏的项目，通常更值得慢慢看"),
]
STOP_WORDS = {"the", "and", "for", "with", "from", "that", "this", "your", "open", "source", "simple", "fast", "free", "build", "using", "based"}
RULES = [
    (r"\b(ai|llm|agent|rag|prompt|chatgpt|gpt|copilot|model)\b", "AI 工具", "一个会读字、写字、帮你思考的小助手", "让电脑帮人回答问题、整理资料、写代码或自动完成一些步骤"),
    (r"\b(machine learning|deep learning|neural|transformer|diffusion|training|inference)\b", "机器学习工具", "一个教电脑从例子里学本事的训练场", "帮程序员训练或使用更聪明的模型"),
    (r"\b(frontend|react|vue|svelte|next\.?js|css|tailwind|component|ui|website|web app)\b", "网页界面工具", "一盒彩色积木", "帮程序员更快做出好看的网页、按钮、页面和交互"),
    (r"\b(api|backend|server|database|postgres|mysql|sqlite|redis|sql|orm|cache)\b", "后台或数据工具", "一个仓库管理员", "帮网站保存资料、查资料、处理请求，让前台页面有东西可用"),
    (r"\b(cli|command line|terminal|shell|powershell|bash|console)\b", "命令行工具", "一个听口令办事的小帮手", "让人不用点很多按钮，敲一行命令就能完成操作"),
    (r"\b(security|auth|password|encrypt|scan|vulnerability|malware|firewall|token)\b", "安全工具", "一把门锁和一个巡逻员", "帮人保护账号、密码、服务器或代码，减少被攻击的风险"),
    (r"\b(docker|kubernetes|deploy|cloud|infra|devops|ci/cd|terraform|helm)\b", "部署运维工具", "一辆搬家公司卡车加一个值班员", "帮程序从电脑搬到服务器，并尽量稳定地跑起来"),
    (r"\b(game|engine|graphics|render|3d|shader|canvas|webgl|animation)\b", "图形或游戏工具", "一套画画和做游戏的工具箱", "帮人做游戏画面、动画、3D 效果或图像渲染"),
    (r"\b(android|ios|mobile|desktop|electron|app|windows|macos|linux)\b", "应用开发工具", "一套做手机或电脑应用的模具", "帮程序员更快做出能安装、能打开、能使用的软件"),
    (r"\b(crawler|scraper|search|index|dataset|data|analytics|visualization|chart)\b", "数据处理工具", "一个会收集、整理和找东西的资料柜", "帮人抓取资料、整理数据、搜索内容或做图表"),
    (r"\b(awesome|guide|book|tutorial|course|learn|examples|roadmap|interview)\b", "学习资料", "一张学习地图", "把某个领域的教程、例子或路线整理好，方便新手少走弯路"),
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
        "User-Agent": "Hot-github/1.0 (+https://github.com/heijiao211-star/Hot-github)",
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
    response = session.get(f"{GITHUB_BASE_URL}/trending?since={period}", timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    items = [item for article in soup.select("article.Box-row") if (item := parse_repo_article(article))]
    if not items:
        raise RuntimeError("没有从 GitHub Trending 页面解析到项目，可能是页面结构变了。")
    return items[:limit]


def keywords(description: str) -> str:
    found: list[str] = []
    for word in re.findall(r"[A-Za-z][A-Za-z0-9.+#-]{2,}", description):
        if word.lower() not in STOP_WORDS and word.lower() not in {item.lower() for item in found}:
            found.append(word)
        if len(found) >= 5:
            break
    return "、".join(found)


def local_explain(repo: RepoItem) -> str:
    text = f"{repo.full_name} {repo.description} {repo.language}".lower()
    kind, analogy, job = "开源项目", "一个别人公开放出来的工具或作品", "解决某类具体问题，或者给程序员提供可以直接参考的代码"
    for pattern, rule_kind, rule_analogy, rule_job in RULES:
        if re.search(pattern, text):
            kind, analogy, job = rule_kind, rule_analogy, rule_job
            break
    kw = keywords(repo.description)
    kw_text = f"作者简介里的关键词是：{kw}。" if kw else ""
    return f"把它想成{analogy}。它属于{kind}，主要是{job}。{kw_text}如果你感兴趣，可以点链接进去看。"


def strip_json_fence(text: str) -> str:
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text.strip(), flags=re.S)
    return match.group(1).strip() if match else text.strip()


def ai_explain(repos: list[RepoItem]) -> dict[str, str]:
    api_key = os.getenv("AI_API_KEY", "").strip()
    model = os.getenv("AI_MODEL", "").strip()
    base_url = os.getenv("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    if not api_key or not model or os.getenv("FORCE_RULE_BASED", "").lower() in {"1", "true", "yes"}:
        return {}

    payload_repos = [{"name": repo.full_name, "description": repo.description, "language": repo.language} for repo in repos]
    prompt = "请把这些 GitHub 项目解释成中文，像跟小学生聊天一样。每个项目 45 到 75 个中文字符，只输出 JSON 对象，key 是 name，value 是解释。"
    response = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "你擅长把技术项目讲给完全不懂技术的人听。"},
                {"role": "user", "content": f"{prompt}\n\n{json.dumps(payload_repos, ensure_ascii=False)}"},
            ],
            "temperature": 0.3,
        },
        timeout=60,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    return {str(key): clean_text(str(value)) for key, value in json.loads(strip_json_fence(content)).items()}


def build_report(sections: list[tuple[str, str, list[RepoItem]]]) -> str:
    all_repos = [repo for _, _, repos in sections for repo in repos]
    try:
        explain_map = ai_explain(all_repos)
    except Exception as exc:  # noqa: BLE001
        print(f"AI 解释生成失败，自动改用免费规则解释：{exc}", file=sys.stderr)
        explain_map = {}

    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    lines = ["# GitHub 热榜小白版", "", f"生成时间：{now}（北京时间）", "", "今天帮你把 GitHub 上热门项目翻成大白话。看到感兴趣的，点项目名就能跳过去。", ""]
    for period_name, period_help, repos in sections:
        lines += [f"## {period_name} Top 10", "", f"{period_help}。", ""]
        for index, repo in enumerate(repos, start=1):
            explanation = explain_map.get(repo.full_name) or local_explain(repo)
            lines += [
                f"### {index}. [{repo.full_name}]({repo.url})",
                "",
                f"- 小白解释：{explanation}",
                f"- 作者简介：{repo.description}",
                f"- 主要语言：{repo.language}",
                f"- 总收藏：{repo.stars}",
                f"- 本榜新增热度：{repo.period_stars}",
                "",
            ]
    return "\n".join(lines).strip() + "\n"


def send_pushplus(title: str, content: str) -> None:
    token = os.getenv("PUSHPLUS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("缺少 PUSHPLUS_TOKEN。请在 GitHub 仓库 Settings -> Secrets and variables -> Actions 里添加。")
    payload = {"token": token, "title": title, "content": content, "template": "markdown"}
    if topic := os.getenv("PUSHPLUS_TOPIC", "").strip():
        payload["topic"] = topic
    response = requests.post(PUSHPLUS_URL, json=payload, timeout=30)
    response.raise_for_status()
    try:
        data = response.json()
    except ValueError:
        data = {}
    if data.get("code") not in (None, 200):
        raise RuntimeError(f"pushplus 返回异常：{data}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Push a friendly GitHub Trending report to pushplus.")
    parser.add_argument("--limit", type=int, default=10, help="每个榜单抓取多少个项目，默认 10。")
    parser.add_argument("--dry-run", action="store_true", help="只生成报告，不发送 pushplus。")
    parser.add_argument("--output", default="latest_report.md", help="报告保存路径，默认 latest_report.md。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    session = get_session()
    sections = [(name, help_text, fetch_trending(session, period, args.limit)) for period, name, help_text in PERIODS]
    report = build_report(sections)
    with open(args.output, "w", encoding="utf-8") as file:
        file.write(report)
    title = f"GitHub 热榜小白版 {dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime('%m-%d')}"
    if args.dry_run:
        print(report)
        print(f"\n已生成报告：{args.output}")
        return 0
    send_pushplus(title, report)
    print(f"已推送到 pushplus，并保存报告：{args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
