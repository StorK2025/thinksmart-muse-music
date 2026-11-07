"""Run with the existing Hub venv; never print the user's configuration."""
import json
import os
from pathlib import Path
import sys
import tempfile
import yaml


def atomic_write(path, text):
    meta = path.stat()
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if hasattr(os, 'chown'):
            os.chown(tmp, meta.st_uid, meta.st_gid)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def configure(data):
    path = data / '.config.yaml'
    c = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    # Validate all inputs before either file is changed. The installer backs up both.
    sessions_path = data / 'agent_sessions.json'
    sessions = None
    if sessions_path.exists():
        sessions = json.loads(sessions_path.read_text(encoding='utf-8'))
        remembered = sessions.get('last_model', {})
        if len(remembered) > 1:
            raise ValueError('此网关有多个设备的模型记录，请使用独立的单设备网关。')
        for record in remembered.values():
            record['model'] = 'Muse'
    c.setdefault('LLM', {})['Muse'] = {
        'type': 'muse', 'wait_seconds': 120,
        'socket_path': '/run/musegadget/musegadget.sock',
        'state_dir': '/var/lib/thinksmart-muse',
    }
    c.setdefault('selected_module', {}).update(LLM='Muse', Intent='function_call', Memory='nomem')
    c.setdefault('Intent', {})['function_call'] = {'type': 'function_call', 'functions': ['play_music']}
    c.setdefault('chat_history', {})['summary'] = False
    # ASR, TTS, admin password and existing model credentials are kept locally.
    atomic_write(path, yaml.safe_dump(c, allow_unicode=True, sort_keys=False))
    if sessions is not None:
        atomic_write(sessions_path, json.dumps(sessions, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    configure(Path(sys.argv[1]))
    print('默认对话已设为 Muse；音乐在本机处理。')
