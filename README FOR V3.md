# Agnes AI Agent v2

一个有自主性的 CLI AI agent，支持文件操作、命令执行、自定义 Skill 加载——用任何 OpenAI 兼容的 API（Claude、DeepSeek、Qwen 等），随时切换模型和服务商，甚至运行时不重启就能换 API 密钥。

## v3 新特性：启动向导（免记事本配置）

v3 不再要求你打开记事本改代码或环境变量。**只要没有 API Key，一启动就会弹出交互向导**：

```
$ python3 agent-v3.py

  还没有配置服务商，跟着提示选一下吧（几秒钟搞定）。

  可用预设：
    1. agnes    (https://api.agnes-ai.cn/v1/chat/completions, 默认模型 agnes-2.5-flash)
    2. openai   (https://api.openai.com/v1/chat/completions, 默认模型 gpt-4o-mini)
    3. deepseek (https://api.deepseek.com/v1/chat/completions, 默认模型 deepseek-chat)
    4. 自定义（自己填 URL / Model / Key）

  选一个 [1-4]，直接回车默认选 1：
```

- 选 1-3：自动套用对应预设的 URL 和默认模型，只需再输入 Key
- 选 4：自己依次填 API 地址、模型名称、Key，全自定义、不挑服务商
- Key 是必填项，留空会一直重新问，不会放你带着空 Key 进去然后一堆 401

**运行中随时想换服务商？** 敲 `/setup`，同样的向导会再跑一遍——如果已经有 Key，会先问你要不要换，回车就是保留原 Key，不用重新输一遍。

这样一来，`--api` / `--model` / `--key` 这些命令行参数和环境变量依然可以用（适合写自动化脚本），但对日常使用者来说，**双击运行或者 `python3 agent-v3.py` 直接跑，全程问答式完成配置，不用碰任何配置文件。**


### 最简单的方式

```bash
# 环境变量里放好 API Key
export AGNES_API_KEY="sk-xxx..."
export AGNES_API_BASE="https://api.openai.com/v1/chat/completions"  # 可选，默认用 Agnes
export AGNES_MODEL="gpt-4o-mini"  # 可选，默认用 agnes-2.5-flash

# 跑起来
python3 agent-v2.py
```

### 交互式输入 API Key

没设环境变量的话，启动时会问你：

```
Enter your API key (or set AGNES_API_KEY env var): sk-xxx...
```

## 核心功能

### 1. 模型 & API 切换（运行时，无需重启）

启动后随便敲这些命令：

| 命令 | 用法 | 例子 |
|------|------|------|
| `/model` | 换模型名字 | `/model` → 输入 `gpt-4o` |
| `/api` | 换 API Base URL | `/api` → 输入 `https://api.deepseek.com/v1/chat/completions` |
| `/key` | 换 API Key | `/key` → 输入 `sk-new-key` |
| `/preset` | 快速切预设方案 | `/preset` → 选择 `openai` / `deepseek` / `agnes` |
| `/config` | 看当前配置 | 显示 Model / API / Key（key 只露前 6 位） |

**例子：临时用 GPT-4 试一下**

```
You  ▸ /preset
选一个预设 (agnes, openai, deepseek): openai
  ✓ 已切换到预设 [openai]  model=gpt-4o-mini  api=https://api.openai.com/v1/chat/completions

You  ▸ /model
新模型名称 (empty to cancel): gpt-4-turbo

You  ▸ 现在开始对话，自动用 gpt-4-turbo 了
```

### 2. 文件 & 系统工具

agent 能帮你：
- `run_command` — 执行 shell 命令（`ls`, `pip install`, 等等）
- `read_file` — 读文件内容
- `write_file` — 创建或覆盖文件
- `list_directory` — 列目录内容（支持 glob pattern）
- `search_files` — 全文搜索某个关键词
- `edit_file` — 替换文件里的某段文本

就是跟 AI agent 说"帮我把 src/ 下所有 .py 文件里的 TODO 都列出来"，它自己决定用哪个工具干，理论上就能跑通——当然前提是你给的 API Key 够聪明。

### 3. 自定义 Skill 系统

#### 目录结构

```
.
├── agent-v2.py
├── skills/                    ← 创建这个文件夹
│   ├── git-commit/
│   │   └── SKILL.md           ← 每个 skill 一个 MD
│   ├── code-review/
│   │   └── SKILL.md
│   └── your-skill/
│       └── SKILL.md
```

#### SKILL.md 格式

**简单版（纯文本）：**

```markdown
# Code Review Skill

审查代码时的规范：
1. 必须检查安全漏洞
2. 必须检查性能问题
...
```

**专业版（带 Frontmatter）：**

