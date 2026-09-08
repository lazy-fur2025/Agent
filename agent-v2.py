import os
import sys
import json
import time
import shutil
import threading
import itertools
import subprocess
import glob as globmod
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# ── UI / 视觉效果 ──────────────────────────────────────────────────────────────
class C:
    """ANSI 颜色，别问为什么不用 colorama，装个依赖还不如手撸几个转义码。"""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    GRAY = "\033[90m"
    WHITE = "\033[97m"


def supports_fancy_output():
    """没接终端（比如被重定向到文件）就别硬上动画，老老实实纯文本。"""
    return sys.stdout.isatty()


FANCY = supports_fancy_output()


def term_width(default=70):
    try:
        return shutil.get_terminal_size((default, 20)).columns
    except Exception:
        return default


def color(text, *codes):
    if not FANCY:
        return text
    return "".join(codes) + text + C.RESET


def rule(char="─", color_code=C.GRAY):
    width = min(term_width(), 78)
    print(color(char * width, color_code))


def gradient_banner():
    """启动横幅，颜色从青到品红过渡，聊胜于无地实现一下'渐变'的感觉。"""
    lines = [
        "   ▄▄▄   ▄▄ ▄▄▄▄▄▄ ▄▄  ▄▄ ▄▄▄▄▄ ▄▄▄▄▄",
        "  ██▀██ ██  ██   ██▀▄▄  ██▄▄  ██▄▄",
        "  ██▄██ ▀██▀▀ ██ ██  ██ ██▄▄▄ ▄▄▄██",
    ]
    palette = [C.CYAN, C.BLUE, C.MAGENTA]
    if FANCY:
        for i, line in enumerate(lines):
            print(color(line, palette[i % len(palette)], C.BOLD))
    else:
        print("AGNES AI AGENT")


class Spinner:
    """在等 API 响应的时候转个圈，免得用户以为程序死了。用 with Spinner('...'): 包一下就行。"""
    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, message="思考中", color_code=C.MAGENTA):
        self.message = message
        self.color_code = color_code
        self._stop = threading.Event()
        self._thread = None
        self._start_time = None

    def _spin(self):
        for frame in itertools.cycle(self.FRAMES):
            if self._stop.is_set():
                break
            elapsed = time.time() - self._start_time
            line = f"\r{color(frame, self.color_code)} {color(self.message, C.DIM)} {color(f'{elapsed:0.1f}s', C.GRAY)}"
            sys.stdout.write(line)
            sys.stdout.flush()
            time.sleep(0.08)

    def __enter__(self):
        if not FANCY:
            print(f"{self.message}...", end="", flush=True)
            self._start_time = time.time()
            return self
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not FANCY:
            elapsed = time.time() - self._start_time
            print(f" ({elapsed:0.1f}s)")
            return False
        self._stop.set()
        if self._thread:
            self._thread.join()
        # 清空这一行，别留残影
        sys.stdout.write("\r" + " " * (term_width()) + "\r")
        sys.stdout.flush()
        return False


def typewriter_print(text, delay=0.012, color_code=None):
    """最终答案逐字吐出来，营造一种'正在打字'的临场感。"""
    if not text:
        return
    if not FANCY:
        print(text)
        return
    for ch in text:
        sys.stdout.write(color(ch, color_code) if color_code else ch)
        sys.stdout.flush()
        # 标点稍微停顿一下，模拟人在换气/思考
        time.sleep(delay * (3 if ch in "。！？.!?\n" else 1))
    print()


TOOL_ICONS = {
    "run_command": "⚡",
    "read_file": "📖",
    "write_file": "✏️ ",
    "list_directory": "📂",
    "search_files": "🔍",
    "edit_file": "🪄",
}


def print_tool_call(fn_name, fn_args_preview):
    icon = TOOL_ICONS.get(fn_name, "🔧")
    print(color(f"  ├─ {icon} ", C.YELLOW) + color(fn_name, C.BOLD, C.CYAN) +
          color(f"({fn_args_preview})", C.GRAY))


def print_tool_result(result, elapsed, ok=True):
    status_color = C.GREEN if ok else C.RED
    status_icon = "✓" if ok else "✗"
    preview = result.strip().replace("\n", " ⏎ ")
    if len(preview) > 100:
        preview = preview[:100] + "…"
    print(color(f"  │  {status_icon} ", status_color) +
          color(preview, C.DIM) +
          color(f"  [{elapsed:0.2f}s]", C.GRAY))


