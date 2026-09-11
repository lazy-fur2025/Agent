#!/usr/bin/env python3
"""Agnes CLI Agent v3 — a small, beginner-friendly terminal AI assistant.

No third-party packages are required. Configure it with AGNES_API_KEY (or /key)
and start chatting. Type /help inside the program to see all commands.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from itertools import cycle
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# ---------------------------------------------------------------------------
# Terminal presentation. ANSI is deliberately optional so redirected output,
# old consoles, and automated tests remain readable.
# ---------------------------------------------------------------------------
class Style:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[96m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"
    GRAY = "\033[90m"


def enable_utf8_output():
    """Avoid UnicodeEncodeError in legacy Windows consoles (Python 3.7+)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


class Console:
    def __init__(self, animated=True):
        enable_utf8_output()
        self.animated = animated and sys.stdout.isatty()

    def paint(self, text, *styles):
        return "".join(styles) + text + Style.RESET if self.animated else text

    def line(self, char="─"):
        print(self.paint(char * min(shutil.get_terminal_size((72, 20)).columns, 82), Style.GRAY))

    def banner(self):
        if not self.animated:
            print("AGNES CLI AGENT")
            return
        art = ("  ▄▄▄   ▄▄ ▄▄▄▄▄▄ ▄▄  ▄▄ ▄▄▄▄▄ ▄▄▄▄▄",
               " ██▀██ ██  ██   ██▀▄▄  ██▄▄  ██▄▄",
               " ██▄██ ▀██▀▀ ██ ██  ██ ██▄▄▄ ▄▄▄██")
        for line, hue in zip(art, (Style.CYAN, Style.BLUE, Style.MAGENTA)):
            print(self.paint(line, hue, Style.BOLD))

    def note(self, text, kind="info"):
        palette = {"ok": ("✓", Style.GREEN), "warn": ("!", Style.YELLOW),
                   "error": ("✗", Style.RED), "info": ("·", Style.GRAY)}
        mark, hue = palette[kind]
        print(self.paint("  {} {}".format(mark, text), hue))

    def type_out(self, text, delay=0.006):
        """A restrained answer transition; it switches off when output is piped."""
        if not text:
            self.note("模型没有返回文字。", "warn")
            return
        if not self.animated:
            print(text)
            return
        for char in text:
            sys.stdout.write(char)
            sys.stdout.flush()
            time.sleep(delay * (2.5 if char in "。！？.!?\n" else 1))
        print()


class Spinner:
    FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def __init__(self, console, label):
        self.console, self.label = console, label
        self.stop = threading.Event()
        self.thread = None
        self.started = 0

    def _draw(self):
        for frame in cycle(self.FRAMES):
            if self.stop.is_set():
                return
            elapsed = time.monotonic() - self.started
            text = "\r{} {} {}".format(
                self.console.paint(frame, Style.MAGENTA),
                self.console.paint(self.label, Style.DIM),
                self.console.paint("{:.1f}s".format(elapsed), Style.GRAY))
            sys.stdout.write(text)
            sys.stdout.flush()
            time.sleep(.09)

    def __enter__(self):
        self.started = time.monotonic()
        if self.console.animated:
            self.thread = threading.Thread(target=self._draw, daemon=True)
            self.thread.start()
        else:
            print(self.label + "…", end="", flush=True)
        return self

    def __exit__(self, *_):
        elapsed = time.monotonic() - self.started
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=.5)
            sys.stdout.write("\r" + " " * shutil.get_terminal_size((72, 20)).columns + "\r")
        else:
            print(" ({:.1f}s)".format(elapsed))
        sys.stdout.flush()


# ---------------------------------------------------------------------------
# Runtime state and API layer
# ---------------------------------------------------------------------------
PRESETS = {
    "agnes": ("https://api.agnes-ai.cn/v1/chat/completions", "agnes-2.5-flash"),
    "openai": ("https://api.openai.com/v1/chat/completions", "gpt-4o-mini"),
    "deepseek": ("https://api.deepseek.com/v1/chat/completions", "deepseek-chat"),
}

DEFAULT_SYSTEM_PROMPT = """You are a helpful AI assistant with agent capabilities.
Explain your intended action briefly before using a tool. Use tools only when they
help. Be concise, careful with user files, and give a clear final answer."""


