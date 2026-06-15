# Hot GitHub

每天北京时间 09:00 自动抓取 GitHub Trending 的日榜、周榜、月榜 Top 10，并把每个项目整理成更清晰的中文精读简报后推送到 pushplus。

## 它会推送什么

- 日榜 Top 10：最近一天突然变热的项目。
- 周榜 Top 10：最近一周持续受关注的项目。
- 月榜 Top 10：最近一个月很多人收藏的项目。
- 每个项目都会包含项目名、GitHub 跳转链接、定位、作者简介、语言、收藏数、热度指数，以及更完整的“解释”。
- 推送内容会先给总览和速览表，再展开每个项目的信息卡，阅读起来更清楚。
- 如果完整日报超过 pushplus 单条限制，会自动拆成多条推送，标题里会标明第几部分。

## 第一次使用

1. 打开仓库的 `Settings`。
2. 进入 `Secrets and variables` -> `Actions`。
3. 新增一个 Repository secret：
   - Name：`PUSHPLUS_TOKEN`
   - Secret：你的 pushplus token
4. 进入 `Actions` 页面，打开 `Daily GitHub Trending PushPlus`。
5. 可以点 `Run workflow` 手动试跑一次；之后会每天北京时间 09:00 自动推送。

## 可选：让解释更像真人

默认版本不需要任何 AI Key，完全靠规则生成通俗解释，优点是免费、稳定、不会泄露 token。解释会尽量说明它是什么、能在工作中解决什么问题，以及在生活或学习里可以怎么理解。

如果你以后想让解释更灵活，可以额外添加这些 Secrets：

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
