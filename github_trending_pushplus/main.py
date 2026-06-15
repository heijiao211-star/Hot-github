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
PUSHPLUS_SAFE_LIMIT = int(os.getenv("PUSHPLUS_SAFE_LIMIT", "18000"))
PERIODS = [
    ("daily", "日榜", "最近一天突然变热的项目，适合看新鲜方向和新工具"),
    ("weekly", "周榜", "最近一周持续有人关注的项目，热度比日榜更稳定"),
    ("monthly", "月榜", "最近一个月很多人收藏的项目，通常更值得慢慢研究"),
]
STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "your",
    "open",
    "source",
    "simple",
    "fast",
    "free",
    "build",
    "using",
    "based",
    "awesome",
}


@dataclass(frozen=True)
class RepoItem:
    full_name: str
    url: str
    description: str
    language: str
    stars: str
    period_stars: str


@dataclass(frozen=True)
class Category:
    pattern: str
    name: str
    analogy: str
    core_value: str
    work_value: str
    life_value: str
    suitable_for: str


@dataclass(frozen=True)
class Explanation:
    overview: str
    work_value: str
    life_value: str
    suitable_for: str


CATEGORIES = [
    Category(
        r"\b(ai|llm|agent|rag|prompt|chatgpt|gpt|copilot|model)\b",
        "AI 助手 / 智能工具",
        "一个会读材料、写内容、帮你整理想法的智能助手",
        "把原本需要人慢慢阅读、总结、编写或判断的事情，交给程序自动做一部分",
        "在工作里可以用来写文档、整理资料、做客服问答、辅助写代码、自动处理重复流程",
        "在学习和生活里可以用来解释难懂内容、整理笔记、做计划，或者把复杂信息翻成好懂的话",
        "适合关注 AI、自动化办公、知识整理、代码助手的人",
    ),
    Category(
        r"\b(machine learning|deep learning|neural|transformer|diffusion|training|inference)\b",
        "机器学习 / 模型工具",
        "一个教电脑从例子里学本事的训练场",
        "帮助电脑从大量样本里学规律，然后用这些规律去识别、预测、生成或推荐",
        "在工作里常用于智能识别、数据预测、图片/文字生成、推荐系统和模型部署",
        "在生活里更像把很多经验整理成一个会判断的小帮手，比如识别图片、翻译文字、推荐内容",
        "适合想了解 AI 底层模型、训练、推理和算法应用的人",
    ),
    Category(
        r"\b(frontend|react|vue|svelte|next\.?js|css|tailwind|component|ui|website|web app)\b",
        "网页界面 / 前端工具",
        "一套做网页和界面的积木",
        "让程序员更快做出好看、清晰、能点击操作的网页或后台页面",
        "在工作里可以用来搭建官网、管理后台、数据看板、表单系统和各种在线工具",
        "在生活里可以理解成做一个能在浏览器打开的小应用，比如记账、清单、作品集或个人网站",
        "适合做网站、后台系统、可视化页面或产品原型的人",
    ),
    Category(
        r"\b(api|backend|server|database|postgres|mysql|sqlite|redis|sql|orm|cache)\b",
        "后台服务 / 数据工具",
        "一个在网站背后值班的仓库管理员",
        "负责接收请求、保存资料、查询数据、处理规则，让前台页面真正能工作",
        "在工作里可以用来做用户系统、订单系统、资料库、接口服务、数据同步和权限管理",
        "在生活里可以理解成一个不会睡觉的记事员，帮应用记住你的信息并在需要时找出来",
        "适合关心网站背后怎么存数据、跑服务、连系统的人",
    ),
    Category(
        r"\b(cli|command line|terminal|shell|powershell|bash|console)\b",
        "命令行 / 效率工具",
        "一个听口令办事的快捷助手",
        "把原来要点很多按钮的操作，变成一行命令或一套自动步骤",
        "在工作里可以用来批量处理文件、自动发布项目、检查代码、生成报表或管理服务器",
        "在生活里可以理解成批处理小秘书，比如一口气改很多文件名、整理下载内容、自动备份资料",
        "适合喜欢提高效率、减少重复点击、经常处理文件或代码的人",
    ),
    Category(
        r"\b(security|auth|password|encrypt|scan|vulnerability|malware|firewall|token)\b",
        "安全 / 账号保护工具",
        "一套门锁、监控和巡检工具",
        "帮助发现风险、保护账号密码、加密资料，减少系统被攻击或资料泄露的可能",
        "在工作里可以用来做登录认证、权限控制、漏洞扫描、密钥管理和安全审计",
        "在生活里可以理解成帮你看门的安全工具，提醒哪些地方可能不安全",
        "适合关心账号安全、系统安全、代码安全和合规检查的人",
    ),
    Category(
        r"\b(docker|kubernetes|deploy|deployment|cloud|infra|devops|ci/cd|terraform|helm)\b",
        "部署 / 运维工具",
        "一辆搬家公司卡车加一个值班员",
        "把程序从开发电脑搬到服务器或云平台，并尽量让它稳定运行、方便更新",
        "在工作里可以用来自动发布、环境搭建、服务监控、扩容缩容和基础设施管理",
        "在生活里可以理解成让一个小网站或工具不用一直开着自己电脑，也能放到云上运行",
        "适合做上线发布、云服务、服务器维护和自动化流程的人",
    ),
    Category(
        r"\b(game|engine|graphics|render|3d|shader|canvas|webgl|animation)\b",
        "图形 / 游戏 / 渲染工具",
        "一套画画、做动画和搭场景的工具箱",
        "帮助生成画面、动画、3D 场景或游戏效果，让视觉内容更容易做出来",
        "在工作里可以用于游戏开发、可视化展示、设计工具、互动页面和图像处理",
        "在生活里可以理解成做小动画、小游戏、3D 展示或视觉特效的材料包",
        "适合关注游戏、动画、3D、图像效果和交互体验的人",
    ),
    Category(
        r"\b(android|ios|mobile|desktop|electron|app|windows|macos|linux)\b",
        "应用开发工具",
        "一套做手机或电脑软件的模具",
        "帮助开发者更快做出能安装、能打开、能长期维护的软件",
        "在工作里可以用来开发手机 App、桌面软件、跨平台工具或企业内部应用",
        "在生活里可以理解成把一个想法做成真正能点开使用的小软件",
        "适合想做 App、桌面工具、跨平台应用和个人软件的人",
    ),
    Category(
        r"\b(crawler|scraper|search|index|dataset|data|analytics|visualization|chart)\b",
        "数据采集 / 分析工具",
        "一个会收集、整理和找资料的资料柜",
        "把散落的信息抓回来、清洗好、存起来，再用搜索、图表或分析方式看清楚",
        "在工作里可以用于报表、市场监控、舆情分析、搜索系统、数据看板和自动统计",
        "在生活里可以理解成自动帮你搜集资料、整理清单、做对比和看趋势",
        "适合经常处理表格、网页资料、搜索结果和数据分析的人",
    ),
    Category(
        r"\b(awesome|guide|book|tutorial|course|learn|examples|roadmap|interview)\b",
        "学习资料 / 知识清单",
        "一张整理好的学习地图",
        "把一个领域的教程、例子、路线或资料集中放好，让新手不用到处乱找",
        "在工作里可以用来快速补课、培训新人、查找实践案例或准备面试",
        "在生活里可以理解成一份已经筛过的书单和路线图，跟着看更容易入门",
        "适合想快速了解新技术、找资料、系统学习的人",
    ),
]

