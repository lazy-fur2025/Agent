---
tags:
  - 程序
  - agent
  - python
created: 2026-09-08
---

# 🤖 简单的 Agent 程序

> 一个自带文件/命令工具的命令行 Agent（AGNES），基于 OpenAI function-calling 协议实现。

## 主程序
- `agent.py` — 命令行 REPL，内置 6 个工具：`run_command` / `read_file` / `write_file` / `list_directory` / `search_files` / `edit_file`

## 运行方式
```bash
python agent.py
```
首次运行会提示输入 API Key（或通过环境变量传入）。

## 环境变量
| 变量 | 默认值 | 说明 |
|---|---|---|
| `AGNES_API_BASE` | `https://api.agnes-ai.cn/v1/chat/completions` | API 地址 |
| `AGNES_API_KEY` | 空 | API Key |
| `AGNES_MODEL` | `agnes-2.5-flash` | 模型名 |
| `AGNES_MAX_ITERATIONS` | 25 | 单次多轮工具调用上限 |

## 内置命令
- `/quit`、`/exit` — 退出
- `/clear` — 清空对话历史
- `/history` — 查看历史消息
- `/system` — 修改 System Prompt