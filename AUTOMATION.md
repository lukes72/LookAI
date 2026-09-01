# 🤖 机器人模式：每天 9:00 自动推送飞书（无需 Hermes）

本项目的原始实现依赖 Hermes 的 `/cron` 做定时与 LLM 补全。本目录新增了一套 **不依赖 Hermes** 的机器人方案：用任意“定时器 + LLM 运行时”完成每天 9:00 的论文抓取、中文摘要、飞书推送。

## 每日流程（机器人执行的动作）

1. `python monitor.py` —— 抓取 arXiv 新论文、下载 PDF、写 `papers_record.xlsx`、输出 `new_papers.json`
2. 读取 `new_papers.json` 中的 `papers_to_process`
3. LLM 为每篇论文生成 `summary_cn`（90–150 字中文总结）与 `affiliations`（作者单位），结果写入 `llm_fill.json`
4. `python fill_llm.py --json llm_fill.json` —— 把补全结果回填 Excel
5. `python viewer/build_data.py` —— 重建 `viewer/papers_data.json`
6. `python monitor.py --sync-pending-state` —— 同步待处理队列
7. `python send_feishu.py` —— 生成飞书日报并发送

> 无新论文时，`send_feishu.py` 会发送一句“今日未发现新论文”。

## 前置准备

### 1. 安装依赖

```bash
pip install openpyxl requests
```

### 2. 登录飞书（lark-cli，user 身份）

```bash
lark-cli auth login
```

登录时选择 **user 身份**，并授予 `offline_access`、`im:message`、`im:message.send_as_user` 等 scope。这样 token 会自动续期，无需每天重新登录。

### 3. 配置接收人

把 `feishu_config.example.json` 复制为 `feishu_config.json`，填入你自己的 `open_id`：

```json
{
  "user_id": "ou_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
}
```

`feishu_config.json` 已被 `.gitignore` 忽略，不会提交到公开仓库。也可以用环境变量 `FEISHU_USER_ID` 代替。

## 自动化方式

### 方式 A：Codex 定时任务（推荐）

在 Codex 桌面端创建一条每天 9:00（本地时区）触发的定时任务，把下面这段作为任务提示词：

```text
你是“论文日报机器人”。现在是每天早上的定时触发。请严格按顺序执行，不要省略任何一步：

1. 用 load_workspace_dependencies 找到本机 Python 可执行文件（通常在 C:\Users\<用户名>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe）。后续所有 python 命令都用这个绝对路径。
2. 进入仓库目录 <REPO_DIR>。
3. 执行 python monitor.py（抓取 arXiv、下载 PDF、生成 new_papers.json）。
4. 读取 new_papers.json：
   - 若 papers_to_process 为空，跳到第 8 步。
   - 否则对 papers_to_process 中每篇论文：根据 abstract 生成 90–150 字中文总结 summary_cn；根据 authors/abstract（或 PDF 前两页）提取作者单位 affiliations，无法确定时填“未找到单位信息”。
5. 把结果写为仓库根目录的 llm_fill.json，格式 {arxiv_id: {affiliations, summary_cn}}。
6. 依次执行：
   python fill_llm.py --json llm_fill.json
   python viewer/build_data.py
   python monitor.py --sync-pending-state
7. 执行 python send_feishu.py，把今天的日报发到飞书。
8. 若第 4 步判定无新论文，也执行一次 python send_feishu.py（会发送“今日未发现新论文”）。
9. 最后用一句话汇报：今天的抓取数量、补全数量、是否已发送飞书。
```

> 注意：Codex 定时任务只在 Codex 桌面端运行时才会触发；关机或退出 Codex 后不会执行。

### 方式 B：Windows 任务计划程序

如果不依赖 Codex，可以用 `schtasks` 每天 9:00 运行一个脚本。但“生成中文总结”需要 LLM，方式 B 下你需要自己把第 3 步替换为调用任意 LLM API 的代码（例如 OpenAI / DeepSeek），再继续走 `fill_llm.py` 之后的流程。

### 方式 C：GitHub Actions

把本仓库 push 到你的 fork 后，可以新增 `.github/workflows/daily.yml`，用 `schedule: cron` 每天触发。需要把飞书 `user_id` 与 LLM API Key 配置为仓库 secrets。

## 文件说明

- `monitor.py`：抓取/查重/下载/写 Excel/输出 `new_papers.json`；`ARXIV_MAX_RESULTS` 环境变量可调抓取数量（默认 50）
- `fill_llm.py`：把 LLM 补全结果回填 Excel
- `send_feishu.py`：读 Excel 生成飞书 Markdown 并发送
- `feishu_config.json`（本地，不入库）：飞书接收人 `open_id`
- `search_keywords.txt`：监控关键词（默认 LLM 量化方向）