DEFAULT_CATEGORY = Category(
    "",
    "开源项目 / 工具作品",
    "一个别人公开放出来的工具或作品",
    "解决某类具体问题，或者给开发者提供可以直接参考、复用、改造的代码",
    "在工作里可以作为现成方案、参考实现、效率工具或项目模板，帮人少走一些弯路",
    "在生活或学习里可以当成一个观察窗口，看看别人是怎么把一个问题做成工具的",
    "适合想看看最近大家在做什么、哪些方向变热的人",
)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Hot-github/1.0 (+https://github.com/heijiao211-star/Hot-github)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
    )
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


def pick_category(repo: RepoItem) -> Category:
    text = f"{repo.full_name} {repo.description} {repo.language}".lower()
    for category in CATEGORIES:
        if re.search(category.pattern, text):
            return category
    return DEFAULT_CATEGORY


def keywords(description: str) -> str:
    found: list[str] = []
    for word in re.findall(r"[A-Za-z][A-Za-z0-9.+#-]{2,}", description):
        if word.lower() not in STOP_WORDS and word.lower() not in {item.lower() for item in found}:
            found.append(word)
        if len(found) >= 5:
            break
    return "、".join(found)


def local_explain(repo: RepoItem) -> Explanation:
    category = pick_category(repo)
    kw = keywords(repo.description)
    keyword_text = f"作者简介里出现的关键词有 {kw}，可以先把它理解成和这些方向有关的项目。" if kw else ""
    overview = (
        f"它可以先理解成{category.analogy}。从项目描述看，它更像是一个「{category.name}」，"
        f"核心作用是{category.core_value}。{keyword_text}"
    )
    return Explanation(
        overview=overview,
        work_value=category.work_value,
        life_value=category.life_value,
        suitable_for=category.suitable_for,
    )


