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
API_BASE = os.environ.get("AGNES_API_BASE", "https://api.agnes-ai.cn/v1/chat/completions")
API_KEY = os.environ.get("AGNES_API_KEY", "")
MODEL = os.environ.get("AGNES_MODEL", "agnes-2.5-flash")
MAX_TOOL_ITERATIONS = int(os.environ.get("AGNES_MAX_ITERATIONS", "25"))  # 防止无限工具调用循环

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
    global API_KEY

    if not API_KEY:
        API_KEY = input("Enter your API key (or set AGNES_API_KEY env var): ").strip()
        if not API_KEY:
            print("No API key provided. Exiting.")
            sys.exit(1)

    print()
    gradient_banner()
    rule("─", C.GRAY)
    print(color("  Model  ", C.DIM) + color(MODEL, C.CYAN, C.BOLD))
    print(color("  API    ", C.DIM) + color(API_BASE, C.GRAY))
    rule("─", C.GRAY)
    print(color("  命令  ", C.DIM) + color("/quit", C.YELLOW) + "  " +
          color("/clear", C.YELLOW) + "  " + color("/system", C.YELLOW) + "  " +
          color("/history", C.YELLOW))
    print(color("  工具  ", C.DIM) +
          color("run_command · read_file · write_file · list_directory · search_files · edit_file", C.MAGENTA))
    rule("─", C.GRAY)
    print()

    history = []
    system_prompt = SYSTEM_PROMPT

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

        print(color("Agent ▸ ", C.YELLOW, C.BOLD))
        reply = chat(user_input, history, system_prompt=system_prompt)  # 真正把改过的 prompt 传进去
        typewriter_print(reply)
        print()


if __name__ == "__main__":
    main()
