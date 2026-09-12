# Agent v3 CLI+

A lightweight, standard-library-only OpenAI-compatible terminal agent. Supports both interactive conversations and scriptable one-shot execution. No external dependencies except Python 3.9+.

**Key features:**
- 🚀 Runs on pure Python stdlib (urllib, json, subprocess, etc.)
- 💬 Interactive REPL mode with rich tool ecosystem
- 🔧 13+ built-in tools (file ops, git, HTTP, archives, etc.)
- 🎯 One-shot execution mode for scripting
- 📋 Session persistence and skill system
- 🔐 Configurable tool policies (ask/auto/readonly)

---

## Installation

No pip install needed. Just grab `agent-v3-cli.py` and run it:

```bash
python agent-v3-cli.py
```

**Requirements:**
- Python 3.9+
- OpenAI-compatible API (Agnes, OpenAI, DeepSeek, or custom)
- API Key (set via environment variable, command-line, or interactive setup)

---

## Quick Start

### Interactive mode (recommended for exploration)

```bash
python agent-v3-cli.py --provider openai --workspace ~/my-project
```

The first time you run without an API key, the setup wizard automatically appears:

```
· 还没有配置服务商，先跑一遍向导（几秒钟搞定）。
可用服务商：
  1. agnes (https://api.agnes-ai.cn/v1/chat/completions)
  2. openai (https://api.openai.com/v1/chat/completions)
  3. deepseek (https://api.deepseek.com/v1/chat/completions)
  4. custom

选择 [1-4，默认 1]：
```

Just pick a provider (1–3 for presets, 4 to enter custom URL), then paste your API key. Done.

> 💡 **Tip:** You can skip the wizard by setting the key beforehand:
> ```bash
> export AGENT_API_KEY="sk-..."
> python agent-v3-cli.py
> ```

### One-shot mode (for scripts/automation)

Execute a single task and exit:

```bash
python agent-v3-cli.py --prompt "check the project structure"
```

Read the task from a file or pipe:

```bash
cat task.txt | python agent-v3-cli.py --stdin --json
```

Capture the result as JSON (useful for automation):

```bash
python agent-v3-cli.py \
  --prompt "list all Python files" \
  --json
```

Output:
```json
{
  "ok": true,
  "answer": "Found 3 Python files: ...",
  "tools": [{"tool": "find_files", ...}]
}
```

---

## Setup: Where's my API key?

### Priority order (highest to lowest):

1. `--key` command-line argument
2. `AGENT_API_KEY` environment variable
3. `AGNES_API_KEY` environment variable (fallback)
4. `OPENAI_API_KEY` environment variable (fallback)
5. Interactive setup wizard (if running in interactive mode and no key found)

### Examples

**Use an environment variable:**

```bash
# Linux/macOS
export AGENT_API_KEY="sk-..."
python agent-v3-cli.py

# Windows PowerShell
$env:AGENT_API_KEY = "sk-..."
python agent-v3-cli.py
```

**Pass it directly (one-shot mode):**

```bash
python agent-v3-cli.py --key "sk-..." --prompt "help me code"
```

**Use a custom API endpoint:**

```bash
python agent-v3-cli.py \
  --api "https://my-llm.example.com/v1/chat/completions" \
  --model "my-model" \
  --key "my-key"
```

---

## Tool Policies

The `--tool-policy` controls what the model can do:

| Policy | Behavior | Use case |
|--------|----------|----------|
| **ask** (default) | Confirm before file writes, deletes, command execution, network requests, and archive extraction. Read-only tools are always allowed. | Interactive use; prevents accidental changes. |
| **auto** | Execute all enabled tools without prompts. | Unattended automation; use only in workspaces you trust the agent to modify. |
| **readonly** | Block all state-changing tools (write, delete, run commands, network access). Only allow reads, searches, git inspection. | Safe exploration of untrusted code. |

Example: Audit a codebase without risk of modification:

```bash
python agent-v3-cli.py --tool-policy readonly --prompt "security review of ./src"
```

---

## Built-in Tools

### File operations

- **workspace_info** — Show workspace boundary and Python version
- **list_directory** — List files in a directory (with optional glob)
- **tree** — Recursive tree view (adjustable depth, 1–8 levels)
- **find_files** — Find files matching a glob pattern
- **read_file** — Read text files (optional line range)
- **file_info** — Get file size, timestamp, and SHA-256
- **search_files** — Full-text regex search across files
- **write_file** — Create or replace a file (requires confirmation by default)
- **append_file** — Append to a file (requires confirmation by default)
- **replace_text** — Find-and-replace in a file (requires confirmation by default)
- **copy_file** — Copy a file (destination must be inside workspace)
- **mkdir** — Create a directory

