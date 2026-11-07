"""Hub provider for the owner's paired Muse account, without an API-model hop.

Only the latest utterance crosses the local authenticated Gadget socket. Muse
owns the conversation context. Music commands are recognized by
bounded local rules and sent through the existing Hub tools.
"""

import json
import os
import re
import select
import socket
import threading
import time
import unicodedata
import uuid
from pathlib import Path
from types import SimpleNamespace

from config.logger import setup_logging
from core.providers.llm.base import LLMProviderBase

logger = setup_logging()
TAG = __name__
MAX_REPLY_BYTES = 256 * 1024


def latest_question(dialogue):
    for entry in reversed(dialogue):
        if entry.get("role") != "user":
            continue
        value = entry.get("content", "")
        if not isinstance(value, str):
            raise ValueError("目前请用语音或文字提问。")
        if value.startswith("{"):
            try:
                wrapped = json.loads(value)
                if isinstance(wrapped, dict) and isinstance(wrapped.get("content"), str):
                    value = wrapped["content"]
            except ValueError:
                pass
        value = unicodedata.normalize("NFKC", value).strip()
        if not value or len(value) > 6000 or any(unicodedata.category(c) in {"Cc", "Cs"} and c not in "\n\t" for c in value):
            raise ValueError("这句话没有识别完整，请简短地再说一次。")
        return value
    raise ValueError("请告诉我想聊什么。")


def local_command(text):
    text = re.sub(r"^[\s，,。]*(?:小麦小麦[，,\s]*)?", "", text).strip()
    text = re.sub(r"^(?:(?:请|帮我|给我|麻烦你|麻烦|我想要|我想)[，,\s]*)+", "", text)
    compact = re.sub(r"[\s，。！？,.!?]", "", text)
    controls = {
        "暂停": "暂停", "暂停音乐": "暂停", "暂停播放": "暂停", "停一下音乐": "暂停",
        "继续播放": "继续", "继续音乐": "继续", "继续播放音乐": "继续", "恢复播放": "继续",
        "停止音乐": "停止音乐", "停止播放": "停止播放", "关掉音乐": "关掉音乐",
        "下一首": "下一首", "切歌": "下一首", "换一首": "下一首", "上一首": "上一首",
        "播放音乐": "random", "放音乐": "random", "听音乐": "random", "打开网易云": "打开网易云",
    }
    if compact in controls:
        return "play_music", {"song_name": controls[compact]}
    match = re.match(r"^(?:播放|放一下|放一首|放首|放|听一下|听一首|听首|听)(.+)$", text)
    if match and not re.match(r"^(你|您|我|说|听|一下|起来)", match[1]):
        query = match[1].strip(" ，。！？,.!?")
        if query:
            return "play_music", {"song_name": query}
    if compact in {"结束对话", "退出对话", "退下", "再见", "不用了"}:
        return "handle_exit_intent", {"say_goodbye": "好的，需要时再叫小麦。"}
    return None


def additional_text(old, new):
    """Do not speak a replay twice or splice a rewritten prefix into old audio."""
    return new[len(old):] if isinstance(new, str) and new.startswith(old) else ""


