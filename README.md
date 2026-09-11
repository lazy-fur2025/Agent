---
tags:
  - 程序
  - agent
  - python
created: 2026-09-08
---

# 🧠 AGNES Agent 程序

> 一个自带文件/命令工具的命令行 Agent，基于 OpenAI function-calling 协议实现，可对接任意 OpenAI 兼容 API（Claude、DeepSeek、Qwen 等）。

## 版本与主程序

- `agent.py` — **v1**：命令行 REPL，内置 6 个工具（`run_command` / `read_file` / `write_file` / `list_directory` / `search_files` / `edit_file`）
- `agent-v2.py` — **v2**：新增运行时切换模型 / API / Key、自定义 Skill 系统、预设方案。完整说明见 [[Agent/README FOR AGENT-V2|AGNES Agent v2 使用说明]]

## 运行方式

```bash
python agent.py        # v1
python agent-v2.py     # v2
```

首次运行会提示输入 API Key（或通过环境变量传入）。

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `AGNES_API_BASE` | `https://api.agnes-ai.cn/v1/chat/completions` | API 地址 |
| `AGNES_API_KEY` | 空 | API Key |
| `AGNES_MODEL` | `agnes-2.5-flash` | 模型名 |
| `AGNES_MAX_ITERATIONS` | 25 | 单次多轮工具调用上限 |
| `AGNES_SKILLS_DIR` | `./skills` | Skill 文件夹位置（v2 用） |

## 内置命令（v1）

- `/quit`、`/exit` — 退出
- `/clear` — 清空对话历史
- `/history` — 查看历史消息
- `/system` — 修改 System Prompt

> v2 命令更丰富：`/model`、`/api`、`/key`、`/preset`、`/config`、`/skills`、`/skill` 等，详见 [[Agent/README FOR AGENT-V2|v2 使用说明]]。

> 说明：本文件夹自带 git 仓库，可独立进行版本管理。