### System & development

- **run_command** — Execute shell/bash commands (confirmation required in ask mode)
- **git_status** — Show `git status` (read-only)
- **git_diff** — Show `git diff` for a file (read-only)
- **git_log** — Show `git log` (read-only)
- **calculate** — Safe arithmetic evaluator (no code execution, just math)

### Network & downloads

- **http_fetch** — HTTP GET a URL and return the response (max 1 MB)
- **download_file** — Download and save a file to workspace (requires confirmation, max 50 MB)

### Archives

- **zip_list** — List contents of a ZIP file
- **tar_list** — List contents of a TAR file
- **extract_archive** — Extract ZIP or TAR (traversal-checked, max 2000 members, 50 MB total)

---

## Commands in interactive mode

Type `/help` in the REPL to see all commands:

```
/help               Show all commands
/setup              Reconfigure API provider/key/model (run wizard)
/config             Show current settings
/model [name]       View or set model
/api [url]          View or set API endpoint
/key [value]        Set API key (interactive input if empty)
/workspace [path]   View or switch workspace
/tools              List available tools
/policy [ask|auto|readonly]  Set tool execution policy
/skills             List available skills
/skill [name|off]   Enable or disable a skill
/system             Edit system prompt
/clear              Clear conversation history
/history            Show message log
/save [file]        Save session to JSON
/load [file]        Load session from JSON
/export [file]      Export conversation to plain text
/quit               Exit
```

**Example session:**

```
You > /setup
可用服务商：
  1. agnes
  2. openai
  3. deepseek
  4. custom
选择 [1-4，默认 1]：2
API Key（直接回车保留现有值）：sk-proj-xxx...
✓ 已配置 gpt-4o-mini @ https://api.openai.com/v1/chat/completions。

You > check the project structure
Agent > [searches workspace and returns summary]

You > /skill python-best-practices
✓ 已启用 Skill：python-best-practices。

You > refactor this for performance
Agent > [uses skill context to suggest improvements]

You > /save my-session.json
✓ 会话已保存到 my-session.json。

You > /quit
```

---

## Skills System

A skill is a custom instruction set stored at `skills/<name>/SKILL.md` inside your workspace.

**Example structure:**

```
my-project/
├── agent-v3-cli.py
└── skills/
    ├── python-best-practices/
    │   └── SKILL.md
    ├── security-review/
    │   └── SKILL.md
    └── documentation/
        └── SKILL.md
```

**What goes in SKILL.md:**

```markdown
# Python Best Practices

When the user asks for Python code or refactoring:
1. Follow PEP 8 style guide
2. Add type hints to function signatures
3. Include docstrings for modules and public functions
4. Prefer built-in types (dict, list) over external libraries when possible
5. Use context managers for file and resource handling

Example:
```python
def process_data(items: list[str]) -> dict[str, int]:
    """Count occurrences of each item."""
    return {item: items.count(item) for item in set(items)}
```
"""
```

**Using skills:**

```
You > /skills
 ● python-best-practices — Follow PEP 8 and add type hints...
   security-review — OWASP top 10 security checks...
   documentation — Write clear READMEs...

You > /skill security-review
✓ 已启用 Skill：security-review。

You > review this login endpoint for vulnerabilities
Agent > [applies skill context, checks for SQL injection, CSRF, etc.]
```

---

## Use Cases & Examples

### Example 1: One-shot project audit

```bash
python agent-v3-cli.py \
  --provider openai \
  --workspace ~/my-project \
  --tool-policy readonly \
  --prompt "security audit: find hardcoded secrets, SQL injection risks, and unvalidated user input" \
  --json | tee audit-result.json
```

### Example 2: Batch file processing

```bash
# Process all markdown files in a directory
for file in docs/*.md; do
  python agent-v3-cli.py \
    --prompt "fix grammar and improve clarity: $file" \
    --workspace . \
    --tool-policy auto
done
```

### Example 3: CI/CD integration

```bash
# In a GitHub Actions workflow
- name: Code review
  run: |
    cat .github/review-checklist.txt | \
    python agent-v3-cli.py \
      --stdin \
      --provider deepseek \
      --workspace ${{ github.workspace }} \
      --skill code-review \
      --tool-policy readonly \
      --json > review.json
```

### Example 4: Interactive development

```bash
python agent-v3-cli.py --workspace ~/active-project
# Then in the REPL:
# - Ask questions about the codebase
# - Generate scaffolding code
# - Refactor with skills
# - Save sessions for later
```

---

