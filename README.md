# LookAI

> 自动抓取 arXiv 最新论文与 AI 科技新闻，生成中文总结，经过质量检查后按需推送到飞书。

lookAI 是一个可以脱离 Codex 独立运行的 Python 日报机器人，包含论文和新闻两条流水线。

- **📚 arXiv 论文日报**：按关键词监控 arXiv（cs.AI / cs.CL / cs.LG 等），下载 PDF、读取全文生成结构化中文总结，推送到飞书。
- **📰 AI 新闻日报**：从公司官方博客 + 中英文科技媒体抓取最近动态（新模型 / 新技术 / 大公司动态），生成中文总结，推送到飞书。

---

## ✨ 核心特性

- 统一入口 `daily_runner.py` 编排抓取、总结、回填、质量检查和可选发送
- 可以使用 Agent Skill 交互调用，也可以使用 OpenClaw、Windows 任务计划或 GitHub Actions 脱离 Codex 定时运行
- 默认只生成和检查结果，不发送飞书；只有显式传入 `--send` 且质量门禁通过才会发送
- 每篇论文带 `【1】【2】` 序号，信息分行排版，快速扫读
- 中文总结**不只读摘要**，会结合全文生成：一句话、动机、方法、结果、结论
- 自动过滤临床医疗、生物医学、审计、农业、金融等非目标方向
- 可选的本地 / GitHub Pages 网页阅读器，支持日期筛选、关键词检索、收藏

---

## 📱 飞书输出示例

### 论文日报

```
论文日报 | 2026-09-01
共 12 篇 · 已按你关注的方向筛选

【1】Jet-RL: Enabling On-Policy FP8 Reinforcement Learning with Unified Training and Rollout Precision Flow
机构：NVIDIA
作者：Haocheng Xi, Charlie Ruan, Peiyuan Liao 等 10 人
2026-01-20 · arXiv 2601.14243 · 机器学习
PDF: https://arxiv.org/pdf/2601.14243
一句话：把训练和 rollout 统一到 FP8 精度，显著降低强化学习显存与通信开销。
动机：LLM 强化学习因 rollout 长序列导致 KV cache 与显存成为瓶颈。
方法：设计统一的 FP8 训练 + rollout 精度流程，减少精度切换损失。
结果：在保持训练稳定性的同时降低显存占用。
结论：FP8 是 LLM RL 的高性价比精度选择。

────────────────────

【2】What Makes Low-Bit Quantization-Aware Training Work for Reasoning LLMs? A Systematic Study
机构：未提供
作者：Keyu Lv, Manyi Zhang, Xiaobo Xia 等 9 人
2026-01-21 · arXiv 2601.14888 · 机器学习
PDF: https://arxiv.org/pdf/2601.14888
一句话：系统研究低比特 QAT 在推理模型上的关键成功因素。
动机：低比特量化对推理型大模型的影响缺乏系统结论。
方法：对多种 QAT 策略做受控对比实验。
结果：指出影响低比特 QAT 效果的关键变量。
结论：合理配置下，低比特 QAT 可用于推理 LLM。
```

无新论文时：

```
今日（2026-09-01）未发现新的 AI 论文。
```

### 新闻日报

```
AI 新闻日报 | 2026-09-01
共 8 条 · 新模型 / 新技术 / 大公司动态

【1】OpenAI 发布新一代推理模型
来源：OpenAI | 2026-09-01
OpenAI 推出新一代推理模型，在数学与代码基准上显著提升，并开放 API 试用。
原文：https://openai.com/news/...

【2】智源社区：多模态大模型新进展
来源：智源社区 | 2026-09-01
研究团队提出新的多模态训练范式，在多个视觉语言基准上刷新记录。
原文：https://hub.baai.ac.cn/...
```

无新新闻时：

```
今日没有新的 AI 新闻。
```

---

## 🧭 监控范围

### 论文关键词（`search_keywords.txt`）

偏理论 / 计算机方向，默认包含：

- 强化学习算法
- 量化与模型压缩
- 大语言模型
- 推理 / 思维链
- LLM 智能体
- 检索增强生成（RAG）
- 代码大模型

临床医疗、生物医学、审计、农业、金融等应用方向已在 `monitor.py` 中通过领域黑名单统一过滤。

### 新闻源（`news_sources.txt`）

- 公司官方博客：OpenAI、Hugging Face、Google、DeepMind
- 英文科技媒体：TechCrunch、The Verge、VentureBeat、MIT Tech Review
- 中文科技媒体：智源社区（hub.baai.ac.cn）、新智元（aiera.com.cn）