```yaml
---
description: 按照 Conventional Commits 规范生成 git commit message
---

# Git Commit Skill

当用户要求生成 commit 时，遵循以下规则：
1. 格式：`<type>(<scope>): <subject>`
2. type 只能是 feat/fix/docs/style/refactor/test/chore
3. subject 用中文，不超过 50 字
...
```

> **提示**：Frontmatter 里的 `description` 会在 `/skills` 列表里显示，用来快速了解这个 skill 是干啥的。没写 frontmatter 的话，系统会自动抓第一段非空文字当简介。

#### Skill 命令

| 命令 | 用法 |
|------|------|
| `/skills` | 列出所有发现的 skill + 简介 |
| `/skill <名字>` | 启用某个 skill，后续所有对话都会遵循这个 skill 的规范 |
| `/skill off` | 关闭当前 skill，回到干净的 system prompt |
| `/skill`（无参数） | 交互式选择 |

**工作流：**

```
You  ▸ /skills
┄┄┄┄┄┄┄┄┄┄┄┄┄┄
  code-review
    检查安全漏洞、性能问题、可读性。
 ● git-commit
    按照 Conventional Commits 生成 commit message
┄┄┄┄┄┄┄┄┄┄┄┄┄┄

You  ▸ 我来写个 git commit message

Agent ▸ 请提供要 commit 的内容...
（此时 agent 知道你要按照 git-commit 规范来，会自动遵循）

You  ▸ /skill code-review

You  ▸ 帮我看看这段代码

Agent ▸ （现在 skill 换成了 code-review，审查时会更严谨）
```

> **原理**：启用 skill 后，该 skill 的完整 SKILL.md 内容会被拼到 system prompt 里，让 AI 在生成回复时遵循其中的规则。没启用任何 skill 时就是原汁原味的 system prompt。

### 4. 会话管理

| 命令 | 用法 |
|------|------|
| `/history` | 看对话历史（简略预览） |
| `/clear` | 清空对话历史（开新话题） |
| `/system` | 编辑当前 system prompt（不影响已启用的 skill） |
| `/quit` / `/exit` | 退出 |

## 环境变量参考

启动时会读这些环境变量（都有默认值，不设也能跑）：

```bash
# API 相关
AGNES_API_KEY=""                     # API 密钥（必需，或启动时交互输入）
AGNES_API_BASE="https://api.agnes-ai.cn/v1/chat/completions"  # API 入口
AGNES_MODEL="agnes-2.5-flash"        # 默认模型

# 行为相关
AGNES_MAX_ITERATIONS="25"            # 最多连续调用工具 25 轮，防无限循环
AGNES_SKILLS_DIR="./skills"          # skill 文件夹位置（相对于工作目录）
```

### 例子

```bash
# 用 OpenAI API，默认 GPT-4o
AGNES_API_KEY="sk-proj-xxx" \
AGNES_API_BASE="https://api.openai.com/v1/chat/completions" \
AGNES_MODEL="gpt-4o" \
python3 agent-v2.py

# 用阿里通义千问，skill 放在自定义目录
AGNES_API_KEY="sk-xxx" \
AGNES_API_BASE="https://dashscope.aliyuncs.com/v1/chat/completions" \
AGNES_MODEL="qwen-max" \
AGNES_SKILLS_DIR="/home/me/my-skills" \
python3 agent-v2.py
```

## 实战场景

### 场景 1：快速用 DeepSeek 试点子

```
You  ▸ /preset
选一个预设 (agnes, openai, deepseek): deepseek

You  ▸ 帮我写个 Python 函数
Agent ▸ （用的是 DeepSeek，更便宜）

You  ▸ /preset
选一个预设: openai   ← 试完了，切回 OpenAI

You  ▸ /model
新模型名称: gpt-4-turbo  ← 或者换个 OpenAI 的模型
```

### 场景 2：用 Skill 统一代码规范

团队统一 commit 规范？写个 `skills/team-standards/SKILL.md`：

```yaml
---
description: 公司代码规范和 commit 规范
---

# 团队标准 Skill

## Commit Message 规范
格式：`<type>(<module>): <description>`
...

## 代码审查清单
- [ ] 单元测试覆盖率 > 80%
- [ ] 无硬编码 secret
...
```

然后每次启动都 `/skill team-standards`，所有操作都会自动遵循。

### 场景 3：一次性项目，多个 skill 切换

```
You  ▸ /skill python-best-practices
你  ▸ 帮我优化这个 Python 代码
Agent ▸ （按 Python 最佳实践来）

You  ▸ /skill git-commit
你  ▸ 生成个 commit message
Agent ▸ （按 commit 规范来）

You  ▸ /skill off
你  ▸ 随便聊天
Agent ▸ （干净的 system prompt，不受限）
```

## 工作原理