def strip_json_fence(text: str) -> str:
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text.strip(), flags=re.S)
    return match.group(1).strip() if match else text.strip()


def coerce_explanation(value: object) -> Explanation | None:
    if isinstance(value, str) and value.strip():
        return Explanation(value.strip(), "", "", "")
    if not isinstance(value, dict):
        return None
    overview = clean_text(str(value.get("overview", "")))
    work_value = clean_text(str(value.get("work_value", "")))
    life_value = clean_text(str(value.get("life_value", "")))
    suitable_for = clean_text(str(value.get("suitable_for", "")))
    if not any([overview, work_value, life_value, suitable_for]):
        return None
    return Explanation(overview, work_value, life_value, suitable_for)


def ai_explain(repos: list[RepoItem]) -> dict[str, Explanation]:
    api_key = os.getenv("AI_API_KEY", "").strip()
    model = os.getenv("AI_MODEL", "").strip()
    base_url = os.getenv("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    if not api_key or not model or os.getenv("FORCE_RULE_BASED", "").lower() in {"1", "true", "yes"}:
        return {}

    payload_repos = [
        {"name": repo.full_name, "description": repo.description, "language": repo.language}
        for repo in repos
    ]
    prompt = (
        "请把这些 GitHub 项目解释成中文，读者是不懂技术但愿意了解工具价值的人。"
        "不要堆术语，不要只写一句空话。每个项目输出 JSON 对象，key 是 name，value 是对象："
        "overview 用 80 到 120 个中文字符说明它是什么和核心作用；"
        "work_value 用 50 到 90 个中文字符说明它在工作中能解决什么问题；"
        "life_value 用 40 到 80 个中文字符说明它在生活或学习中可以怎么理解；"
        "suitable_for 用 25 到 50 个中文字符说明适合谁关注。只输出严格 JSON。"
    )
    response = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "你擅长把技术项目讲成清楚、具体、好读的中文简报。"},
                {"role": "user", "content": f"{prompt}\n\n{json.dumps(payload_repos, ensure_ascii=False)}"},
            ],
            "temperature": 0.35,
        },
        timeout=60,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    parsed = json.loads(strip_json_fence(content))
    result: dict[str, Explanation] = {}
    for name, value in parsed.items():
        explanation = coerce_explanation(value)
        if explanation:
            result[str(name)] = explanation
    return result


def extract_count(value: str) -> int:
    match = re.search(r"([\d,]+)", value or "")
    if not match:
        return 0
    return int(match.group(1).replace(",", ""))


def heat_index(repo: RepoItem, repos: list[RepoItem]) -> str:
    counts = [extract_count(item.period_stars) for item in repos]
    max_count = max(counts or [0])
    current = extract_count(repo.period_stars)
    if not max_count or not current:
        return "未显示"
    score = max(1.0, round(current / max_count * 10, 1))
    return f"{score:.1f} / 10"


def category_name(repo: RepoItem) -> str:
    return pick_category(repo).name


def format_overview_table(sections: list[tuple[str, str, list[RepoItem]]]) -> list[str]:
    lines = [
        "## 今日总览",
        "",
        "| 榜单 | 观察重点 | 第一名 | 最高热度 |",
        "|---|---|---|---|",
    ]
    for period_name, period_help, repos in sections:
        top = repos[0]
        lines.append(
            f"| {period_name} | {period_help} | [{top.full_name}]({top.url}) | {top.period_stars} |"
        )
    return lines + [""]


def format_rank_table(period_name: str, repos: list[RepoItem]) -> list[str]:
    lines = [
        f"### {period_name}速览",
        "",
        "| 排名 | 项目 | 定位 | 语言 | 热度指数 | 总收藏 |",
        "|---:|---|---|---|---:|---:|",
    ]
    for index, repo in enumerate(repos, start=1):
        lines.append(
            f"| {index} | [{repo.full_name}]({repo.url}) | {category_name(repo)} | {repo.language} | {heat_index(repo, repos)} | {repo.stars} |"
        )
    return lines + [""]