@dataclass
class Settings:
    endpoint: str
    api_key: str
    model: str
    workspace: Path
    max_tool_rounds: int = 20
    max_context_chars: int = 48000
    animations: bool = True


class ApiError(RuntimeError):
    pass


def request_chat(settings, messages, tools):
    """Call an OpenAI-compatible chat endpoint with useful, non-traceback errors."""
    payload = json.dumps({"model": settings.model, "messages": messages, "tools": tools},
                         ensure_ascii=False).encode("utf-8")
    request = Request(settings.endpoint, data=payload, method="POST")
    request.add_header("Content-Type", "application/json")
    if settings.api_key:
        request.add_header("Authorization", "Bearer " + settings.api_key)
    try:
        with urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            detail = "(没有错误详情)"
        raise ApiError("服务器返回 HTTP {}：{}".format(exc.code, detail)) from exc
    except URLError as exc:
        raise ApiError("无法连接 API：{}".format(exc.reason)) from exc
    except TimeoutError as exc:
        raise ApiError("API 请求超时（120 秒）。") from exc
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApiError("API 返回的不是 JSON：{}".format(raw[:300])) from exc
    if result.get("error"):
        raise ApiError("API 错误：{}".format(result["error"]))
    choices = result.get("choices") or []
    if not choices or not choices[0].get("message"):
        raise ApiError("响应缺少 choices[0].message：{}".format(raw[:300]))
    return choices[0]["message"]


def bounded_messages(history, system_prompt, limit):
    """Keep whole user turns, avoiding invalid orphaned tool-result messages."""
    starts = [i for i, item in enumerate(history) if item.get("role") == "user"]
    groups = [history[starts[n]: starts[n + 1] if n + 1 < len(starts) else len(history)]
              for n in range(len(starts))]
    chosen, used = [], len(system_prompt)
    for group in reversed(groups):
        size = len(json.dumps(group, ensure_ascii=False))
        if chosen and used + size > limit:
            break
        chosen.insert(0, group)
        used += size
    return [{"role": "system", "content": system_prompt}] + [x for group in chosen for x in group]


# ---------------------------------------------------------------------------
# Small, transparent tool set. File tools intentionally stay inside the chosen
# workspace; /workspace explicitly changes that boundary when needed.
# ---------------------------------------------------------------------------
SEARCH_SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", ".idea", ".vscode"}


def tool_schema(name, description, properties, required=()):
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": list(required)}}}


TOOLS = [
    tool_schema("run_command", "Run a shell command in the current workspace and return output.", {
        "command": {"type": "string", "description": "Shell command to run"},
        "workdir": {"type": "string", "description": "Optional directory inside workspace"}}, ("command",)),
    tool_schema("read_file", "Read a UTF-8 text file inside the workspace.", {
        "path": {"type": "string", "description": "Workspace-relative path"}}, ("path",)),
    tool_schema("write_file", "Create or replace a UTF-8 text file inside the workspace.", {
        "path": {"type": "string", "description": "Workspace-relative path"},
        "content": {"type": "string", "description": "Complete file contents"}}, ("path", "content")),
    tool_schema("list_directory", "List a directory inside the workspace.", {
        "path": {"type": "string", "description": "Workspace-relative directory, default ."},
        "pattern": {"type": "string", "description": "Optional glob, e.g. *.py"}}),
    tool_schema("search_files", "Search UTF-8 text files in the workspace using a regular expression.", {
        "pattern": {"type": "string", "description": "Regular expression"},
        "path": {"type": "string", "description": "Workspace-relative directory, default ."},
        "include": {"type": "string", "description": "Optional glob, e.g. *.py"}}, ("pattern",)),
    tool_schema("edit_file", "Replace one exact piece of text in a workspace text file.", {
        "path": {"type": "string", "description": "Workspace-relative path"},
        "old_text": {"type": "string", "description": "Exact text to replace"},
        "new_text": {"type": "string", "description": "Replacement text"}}, ("path", "old_text", "new_text")),
]


