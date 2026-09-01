# 🤖 机器人模式：每天 9:00 自动推送飞书（论文 + AI 新闻）

本目录实现了两套不依赖 Hermes 的机器人日报：**arXiv 论文日报** 和 **AI 新闻日报**。每天 9:00 的 Codex 定时任务会依次执行两条流水线，最后都推送到飞书。

## 每日流程（机器人执行的动作）

### A. arXiv 论文日报

1. `python monitor.py` —— 抓取 arXiv 新论文、下载 PDF、写 `papers_record.xlsx`、输出 `new_papers.json`
2. 读取 `new_papers.json` 中的 `papers_to_process`
3. LLM 为每篇论文生成结构化中文总结 `summary_cn` 与作者单位 `affiliations`，结果写入 `llm_fill.json`
4. `python fill_llm.py --json llm_fill.json` —— 把补全结果回填 Excel
5. `python viewer/build_data.py` —— 重建 `viewer/papers_data.json`
6. `python monitor.py --sync-pending-state` —— 同步待处理队列
7. `python send_feishu.py` —— 生成并发送论文日报（每篇带 `【1】` `【2】` 序号，总结分行展示）

> 无新论文时，`send_feishu.py` 会发送一句“今日未发现新论文”。

### B. AI 新闻日报

1. `python news_monitor.py --hours 24` —— 从 `news_sources.txt` 的多家媒体 RSS 抓取最近 24 小时 AI 动态，输出 `news_items.json`
2. 读取 `news_items.json`，对每条新闻生成 1–2 句中文 `summary_cn`，聚焦“大公司新模型 / 新技术 / 重要合作与产品动态”，丢弃明显无关条目
3. 把带总结的条目写回 `news_items.json`
4. `python send_news_feishu.py` —— 生成并发送新闻日报（带 `【1】` `【2】` 序号、💡 中文总结、🔗 原文链接）

> 无新新闻时，`send_news_feishu.py` 会发送一句“今日没有新的 AI 新闻”。

## 前置准备

### 1. 安装依赖

```bash
pip install openpyxl requests pymupdf
```

### 2. 配置飞书

`send_feishu.py`（论文日报）使用 lark-cli user 身份；`send_news_feishu.py`（新闻日报）使用应用机器人身份。应用机器人的凭据写在 `feishu_config.json`：

```json
{
  "app_id": "cli_xxxxxxxxxxxxxxxxxxxxxxxx",
  "app_secret": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "user_id": "ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
}
```

`feishu_config.json` 已被 `.gitignore` 忽略，不会提交到公开仓库。

### 3. 登录飞书（论文日报用 user 身份）

```bash
lark-cli auth login
```

登录时选择 **user 身份**，授予 `offline_access`、`im:message`、`im:message.send_as_user` 等 scope。

## 自动化方式

### 方式 A：Codex 定时任务（推荐）

在 Codex 桌面端创建一条每天 9:00（本地时区）触发的定时任务，提示词覆盖「论文 + 新闻」两条流程。本仓库已经配置了自动化 `arxiv-9-00`（heartbeat），每天 9:00 触发当前线程执行上述流程。

> 注意：Codex 定时任务只在 Codex 桌面端运行时才会触发；关机或退出 Codex 后不会执行。

### 方式 B：Windows 任务计划程序

如果不依赖 Codex，可以用 `schtasks` 每天 9:00 运行脚本。但「生成中文总结」需要 LLM，方式 B 下你需要自己把总结步骤替换为调用任意 LLM API（例如 OpenAI / DeepSeek），再继续走 `fill_llm.py` / `send_news_feishu.py` 之后的流程。

### 方式 C：GitHub Actions

把本仓库 push 到 fork 后，可以新增 `.github/workflows/daily.yml`，用 `schedule: cron` 每天触发。需要把飞书 `app_id` / `app_secret` / `user_id` 与 LLM API Key 配置为仓库 secrets。

## 文件说明

- `monitor.py`：抓取/查重/下载 arXiv 论文、写 Excel、输出 `new_papers.json`；`ARXIV_MAX_RESULTS` 环境变量可调抓取数量（默认 50）
- `fill_llm.py`：把 LLM 补全结果回填 Excel
- `send_feishu.py`：读 Excel 生成带序号、分行总结的论文日报并发送
- `news_monitor.py`：从 `news_sources.txt` 的 RSS 源抓取 AI 新闻、去重、输出 `news_items.json`；`--hours` 控制时间窗口，`--dry-run` 只预览
- `news_sources.txt`：AI 新闻 RSS 源列表（公司官方博客 + 中英文科技媒体）
- `send_news_feishu.py`：读 `news_items.json` 生成带序号、💡 总结、🔗 链接的新闻日报并发送
- `feishu_config.json`（本地，不入库）：飞书应用机器人 `app_id` / `app_secret` 与接收人 `user_id`
- `search_keywords.txt`：论文监控关键词
- `news_items.json` / `news_seen.txt`（本地，不入库）：新闻采集结果与去重记录
