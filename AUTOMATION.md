# 机器人模式：每天生成论文与 AI 新闻日报

lookAI 的统一入口是 `daily_runner.py`。它抓取 arXiv 论文和 AI 新闻，调用 OpenAI-compatible LLM 生成中文总结，更新状态，运行质量门禁，并在明确授权时调用飞书发送器。

默认运行不会发送飞书。只有显式传入 `--send` 且质量门禁通过时，才允许发送。`--no-send` 和 `--dry-run` 用于检查，不会调用飞书 API。

## 每日流程

1. `monitor.py` 抓取论文、下载 PDF，维护 `papers_record.xlsx`、`crawled_ids.txt` 和 `new_papers.json`。
2. `news_monitor.py` 从 RSS 源抓取新闻，维护 `news_items.json` 和 `news_seen.txt`。
3. `daily_runner.py` 对待处理论文和缺少总结的新闻调用 LLM，回填中文总结。
4. `viewer/build_data.py` 重建 `viewer/papers_data.json`。
5. `quality_review.py` 检查字段、URL、总结、占位文本和高风险断言，写入 `quality_review.json`。
6. 只有使用 `--send` 且检查通过，才调用论文和新闻飞书发送器。

LLM 调用失败或质量门禁失败时，统一入口返回非零退出码并禁止发送。无新论文或无新新闻时，发送器会生成对应的空结果提示，但仍受质量检查和发送开关控制。

## 前置准备

### 1. 安装依赖

```bash
pip install openpyxl==3.1.5 requests==2.32.3 pymupdf==1.26.4 feedparser==6.0.11
```

### 2. 配置凭据

本地运行可以使用被 `.gitignore` 忽略的 `feishu_config.json`，也可以使用环境变量：

- LLM：`LLM_API_BASE`、`LLM_API_KEY`、`LLM_MODEL`
- 飞书：`FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_USER_ID`

不要把密钥写进脚本、Skill、OpenClaw 示例、日志或 Git 仓库。GitHub Actions 必须使用仓库的 Actions Secrets，不要把密钥写入工作流文件。

## 自动化方式

### 方式 A：GitHub Actions（推荐，脱离本机）

项目提供 `.github/workflows/daily.yml`，每天 UTC 01:00，也就是北京时间 09:00，在 GitHub 云端运行。它不依赖本机开机、Codex 桌面端或 OpenClaw 常驻。

在 GitHub 仓库 `Settings > Secrets and variables > Actions` 中配置以下六个 Secrets：

`LLM_API_BASE`、`LLM_API_KEY`、`LLM_MODEL`、`FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_USER_ID`。

工作流执行 `python daily_runner.py --hours 24 --send`。LLM 或质量检查失败会使任务失败并阻止发送；成功后提交运行所需的状态文件和 `viewer/papers_data.json`，以便下一次云端运行继承去重记录和历史总结。也可以在 Actions 页面使用 `workflow_dispatch` 手动触发。

需要持久化的文件是：

```text
papers_record.xlsx
crawled_ids.txt
pending_llm_ids.txt
new_papers.json
news_items.json
news_seen.txt
quality_review.json
viewer/papers_data.json
```

其中若干状态文件被 `.gitignore` 忽略，工作流会在确认文件存在后使用 `git add -f` 暂存它们。`papers/` 下的 PDF、`feishu_config.json`、临时 LLM 文件和任何密钥不会提交。

### 方式 B：OpenClaw（脱离 Codex）

项目提供 `openclaw/daily-job.example.yaml`。把它导入或改写为当前 OpenClaw 版本的定时任务格式，工作目录指向本项目，命令使用：

```text
python daily_runner.py --date {{date}} --hours 24 --send
```

示例文件默认不启用发送，实际部署时应通过受保护的环境变量注入凭据，再明确改为 `--send`。OpenClaw 不同版本的字段名可能不同，应以当前运行时 schema 为准。OpenClaw 负责调度，不替代日报质量门禁。

### 方式 C：Windows 任务计划程序（脱离 Codex）

使用项目中的 `run_daily.ps1`，它默认调用 `daily_runner.py --hours 24 --no-send`。可以在任务计划程序中设置每天 9:00 运行 `powershell.exe`，参数为：

```text
-NoProfile -ExecutionPolicy Bypass -File "C:\Users\ysshen\Desktop\hermes-arxiv-agent\run_daily.ps1"
```

LLM 和飞书环境变量应配置在运行账户的环境中，或由受保护的本地启动方式注入。要真实发送时，把脚本中的 `--no-send` 改为 `--send`。此方式依赖本机运行，不适合关机期间的任务。

### 方式 D：Agent Skill（交互式排查）

Skill 位于 `C:\Users\ysshen\.codex\skills\hermes-arxiv-daily`，用于手动触发或排查日报，不是后台调度器。它只是调用项目统一入口，例如：

```text
python scripts/run_daily.py --date 2026-09-01 --hours 24 --no-send
```

真正的每日自动执行应交给 GitHub Actions、OpenClaw 或 Windows 任务计划；Agent Skill 适合检查 `quality_review.json`、复现失败和手动补跑。

## 文件说明

- `monitor.py`：抓取、查重、下载 arXiv 论文，写 Excel 和 `new_papers.json`；`ARXIV_MAX_RESULTS` 可调抓取数量
- `fill_llm.py`：把 LLM 生成的中文总结和单位回填 Excel
- `daily_runner.py`：统一编排抓取、LLM 总结、回填、质量检查和可选发送
- `quality_review.py`：检查字段完整性、URL、总结、占位文本和高风险断言
- `send_feishu.py`：读 Excel 生成并发送论文日报
- `news_monitor.py`：从 `news_sources.txt` 抓取、去重并输出 AI 新闻
- `send_news_feishu.py`：读 `news_items.json` 生成并发送新闻日报
- `openclaw/daily-job.example.yaml`：OpenClaw 定时任务示例，默认不发送
- `run_daily.ps1`：Windows 任务计划程序入口，默认不发送
- `search_keywords.txt` / `news_sources.txt`：论文关键词和新闻 RSS 源
- `feishu_config.json`：本地飞书凭据配置，不入库

## 质量门禁与凭据安全

以下任一情况会阻止发送：LLM 调用失败、标题或来源缺失、URL 无效、中文总结为空或仍是占位文本、历史论文记录未完成，或出现质量规则拒绝的高风险断言。请先查看 `quality_review.json`，再用 `--skip-fetch --no-send` 重跑检查，不要直接调用发送脚本绕过门禁。

之前在聊天、日志或命令行中暴露过的飞书 App Secret 和 GitHub token 应立即轮换或撤销。新的凭据只能放在 GitHub Actions Secrets、环境变量或被 `.gitignore` 忽略的本地配置中；GitHub token 使用最小权限。