class ToolRunner:
    MAX_FILE_BYTES = 512 * 1024

    def __init__(self, settings):
        self.settings = settings

    def path(self, value="."):
        root = self.settings.workspace.resolve()
        candidate = (root / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            raise ValueError("路径必须位于工作目录内：{}".format(root))
        return candidate

    def run_command(self, args):
        command = str(args.get("command", "")).strip()
        if not command:
            return "[ERROR] 命令不能为空。"
        try:
            workdir = self.path(args.get("workdir") or ".")
            if not workdir.is_dir():
                return "[ERROR] 工作目录不存在：{}".format(workdir)
            result = subprocess.run(command, shell=True, cwd=str(workdir), timeout=60,
                                    capture_output=True, text=True, encoding="utf-8", errors="replace")
            output = (result.stdout or "") + (("\n[stderr]\n" + result.stderr) if result.stderr else "")
            if result.returncode:
                output += "\n[exit code: {}]".format(result.returncode)
            return output.strip() or "(无输出)"
        except subprocess.TimeoutExpired:
            return "[ERROR] 命令超过 60 秒，已停止。"
        except Exception as exc:
            return "[ERROR] {}".format(exc)

    def read_file(self, args):
        try:
            file = self.path(args.get("path", ""))
            if not file.is_file():
                return "[ERROR] 文件不存在：{}".format(file)
            if file.stat().st_size > self.MAX_FILE_BYTES:
                return "[ERROR] 文件过大（上限 512KB）。"
            return file.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return "[ERROR] {}".format(exc)

    def write_file(self, args):
        try:
            file = self.path(args.get("path", ""))
            text = str(args.get("content", ""))
            if len(text.encode("utf-8")) > self.MAX_FILE_BYTES:
                return "[ERROR] 写入内容超过 512KB 上限。"
            file.parent.mkdir(parents=True, exist_ok=True)
            temp = file.with_name(file.name + ".agent-tmp")
            temp.write_text(text, encoding="utf-8")
            temp.replace(file)  # Atomic replacement avoids half-written files.
            return "已写入 {}（{} 字符）".format(file.relative_to(self.settings.workspace), len(text))
        except Exception as exc:
            return "[ERROR] {}".format(exc)

    def list_directory(self, args):
        try:
            directory = self.path(args.get("path") or ".")
            if not directory.is_dir():
                return "[ERROR] 目录不存在：{}".format(directory)
            pattern = args.get("pattern") or "*"
            entries = sorted(directory.glob(pattern), key=lambda p: (not p.is_dir(), p.name.lower()))
            lines = [("📁 " if item.is_dir() else "📄 ") + item.name for item in entries[:100]]
            if len(entries) > 100:
                lines.append("… 还有 {} 项".format(len(entries) - 100))
            return "\n".join(lines) or "（空目录）"
        except Exception as exc:
            return "[ERROR] {}".format(exc)

    def search_files(self, args):
        try:
            regex = re.compile(str(args.get("pattern", "")))
            folder = self.path(args.get("path") or ".")
            include = args.get("include") or "*"
            matches, scanned = [], 0
            for file in folder.rglob(include):
                if file.is_symlink() or any(part in SEARCH_SKIP for part in file.parts) or not file.is_file():
                    continue
                scanned += 1
                if scanned > 5000:
                    matches.append("… 已扫描 5000 个文件，提前停止。")
                    break
                if file.stat().st_size > self.MAX_FILE_BYTES:
                    continue
                for number, line in enumerate(file.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    if regex.search(line):
                        matches.append("{}:{}: {}".format(file.relative_to(self.settings.workspace), number, line.strip()[:160]))
                        if len(matches) >= 50:
                            return "\n".join(matches) + "\n… 结果已截断。"
            return "\n".join(matches) or "（未找到匹配）"
        except re.error as exc:
            return "[ERROR] 正则表达式无效：{}".format(exc)
        except Exception as exc:
            return "[ERROR] {}".format(exc)

    def edit_file(self, args):
        try:
            file = self.path(args.get("path", ""))
            if not file.is_file():
                return "[ERROR] 文件不存在：{}".format(file)
            old, new = str(args.get("old_text", "")), str(args.get("new_text", ""))
            if not old:
                return "[ERROR] old_text 不能为空，避免意外插入。"
            content = file.read_text(encoding="utf-8", errors="replace")
            if old not in content:
                return "[ERROR] 没有找到要替换的文本。"
            occurrences = content.count(old)
            updated = content.replace(old, new, 1)
            if len(updated.encode("utf-8")) > self.MAX_FILE_BYTES:
                return "[ERROR] 编辑后文件超过 512KB 上限。"
            temp = file.with_name(file.name + ".agent-tmp")
            temp.write_text(updated, encoding="utf-8")
            temp.replace(file)
            suffix = "（找到 {} 处，仅替换第一处）".format(occurrences) if occurrences > 1 else ""
            return "已编辑 {}{}".format(file.relative_to(self.settings.workspace), suffix)
        except Exception as exc:
            return "[ERROR] {}".format(exc)

    def execute(self, name, args):
        method = getattr(self, name, None)
        return method(args) if method else "[ERROR] 未知工具：{}".format(name)


# ---------------------------------------------------------------------------
# Conversation and commands
# ---------------------------------------------------------------------------
class Agent:
    def __init__(self, settings, console):
        self.settings, self.console = settings, console
        self.history = []
        self.system_prompt = DEFAULT_SYSTEM_PROMPT
        self.active_skill = None
        self.skills = {}
        self.refresh_skills()
        self.tools = ToolRunner(settings)

    def refresh_skills(self):
        root = self.settings.workspace / "skills"
        found = {}
        if root.is_dir():
            for item in sorted(root.iterdir()):
                file = item / "SKILL.md"
                if file.is_file():
                    try:
                        body = file.read_text(encoding="utf-8", errors="replace")
                        description = next((line.strip() for line in body.splitlines()
                                            if line.strip() and not line.startswith(("#", "---"))), "（无简介）")
                        found[item.name] = (file, description[:160])
                    except OSError:
                        pass
        self.skills = found

    def effective_prompt(self):
        if not self.active_skill or self.active_skill not in self.skills:
            return self.system_prompt
        try:
            skill_text = self.skills[self.active_skill][0].read_text(encoding="utf-8", errors="replace")
            return "{}\n\n---\n# 已启用 Skill: {}\n{}".format(self.system_prompt, self.active_skill, skill_text)
        except OSError as exc:
            self.console.note("无法读取 Skill：{}".format(exc), "warn")
            return self.system_prompt

    def ask(self, user_text):
        if not self.settings.api_key:
            self.console.note("还没有 API Key。用 /key 填入，或设置 AGNES_API_KEY 后重启。", "warn")
            return
        turn_start = len(self.history)
        self.history.append({"role": "user", "content": user_text})
        for round_number in range(self.settings.max_tool_rounds):
            try:
                label = "思考中" if round_number == 0 else "继续处理（第 {} 轮）".format(round_number + 1)
                with Spinner(self.console, label):
                    message = request_chat(self.settings, bounded_messages(self.history, self.effective_prompt(),
                                                                           self.settings.max_context_chars), TOOLS)
            except ApiError as exc:
                self.console.note(str(exc), "error")
                # A later tool round may already have added an assistant/tool
                # sequence. Remove the entire failed turn, not just its tail.
                del self.history[turn_start:]
                return
            content, calls = message.get("content") or "", message.get("tool_calls") or []
            if not calls:
                self.history.append({"role": "assistant", "content": content})
                print(self.console.paint("Agent ▸ ", Style.YELLOW, Style.BOLD), end="")
                self.console.type_out(content)
                return
            self.history.append({"role": "assistant", "content": content or None, "tool_calls": calls})
            for call in calls:
                function = call.get("function") or {}
                name, raw = function.get("name", ""), function.get("arguments") or "{}"
                try:
                    args = json.loads(raw)
                    if not isinstance(args, dict):
                        raise ValueError("参数不是对象")
                except (json.JSONDecodeError, ValueError) as exc:
                    args, result = {}, "[ERROR] 工具参数无效：{}".format(exc)
                else:
                    preview = json.dumps(args, ensure_ascii=False)[:100]
                    print(self.console.paint("  ├─ ⚡ {}({})".format(name, preview), Style.CYAN))
                    started = time.monotonic()
                    with Spinner(self.console, "执行 {}".format(name)):
                        result = self.tools.execute(name, args)
                    ok = not result.startswith("[ERROR]")
                    marker, hue = ("✓", Style.GREEN) if ok else ("✗", Style.RED)
                    compact = result.replace("\n", " ⏎ ")[:130]
                    print(self.console.paint("  │  {} {}  [{:.2f}s]".format(marker, compact, time.monotonic() - started), hue))
                self.history.append({"role": "tool", "tool_call_id": call.get("id", ""),
                                     "content": result[:8000]})
        self.console.note("工具调用次数达到上限，已停止以避免死循环。", "warn")

    def save(self, filename):
        path = Path(filename or "agnes-session.json").expanduser()
        if not path.is_absolute():
            path = self.settings.workspace / path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"version": 3, "model": self.settings.model,
                                        "endpoint": self.settings.endpoint, "history": self.history,
                                        "system_prompt": self.system_prompt, "active_skill": self.active_skill},
                                       ensure_ascii=False, indent=2), encoding="utf-8")
            self.console.note("会话已保存到 {}（不包含 API Key）。".format(path), "ok")
        except OSError as exc:
            self.console.note("保存失败：{}".format(exc), "error")

    def load(self, filename):
        path = Path(filename or "agnes-session.json").expanduser()
        if not path.is_absolute():
            path = self.settings.workspace / path
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            history = data.get("history")
            if not isinstance(history, list):
                raise ValueError("缺少有效的 history")
            self.history = history
            self.system_prompt = str(data.get("system_prompt") or DEFAULT_SYSTEM_PROMPT)
            self.active_skill = data.get("active_skill") if data.get("active_skill") in self.skills else None
            self.settings.model = str(data.get("model") or self.settings.model)
            self.settings.endpoint = str(data.get("endpoint") or self.settings.endpoint)
            self.console.note("已载入 {} 条记录。".format(len(history)), "ok")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self.console.note("载入失败：{}".format(exc), "error")


