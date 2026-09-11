# Agnes AI Agent

命令行 Agent：OpenAI function-calling，可对接任意 OpenAI 兼容 API（Agnes、OpenAI、DeepSeek、Qwen、Claude 兼容网关等）。内置文件与命令工具。MIT。

主程序按三代演进，**三代能力都保留，不是后者覆盖前者。**

| 文件 | 代际 | 要点 |
|---|---|---|
| `agent.py` | v1 | REPL + 6 个工具 + 基础斜杠命令 |
| `agent-v2.py` | v2 | 运行时切模型/API/Key、预设、Skill 系统 |
| `agent-v3.py` | v3 | 启动向导 + `/setup`，免记事本改配置 |

```bash
python agent.py         # v1
python3 agent-v2.py     # v2
python3 agent-v3.py     # v3
```

本目录可自带 git，独立做版本管理。

---

## 三代分别有什么

### v1 — 能跑的最小 Agent

- 对话循环 + function calling
- 六工具：`run_command` / `read_file` / `write_file` / `list_directory` / `search_files` / `edit_file`
- 命令：`/quit` `/exit` `/clear` `/history` `/system`
- 启动无 Key 则交互输入，或用环境变量
- 预设字典（agnes / openai / deepseek）在代码里，**v1 运行时没有 `/preset` 命令**

### v2 — 运行时换脑、换钥匙、换规范

在 v1 之上增加：

- `/model` `/api` `/key` `/config`：下一句生效，不用重启
- `/preset`：一套切换 URL + 默认模型（**文档有、实现必须真的写进 REPL，否则按普通对话送给模型**）
- Skill：扫描 `skills/<name>/SKILL.md`，`/skills` 列表，`/skill <name>` 启用，`/skill off` 关闭
- Frontmatter 的 `description` 当列表简介；没有则取首段非标题文字
- 工具报错更可读；搜索跳过软链、`.git`、`node_modules` 等

### v3 — 启动向导，免记事本

在 v2 之上增加：

- **没有 API Key 时启动即向导**，不放空 Key 进对话然后一堆 401
- 选项：
  1. agnes（`https://api.agnes-ai.cn/v1/chat/completions`，默认 `agnes-2.5-flash`）
  2. openai（`https://api.openai.com/v1/chat/completions`，默认 `gpt-4o-mini`）
  3. deepseek（`https://api.deepseek.com/v1/chat/completions`，默认 `deepseek-chat`）
  4. 自定义：依次填 URL / Model / Key
- 选 1–3 只再要 Key；选 4 三项都填
- Key 留空会反复问
- 运行中 `/setup` 再走同一套向导；已有 Key 时先问换不换，回车保留
- 命令行参数与环境变量仍可用，方便脚本；日常双击或 `python3 agent-v3.py` 问答即可

v3 文档里若仍写 `python3 agent-v2.py`，以文件名为准：向导在 **v3**。

---

## 环境变量（三代共用）

| 变量 | 默认 | 说明 |
|---|---|---|
| `AGNES_API_BASE` | `https://api.agnes-ai.cn/v1/chat/completions` | Chat Completions 地址 |
| `AGNES_API_KEY` | 空 | 密钥 |
| `AGNES_MODEL` | `agnes-2.5-flash` | 模型名 |
| `AGNES_MAX_ITERATIONS` | `25` | 单次工具循环上限，防死转 |
| `AGNES_SKILLS_DIR` | `./skills` | Skill 目录（v2/v3） |

```bash
# 脚本式（v2/v3 都认）
AGNES_API_KEY="sk-xxx" \
AGNES_API_BASE="https://api.openai.com/v1/chat/completions" \
AGNES_MODEL="gpt-4o" \
python3 agent-v3.py

# 通义
AGNES_API_KEY="sk-xxx" \
AGNES_API_BASE="https://dashscope.aliyuncs.com/v1/chat/completions" \
AGNES_MODEL="qwen-max" \
AGNES_SKILLS_DIR="/home/me/my-skills" \
python3 agent-v3.py
```

---

## 斜杠命令总表

| 命令 | v1 | v2 | v3 | 作用 |
|---|---|---|---|---|
| `/quit` `/exit` | ✓ | ✓ | ✓ | 退出 |
| `/clear` | ✓ | ✓ | ✓ | 清空历史 |
| `/history` | ✓ | ✓ | ✓ | 历史预览 |
| `/system` | ✓ | ✓ | ✓ | 改基础 system prompt（不替换已启用 Skill 正文） |
| `/model` | | ✓ | ✓ | 换模型名 |
| `/api` | | ✓ | ✓ | 换 Base URL |
| `/key` | | ✓ | ✓ | 换 Key |
| `/preset` | | ✓ | ✓ | 套用 agnes / openai / deepseek |
| `/config` | | ✓ | ✓ | 看 Model / API / Key 前 6 位 / 当前 Skill |
| `/skills` | | ✓ | ✓ | 列出已发现 Skill |
| `/skill` `/skill <name>` `/skill off` | | ✓ | ✓ | 选、启用、关闭 |
| `/setup` | | | ✓ | 再跑启动向导 |

换模型 / API / Key / 预设 / setup 之后，**下一句对话立刻生效**。

---

## 六工具（三代都有）