class LLMProvider(LLMProviderBase):
    def __init__(self, config):
        self.socket_path = config.get("socket_path", "/run/musegadget/musegadget.sock")
        self.state_dir = Path(config.get("state_dir", "/var/lib/thinksmart-muse"))
        self.wait_seconds = min(180, max(30, int(config.get("wait_seconds", 120))))
        self._lock = threading.RLock()
        self._active = {}

    def _session(self):
        with self._lock:
            self.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            path = self.state_dir / "session-id"
            if path.exists():
                return str(uuid.UUID(path.read_text().strip()))
            value = str(uuid.uuid4())
            tmp = path.with_name(".session-" + uuid.uuid4().hex)
            fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            try:
                with os.fdopen(fd, "w") as f:
                    f.write(value + "\n")
                os.replace(tmp, path)
            finally:
                tmp.unlink(missing_ok=True)
            return value

    def abort(self, conn):
        with self._lock:
            active = list(self._active.get(conn.session_id, ()))
        for sock, cancelled in active:
            cancelled.set()
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def on_conn_close(self, conn):
        self.abort(conn)

    def response(self, session_id, dialogue, **kwargs):
        try:
            question = latest_question(dialogue)
        except ValueError as error:
            yield str(error)
            return
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        cancelled = threading.Event()
        item = (sock, cancelled)
        with self._lock:
            self._active.setdefault(session_id, []).append(item)
        started = time.monotonic()
        spoken = ""
        outcome = "unavailable"
        sent = False
        try:
            request = {"message": question, "session_id": self._session(), "wait": self.wait_seconds, "stream": True}
            sock.settimeout(5)
            sock.connect(self.socket_path)
            if cancelled.is_set():
                return
            sock.sendall((json.dumps(request, ensure_ascii=False) + "\n").encode())
            sent = True
            buffer = b""
            deadline = started + self.wait_seconds + 8
            while not cancelled.is_set():
                if time.monotonic() >= deadline:
                    outcome = "pending"
                    yield "Muse 还没有返回完整回答，请稍后再问；我没有重复提交这个问题。"
                    return
                if not select.select([sock], [], [], 0.5)[0]:
                    # The Hub observes interruption on every yielded chunk.
                    yield ""
                    continue
                chunk = sock.recv(16384)
                if not chunk:
                    if cancelled.is_set():
                        return
                    raise ConnectionError("local reply stream ended")
                buffer += chunk
                if len(buffer) > MAX_REPLY_BYTES:
                    raise ValueError("local reply is too large")
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    frame = json.loads(line)
                    if not isinstance(frame, dict):
                        raise ValueError("invalid local reply")
                    if frame.get("type") == "accepted":
                        continue
                    if frame.get("type") == "reply":
                        text = frame.get("text", "")
                        extra = additional_text(spoken, text)
                        if extra:
                            spoken += extra
                            yield extra
                        continue
                    if not frame.get("ok"):
                        outcome = "uncertain" if frame.get("sent") == "unknown" else "unavailable"
                        if outcome == "uncertain":
                            yield "问题可能已经送到 Muse，但还没有收到确认。我没有重复发送。"
                        else:
                            yield "Muse 当前连接不稳定，请稍后再说一次。"
                        return
                    reply = frame.get("reply")
                    if isinstance(reply, str):
                        extra = additional_text(spoken, reply)
                        if extra:
                            spoken += extra
                            yield extra
                        outcome = "partial" if frame.get("partial") else "answered"
                        if frame.get("partial"):
                            yield "\nMuse 还在继续处理。"
                        elif not spoken:
                            yield "Muse 已经处理完成，但没有返回文字。"
                    else:
                        outcome = "pending"
                        yield "Muse 还没有返回回答，我没有重复发送这个问题。"
                    return
        except (OSError, ValueError) as error:
            if not cancelled.is_set():
                outcome = "uncertain" if sent else "unavailable"
                logger.bind(tag=TAG).warning("Muse 直接连接异常: " + type(error).__name__)
                yield ("Muse 的连接中断了，问题可能已经送达，我没有重复发送。" if sent else "暂时连接不到 Muse，请稍后再试。")
        finally:
            sock.close()
            with self._lock:
                values = self._active.get(session_id, [])
                if item in values:
                    values.remove(item)
                if not values:
                    self._active.pop(session_id, None)
            logger.bind(tag=TAG).info("Muse 直接对话结束: status=%s, seconds=%.2f, response_chars=%d" %
                                     ("interrupted" if cancelled.is_set() else outcome, time.monotonic()-started, len(spoken)))

    def response_with_functions(self, session_id, dialogue, functions=None, **kwargs):
        try:
            question = latest_question(dialogue)
        except ValueError as error:
            yield str(error), None
            return
        command = local_command(question)
        allowed = {d.get("function", {}).get("name") for d in (functions or []) if isinstance(d, dict)}
        if command and command[0] in allowed:
            name, arguments = command
            call = SimpleNamespace(index=0, id="muse-local-" + uuid.uuid4().hex,
                                   function=SimpleNamespace(name=name, arguments=json.dumps(arguments, ensure_ascii=False)))
            logger.bind(tag=TAG).info("Muse 模式本机指令: " + name)
            yield None, [call]
            return
        for chunk in self.response(session_id, dialogue, **kwargs):
            yield chunk, None
