#!/usr/bin/env python3
"""Install this add-on on the supported image. No flashing and no account tokens."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request

from transaction import Transaction

ROOT = Path(__file__).resolve().parents[1]
SDK_REV = '463bd2a05380fea4211b0099ad0f70933c108b20'
STATE = Path('/var/lib/thinksmart-muse-music')
SDK_PREFIX = Path('/opt/musegadget')
ASSETS = Path('/usr/local/share/thinksmart-kiosk')
MARKER = STATE / 'installed.json'
OWNERSHIP = STATE / 'managed-install.json'


def run(*args, capture=False, check=True, cwd=None, env=None):
    result = subprocess.run([str(a) for a in args], text=True, encoding='utf-8',
                            stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE if capture else None,
                            check=False, cwd=cwd, env=env)
    if check and result.returncode:
        # No raw captured configuration, credentials or remote command output in errors.
        raise RuntimeError('操作失败: ' + str(args[0]) + '，退出码 ' + str(result.returncode))
    return result.stdout.strip() if capture else result.returncode


def proxy_environment(value):
    if not value:
        return {}
    p = urllib.parse.urlsplit(value)
    if (p.scheme != 'http' or not p.hostname or p.username or p.password
            or p.path not in ('', '/') or p.query or p.fragment
            or not re.fullmatch(r'http://[A-Za-z0-9.\-\[\]:]+/?', value)):
        raise ValueError('代理请填写不带账号密码的 HTTP 地址，例如 http://127.0.0.1:7890')
    if not p.port or not 1 <= p.port <= 65535:
        raise ValueError('代理必须包含有效端口')
    return {**{k: value.rstrip('/') for k in ('http_proxy', 'https_proxy', 'HTTP_PROXY',
                                             'HTTPS_PROXY', 'ws_proxy', 'wss_proxy')},
            'no_proxy': 'localhost,127.0.0.1,::1', 'NO_PROXY': 'localhost,127.0.0.1,::1'}


def user_service(user, uid, action, check=True):
    return run('runuser', '-u', user, '--', 'env', f'XDG_RUNTIME_DIR=/run/user/{uid}',
               'systemctl', '--user', action, 'xiaozhi-hub.service', check=check)


def hub_identity(args):
    import pwd
    if not re.fullmatch(r'[a-z_][a-z0-9_-]*', args.user):
        raise ValueError('无效设备用户名')
    account = pwd.getpwnam(args.user)
    if account.pw_uid == 0 or account.pw_gid == 0:
        raise ValueError('Hub 和屏幕必须使用普通账号，不能选择 root。')
    hub = Path(args.hub or (Path(account.pw_dir) / 'xiaozhi-hub-server/main/xiaozhi-server')).resolve()
    return account, hub


def preflight(args):
    if platform.system() != 'Linux' or platform.machine() not in ('aarch64', 'arm64'):
        raise ValueError('请在 ThinkSmart 的 Ubuntu SSH 窗口执行；电脑 PowerShell 不是安装目标。')
    os_release = Path('/etc/os-release').read_text()
    if not re.search(r'^VERSION_ID="?24\.04"?$', os_release, re.M):
        raise ValueError('此版本只验证了 Ubuntu 24.04 基础镜像；停止以免改坏其他系统。')
    account, hub = hub_identity(args)
    for name in ('systemctl', 'git', 'curl', 'runuser'):
        if not shutil.which(name):
            raise ValueError('缺少命令 ' + name + '，请按 README 的准备步骤安装。')
    required = [hub / 'data/.config.yaml', hub / '.venv/bin/python',
                hub / 'core/providers/llm/base.py', hub / 'core/admin/config_store.py',
                Path('/usr/local/bin/thinksmart-kiosk.py'), Path('/usr/local/bin/thinksmart-kiosk-session'),
                ASSETS / 'welcome.html']
    for p in required:
        if not p.is_file():
            raise ValueError('缺少基础镜像组件: ' + str(p) + '；请先完成 docs/BASE_IMAGE.md。')
    for unit in ('thinksmart-kiosk.service', 'thinksmart-client.service'):
        if run('systemctl', 'show', '-p', 'LoadState', '--value', unit, capture=True) != 'loaded':
            raise ValueError('基础服务未安装: ' + unit)
    if shutil.disk_usage('/').free < 400 * 1024**2:
        raise ValueError('根分区至少需要 400 MiB 空闲空间。')
    # Intentionally only returns module names, never API keys or configuration bodies.
    code = ('from core.admin.config_store import load_merged; import json; '
            'c=load_merged(); print(json.dumps(c.get("selected_module",{})))')
    selected = json.loads(run(hub / '.venv/bin/python', '-c', code, capture=True, cwd=hub).splitlines()[-1])
    if selected.get('ASR') != 'SherpaXASR':
        raise ValueError('请先在小智后台选择并安装本地 SherpaXASR，参见 docs/BASE_IMAGE.md。')
    if selected.get('TTS') != 'EdgeTTS':
        raise ValueError('请先在小智后台把语音合成选为 EdgeTTS，参见 docs/BASE_IMAGE.md。')
    proxy_environment(args.proxy)
    print(f'环境检查通过：ARM64 / Ubuntu 24.04 / 用户 {args.user} / 本地识别 / EdgeTTS。')
    print('安装位置: ' + str(hub))
    return account, hub


def copy_file(source, target, mode=0o644, owner=None):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise ValueError('不覆盖符号链接: ' + str(target))
    shutil.copyfile(source, target)
    target.chmod(mode)
    if owner:
        os.chown(target, *owner)


def write_file(target, text, mode=0o644):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise ValueError('不覆盖符号链接: ' + str(target))
    target.write_text(text, encoding='utf-8')
    target.chmod(mode)


def fetch_sdk(env):
    source = STATE / ('source-' + SDK_REV)
    if not source.exists():
        source.mkdir(mode=0o700)
        run('git', 'init', '-q', source)
    run('git', '-C', source, 'config', 'core.autocrlf', 'false')
    run('git', '-C', source, 'fetch', '-q', '--depth=1',
        'https://github.com/facebookincubator/muse-gadget-sdk.git', SDK_REV, env=env)
    run('git', '-C', source, 'checkout', '-q', '--detach', SDK_REV)
    if run('git', '-C', source, 'rev-parse', 'HEAD', capture=True) != SDK_REV:
        raise RuntimeError('SDK 源码版本不匹配')
    lock = json.loads((ROOT / 'sdk/upstream-lock.json').read_text())
    for name, expected in lock['sha256'].items():
        content = (source / 'linux/src/musegadget' / name).read_bytes()
        if hashlib.sha256(content).hexdigest() != expected:
            raise RuntimeError('SDK 文件校验失败: ' + name)
    return source


def sdk_dir():
    p = Path(run(SDK_PREFIX / 'venv/bin/python', '-c',
                 'import musegadget; print(next(iter(musegadget.__path__)))', capture=True)).resolve()
    if not p.is_relative_to(SDK_PREFIX) or p.name != 'musegadget':
        raise ValueError('SDK 安装路径异常')
    return p


def config_kiosk(old, uid):
    # Keep orientation and renderer settings from the image. Music goes direct,
    # so a Muse proxy node in another region does not break music licensing.
    changes = {'URL': 'https://music.163.com/', 'VOICE_URL': 'http://127.0.0.1:8090/',
               'NETEASE_URL': 'https://music.163.com/', 'PROXY': '',
               'MUSIC_COMMAND_FILE': f'/run/user/{uid}/thinksmart-music-command.json'}
    lines = []
    for line in old.splitlines():
        key = line.partition('=')[0].strip()
        if key not in changes and key not in {'CHATGPT_URL', 'STUDY_URL'}:
            lines.append(line)
    lines += [f'{key}="{value}"' for key, value in changes.items()]
    return '\n'.join(lines) + '\n'


def install(args, account, hub):
    import grp
    import pwd
    uid, gid = account.pw_uid, account.pw_gid
    group = grp.getgrgid(gid).gr_name
    previous = json.loads(MARKER.read_text()) if MARKER.exists() else None
    managed = json.loads(OWNERSHIP.read_text()) if OWNERSHIP.exists() else previous
    if SDK_PREFIX.exists() and not managed:
        raise ValueError('发现不是由本项目管理的 Muse SDK。停止安装；原有设备无需重装。')
    if managed and (managed['user'] != args.user or managed['hub'] != str(hub)):
        raise ValueError('已有安装的用户或网关位置不同，停止覆盖。')
    try:
        bridge = pwd.getpwnam('musebridge')
    except KeyError:
        bridge = None
    if bridge:
        extra_groups = [g.gr_name for g in grp.getgrall() if 'musebridge' in g.gr_mem and g.gr_gid != gid]
        if (not managed or bridge.pw_uid != managed.get('bridge_uid') or bridge.pw_uid == 0
                or bridge.pw_gid != gid or bridge.pw_shell != '/usr/sbin/nologin' or extra_groups):
            raise ValueError('已有 musebridge 账号不属于本次受管理安装，或权限不匹配。')
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    STATE.chmod(0o700)
    env = dict(os.environ)
    # Do not silently inherit a desktop/global proxy or account-bearing proxy URL.
    for key in list(env):
        if key.lower().endswith('_proxy'):
            del env[key]
    env.update(proxy_environment(args.proxy))
    print('获取固定版本的官方 Muse SDK…')
    source = fetch_sdk(env)  # Network failure here cannot change running services.
    provider = hub / 'core/providers/llm/muse'
    mapping = {
        ROOT / 'app/thinksmart-kiosk.py': Path('/usr/local/bin/thinksmart-kiosk.py'),
        **{ROOT / 'app' / name: ASSETS / name for name in
           ('launcher.html', 'kiosk-tools.js', 'kiosk_keyboard.py', 'kiosk_navigation.py')},
        ROOT / 'hub/muse_llm.py': provider / 'muse.py',
        ROOT / 'hub/zz_local_netease_music.py': hub / 'plugins_func/functions/zz_local_netease_music.py',
        ROOT / 'scripts/thinksmart-muse-pair': Path('/usr/local/sbin/thinksmart-muse-pair'),
    }
    config = Path('/etc/thinksmart-kiosk.conf')
    proxy_file = Path('/etc/thinksmart-muse/proxy.env')
    dropin = Path('/etc/systemd/system/musegadget.service.d/thinksmart-muse-music.conf')
    targets = list(mapping.values()) + [config, proxy_file, dropin, MARKER,
        provider / '__init__.py', hub / 'data/.config.yaml', hub / 'data/agent_sessions.json',
        Path('/etc/bluetooth/main.conf'), Path('/etc/bluetooth/main.conf.pre-musegadget'),
        Path('/etc/systemd/system/bluetooth.service.d/zz-musegadget.conf'),
        Path('/etc/systemd/system/musegadget.service'), Path('/usr/local/bin/musegadget')]
    if previous:
        installed_sdk = sdk_dir()
        targets += [installed_sdk / n for n in ('network.py', 'service.py', 'link_client.py')]
    backup = Path('/var/backups/thinksmart-muse-music-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    txn = Transaction(backup)
    txn.backup(targets)
    write_file(backup / 'context.json', json.dumps({'user': args.user, 'uid': uid,
        'hub': str(hub), 'had_muse': bool(previous)}), 0o600)
    print('原配置备份: ' + str(backup))
    try:
        if not bridge:
            run('useradd', '--system', '--home-dir', '/var/lib/musebridge', '--create-home',
                '--gid', group, '--shell', '/usr/sbin/nologin', 'musebridge')
            Path('/var/lib/musebridge').chmod(0o700)
            bridge = pwd.getpwnam('musebridge')
        write_file(OWNERSHIP, json.dumps({'user': args.user, 'hub': str(hub),
                   'sdk': SDK_REV, 'bridge_uid': bridge.pw_uid}), 0o600)
        permission = subprocess.run(['sudo', '-n', '-l', '-U', 'musebridge'], capture_output=True)
        if permission.returncode == 0:
            raise ValueError('musebridge 意外拥有 sudo 权限，请先移除相关规则。')
        if not previous:
            run('bash', source / 'linux/install.sh', '--from', source / 'linux',
                '--run-as', 'musebridge', '--yes', '--no-pair', env=env)
        installed_sdk = sdk_dir()
        for src, name in [('muse-network.py', 'network.py'), ('muse-service.py', 'service.py'),
                          ('muse-link-client.py', 'link_client.py')]:
            copy_file(ROOT / 'sdk' / src, installed_sdk / name)
        run(SDK_PREFIX / 'venv/bin/python', ROOT / 'tests/verify_muse_service.py')
        run(SDK_PREFIX / 'venv/bin/python', ROOT / 'tests/verify_muse_network.py')
        run(hub / '.venv/bin/python', ROOT / 'tests/verify_muse_direct.py')
        for src, dest in mapping.items():
            executable = dest.name in {'thinksmart-kiosk.py', 'thinksmart-muse-pair'}
            owner = (uid, gid) if dest.is_relative_to(hub) else None
            copy_file(src, dest, 0o755 if executable else 0o644, owner)
        provider.mkdir(parents=True, exist_ok=True)
        os.chown(provider, uid, gid)
        if not (provider / '__init__.py').exists():
            write_file(provider / '__init__.py', '')
            os.chown(provider / '__init__.py', uid, gid)
        conversation_state = Path('/var/lib/thinksmart-muse')
        conversation_state.mkdir(mode=0o700, exist_ok=True)
        os.chown(conversation_state, uid, gid)
        conversation_state.chmod(0o700)
        write_file(proxy_file, ''.join(f'{k}={v}\n' for k, v in proxy_environment(args.proxy).items()), 0o600)
        write_file(dropin, '[Service]\nEnvironmentFile=-/etc/thinksmart-muse/proxy.env\n')
        write_file(config, config_kiosk(config.read_text() if config.exists() else '', uid))
        run(hub / '.venv/bin/python', ROOT / 'scripts/configure_hub.py', hub / 'data')
        run('runuser', '-u', args.user, '--', hub / '.venv/bin/python', '-c',
            'from core.admin.config_store import load_merged; from core.utils.llm import create_instance; '
            'c=load_merged(); assert callable(create_instance("muse",c["LLM"]["Muse"]).response_with_functions)', cwd=hub)
        run('systemctl', 'daemon-reload')
        run('systemctl', 'enable', 'musegadget.service')
        run('systemctl', 'restart', 'musegadget.service', 'thinksmart-kiosk.service')
        user_service(args.user, uid, 'restart')
        wait_healthy(args.user, uid)
        write_file(MARKER, json.dumps({'version': (ROOT / 'VERSION').read_text().strip(),
            'sdk': SDK_REV, 'user': args.user, 'uid': uid, 'hub': str(hub), 'backup': str(backup)}, indent=2), 0o600)
    except BaseException:
        print('安装未完成，正在恢复原配置…', file=sys.stderr)
        restore(backup)
        raise
    print('\n安装完成。下一步：sudo thinksmart-muse-pair')
    print('配对成功后说“小麦小麦，你好”；屏幕点击“网易云登录 / 原页”扫码登录自己的音乐账号。')
    print('再次检查：sudo bash install.sh --doctor')
    print('恢复原配置：sudo bash install.sh --rollback ' + str(backup))


def wait_healthy(user, uid):
    for _ in range(90):
        try:
            healthy = run('systemctl', 'is-active', '--quiet', 'musegadget.service',
                          'thinksmart-kiosk.service', 'thinksmart-client.service', check=False) == 0
            # is-active with multiple units can succeed if only one is active.
            healthy = healthy and all(run('systemctl', 'is-active', '--quiet', u, check=False) == 0
                for u in ('musegadget.service', 'thinksmart-kiosk.service', 'thinksmart-client.service'))
            healthy = healthy and user_service(user, uid, 'is-active', check=False) == 0
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open('http://127.0.0.1:16688/admin/', timeout=2) as response:
                if healthy and response.status == 200 and Path('/run/musegadget/musegadget.sock').is_socket():
                    return
        except OSError:
            pass
        time.sleep(1)
    raise RuntimeError('服务未在 90 次检查内就绪')


def restore(backup):
    backup = Path(backup).resolve()
    if backup.parent != Path('/var/backups') or not backup.name.startswith('thinksmart-muse-music-'):
        raise ValueError('只能恢复 /var/backups/thinksmart-muse-music-* 中的备份。')
    context_path = backup / 'context.json'
    for p in (backup, context_path):
        meta = p.stat()
        if meta.st_uid != os.geteuid() or meta.st_mode & 0o022:
            raise ValueError('恢复上下文不可信')
    c = json.loads(context_path.read_text())
    run('systemctl', 'stop', 'musegadget.service', check=False)
    if not c['had_muse']:
        run('systemctl', 'disable', 'musegadget.service', check=False)
    Transaction.restore(backup)
    run('systemctl', 'daemon-reload')
    run('systemctl', 'restart', 'bluetooth.service', 'thinksmart-kiosk.service', check=False)
    if c['had_muse']:
        run('systemctl', 'restart', 'musegadget.service', check=False)
    user_service(c['user'], c['uid'], 'restart', check=False)
    print('已恢复配置。已下载的 SDK、系统依赖和账号配对数据保留，不会自动删除。')


def doctor(args):
    account, hub = hub_identity(args)
    for unit in ('bluetooth', 'musegadget', 'thinksmart-client', 'thinksmart-kiosk'):
        status = run('systemctl', 'is-active', unit, capture=True, check=False)
        print(unit + ': ' + status)
    print('Hub:')
    user_service(args.user, account.pw_uid, 'is-active', check=False)
    print('Token 已保存:', Path('/var/lib/musegadget/sdk_token').is_file())
    print('手机已配对:', Path('/var/lib/musegadget/pairing.json').is_file())
    print('本地连接通道:', Path('/run/musegadget/musegadget.sock').is_socket())
    print('根分区空闲 MiB:', shutil.disk_usage('/').free // 1024**2)
    print('此检查不会发送问题、播放音乐或输出凭据；实际回答请用唤醒词测试。')


def main():
    parser = argparse.ArgumentParser(description='ThinkSmart 小麦 Muse + 网易云安装器')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='只检查环境，不修改设备')
    mode.add_argument('--doctor', action='store_true', help='查看服务和配对状态，不输出凭据')
    mode.add_argument('--rollback', metavar='BACKUP', help='恢复指定的本机备份')
    parser.add_argument('--user', default='ubuntu', help='运行网关和屏幕的普通账号')
    parser.add_argument('--hub', help='xiaozhi-server 路径，通常自动确定')
    parser.add_argument('--proxy', default='', help='Muse/安装下载使用的本机 HTTP 代理；网易云直连')
    args = parser.parse_args()
    if platform.system() != 'Linux':
        parser.error('请在音箱 Ubuntu 的 SSH 窗口运行，不是在电脑 PowerShell。')
    if os.geteuid() != 0:
        parser.error('请用 sudo bash install.sh（只读检查也需要读取受保护的状态）。')
    os.umask(0o077)
    # A second invocation must not race backups or service changes.
    import fcntl
    with open('/run/lock/thinksmart-muse-music.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.rollback:
            restore(args.rollback)
        elif args.doctor:
            doctor(args)
        else:
            account, hub = preflight(args)
            if not args.check:
                install(args, account, hub)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        print('未完成：' + str(error), file=sys.stderr)
        sys.exit(1)