HELP = """常用命令
  /help                 显示这份帮助
  /setup                重新走一遍服务商配置向导（选预设或自定义 URL/Key/Model）
  /clear                清空当前对话；/history 查看简要历史
  /save [文件]          保存会话（不会保存 API Key）
  /load [文件]          载入会话；/export [文件] 导出纯文本记录
  /model [名称]         查看或切换模型；/api [地址]、/key
  /preset [agnes|openai|deepseek]  应用接口与模型预设
  /workspace [目录]     切换文件工具目录；命令默认也从这里运行
  /skills               查看 skills/<名称>/SKILL.md
  /skill <名称|off>     启用一个 Skill 或关闭它
  /system               编辑系统提示词；/config 查看当前配置
  /theme [on|off]       开关颜色、转圈与打字过渡；/quit 退出"""


def print_header(agent):
    ui = agent.console
    print()
    ui.banner()
    ui.line()
    print(ui.paint("  模型  ", Style.DIM) + ui.paint(agent.settings.model, Style.CYAN, Style.BOLD))
    print(ui.paint("  工作区", Style.DIM) + " " + ui.paint(str(agent.settings.workspace), Style.GRAY))
    print(ui.paint("  提示  ", Style.DIM) + "/help 查看命令，/config 查看配置，/setup 重新选服务商")
    ui.line()
    print()