# ── Config ──────────────────────────────────────────────────────────────────
# 这三个是运行时可变的，/model /api /key 命令直接改这几个全局变量。
# 想图省事也可以照旧用环境变量做启动默认值。
API_BASE = os.environ.get("AGNES_API_BASE", "https://api.agnes-ai.cn/v1/chat/completions")
API_KEY = os.environ.get("AGNES_API_KEY", "")
MODEL = os.environ.get("AGNES_MODEL", "agnes-2.5-flash")
MAX_TOOL_ITERATIONS = int(os.environ.get("AGNES_MAX_ITERATIONS", "25"))  # 防止无限工具调用循环

# 一些预设方案，/preset 命令直接套用，懒人福音（自己加就完了，key 留空到时候会提示你输）
PRESETS = {
    "agnes": {
        "api_base": "https://api.agnes-ai.cn/v1/chat/completions",
        "model": "agnes-2.5-flash",
    },
    "openai": {
        "api_base": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o-mini",
    },
    "deepseek": {
        "api_base": "https://api.deepseek.com/v1/chat/completions",
        "model": "deepseek-chat",
    },
}

# ── Skills（用户自己写的 SKILL.md）─────────────────────────────────────────────
# 目录结构约定：SKILLS_DIR/<skill_name>/SKILL.md
# 每个 SKILL.md 建议开头写一段简介（用于列表展示），后面才是详细内容。
SKILLS_DIR = os.environ.get("AGNES_SKILLS_DIR", os.path.join(os.getcwd(), "skills"))


def discover_skills(skills_dir=None):
    """扫描 skills 目录，返回 {name: {"path": ..., "description": ...}}。
    只做发现和摘要提取，不加载全文——全文等 /skill 手动启用的时候再读，
    省得目录里随便扔几个大文件就把内存莫名其妙吃掉。"""
    skills_dir = skills_dir or SKILLS_DIR
    found = {}
    if not os.path.isdir(skills_dir):
        return found
    for entry in sorted(os.listdir(skills_dir)):
        skill_path = os.path.join(skills_dir, entry, "SKILL.md")
        if not os.path.isfile(skill_path):
            continue
        try:
            with open(skill_path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            found[entry] = {"path": skill_path, "description": f"[读取失败: {e}]"}
            continue
        found[entry] = {"path": skill_path, "description": extract_skill_description(text)}
    return found


def extract_skill_description(text):
    """从 SKILL.md 里挑一段能当列表摘要用的简介：
    优先找 frontmatter 里的 description 字段（常见于 Claude Code 风格的 SKILL.md），
    没有的话就取第一个非标题、非空的段落，截断到合理长度。"""
    lines = text.splitlines()

    # 尝试解析 --- ... --- 之间的 YAML frontmatter
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                frontmatter = lines[1:i]
                for fm_line in frontmatter:
                    if fm_line.lower().startswith("description:"):
                        desc = fm_line.split(":", 1)[1].strip().strip('"').strip("'")
                        if desc:
                            return desc[:200]
                break

    # 没有 frontmatter，就找正文第一段非标题文字
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("---"):
            continue
        return stripped[:200]

    return "(无简介)"

SYSTEM_PROMPT = """You are a helpful AI assistant with agent capabilities. You can use tools to interact with the user's system.

When you need to use a tool, call it directly. After receiving a tool result, continue reasoning and decide if you need more tool calls or can give a final answer.

Always explain what you're doing before and after using tools. Be concise and helpful."""

# ── Tools Definition (OpenAI function calling format) ────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Execute a shell command and return its output. Use for running programs, installing packages, checking system state, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute"
                    },
                    "workdir": {
                        "type": "string",
                        "description": "Working directory (optional, defaults to current dir)"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or relative path to the file"
                    },
                    "encoding": {
                        "type": "string",
                        "description": "File encoding (default: utf-8)"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file, creating it if it doesn't exist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or relative path to the file"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file"
                    },
                    "encoding": {
                        "type": "string",
                        "description": "File encoding (default: utf-8)"
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and directories at a given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path (default: current directory)"
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern to filter (e.g. '*.py', '**/*.txt')"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search for text patterns in files using regex.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regex pattern to search for"
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to search in (default: current directory)"
                    },
                    "include": {
                        "type": "string",
                        "description": "File glob to include (e.g. '*.py')"
                    }
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Edit a file by replacing old text with new text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file"
                    },
                    "old_text": {
                        "type": "string",
                        "description": "Exact text to find and replace"
                    },
                    "new_text": {
                        "type": "string",
                        "description": "Replacement text"
                    },
                    "encoding": {
                        "type": "string",
                        "description": "File encoding (default: utf-8)"
                    }
                },
                "required": ["path", "old_text", "new_text"]
            }
        }
    },
]