1. **启动**：
   - 扫描 `AGNES_SKILLS_DIR`，发现所有 `*/SKILL.md` 文件（只读简介，不加载全文）
   - 显示启动横幅、命令列表、发现了多少个 skill

2. **对话循环**：
   - 接收用户输入，先判断是不是 `/` 开头的命令
   - 如果是命令，就执行（切模型、启用 skill 等）
   - 如果不是，拼接"基础 system prompt + 当前启用的 skill 全文"，发给 API
   - API 回复可能包含工具调用，自动执行工具，把结果喂回 API，循环最多 25 轮

3. **Skill 机制**：
   - 启用某个 skill 后，每次调用 `api_call()` 都会把 SKILL.md 全文拼进 system prompt
   - 关闭 skill 后，system prompt 恢复成原始版本（或手动编辑的版本）
   - system prompt 的改动对已经启用的 skill 无效（skill 内容总是最新的）

## 常见问题

### Q：换了模型/API/Key 后什么时候生效？
A：下一句话立刻生效，无需重启或重新登录。

### Q：能同时启用多个 Skill 吗？
A：当前只支持一个。如果需要多个规范叠加，建议把它们合并成一个 SKILL.md。

### Q：Skill 文件太大会卡吗？
A：不会。列表阶段只读简介（百字以内），真正启用时才读全文。即使 SKILL.md 有 10MB，也只在你手动 `/skill <name>` 时才加载。

### Q：能把 Skill 上传到云端吗？
A：目前只支持本地文件。如果有需求可以自己改成 HTTP 或 S3 加载，核心逻辑改两行就行。

### Q：AI 没有遵循 Skill 规范怎么办？
A：
1. 确认 `/config` 里 Skill 那行确实显示了你要的名字
2. 试试换个更聪明的模型（gpt-4 > gpt-4o-mini）
3. 在 Skill 里加更详细的例子和约束
4. 某些 API（比如老版 Claude）可能对 system prompt 不够敏感，试试看 Prompt Engineering 的调整

### Q：命令列表太长了能不能精简？
A：改一下启动横幅部分的代码就行，这是最顶层的 UI 代码，改不坏。

### Q：怎么离线用？
A：不行。这是个 API 客户端，需要网络连接才能调用 LLM。可以自己改代码接本地 Ollama 或其他本地模型服务，只需改 `api_call()` 函数。

## 故障排除

### 启动时报 `[错误] 网络请求失败`
- 检查网络连接
- 检查 `AGNES_API_BASE` 是不是正确的 URL（确认 https:// 不是 http://）
- 试试 `curl` 手工测试一下 API 端点

### 启动时报 `HTTP 401 Unauthorized`
- API Key 错了或过期，用 `/key` 换一个
- API Base URL 可能不对（某些服务商的 URL 稍有不同）

### `/skills` 列出来为空
- 检查 `AGNES_SKILLS_DIR` 指向的目录是不是存在
- 检查目录里是不是真的有 `<name>/SKILL.md` 这样的结构（不是 `<name>/skill.md` 小写）
- 试试 `ls -R skills/` 看看实际目录结构

### AI 执行工具时报错
- 权限问题？检查 agent 能不能访问那些文件和目录
- 命令错误？比如 `run_command` 里的 bash 语法有问题
- 看 `/history` 这一轮 AI 说了什么，可能能找到线索

## 高级用法

### 自定义 System Prompt

启动后可以 `/system` 手动编辑，但这只影响"基础 system prompt"部分。如果启用了 skill，skill 内容还是会自动拼上去。

### 集成到脚本

```python
import agent

# 直接 call api_call 函数，不进 REPL
agent.API_KEY = "sk-xxx"
agent.MODEL = "gpt-4o"
agent.API_BASE = "https://api.openai.com/v1/chat/completions"

messages = [{"role": "user", "content": "hello"}]
response = agent.api_call(messages, tools=agent.TOOLS)
print(response)
```

### 自定义工具

加新工具也很简单，三步：

1. 加到 `TOOLS` 列表里（定义工具的 schema）
2. 写执行函数，加到 `TOOL_EXECUTORS` 字典里
3. 完事

参考已有的 6 个工具的实现就能抄。

## 更新日志

### v2（当前）
- ✅ 运行时换模型/API/Key（不重启）
- ✅ Skill 系统（自动发现、手动启用、运行时切换）
- ✅ Frontmatter 简介提取
- ✅ 优化了 6 个工具的错误提示

### v1
- ✅ 基础 AI agent（工具调用、对话历史）
- ✅ 预设方案（agnes/openai/deepseek）

## 许可证

MIT（随便用，别甩锅我就行）

---

**有问题？直接改代码。有 bug？我没时间修。有好主意？自己加。**

（不过如果你真的加了什么好东西，记得告诉我一声，我可能会"哼"一下然后偷偷很开心。）