def export_history(agent, filename):
    path = Path(filename or "agnes-history.txt").expanduser()
    if not path.is_absolute():
        path = agent.settings.workspace / path
    try:
        lines = ["Agnes CLI 会话记录", "=" * 22, ""]
        for entry in agent.history:
            role = entry.get("role", "unknown").upper()
            content = entry.get("content") or ""
            if content:
                lines.extend([role, content, ""])
        path.write_text("\n".join(lines), encoding="utf-8")
        agent.console.note("已导出到 {}。".format(path), "ok")
    except OSError as exc:
        agent.console.note("导出失败：{}".format(exc), "error")


def repl(agent):
    print_header(agent)
    ui = agent.console
    while True:
        try:
            text = input(ui.paint("You  ▸ ", Style.CYAN, Style.BOLD)).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n" + ui.paint("再见啦～ 👋", Style.MAGENTA))
            return
        if not text:
            continue
        if not text.startswith("/"):
            agent.ask(text)
            print()
            continue
        command, _, argument = text[1:].partition(" ")
        command, argument = command.lower(), argument.strip()
        if command in ("quit", "exit", "q"):
            print(ui.paint("再见啦～ 👋", Style.MAGENTA))
            return
        if command in ("help", "?"):
            print(HELP)
        elif command in ("clear", "reset"):
            agent.history.clear()
            ui.note("历史已清空。", "ok")
        elif command == "history":
            if not agent.history:
                ui.note("当前没有历史记录。")
            for item in agent.history:
                body = (item.get("content") or "").replace("\n", " ")[:110]
                if body:
                    print(ui.paint("  [{}] ".format(item.get("role", "?")), Style.BLUE) + body)
        elif command == "save":
            agent.save(argument)
        elif command == "load":
            agent.load(argument)
        elif command == "export":
            export_history(agent, argument)
        elif command == "config":
            key = (agent.settings.api_key[:6] + "…") if agent.settings.api_key else "（未设置）"
            print("  模型: {}\n  API: {}\n  Key: {}\n  工作区: {}\n  Skill: {}".format(
                agent.settings.model, agent.settings.endpoint, key, agent.settings.workspace,
                agent.active_skill or "（未启用）"))
        elif command == "model":
            if argument:
                agent.settings.model = argument
                ui.note("模型已切换为 {}。".format(argument), "ok")
            else:
                print("当前模型：{}；用 /model <名称> 修改。".format(agent.settings.model))
        elif command == "api":
            if argument:
                agent.settings.endpoint = argument
                ui.note("API 地址已更新。", "ok")
            else:
                print("当前 API：{}；用 /api <地址> 修改。".format(agent.settings.endpoint))
        elif command == "key":
            value = argument or input(ui.paint("输入 API Key（留空取消）：", Style.DIM)).strip()
            if value:
                agent.settings.api_key = value
                ui.note("API Key 已更新（仅保存在本次运行内）。", "ok")
        elif command == "preset":
            if argument not in PRESETS:
                print("可用预设：" + "、".join(PRESETS))
            else:
                agent.settings.endpoint, agent.settings.model = PRESETS[argument]
                ui.note("已应用 {} 预设。".format(argument), "ok")
        elif command == "setup":
            run_setup_wizard(ui, agent.settings)
        elif command == "workspace":
            if not argument:
                print("当前工作区：{}".format(agent.settings.workspace))
            else:
                folder = Path(argument).expanduser().resolve()
                if folder.is_dir():
                    agent.settings.workspace = folder
                    agent.tools = ToolRunner(agent.settings)
                    agent.refresh_skills()
                    agent.active_skill = None
                    ui.note("工作区已切换到 {}。".format(folder), "ok")
                else:
                    ui.note("目录不存在：{}".format(folder), "error")
        elif command == "skills":
            agent.refresh_skills()
            if not agent.skills:
                ui.note("没有找到 Skill；放在 skills/<名称>/SKILL.md 即可。")
            for name, (_, description) in agent.skills.items():
                state = " ●" if name == agent.active_skill else "  "
                print(ui.paint(state + " " + name, Style.MAGENTA, Style.BOLD) + " — " + description)
        elif command == "skill":
            agent.refresh_skills()
            if argument.lower() in ("off", "none", "取消"):
                agent.active_skill = None
                ui.note("Skill 已关闭。", "ok")
            elif argument in agent.skills:
                agent.active_skill = argument
                ui.note("已启用 Skill：{}。".format(argument), "ok")
            else:
                ui.note("请输入有效名称；用 /skills 查看。", "warn")
        elif command == "system":
            value = input(ui.paint("新系统提示词（留空取消）：", Style.DIM)).strip()
            if value:
                agent.system_prompt = value
                ui.note("系统提示词已更新。", "ok")
        elif command == "theme":
            if argument.lower() in ("off", "0"):
                agent.console.animated = False
            elif argument.lower() in ("on", "1"):
                agent.console.animated = sys.stdout.isatty()
            else:
                print("当前：{}；用 /theme on 或 /theme off 修改。".format("开" if ui.animated else "关"))
        else:
            ui.note("未知命令。输入 /help 查看可用命令。", "warn")