---

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install openpyxl==3.1.5 requests==2.32.3 pymupdf==1.26.4 feedparser==6.0.11
```

### 2. 配置 LLM

中文总结通过 OpenAI-compatible API 生成。运行前设置：

```powershell
$env:LLM_API_BASE = "https://api.openai.com/v1"
$env:LLM_API_KEY = "你的 LLM API Key"
$env:LLM_MODEL = "gpt-4o-mini"
```

也可以使用兼容 OpenAI API 的其他服务。不要把密钥写进脚本、Skill、OpenClaw 配置示例或 Git 仓库。

### 3. 配置飞书机器人（仅在明确需要发送时）

复制 `feishu_config.example.json` 为 `feishu_config.json`，填入你的飞书应用凭据：

```json
{
  "app_id": "cli_xxxxxxxxxxxxxxxxxxxxxxxx",
  "app_secret": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "user_id": "ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
}
```

- `app_id` / `app_secret`：飞书开放平台自建应用的凭证
- `user_id`：接收日报的飞书用户 open_id

> `feishu_config.json` 已被 `.gitignore` 忽略，**不会被提交到仓库**，请放心保存密钥。

也可以不写文件，直接使用环境变量 `FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `FEISHU_USER_ID`。

### 4. 手动跑一次看效果

```bash
# 抓取论文和新闻，生成总结并进行质量检查，不发送
python daily_runner.py --date 2026-09-01 --hours 24 --no-send

# 使用本地现有数据检查，不重新抓取
python daily_runner.py --skip-fetch --no-send
```

统一入口还支持 `--papers-only`、`--news-only` 和 `--dry-run`。真实发送必须显式使用 `--send`，且质量检查通过；不要绕过入口直接调用发送脚本。
---

## 🤖 每天 9:00 自动推送

详细流水线与自动化方式见 [AUTOMATION.md](AUTOMATION.md)。推荐使用 GitHub Actions：项目已提供 `.github/workflows/daily.yml`，每天 UTC 01:00（北京时间 09:00）在云端运行，与本机是否开机、Codex 桌面端是否运行无关。工作流会在质量门禁通过后发送飞书，并提交云端下一次运行所需的状态文件。

在仓库 `Settings > Secrets and variables > Actions` 中配置：

`LLM_API_BASE`、`LLM_API_KEY`、`LLM_MODEL`、`FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_USER_ID`。

需要持久化的状态文件包括 `papers_record.xlsx`、`crawled_ids.txt`、`pending_llm_ids.txt`、`new_papers.json`、`news_items.json`、`news_seen.txt`、`quality_review.json` 和 `viewer/papers_data.json`。PDF、本地 `feishu_config.json`、临时 LLM 文件和密钥不会提交。

工作流支持 Actions 页面中的 `workflow_dispatch` 手动触发。`daily_runner.py --send` 在 LLM 调用失败或质量门禁失败时返回非零并禁止发送。

项目也提供：

- `openclaw/daily-job.example.yaml`：OpenClaw 定时任务示例
- `run_daily.ps1`：Windows 任务计划程序入口
- `C:\Users\ysshen\.codex\skills\hermes-arxiv-daily`：交互式 Agent Skill

> 提示：OpenClaw、Windows 任务计划和 Agent Skill 分别适合独立调度、本机调度和交互式排查；只有 GitHub Actions 能在不依赖本机开机的情况下运行。

---

## 🗂 项目结构

```
lookAI/
├── daily_runner.py          # 统一编排入口，默认不发送
├── quality_review.py        # 论文、新闻和总结质量门禁
├── monitor.py               # 抓取/查重/下载 arXiv 论文，写 Excel
├── fill_llm.py              # 把 LLM 生成的中文总结/单位回填到 Excel
├── send_feishu.py           # 论文日报发送实现，由统一入口按需调用
├── news_monitor.py          # 抓取/去重 AI 新闻，输出 news_items.json
├── send_news_feishu.py      # 新闻日报发送实现，由统一入口按需调用
├── search_keywords.txt      # 论文监控关键词
├── news_sources.txt         # 新闻 RSS 源
├── feishu_config.example.json  # 飞书配置模板
├── viewer/                  # 可选的网页阅读器
└── images/                  # 文档配图
```

## 运行边界

- LLM 请求失败、总结缺失、URL 无效、占位文本、历史记录不完整或质量门禁失败时，统一入口会阻止发送。
- `quality_review.json` 保存最近一次检查结果，可用于排查日报为什么没有发送。
- 历史 Excel 中未完成的总结也可能阻断整日报告；需要先补全数据，再重新运行质量检查。
- 之前在聊天、日志或命令行中暴露过的飞书 App Secret 和 GitHub token 应立即轮换或撤销，新的凭据只放在 GitHub Actions Secrets、本地忽略配置或环境变量中；GitHub token 使用最小权限。
---

## 📄 License

本项目为个人使用项目，代码可自由修改与自用。