# ── Tool Execution ───────────────────────────────────────────────────────────
def exec_run_command(args):
    cmd = args.get("command", "")
    workdir = args.get("workdir", None)
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=60, cwd=workdir,
            encoding="utf-8", errors="replace"
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += "\n[STDERR]\n" + result.stderr
        if result.returncode != 0:
            output += f"\n[Exit code: {result.returncode}]"
        return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return "[ERROR] Command timed out after 60 seconds"
    except Exception as e:
        return f"[ERROR] {e}"


def exec_read_file(args):
    path = args.get("path", "")
    enc = args.get("encoding", "utf-8")
    try:
        p = Path(path).expanduser()
        if not p.exists():
            return f"[ERROR] File not found: {path}"
        if p.stat().st_size > 512 * 1024:
            return f"[ERROR] File too large ({p.stat().st_size} bytes). Limit is 512KB."
        return p.read_text(encoding=enc)
    except Exception as e:
        return f"[ERROR] {e}"


def exec_write_file(args):
    path = args.get("path", "")
    content = args.get("content", "")
    enc = args.get("encoding", "utf-8")
    try:
        p = Path(path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding=enc)
        return f"File written: {path} ({len(content)} chars)"
    except Exception as e:
        return f"[ERROR] {e}"


def exec_list_directory(args):
    path = args.get("path", ".")
    pattern = args.get("pattern", None)
    try:
        p = Path(path).expanduser()
        if not p.exists():
            return f"[ERROR] Directory not found: {path}"
        if not p.is_dir():
            return f"[ERROR] Not a directory: {path}"
        if pattern:
            entries = sorted(p.glob(pattern))
        else:
            entries = sorted(p.iterdir())
        lines = []
        for entry in entries[:100]:
            prefix = "📁 " if entry.is_dir() else "  📄 " if entry.suffix else "  📄 "
            lines.append(f"{prefix}{entry.name}")
        if len(entries) > 100:
            lines.append(f"... and {len(entries) - 100} more")
        return "\n".join(lines) if lines else "(empty directory)"
    except Exception as e:
        return f"[ERROR] {e}"


SEARCH_EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".idea", ".vscode"}


def exec_search_files(args):
    import re as re_mod
    pattern = args.get("pattern", "")
    path = args.get("path", ".")
    include = args.get("include", None)
    try:
        regex = re_mod.compile(pattern)
    except re_mod.error as e:
        return f"[ERROR] Invalid regex: {e}"
    results = []
    files_scanned = 0
    try:
        p = Path(path).expanduser()
        files = p.rglob(include) if include else p.rglob("*")
        for f in files:
            # 跳过软链接：原代码会在循环软链接（比如 a -> b -> a）里卡死，这里直接排除
            if f.is_symlink():
                continue
            # 跳过 .git / node_modules 等重型目录，否则一次搜索能跑到天荒地老
            if any(part in SEARCH_EXCLUDE_DIRS for part in f.parts):
                continue
            if not f.is_file():
                continue
            files_scanned += 1
            if files_scanned > 5000:
                results.append(f"... (已扫描 5000 个文件，提前停止，结果可能不全)")
                break
            if f.stat().st_size > 512 * 1024:
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
                for i, line in enumerate(text.splitlines(), 1):
                    if regex.search(line):
                        results.append(f"{f}:{i}: {line.strip()[:120]}")
                        if len(results) >= 50:
                            return "\n".join(results) + "\n... (truncated)"
            except Exception:
                continue
    except Exception as e:
        return f"[ERROR] {e}"
    return "\n".join(results) if results else "(no matches found)"


def exec_edit_file(args):
    path = args.get("path", "")
    old_text = args.get("old_text", "")
    new_text = args.get("new_text", "")
    enc = args.get("encoding", "utf-8")
    try:
        p = Path(path).expanduser()
        if not p.exists():
            return f"[ERROR] File not found: {path}"
        content = p.read_text(encoding=enc)
        if old_text not in content:
            return f"[ERROR] Text not found in file"
        count = content.count(old_text)
        new_content = content.replace(old_text, new_text, 1)
        p.write_text(new_content, encoding=enc)
        msg = f"File edited: {path}"
        if count > 1:
            msg += f" (warning: {count} occurrences found, replaced first only)"
        return msg
    except Exception as e:
        return f"[ERROR] {e}"