def run_setup_wizard(console, settings):
    """首次启动或缺少 API Key 时的交互式配置向导。
    整个过程只在终端里问答完成，不需要用户去改任何文件。"""
    console.line()
    console.note("还没有配置服务商，跟着提示选一下吧（几秒钟搞定）。", "info")
    print()

    names = list(PRESETS.keys())
    print(console.paint("  可用预设：", Style.DIM))
    for i, name in enumerate(names, 1):
        endpoint, model = PRESETS[name]
        print("    {}. {}  ({}, 默认模型 {})".format(i, console.paint(name, Style.CYAN, Style.BOLD), endpoint, model))
    print("    {}. {}".format(len(names) + 1, console.paint("自定义（自己填 URL / Model / Key）", Style.MAGENTA)))
    print()

    choice = input(console.paint("  选一个 [1-{}]，直接回车默认选 1：".format(len(names) + 1), Style.DIM)).strip()
    if not choice:
        choice = "1"

    if choice.isdigit() and 1 <= int(choice) <= len(names):
        picked = names[int(choice) - 1]
        settings.endpoint, settings.model = PRESETS[picked]
        console.note("已选择预设：{}".format(picked), "ok")
    else:
        # 自定义分支：不管选了最后一项还是随便输了个乱七八糟的东西，都当自定义处理，
        # 别因为用户手滑打错数字就直接崩给他看。
        console.note("自定义模式，直接输入即可（留空则用默认值）。", "info")
        custom_url = input(console.paint("  API 地址（Chat Completions 端点）：", Style.DIM)).strip()
        if custom_url:
            settings.endpoint = custom_url
        custom_model = input(console.paint("  模型名称：", Style.DIM)).strip()
        if custom_model:
            settings.model = custom_model

    # API Key：首次配置必须填；如果是 /setup 重新配置且已有 key，问一下要不要换，
    # 免得用户明明想换新 key 却发现向导跳过了这一步。
    if settings.api_key:
        keep = input(console.paint(
            "  已有 API Key（{}...），是否更换？直接回车=保留，输入新值=更换：".format(settings.api_key[:6]),
            Style.DIM)).strip()
        if keep:
            settings.api_key = keep
    else:
        while not settings.api_key:
            key = input(console.paint("  API Key（必填，输入后不回显到日志/存档）：", Style.DIM)).strip()
            if key:
                settings.api_key = key
            else:
                console.note("API Key 不能为空，重新输入一次。", "warn")

    console.note("配置完成：{} @ {}".format(settings.model, settings.endpoint), "ok")
    console.line()
    print()