| 工具 | 做什么 |
|---|---|
| `run_command` | shell（`ls`、`pip install` 等），可指定工作目录 |
| `read_file` | 读文件 |
| `write_file` | 写文件，不存在则创建 |
| `list_directory` | 列目录，可 glob |
| `search_files` | 正则搜文本 |
| `edit_file` | 把文件里一段旧文本换成新文本 |

对 Agent 说「把 `src/` 下所有 `.py` 的 TODO 列出来」，由模型选工具。前提是对面模型会 function calling，并且你接受 **`run_command` 等于把这台机器的 shell 借出去**——没有白名单、没有二次确认。当玩具可以，当生产要自己加笼子。

---

## Skill（v2 / v3）

```
.
├── agent-v2.py / agent-v3.py
└── skills/
    ├── git-commit/SKILL.md
    ├── code-review/SKILL.md
    └── your-skill/SKILL.md
```

文件名必须是 `SKILL.md`（大写）。列表阶段只抽简介；`/skill` 启用时才读全文，大文件不会在启动时撑爆内存。

简单版：纯 Markdown 规范。  
带简介版：

```yaml
---
description: 按照 Conventional Commits 规范生成 git commit message
---

# Git Commit Skill
格式：`<type>(<scope>): <subject>`
type 仅限 feat/fix/docs/style/refactor/test/chore
subject 中文，不超过 50 字
```

当前**同时只启用一个** Skill。要叠加规范，合并成一份 `SKILL.md`。

原理：启用后把 Skill 全文拼进 system prompt。`/system` 只改基础段；Skill 段永远是文件最新内容。`/skill off` 回到基础 prompt。

---

## 工作流（对话时发生什么）

1. 启动：扫 Skill 目录（只读简介）；v3 若无 Key 先走向导。
2. 输入若以 `/` 开头，走命令，不打 API。
3. 否则：`基础 system + 当前 Skill 全文` → API。
4. 若返回 `tool_calls`：执行工具，结果当 `role: tool` 喂回，最多 `AGNES_MAX_ITERATIONS`（默认 25）轮。
5. 无工具调用则打印最终回答。

---

## 实战

**切服务商（v2 用预设，v3 也可用向导）**

```
You  ▸ /preset
选一个预设 (agnes, openai, deepseek): deepseek

You  ▸ 帮我写个 Python 函数

You  ▸ /setup          # 仅 v3，整段重配
```

**团队规范**

`skills/team-standards/SKILL.md` 写 commit 格式和审查清单，每次 `/skill team-standards`。

**同一天换几顶帽子**

```
/skill python-best-practices
（优化代码）
/skill git-commit
（写 commit）
/skill off
（闲聊，干净 prompt）
```

---

## 常见问题

**换了配置何时生效？** 下一句。

**多个 Skill？** 现版本不行，合并文件。

**Skill 很大卡不卡？** 列表不读全文；启用才读。

**Skill 能放云端？** 现版本仅本地。改加载路径即可。

**模型不听 Skill？** 看 `/config` 是否显示该名；换更强模型；在 Skill 里加例子；部分网关对 system 不敏感。

**离线？** 这是 API 客户端。要接 Ollama，改 `api_call()` 指向本地。

**命令列表太长？** 改启动横幅那段 UI。

---

## 故障排除

**网络请求失败**  
网、URL 是否 `https://`、用 curl 打该 Completions 地址。

**HTTP 401**  
Key 错或过期；Base URL 和服务商不匹配。v2/v3 用 `/key` 或 `/setup`。

**`/skills` 空**  
目录是否存在；必须是 `<name>/SKILL.md`；`ls -R skills/`。

**工具报错**  
权限、命令本身、`/history` 看模型点了什么。

---

## 高级

**只改基础人设：** `/system`。有 Skill 时 Skill 仍会拼上。

**当库调用（不要 REPL）：**

```python
import agent

agent.API_KEY = "sk-xxx"
agent.MODEL = "gpt-4o"
agent.API_BASE = "https://api.openai.com/v1/chat/completions"

messages = [{"role": "user", "content": "hello"}]
response = agent.api_call(messages, tools=agent.TOOLS)
print(response)
```

模块名按你实际文件改（`agent` / 拆出来的模块）。

**加工具三步：** `TOOLS` 里加 schema → 写执行函数 → 挂进 `TOOL_EXECUTORS`。

---

## 实现时不要再和文档打架的点

1. README 写了 `/preset`，REPL 就必须处理 `/preset`，不能只留 `PRESETS` 字典。
2. v3 入口文件是 `agent-v3.py`，示例命令不要抄成 v2。
3. `run_command` 为 `shell=True` 时，文档必须写明风险；要给人用，加工作目录沙箱和危险命令确认。
4. `write_file` / `edit_file` 目前可写到家目录；生产环境加根路径限制。
5. 历史只增不减，长对话自己 `/clear` 或以后做裁剪。

---

## 更新日志

**v1**  
基础 Agent、六工具、`/quit` `/clear` `/history` `/system`；代码内预设表。

**v2**  
运行时 `/model` `/api` `/key` `/preset` `/config`；Skill 发现与启用；Frontmatter 简介；工具错误信息。

**v3**  
无 Key 启动向导（4 选 1 + 自定义）；Key 空则重问；`/setup` 可重复配置并可选保留旧 Key；环境变量与 CLI 仍可用。

---

许可证：MIT。