TOOL_EXECUTORS = {
    "run_command": exec_run_command,
    "read_file": exec_read_file,
    "write_file": exec_write_file,
    "list_directory": exec_list_directory,
    "search_files": exec_search_files,
    "edit_file": exec_edit_file,
}

# ── API Call ─────────────────────────────────────────────────────────────────
class ApiCallError(Exception):
    """封装 API 调用失败的具体原因，方便上层给用户一个人话解释而不是裸 traceback。"""
    pass


def api_call(messages, tools=None):
    # 注意：这里读的是全局 MODEL/API_BASE/API_KEY，/model /api /key 命令改了之后
    # 下一次调用立刻生效，不用重启、不用改环境变量。
    payload = {
        "model": MODEL,
        "messages": messages,
    }
    if tools:
        payload["tools"] = tools

    data = json.dumps(payload).encode("utf-8")
    req = Request(API_BASE, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if API_KEY:
        req.add_header("Authorization", f"Bearer {API_KEY}")

    try:
        with urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
    except HTTPError as e:
        # 服务器有响应但状态码不对（401/429/500 等），把服务器返回的错误体也带出来
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = "(no body)"
        raise ApiCallError(f"HTTP {e.code} {e.reason}: {body[:500]}") from e
    except URLError as e:
        # 网络层面的问题：DNS、超时、连接被拒绝等
        raise ApiCallError(f"网络请求失败: {e.reason}") from e

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        # 网关抽风返回了非 JSON（比如 HTML 错误页），别让 json.loads 直接把程序炸了
        raise ApiCallError(f"响应不是合法 JSON（可能是网关错误页）: {raw[:300]}") from e

    if "error" in parsed:
        # 有些 OpenAI 兼容网关会用 200 状态码但在 body 里塞 error 字段
        raise ApiCallError(f"API 返回错误: {parsed['error']}")

    return parsed


def chat(user_input, history, system_prompt=None):
    history.append({"role": "user", "content": user_input})
    active_system_prompt = system_prompt or SYSTEM_PROMPT

    # Loop for multi-step tool calling，但绝不无限循环——25 轮还没完事说明模型自己都迷路了
    for iteration in range(MAX_TOOL_ITERATIONS):
        messages = [{"role": "system", "content": active_system_prompt}] + history
        spin_msg = "思考中" if iteration == 0 else f"继续推理（第 {iteration + 1} 轮）"
        try:
            with Spinner(spin_msg):
                resp = api_call(messages, tools=TOOLS)
        except ApiCallError as e:
            print(color(f"  ✗ API 错误: {e}", C.RED))
            return f"[API 错误] {e}"
        except Exception as e:
            print(color(f"  ✗ 未知错误: {e}", C.RED))
            return f"[未知错误] {type(e).__name__}: {e}"

        # 防御性解析：resp 结构不对时给出可诊断信息，而不是裸 KeyError/IndexError
        choices = resp.get("choices")
        if not choices:
            return f"[错误] API 响应里没有 choices 字段，原始响应: {json.dumps(resp, ensure_ascii=False)[:300]}"

        choice = choices[0]
        msg = choice.get("message")
        if not msg:
            return f"[错误] choices[0] 里没有 message 字段: {json.dumps(choice, ensure_ascii=False)[:300]}"

        content = msg.get("content", "") or ""
        tool_calls = msg.get("tool_calls", None)

        # No tool calls → final answer
        if not tool_calls:
            history.append({"role": "assistant", "content": content})
            return content

        # Process tool calls
        history.append({
            "role": "assistant",
            "content": content or None,
            "tool_calls": tool_calls
        })

        for tc in tool_calls:
            fn = tc.get("function", {})
            fn_name = fn.get("name", "")
            raw_args = fn.get("arguments", "{}")
            try:
                fn_args = json.loads(raw_args) if raw_args else {}
            except json.JSONDecodeError:
                # 模型有时会吐出不合法的 JSON 参数，别让整个流程崩掉，让工具自己报错即可
                fn_args = {}
                print(color(f"  ⚠️  {fn_name} 的参数不是合法 JSON: {raw_args[:100]}", C.YELLOW))

            args_preview = json.dumps(fn_args, ensure_ascii=False)[:100]
            print_tool_call(fn_name, args_preview)

            executor = TOOL_EXECUTORS.get(fn_name)
            t0 = time.time()
            if executor:
                try:
                    with Spinner(f"执行 {fn_name}", color_code=C.BLUE):
                        result = executor(fn_args)
                    ok = not result.strip().startswith("[ERROR]")
                except Exception as e:
                    # 工具执行器内部理论上都自己 try/except 了，这里是最后一道保险
                    result = f"[ERROR] 工具执行异常: {type(e).__name__}: {e}"
                    ok = False
            else:
                result = f"[ERROR] Unknown tool: {fn_name}"
                ok = False
            elapsed = time.time() - t0
            print_tool_result(result, elapsed, ok=ok)

            # Truncate long results
            if len(result) > 8000:
                result = result[:8000] + f"\n... (truncated, total {len(result)} chars)"

            history.append({
                "role": "tool",
                "tool_call_id": tc.get("id", ""),
                "content": result
            })

        # Continue loop - model may want more tool calls or final answer

    # 到这里说明连续 MAX_TOOL_ITERATIONS 轮都没给出最终答案，大概率是模型在瞎绕圈子
    return (f"[警告] 已连续调用工具 {MAX_TOOL_ITERATIONS} 轮仍未得到最终答案，"
            f"为防止死循环已中止。可以用 /history 看看它在干嘛，或者换个问法。")


# ── Main REPL ────────────────────────────────────────────────────────────────
def main():
    global API_KEY, MODEL, API_BASE

    if not API_KEY:
        API_KEY = input("Enter your API key (or set AGNES_API_KEY env var): ").strip()
        if not API_KEY:
            print("No API key provided. Exiting.")
            sys.exit(1)

    history = []
    system_prompt = SYSTEM_PROMPT
    available_skills = discover_skills()
    active_skill = None  # 当前手动启用的 skill 名字，None 表示不启用任何 skill

    def effective_system_prompt():
        """把基础 system prompt 和当前启用的 skill 全文拼在一起。
        没启用任何 skill 就原样返回，不多加一个字。"""
        if not active_skill:
            return system_prompt
        skill_info = available_skills.get(active_skill)
        if not skill_info:
            return system_prompt
        try:
            with open(skill_info["path"], "r", encoding="utf-8") as f:
                skill_content = f.read()
        except Exception as e:
            print(color(f"  ⚠️  读取 skill [{active_skill}] 失败: {e}", C.YELLOW))
            return system_prompt
        return (
            f"{system_prompt}\n\n"
            f"---\n"
            f"# 已启用的 Skill: {active_skill}\n"
            f"以下是这个 skill 的完整说明，请在相关任务中遵循其中的指导：\n\n"
            f"{skill_content}"
        )

    print()
    gradient_banner()
    rule("─", C.GRAY)
    print(color("  Model  ", C.DIM) + color(MODEL, C.CYAN, C.BOLD))
    print(color("  API    ", C.DIM) + color(API_BASE, C.GRAY))
    rule("─", C.GRAY)
    print(color("  命令  ", C.DIM) + color("/quit", C.YELLOW) + "  " +
          color("/clear", C.YELLOW) + "  " + color("/system", C.YELLOW) + "  " +
          color("/history", C.YELLOW))
    print(color("  配置  ", C.DIM) + color("/model", C.GREEN) + "  " +
          color("/api", C.GREEN) + "  " + color("/key", C.GREEN) + "  " +
          color("/preset", C.GREEN) + "  " + color("/config", C.GREEN))
    print(color("  Skill ", C.DIM) + color("/skills", C.MAGENTA) + "  " +
          color("/skill <name>", C.MAGENTA) + "  " +
          color(f"(发现 {len(available_skills)} 个，目录: {SKILLS_DIR})", C.GRAY))
    print(color("  工具  ", C.DIM) +
          color("run_command · read_file · write_file · list_directory · search_files · edit_file", C.MAGENTA))
    rule("─", C.GRAY)
    print()

    while True:
        try:
            user_input = input(color("You  ▸ ", C.CYAN, C.BOLD)).strip()
        except (EOFError, KeyboardInterrupt):
            print(color("\n再见啦～ 👋", C.MAGENTA))
            break

        if not user_input:
            continue

        # Slash commands
        if user_input.lower() == "/quit" or user_input.lower() == "/exit":
            print(color("再见啦～ 👋", C.MAGENTA))
            break
        elif user_input.lower() == "/clear":
            history.clear()
            print(color("  ✓ 历史已清空", C.GREEN))
            continue
        elif user_input.lower() == "/history":
            rule("┄", C.GRAY)
            for msg in history:
                role = msg["role"]
                content = msg.get("content", "")
                if content:
                    preview = content[:80].replace("\n", " ")
                    role_color = {"user": C.CYAN, "assistant": C.YELLOW, "tool": C.BLUE}.get(role, C.GRAY)
                    print(color(f"  [{role}] ", role_color, C.BOLD) + color(preview, C.DIM))
            rule("┄", C.GRAY)
            continue
        elif user_input.lower() == "/system":
            new_prompt = input(color("New system prompt (empty to cancel): ", C.DIM)).strip()
            if new_prompt:
                system_prompt = new_prompt  # 原来这里赋值给一个根本不存在的 SYSTEM_PROMPT_GLOBAL，等于白改
                print(color("  ✓ System prompt 已更新", C.GREEN))
            continue
        elif user_input.lower() == "/config":
            rule("┄", C.GRAY)
            print(color("  Model  ", C.DIM) + color(MODEL, C.CYAN, C.BOLD))
            print(color("  API    ", C.DIM) + color(API_BASE, C.GRAY))
            print(color("  Key    ", C.DIM) + color((API_KEY[:6] + "..." if API_KEY else "(未设置)"), C.GRAY))
            print(color("  Skill  ", C.DIM) + color((active_skill or "(未启用)"), C.MAGENTA))
            rule("┄", C.GRAY)
            continue
        elif user_input.lower() == "/model":
            new_model = input(color("新模型名称 (empty to cancel): ", C.DIM)).strip()
            if new_model:
                MODEL = new_model
                print(color(f"  ✓ 模型已切换为 {MODEL}", C.GREEN))
            continue
        elif user_input.lower() == "/api":
            new_api = input(color("新 API Base URL (empty to cancel): ", C.DIM)).strip()
            if new_api:
                API_BASE = new_api
                print(color(f"  ✓ API Base 已切换为 {API_BASE}", C.GREEN))
            continue
        elif user_input.lower() == "/key":
            new_key = input(color("新 API Key (empty to cancel): ", C.DIM)).strip()
            if new_key:
                API_KEY = new_key
                print(color("  ✓ API Key 已更新", C.GREEN))
            continue
        elif user_input.lower() == "/skills":
            available_skills = discover_skills()  # 重新扫一遍，方便运行时新加的 skill 也能被发现
            if not available_skills:
                print(color(f"  （没在 {SKILLS_DIR} 找到任何 SKILL.md，", C.GRAY) +
                      color("放到 skills/<name>/SKILL.md 就能被发现）", C.GRAY))
            else:
                rule("┄", C.GRAY)
                for name, info in available_skills.items():
                    mark = color(" ●", C.GREEN) if name == active_skill else "  "
                    print(mark + color(f" {name}", C.BOLD, C.MAGENTA))
                    print(color(f"     {info['description']}", C.DIM))
                rule("┄", C.GRAY)
            continue
        elif user_input.lower().startswith("/skill"):
            rest = user_input[len("/skill"):].strip()
            if not rest:
                # 没带参数：交互式选一个，off 表示取消启用
                names = ", ".join(available_skills.keys()) if available_skills else "(无)"
                rest = input(color(f"启用哪个 skill？({names}, off=取消): ", C.DIM)).strip()
            if not rest:
                continue
            if rest.lower() in ("off", "none", "no", "取消"):
                if active_skill:
                    print(color(f"  ✓ 已关闭 skill [{active_skill}]", C.GREEN))
                    active_skill = None
                else:
                    print(color("  （当前本来就没启用任何 skill）", C.GRAY))
                continue
            if rest not in available_skills:
                # 手滑打错名字很正常，重新扫一遍再确认一次，免得误报"不存在"
                available_skills = discover_skills()
            if rest in available_skills:
                active_skill = rest
                print(color(f"  ✓ 已启用 skill [{active_skill}]", C.GREEN) +
                      color(f" —— {available_skills[active_skill]['description']}", C.DIM))
            else:
                names = ", ".join(available_skills.keys()) if available_skills else "(无)"
                print(color(f"  ✗ 没有叫 [{rest}] 的 skill，可选: {names}", C.RED))
            continue

        print(color("Agent ▸ ", C.YELLOW, C.BOLD))
        reply = chat(user_input, history, system_prompt=effective_system_prompt())
        typewriter_print(reply)
        print()


if __name__ == "__main__":
    main()