def main():
    # Windows may still start Python with a legacy GBK console encoding.  The UI
    # intentionally uses Chinese text and a few harmless symbols, so prefer UTF-8.
    enable_utf8_output()
    parser = argparse.ArgumentParser(description="轻量级终端 AI Agent（无第三方依赖）")
    parser.add_argument("--api", default=os.getenv("AGNES_API_BASE", PRESETS["agnes"][0]), help="Chat Completions API 地址")
    parser.add_argument("--model", default=os.getenv("AGNES_MODEL", PRESETS["agnes"][1]), help="模型名称")
    parser.add_argument("--key", default=os.getenv("AGNES_API_KEY", ""), help="API Key（也可启动后用 /key 输入）")
    parser.add_argument("--workspace", default=os.getenv("AGNES_WORKSPACE", os.getcwd()), help="工具文件操作的根目录")
    parser.add_argument("--plain", action="store_true", help="关闭颜色和过渡动画")
    parser.add_argument("--setup", action="store_true", help="强制显示服务商选择向导（即使已有 Key）")
    args = parser.parse_args()
    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.is_dir():
        parser.error("工作目录不存在：{}".format(workspace))
    settings = Settings(args.api, args.key, args.model, workspace, animations=not args.plain)
    console = Console(settings.animations)
    if args.setup or not settings.api_key:
        run_setup_wizard(console, settings)
    repl(Agent(settings, console))


if __name__ == "__main__":
    main()
