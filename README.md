# Hot GitHub

每天北京时间 09:00 自动抓取 GitHub Trending 的日榜、周榜、月榜 Top 10，为每个项目生成中文一句话精读，并以暗色高级 HTML 卡片的形式推送到 pushplus。

## 它会推送什么

- 日榜 Top 10：最近一天突然变热的项目。
- 周榜 Top 10：最近一周持续受关注的项目。
- 月榜 Top 10：最近一个月很多人收藏的项目。
- 每个项目包含排名、项目名、语言、总星数、本期新增星数和中文精读。
- 整合成暗色高级 HTML 页面，微信里点开即可阅读。
- 优先使用 AI 生成中文摘要；AI 不可用时自动回退到类目规则模板。

## 第一次使用

1. 打开仓库的 `Settings`。
2. 进入 `Secrets and variables` -> `Actions`。
3. 新增以下 Repository secrets：
   - `PUSHPLUS_TOKEN`：你的 pushplus token
4. 进入 `Actions` 页面，点击 `Daily GitHub Trending PushPlus`。
5. 点 `Run workflow` 手动试跑一次；之后会每天北京时间 09:00 自动推送。

## 可选：让 AI 生成更灵活的中文精读

默认版本不需要 AI Key，完全靠类目规则模板生成纯中文介绍，优点是免费、稳定、不会泄露 token。

如果想让每条精读更加灵活自然，可以额外添加以下 Secrets：

- `AI_API_KEY`：OpenAI 兼容接口的 API Key。
- `AI_BASE_URL`：接口地址，不填时默认 `https://api.openai.com/v1`。
- `AI_MODEL`：模型名，例如你自己账号可用的模型。

不填这些也不影响每天推送。

## 手动本地运行

```bash
pip install -r requirements.txt
python -m github_trending_pushplus.main --dry-run
```

真正推送时需要环境变量：

```bash
PUSHPLUS_TOKEN=你的token python -m github_trending_pushplus.main
```

## 注意

GitHub Actions 的定时任务使用 UTC 时间，所以 workflow 里写的是 `0 1 * * *`，对应北京时间每天 09:00。GitHub Trending 没有官方开放 API，这个项目是读取 GitHub Trending 网页内容。如果 GitHub 以后大改页面结构，抓取逻辑可能需要调整。
