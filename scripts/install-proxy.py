#!/usr/bin/env python3
"""Optional fresh Mihomo install from the owner's exported Clash YAML.

No subscription URL, node, account, binary or dashboard is bundled in this repo.
"""
import argparse
import gzip
import hashlib
import io
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

from setup import proxy_environment

CORE_URL = 'https://github.com/MetaCubeX/mihomo/releases/download/v1.19.33/mihomo-linux-arm64-v1.19.33.gz'
CORE_SHA = 'ba408b317080ee265c46cb923a50018c1b82cbd708551cdd46a1e3e307396187'
UI_URL = 'https://github.com/MetaCubeX/metacubexd/releases/download/v1.274.4/compressed-dist.tgz'
UI_SHA = '144f60aaa3b23090d331992761f2ead543b2339ac0d5a3e88a933875f6d8ef2f'


def sanitize(c):
    if not isinstance(c, dict) or not (c.get('proxies') or c.get('proxy-providers')):
        raise ValueError('需要包含实际节点或 proxy-providers 的完整 Clash YAML；不是订阅链接或 base64 文本。')
    for key in ('external-controller-tls', 'external-controller-unix', 'external-ui-url',
                'external-ui-name', 'authentication', 'secret', 'listeners', 'script'):
        c.pop(key, None)
    c.update({'mixed-port': 7890, 'port': 0, 'socks-port': 0, 'redir-port': 0, 'tproxy-port': 0,
              'allow-lan': False, 'bind-address': '127.0.0.1',
              'external-controller': '127.0.0.1:9090', 'external-ui': '/var/lib/mihomo/ui',
              'tun': {'enable': False}, 'mode': 'rule', 'log-level': 'warning'})
    c['profile'] = {**(c.get('profile') or {}), 'store-selected': True}
    # Do not expose a DNS listener inherited from a subscription.
    if isinstance(c.get('dns'), dict):
        c['dns'].pop('listen', None)
    return c


def download(url, expected, opener):
    with opener.open(url, timeout=90) as response:
        data = response.read(60 * 1024**2 + 1)
    if len(data) > 60 * 1024**2 or hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('官方下载文件的 SHA-256 校验失败')
    return data


def unpack_ui(data, destination):
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        members = archive.getmembers()
        for member in members:
            target = (destination / member.name).resolve()
            if not target.is_relative_to(destination.resolve()) or not (member.isdir() or member.isfile()):
                raise ValueError('面板压缩包包含不安全的路径或链接')
        if sum(x.size for x in members) > 150 * 1024**2:
            raise ValueError('面板解压体积异常')
        archive.extractall(destination, members=members, filter='data')


