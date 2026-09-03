# 🤖 机器人模式：每天 9:00 生成论文与 AI 新闻日报

lookAI 的统一入口是 `daily_runner.py`。它负责抓取 arXiv 论文和 AI 新闻、调用 OpenAI-compatible LLM 生成中文总结、更新本地数据、运行质量门禁，并在明确授权时调用飞书发送器。

默认运行不会发送任何飞书消息。只有显式传入 `--send`，且质量门禁通过，才允许发送。

## 每日流程

一次完整运行相当于：

1. 抓取论文和新闻，分别写入项目现有数据文件。
2. 对待处理论文和缺少总结的新闻调用 LLM，回填中文总结。
3. 重建网页阅读器数据。
4. 运行 `quality_review.py` 规则并写入 `quality_review.json`。
5. 默认结束，不发送；只有 `--send` 且质量检查通过时才调用两个飞书发送器。

无新论文或无新新闻时，现有发送器会生成对应的空结果提示，但仍然受统一质量检查和发送开关控制。

## 前置准备

### 1. 安装依赖

```bash
pip install openpyxl requests pymupdf
```

### 2. 配置飞书

`send_feishu.py`（论文日报）与 `send_news_feishu.py`（新闻日报）都使用飞书应用机器人身份，凭据写在 `feishu_config.json`：

```json
{
  "app_id": "cli_xxxxxxxxxxxxxxxxxxxxxxxx",
  "app_secret": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "user_id": "ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
}
```

`feishu_config.json` 已被 `.gitignore` 忽略，不会提交到公开仓库。

> 也可以不写文件，直接使用环境变量 `FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `FEISHU_USER_ID`。

LLM 配置使用 `LLM_API_BASE`、`LLM_API_KEY` 和 `LLM_MODEL`。凭据只能放在本机忽略配置或运行环境中，不能写入计划任务示例、Skill 文件或日志。

## 自动化方式

### 方式 A：OpenClaw（脱离 Codex）

项目提供 `openclaw/daily-job.example.yaml`。把它导入或改写为当前 OpenClaw 版本的定时任务格式，工作目录指向本项目，命令使用：

```text
python daily_runner.py --date {{date}} --hours 24 --no-send
```

示例文件特意不启用发送。OpenClaw 不同版本的字段名可能不同，应以本机运行时的 schema 为准。

### 方式 B：Windows 任务计划程序（脱离 Codex）

使用项目中的 `run_daily.ps1`，它会进入项目目录并调用 `daily_runner.py --hours 24 --no-send`。可以在任务计划程序中设置每天 9:00 运行 `powershell.exe`，参数为：

```text
-NoProfile -ExecutionPolicy Bypass -File "C:\Users\ysshen\Desktop\hermes-arxiv-agent\run_daily.ps1"
```

LLM 环境变量应配置在运行账户的环境中，或由受保护的本地启动方式注入。默认仍然不发送飞书。

### 方式 C：GitHub Actions

把本仓库 push 到 GitHub 后，可以新增 `.github/workflows/daily.yml`，用 `schedule: cron` 每天触发。需要把 LLM API Key 配置为仓库 secrets；只有明确需要发送时，才额外配置飞书凭据并显式传入 `--send`。GitHub Actions 托管在云端，与本机是否开机无关。

### 方式 D：Agent Skill（交互式）

Skill 位于 `C:\Users\ysshen\.codex\skills\hermes-arxiv-daily`，用于在 Agent 中手动触发或排查日报，不是后台调度器。它只是调用项目的统一入口，例如：

```text
python scripts/run_daily.py --date 2026-09-01 --hours 24 --no-send
```

真正的每日自动执行应交给 OpenClaw、Windows 任务计划或 GitHub Actions，因此不依赖 Codex 桌面端持续运行。

## 文件说明

- `monitor.py`：抓取/查重/下载 arXiv 论文、写 Excel、输出 `new_papers.json`；`ARXIV_MAX_RESULTS` 环境变量可调抓取数量（默认 50）
- `fill_llm.py`：把 LLM 补全结果回填 Excel
- `daily_runner.py`：统一编排抓取、LLM 总结、回填、质量检查和可选发送
- `quality_review.py`：检查字段完整性、URL、总结、占位文本和高风险断言
- `send_feishu.py`：读 Excel 生成论文日报并发送，由统一入口按需调用
- `news_monitor.py`：从 `news_sources.txt` 的 RSS 源抓取 AI 新闻、去重、输出 `news_items.json`；`--hours` 控制时间窗口，`--dry-run` 只预览
- `news_sources.txt`：AI 新闻 RSS 源列表（公司官方博客 + 中英文科技媒体）
- `send_news_feishu.py`：读 `news_items.json` 生成新闻日报并发送，由统一入口按需调用
- `openclaw/daily-job.example.yaml`：OpenClaw 定时任务示例，默认不发送
- `run_daily.ps1`：Windows 任务计划程序入口，默认不发送
- `feishu_config.json`（本地，不入库）：飞书应用机器人 `app_id` / `app_secret` 与接收人 `user_id`
- `search_keywords.txt`：论文监控关键词
- `news_items.json` / `news_seen.txt`（本地，不入库）：新闻采集结果与去重记录

## 质量门禁与凭据安全

以下任一情况会让运行失败或阻止发送：LLM 调用失败、标题或来源缺失、URL 无效、中文总结为空或仍是占位文本、历史论文记录未完成、或出现质量规则拒绝的高风险断言。请先查看 `quality_review.json`，用 `--skip-fetch --no-send` 重跑检查，不要直接调用发送脚本绕过门禁。

之前曾暴露在聊天、日志或命令行中的飞书 App Secret 应立即在飞书开放平台轮换或重置。不要复用已经暴露的凭据。