def format_repo_card(index: int, repo: RepoItem, repos: list[RepoItem], explanation: Explanation) -> list[str]:
    lines = [
        f"#### No.{index:02d}  [{repo.full_name}]({repo.url})",
        "",
        "| 信息位 | 内容 |",
        "|---|---|",
        f"| 项目定位 | {category_name(repo)} |",
        f"| 主要语言 | {repo.language} |",
        f"| 总收藏 | {repo.stars} |",
        f"| 热度指数 | {heat_index(repo, repos)} |",
        f"| 本榜新增 | {repo.period_stars} |",
        "",
        f"> **作者简介**：{repo.description}",
        "",
        f"**解释**：{explanation.overview}",
    ]
    if explanation.work_value:
        lines.append(f"**工作里能解决什么**：{explanation.work_value}。")
    if explanation.life_value:
        lines.append(f"**生活/学习里怎么理解**：{explanation.life_value}。")
    if explanation.suitable_for:
        lines.append(f"**适合谁看**：{explanation.suitable_for}。")
    lines += ["", "---", ""]
    return lines


def build_report(sections: list[tuple[str, str, list[RepoItem]]]) -> str:
    all_repos = [repo for _, _, repos in sections for repo in repos]
    try:
        explain_map = ai_explain(all_repos)
    except Exception as exc:  # noqa: BLE001
        print(f"AI 解释生成失败，自动改用免费规则解释：{exc}", file=sys.stderr)
        explain_map = {}

    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    lines = [
        "# GitHub 热榜精读",
        "",
        f"> 生成时间：{now}（北京时间）",
        "> 覆盖范围：日榜、周榜、月榜 Top 10",
        "> 阅读方式：先看速览表，遇到感兴趣的项目再看详细解释，项目名可直接跳转 GitHub。",
        "",
    ]
    lines += format_overview_table(sections)

    for period_name, period_help, repos in sections:
        lines += [f"## {period_name} Top 10", "", f"> {period_help}。", ""]
        lines += format_rank_table(period_name, repos)
        for index, repo in enumerate(repos, start=1):
            explanation = explain_map.get(repo.full_name) or local_explain(repo)
            lines += format_repo_card(index, repo, repos, explanation)
    return "\n".join(lines).strip() + "\n"


def split_long_text(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""
    for block in re.split(r"\n(?=#### No\.\d{2}\s+|\## )", text):
        block = block.strip()
        if not block:
            continue
        candidate = f"{current}\n\n{block}".strip() if current else block
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        if len(block) <= limit:
            current = block
            continue
        paragraphs = block.split("\n\n")
        for paragraph in paragraphs:
            candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
            if len(candidate) <= limit:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = paragraph[:limit]
                rest = paragraph[limit:]
                while rest:
                    chunks.append(current)
                    current = rest[:limit]
                    rest = rest[limit:]
    if current:
        chunks.append(current)
    return chunks


def build_pushplus_parts(content: str, limit: int = PUSHPLUS_SAFE_LIMIT) -> list[str]:
    if len(content) <= limit:
        return [content]

    parts: list[str] = []
    section_pattern = re.compile(r"(?m)^## (日榜|周榜|月榜) Top 10$")
    matches = list(section_pattern.finditer(content))
    if not matches:
        return split_long_text(content, limit)

    overview = content[: matches[0].start()].strip()
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        section = content[match.start() : end].strip()
        if index == 0 and overview:
            section = f"{overview}\n\n{section}"
        parts.extend(split_long_text(section, limit))
    return parts


def send_pushplus_once(title: str, content: str) -> None:
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


def send_pushplus(title: str, content: str) -> None:
    parts = build_pushplus_parts(content)
    for index, part in enumerate(parts, start=1):
        part_title = title if len(parts) == 1 else f"{title}（{index}/{len(parts)}）"
        send_pushplus_once(part_title, part)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Push a polished GitHub Trending report to pushplus.")
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
    title = f"GitHub 热榜精读 {dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime('%m-%d')}"
    if args.dry_run:
        print(report)
        print(f"\n已生成报告：{args.output}")
        return 0
    send_pushplus(title, report)
    print(f"已推送到 pushplus，并保存报告：{args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