## Troubleshooting

### "没有 API Key" error in one-shot mode

**Cause:** You didn't provide an API key and one-shot mode doesn't trigger the interactive wizard.

**Solution:** Set the key via environment variable or `--key`:

```bash
export AGENT_API_KEY="sk-..."
python agent-v3-cli.py --prompt "your task"
```

### Setup wizard doesn't appear in interactive mode

**Cause:** Key is already set (via env var or previous session).

**Solution:** Run `/setup` to reconfigure, or unset the variable:

```bash
unset AGENT_API_KEY
python agent-v3-cli.py
```

### "无法连接 API" error

**Cause:** Network issue or wrong endpoint.

**Solution:**
- Check your internet connection
- Verify the API endpoint is correct: `python agent-v3-cli.py --config`
- Try a different provider: `/setup`
- Check if the service is down (visit the website)

### Tool execution stuck asking for confirmation

**Cause:** `--tool-policy ask` (default) requires manual approval for sensitive operations.

**Solution:** Either approve the action, or use `--tool-policy auto` for unattended runs (be careful!).

### Can't write to workspace files

**Cause:** File path is outside the workspace boundary.

**Solution:** Change workspace with `/workspace /my/real/workspace` or use `--workspace`.

---

## Tips & Tricks

**Save sessions for later:**
```bash
python agent-v3-cli.py --session my-work.json
# ... do stuff ...
# Later: restore with --session my-work.json
```

**Export conversations to share:**
```
You > /export conversation.txt
✓ 已导出到 conversation.txt。
```

**Limit tools for safety:**
```bash
python agent-v3-cli.py --tools read_file,search_files,calculate
# Model can only read and search, never modify
```

**Use with pipes (Unix/Linux):**
```bash
echo "fix any typos in this README" | \
  python agent-v3-cli.py --stdin --workspace . --json
```

**Combine with other CLI tools:**
```bash
# Generate a script, then run it
python agent-v3-cli.py \
  --prompt "write a bash script to backup /home" \
  --json | jq -r '.answer' > backup.sh
bash backup.sh
```

---

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `AGENT_API_KEY` | API authentication key | (required) |
| `AGNES_API_KEY` | Fallback key (older naming) | (empty) |
| `OPENAI_API_KEY` | Fallback key (OpenAI style) | (empty) |
| `AGENT_API_BASE` | Custom API endpoint | (preset-dependent) |
| `AGENT_MODEL` | Model name | (preset-dependent) |
| `AGENT_PROVIDER` | Service preset (agnes/openai/deepseek) | agnes |
| `AGENT_WORKSPACE` | Default working directory | current dir |

---

## Command-Line Arguments

```
python agent-v3-cli.py --help

positional arguments:
  message               Single task text (also accepts --prompt)

optional arguments:
  --prompt TEXT         Execute one task and exit
  --stdin              Read task from standard input
  --provider {agnes,openai,deepseek}
                       API provider preset (default: agnes)
  --api URL            Custom Chat Completions endpoint
  --model NAME         Model name
  --key KEY            API key (use environment vars instead for security)
  --workspace PATH     Working directory (default: current dir)
  --session FILE       Load/save conversation session
  --save-session FILE  Save after one-shot task
  --tools NAMES        Comma-separated tool names to enable (default: all)
  --no-tools           Disable all tools
  --tool-policy {ask,auto,readonly}
                       Tool execution policy (default: ask)
  --max-tool-rounds N  Max tool calls per task (default: 20)
  --context-chars N    Conversation history budget (default: 48000)
  --timeout N          API request timeout in seconds (default: 120)
  --plain              Disable terminal colors
  --json               Output JSON for one-shot tasks
  --list-tools         Show all tools and exit
  --version            Show version and exit
```

---

## Performance & Limits

- **File size limit:** 512 KB per file read
- **Tool output limit:** 24 KB per tool result
- **HTTP fetch limit:** 1 MB per response
- **Archive extraction limit:** 2000 members, 50 MB total
- **Context window:** Configurable, default 48,000 characters
- **Tool loops:** Max 20 per task (prevent infinite loops)

---

## Changelog

### v4.0.0 (current)
- ✅ Startup wizard: no API key? We ask you interactively (interactive mode only)
- ✅ `/setup` command to reconfigure mid-session
- ✅ 13+ tools (git, archives, network, math, etc.)
- ✅ Skill system with auto-discovery
- ✅ Session persistence
- ✅ Three tool policies (ask/auto/readonly)

---

## License

MIT — use freely, keep the attribution.

---

**Questions or bugs?** Check the repo issues or refer to the code comments.
