"""Local ThinkSmart voice bridge for NetEase Cloud Music's official web player.

This file intentionally re-registers the built-in ``play_music`` tool.  The Hub's
plugin loader imports modules alphabetically, so the ``zz_`` prefix makes this
device-local implementation replace the stock local-file player without changing
the tracked Hub configuration.
"""

import json
import os
import re
import time
from pathlib import Path

from plugins_func.register import Action, ActionResponse, ToolType, register_function


RUNTIME_DIR = os.environ.get("XDG_RUNTIME_DIR")
if not RUNTIME_DIR:
    RUNTIME_DIR = f"/run/user/{getattr(os, 'getuid', lambda: 1000)()}"
COMMAND_FILE = Path(RUNTIME_DIR) / "thinksmart-music-command.json"


play_music_function_desc = {
    "type": "function",
    "function": {
        "name": "play_music",
        "description": (
            "使用网易云音乐官方网页播放或控制音乐。用户要求播放歌曲、播放音乐、"
            "暂停、继续、停止、上一首、下一首或切歌时调用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "song_name": {
                    "type": "string",
                    "description": (
                        "具体歌曲名，可同时带歌手名；控制命令则填写：暂停、继续、停止、"
                        "上一首、下一首。用户没有指定歌曲而只是说播放音乐时填写 random。"
                    ),
                }
            },
            "required": ["song_name"],
        },
    },
}


def _classify(value):
    original = str(value or "").strip()
    compact = re.sub(r"[\s，。！？,.!?]", "", original).lower()
    if any(word in compact for word in ("下一首", "下首", "切歌", "换一首")):
        return "next", ""
    if any(word in compact for word in ("上一首", "上首")):
        return "previous", ""
    if any(word in compact for word in ("暂停", "停一下")):
        return "pause", ""
    if any(word in compact for word in ("停止播放", "停止音乐", "关掉音乐")):
        return "stop", ""
    if any(word in compact for word in ("继续播放", "继续音乐", "恢复播放", "继续")):
        return "resume", ""
    if compact in {"", "random", "随机", "播放音乐", "放音乐", "音乐"}:
        return "resume", ""
    if compact in {"打开网易云", "网易云", "网易云音乐"}:
        return "open", ""
    query = re.sub(r"^(请|帮我|给我)*(播放|放一下|放一首|放)", "", original).strip()
    return "play", query or original


def _send_command(action, query):
    payload = {
        "action": action,
        "query": query,
        "created": time.time(),
    }
    temporary = COMMAND_FILE.with_name(
        f".{COMMAND_FILE.name}.{os.getpid()}.{time.time_ns()}.tmp"
    )
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, COMMAND_FILE)


@register_function("play_music", play_music_function_desc, ToolType.SYSTEM_CTL)
async def play_music(conn, song_name="random"):
    action, query = _classify(song_name)
    try:
        _send_command(action, query)
        conn.logger.bind(tag=__name__).info(
            f"网易云网页音乐命令: action={action}"
        )
        result = f"网易云命令已接收: {action}"
        if query:
            result += f" {query}"
        # RECORD matches the stock music tool: do not speak over the song that is starting.
        return ActionResponse(action=Action.RECORD, result=result, response=result)
    except Exception as error:
        conn.logger.bind(tag=__name__).error(f"发送网易云网页音乐命令失败: {error}")
        return ActionResponse(
            action=Action.RESPONSE,
            result=str(error),
            response="网易云音乐控制暂时不可用",
        )