def main():
    parser = argparse.ArgumentParser(description='可选：安装本机代理，仅适用于尚未安装 Mihomo 的设备')
    parser.add_argument('--config', required=True, help='自己从 Clash 导出的完整 YAML 文件，不是订阅链接')
    parser.add_argument('--bootstrap-proxy', default='', help='仅供下载使用，例如电脑上的 HTTP 代理')
    args = parser.parse_args()
    if platform.system() != 'Linux' or platform.machine() != 'aarch64' or os.geteuid() != 0:
        parser.error('请在音箱 SSH 中用 sudo python3 scripts/install-proxy.py 运行')
    import fcntl
    lock = open('/run/lock/thinksmart-muse-proxy-install.lock', 'w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    import pwd
    try:
        import yaml
    except ImportError:
        parser.error('先运行 sudo apt-get install -y python3-yaml')
    unit = Path('/etc/systemd/system/mihomo.service')
    target = Path('/etc/mihomo/config.yaml')
    binary = Path('/usr/local/bin/mihomo')
    data_dir = Path('/var/lib/mihomo')
    for p in (unit, target.parent, binary, data_dir):
        if p.exists() or p.is_symlink():
            parser.error('已有 Mihomo 文件，停止覆盖；请直接使用现有代理或按 NETWORK.md 更新订阅。')
    existing = subprocess.run(['systemctl', 'show', '-p', 'LoadState', '--value', 'mihomo.service'],
                              capture_output=True, text=True)
    if shutil.which('mihomo') or existing.stdout.strip() not in ('', 'not-found'):
        parser.error('检测到其他位置安装的 Mihomo，不覆盖已有服务。')
    try:
        pwd.getpwnam('thinksmart-proxy')
    except KeyError:
        pass
    else:
        parser.error('已有 thinksmart-proxy 账号，停止覆盖。')
    if Path(args.config).stat().st_size > 2 * 1024**2:
        parser.error('配置文件超过 2 MiB')
    try:
        config = sanitize(yaml.safe_load(Path(args.config).read_text(encoding='utf-8-sig')))
    except Exception:
        parser.error('无法读取完整 Clash YAML；没有输出配置内容。')
    env = proxy_environment(args.bootstrap_proxy)
    proxy = env.get('http_proxy')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({'https': proxy} if proxy else {}))
    print('下载固定版本并验证官方 SHA-256…')
    core = gzip.decompress(download(CORE_URL, CORE_SHA, opener))
    ui = download(UI_URL, UI_SHA, opener)
    # All validation and downloads finish before the first persistent change.
    with tempfile.TemporaryDirectory(prefix='thinksmart-proxy-') as temporary:
        stage = Path(temporary)
        unpack_ui(ui, stage / 'ui')
        (stage / 'mihomo').write_bytes(core)
        (stage / 'mihomo').chmod(0o755)
        created_user = False
        try:
            subprocess.run(['useradd', '--system', '--user-group', '--no-create-home',
                            '--shell', '/usr/sbin/nologin', 'thinksmart-proxy'], check=True)
            created_user = True
            owner = pwd.getpwnam('thinksmart-proxy')
            data_dir.mkdir(mode=0o700)
            shutil.copytree(stage / 'ui', data_dir / 'ui')
            for p in [data_dir, *data_dir.rglob('*')]:
                os.chown(p, owner.pw_uid, owner.pw_gid)
            target.parent.mkdir(exist_ok=True, mode=0o750)
            os.chown(target.parent, 0, owner.pw_gid)
            target.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding='utf-8')
            target.chmod(0o640)
            os.chown(target, 0, owner.pw_gid)
            shutil.copyfile(stage / 'mihomo', binary)
            binary.chmod(0o755)
            # Use the service's actual home for both validation and runtime.
            result = subprocess.run(['runuser', '-u', 'thinksmart-proxy', '--', str(binary),
                '-t', '-d', str(data_dir), '-f', str(target)], capture_output=True,
                env={**{k: v for k, v in os.environ.items() if not k.lower().endswith('_proxy')}, **env})
            if result.returncode:
                raise ValueError('代理配置测试失败，请检查节点/规则依赖。未打印可能含订阅信息的原始输出。')
            unit.write_text('''[Unit]
Description=ThinkSmart local Mihomo proxy
After=network-online.target
Wants=network-online.target
[Service]
User=thinksmart-proxy
Group=thinksmart-proxy
ExecStart=/usr/local/bin/mihomo -d /var/lib/mihomo -f /etc/mihomo/config.yaml
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/var/lib/mihomo
[Install]
WantedBy=multi-user.target
''', encoding='utf-8')
            unit.chmod(0o644)
            subprocess.run(['systemctl', 'daemon-reload'], check=True)
            subprocess.run(['systemctl', 'enable', '--now', 'mihomo'], check=True)
            subprocess.run(['systemctl', 'is-active', '--quiet', 'mihomo'], check=True)
        except BaseException:
            subprocess.run(['systemctl', 'disable', '--now', 'mihomo'], capture_output=True)
            for p in (unit, target, binary):
                p.unlink(missing_ok=True)
            if target.parent.exists():
                target.parent.rmdir()  # This run created the previously absent directory.
            if data_dir.exists():
                shutil.rmtree(data_dir)  # Fixed path proved absent at entry; only this run created it.
            if created_user:
                subprocess.run(['userdel', 'thinksmart-proxy'], capture_output=True)
            subprocess.run(['systemctl', 'daemon-reload'], capture_output=True)
            raise
    print('代理已安装。请按 docs/NETWORK.md 建立 9090 隧道并选择可用节点。')
    print('原导出配置仍在你指定的位置，请自行妥善保管或删除；不要提交到 Git。')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Avoid URLs/auth strings from HTTP exception bodies.
        print('代理安装未完成。错误类型: ' + type(error).__name__)
        raise SystemExit(1)
