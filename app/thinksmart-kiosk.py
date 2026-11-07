# SPDX-License-Identifier: MIT
# Derived from HalfBit ThinkSmart kiosk; see THIRD_PARTY.md.
#!/usr/bin/env python3
"""Full-screen single-page browser for the ThinkSmart kiosk session (runs inside Weston).

Reads URL= from /etc/thinksmart-kiosk.conf. Cookies and site data persist in
~/.local/share/thinksmart-kiosk so logins survive reboots.

While the URL can't be loaded (nothing installed there yet, the service is starting or
was removed, no network) the built-in welcome page is shown instead of WebKit's error
page, and the URL is retried in the background until it answers. A device that has never
been on a network (fresh image: no saved Wi-Fi, no address) also stays on the welcome page,
where Wi-Fi is set up on the screen, even though the local voice client would load.
"""
import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import gi

gi.require_version('Gtk', '3.0')
gi.require_version('WebKit2', '4.1')
from gi.repository import GLib, Gtk, WebKit2  # noqa: E402

CONF = '/etc/thinksmart-kiosk.conf'
WELCOME = '/usr/local/share/thinksmart-kiosk/welcome.html'
LAUNCHER = '/usr/local/share/thinksmart-kiosk/launcher.html'
TOOLS_SCRIPT = '/usr/local/share/thinksmart-kiosk/kiosk-tools.js'
RETRY_SECONDS = 5


def netease_control_script(action):
    """JavaScript for the small, stable controls in NetEase's official web player."""
    return r"""
(() => {
  const action = %s;
  const docs = [document];
  try {
    const frame = document.getElementById('g_iframe');
    if (frame && frame.contentDocument) docs.push(frame.contentDocument);
  } catch (_) {}
  const audios = docs.flatMap(doc => Array.from(doc.querySelectorAll('audio')));
  const click = selector => {
    for (const doc of docs) {
      const element = doc.querySelector(selector);
      if (element) { element.click(); return true; }
    }
    return false;
  };
  if (action === 'toggle') {
    const audio = audios.find(item => !item.paused) ||
                  audios.find(item => Number.isFinite(item.duration) && item.duration > 0) ||
                  audios[0];
    if (audio) {
      if (audio.paused) audio.play().catch(() => {});
      else audio.pause();
      return true;
    }
    return click('.m-playbar [data-action="play"]');
  }
  if (action === 'pause' || action === 'stop') {
    let changed = false;
    for (const audio of audios) {
      if (!audio.paused) { audio.pause(); changed = true; }
      if (action === 'stop') {
        try { audio.currentTime = 0; } catch (_) {}
      }
    }
    if (!changed) click('.m-playbar .pas');
    return changed;
  }
  if (action === 'resume') {
    const audio = audios.find(item => item.paused) || audios[0];
    if (audio) { audio.play().catch(() => {}); return true; }
    return click('.m-playbar [data-action="play"]');
  }
  if (action === 'next') return click('.m-playbar [data-action="next"], .m-playbar .nxt');
  if (action === 'previous') return click('.m-playbar [data-action="prev"], .m-playbar .prv');
  return false;
})()
""" % json.dumps(action)


def netease_seek_script(ratio):
    """Seek the active official web player to a normalized 0..1 position."""
    return r"""
(() => {
  const ratio = %s;
  const docs = [document];
  try {
    const frame = document.getElementById('g_iframe');
    if (frame && frame.contentDocument) docs.push(frame.contentDocument);
  } catch (_) {}
  const audios = docs.flatMap(doc => Array.from(doc.querySelectorAll('audio')));
  const audio = audios.find(item => !item.paused) ||
                audios.find(item => Number.isFinite(item.duration) && item.duration > 0) ||
                audios[0];
  if (!audio || !Number.isFinite(audio.duration) || audio.duration <= 0) return false;
  audio.currentTime = audio.duration * Math.max(0, Math.min(1, ratio));
  return true;
})()
""" % json.dumps(ratio)


def netease_open_lyrics_script():
    """Open NetEase's own queue panel so its official timed lyric DOM is populated."""
    return r"""
(() => {
  if (document.querySelector('.listlyric p')) return true;
  const panel = document.querySelector('#g_player [data-action="panel"]');
  if (!panel) return false;
  panel.click();
  return true;
})()
"""


def netease_set_mode_script(mode):
    """Set an exact official player mode instead of blindly cycling the button."""
    wanted = {
        'list': 'icn-loop',
        'single': 'icn-one',
        'shuffle': 'icn-shuffle',
    }[mode]
    return r"""
(() => {
  const wanted = %s;
  let attempts = 0;
  const apply = () => {
    const button = document.querySelector('#g_player [data-action="mode"]');
    if (!button) return false;
    if (button.classList.contains(wanted)) return true;
    button.click();
    attempts += 1;
    return button.classList.contains(wanted) || attempts >= 4;
  };
  if (!apply()) {
    const timer = setInterval(() => { if (apply()) clearInterval(timer); }, 180);
  }
})()
""" % json.dumps(wanted)


def netease_queue_play_script(song_id):
    """Play one item already present in NetEase's official queue."""
    return r"""
(() => {
  const row = document.querySelector('.listbdc li[data-id=%s]');
  if (!row) return false;
  row.click();
  return true;
})()
""" % json.dumps(song_id)


def netease_page_play_script(song_id):
    """Play a song row on the official playlist page loaded in the same-origin iframe."""
    return r"""
(() => {
  const frame = document.getElementById('g_iframe');
  const doc = frame && frame.contentDocument;
  if (!doc) return false;
  const selector = '[data-res-action="play"][data-res-type="18"][data-res-id=%s]';
  const button = doc.querySelector(selector);
  if (!button) return false;
  button.click();
  return true;
})()
""" % json.dumps(song_id)


def netease_playlist_play_all_script(playlist_id):
    """Ask NetEase's official playlist action to replace the queue and start the list."""
    return r"""
(() => {
  const playlistId = %s;
  if (window.__thinksmartPlaylistPlayTimer) {
    clearInterval(window.__thinksmartPlaylistPlayTimer);
    window.__thinksmartPlaylistPlayTimer = null;
  }
  let attempts = 0;
  const tryPlay = () => {
    let doc = null;
    try {
      const frame = document.getElementById('g_iframe');
      doc = frame && frame.contentDocument;
    } catch (_) {}
    if (!doc) return false;
    const selectors = [
      `[data-res-action="play"][data-res-type="13"][data-res-id="${playlistId}"]`,
      `.u-btni-addply[data-res-id="${playlistId}"]`,
      `[data-res-action="play"][data-res-id="${playlistId}"]`,
    ];
    for (const selector of selectors) {
      const button = doc.querySelector(selector);
      if (button) { button.click(); return true; }
    }
    return false;
  };
  if (!tryPlay()) {
    window.__thinksmartPlaylistPlayTimer = setInterval(() => {
      attempts += 1;
      if (tryPlay() || attempts >= 40) {
        clearInterval(window.__thinksmartPlaylistPlayTimer);
        window.__thinksmartPlaylistPlayTimer = null;
      }
    }, 250);
  }
})()
""" % json.dumps(playlist_id)


def netease_navigate_script(target):
    """Navigate only to a prevalidated route inside NetEase's official top page."""
    return "location.hash = " + json.dumps('#' + target)


def netease_search_autoplay_script():
    """Wait for NetEase's same-origin search iframe, then play its first real song result."""
    return r"""
(() => {
  if (window.__thinksmartNeteaseTimer) clearInterval(window.__thinksmartNeteaseTimer);
  let attempts = 0;
  const tryPlay = () => {
    const docs = [document];
    try {
      const frame = document.getElementById('g_iframe');
      if (frame && frame.contentDocument) docs.push(frame.contentDocument);
    } catch (_) {}
    for (const doc of docs) {
      const buttons = Array.from(doc.querySelectorAll(
        '[data-res-action="play"][data-res-type="18"][data-res-id]'
      ));
      const target = buttons.find(item => item.getClientRects().length > 0);
      if (target) { target.click(); return true; }
    }
    return false;
  };
  if (!tryPlay()) {
    window.__thinksmartNeteaseTimer = setInterval(() => {
      attempts += 1;
      if (tryPlay() || attempts >= 40) {
        clearInterval(window.__thinksmartNeteaseTimer);
        window.__thinksmartNeteaseTimer = null;
      }
    }, 750);
  }
})()
"""


def read_conf():
    conf = {}
    try:
        with open(CONF) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                conf[key.strip()] = value.strip().strip('"\'')
    except OSError:
        pass
    return conf


def device_status():
    """What the welcome page shows about the device: addresses, host name, Wi-Fi."""
    addrs = []
    try:
        out = subprocess.run(['ip', '-4', '-o', 'addr', 'show', 'scope', 'global'],
                             capture_output=True, text=True, timeout=2).stdout
        addrs = [(line.split()[1], line.split()[3].split('/')[0]) for line in out.splitlines()]
    except (OSError, subprocess.SubprocessError, IndexError):
        pass
    # usb0 is the USB-cable network (the computer on the other end gets 172.16.42.2); it is
    # always up, so it doesn't mean the device is online and is shown only as a rescue hint
    ips = [ip for iface, ip in addrs if not iface.startswith('usb')]
    usb = next((ip for iface, ip in addrs if iface.startswith('usb')), '')
    ssid = ''
    try:
        out = subprocess.run(['nmcli', '-t', '-f', 'ACTIVE,SSID', 'dev', 'wifi'],
                             capture_output=True, text=True, timeout=2).stdout
        ssid = next((line[4:] for line in out.splitlines() if line.startswith('yes:')), '')
    except (OSError, subprocess.SubprocessError):
        pass
    return {'ip': ','.join(ips), 'usb': usb, 'host': socket.gethostname(), 'ssid': ssid}


def nmcli(*args, timeout=10):
    return subprocess.run(['nmcli', *args], capture_output=True, text=True, timeout=timeout)


def nmcli_fields(line):
    """Split one line of `nmcli -t` output (':' separated, '\\:' escaped)."""
    return [f.replace('\\:', ':').replace('\\\\', '\\') for f in re.split(r'(?<!\\):', line)]


def connection_uuids(active=False):
    out = nmcli('-t', '-f', 'UUID,TYPE', 'connection', 'show', *(['--active'] if active else [])).stdout
    return {f[0]: f[1] for f in map(nmcli_fields, out.splitlines()) if len(f) >= 2}


def wifi_profiles():
    """Saved Wi-Fi networks (NetworkManager keeps their passwords): SSID -> profile UUID."""
    profiles = {}
    for uuid, kind in connection_uuids().items():
        if kind == '802-11-wireless':
            ssid = nmcli('-g', '802-11-wireless.ssid', 'connection', 'show', 'uuid', uuid).stdout.strip()
            if ssid:
                profiles[nmcli_fields(ssid)[0]] = uuid
    return profiles


def needs_network_setup():
    """Fresh device: no saved Wi-Fi network and no address on any other interface (USB aside)."""
    try:
        return not device_status()['ip'] and not wifi_profiles()
    except (OSError, subprocess.SubprocessError):
        return False


def wifi_scan(_msg, _progress):
    try:
        out = nmcli('-t', '-f', 'IN-USE,SSID,SIGNAL,SECURITY', 'dev', 'wifi', 'list', '--rescan', 'yes',
                    timeout=25).stdout
        saved = wifi_profiles()
    except (OSError, subprocess.SubprocessError):
        return {'ok': False}
    best = {}  # one entry per SSID: the connected one, else the strongest access point
    for line in out.splitlines():
        f = nmcli_fields(line)
        if len(f) < 4 or not f[1]:
            continue
        n = {'ssid': f[1], 'signal': int(f[2] or 0), 'secure': f[3] not in ('', '--'),
             'active': f[0] == '*', 'saved': f[1] in saved}
        old = best.get(n['ssid'])
        if old is None or n['active'] or (not old['active'] and n['signal'] > old['signal']):
            best[n['ssid']] = n
    return {'ok': True, 'networks': sorted(best.values(), key=lambda n: (not n['active'], not n['saved'], -n['signal']))}


def reconnect_later(uuid):
    """After a failed attempt, bring the previous network back without making the user wait for it."""
    def work():
        try:
            nmcli('connection', 'up', 'uuid', uuid, timeout=45)
        except (OSError, subprocess.SubprocessError):
            pass
    threading.Thread(target=work, daemon=True).start()


def supplicant_state(path):
    """wpa_supplicant's state for wlan0 (scanning, associating, 4way_handshake, completed, ...)."""
    try:
        out = subprocess.run(['busctl', 'get-property', 'fi.w1.wpa_supplicant1', path,
                              'fi.w1.wpa_supplicant1.Interface', 'State'],
                             capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return ''
    return out.split('"')[1] if out.count('"') >= 2 else ''


def supplicant_path():
    try:
        out = subprocess.run(['busctl', 'call', 'fi.w1.wpa_supplicant1', '/fi/w1/wpa_supplicant1',
                              'fi.w1.wpa_supplicant1', 'GetInterface', 's', 'wlan0'],
                             capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return ''
    return out.split('"')[1] if out.count('"') >= 2 else ''


# A good password finishes the 4-way handshake in ~0.1 s (17 joins on this device: median 0.10 s,
# slowest 0.83 s); with a wrong one wpa_supplicant waits 10 s before giving up. Access points
# resend a lost handshake frame about once a second and give up after ~4 tries, so a handshake
# still stuck after 5 s won't succeed whatever the signal: call it a wrong password then.
HANDSHAKE_GIVE_UP = 5.0
STAGES = {'scanning': 'scan', 'authenticating': 'join', 'associating': 'join', 'associated': 'join',
          '4way_handshake': 'auth', 'group_handshake': 'auth', 'completed': 'ip'}


def run_nmcli_watched(cmd, progress):
    """Run an nmcli activation while reporting wpa_supplicant's stages through progress(stage).

    Returns (ok, error text). Stops early once the handshake hangs (wrong password).
    """
    path = supplicant_path()
    p = subprocess.Popen(['nmcli', *cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 50
    stage = handshake_since = None
    left_old = False  # 'completed' only counts once the old network has been dropped
    while p.poll() is None:
        state = supplicant_state(path) if path else ''
        left_old = left_old or (state not in ('', 'completed'))
        new_stage = STAGES.get(state) if left_old else None
        if new_stage and new_stage != stage:
            stage = new_stage
            progress(stage)
        if state in ('4way_handshake', 'group_handshake'):
            handshake_since = handshake_since or time.monotonic()
            if time.monotonic() - handshake_since > HANDSHAKE_GIVE_UP:
                break
        else:
            handshake_since = None
        if time.monotonic() > deadline:
            break
        time.sleep(0.25)
    if p.poll() is None:
        wrong = handshake_since is not None
        p.terminate()
        nmcli('device', 'disconnect', 'wlan0')  # stop the activation NetworkManager is still running
        return False, 'Secrets were required' if wrong else 'Timeout'
    out, err = p.communicate()
    return p.returncode == 0, (err or out).strip()


def wifi_connect(msg, progress):
    """Join a network: with the saved password when no new one is given, else with the new one."""
    ssid, password = str(msg.get('ssid') or ''), str(msg.get('password') or '')
    if not 0 < len(ssid.encode()) <= 32 or (password and not 8 <= len(password) <= 63):
        return {'ok': False, 'reason': 'invalid'}
    before = connection_uuids()
    previous = next((u for u, t in connection_uuids(active=True).items() if t == '802-11-wireless'), None)
    saved = wifi_profiles().get(ssid)
    # `dev wifi connect` writes a typed password into the saved profile; keep the old one so a
    # typo doesn't cost the network that was working
    old_psk = None
    if saved and password:
        old_psk = nmcli('-s', '-g', '802-11-wireless-security.psk', 'connection', 'show', 'uuid', saved).stdout.strip()
    if saved and not password and not msg.get('hidden'):
        cmd = ['--wait', '40', 'connection', 'up', 'uuid', saved]
    else:
        cmd = ['--wait', '40', 'dev', 'wifi', 'connect', ssid]
        if password:
            cmd += ['password', password]
        if msg.get('hidden'):
            cmd += ['hidden', 'yes']
    ok, err = run_nmcli_watched(cmd, progress)
    if ok:
        return {'ok': True}
    reason =('password' if 'Secrets were required' in err or 'no-secrets' in err or 'password' in err.lower() else
              'notfound' if 'No network with SSID' in err else
              'timeout' if 'Timeout' in err or 'timed out' in err else 'failed')
    # Don't keep a new profile with a wrong password around; put a saved one's password back
    for uuid in set(connection_uuids()) - set(before):
        nmcli('connection', 'delete', 'uuid', uuid)
    if old_psk:
        nmcli('connection', 'modify', 'uuid', saved, 'wifi-sec.psk', old_psk)
    if previous:
        reconnect_later(previous)
    return {'ok': False, 'reason': reason, 'detail': err.splitlines()[-1][:120] if err else ''}


def wifi_forget(msg, _progress):
    ssid = str(msg.get('ssid') or '')
    for name, uuid in wifi_profiles().items():
        if name == ssid:
            nmcli('connection', 'delete', 'uuid', uuid)
    return {'ok': True}


UPDATE_STATE = '/var/lib/thinksmart-update'


def update_status(_msg, _progress):
    """What the root updater (thinksmart-update) found or is doing, for the welcome page."""
    try:
        with open(os.path.join(UPDATE_STATE, 'status.json')) as f:
            return {'ok': True, 'update': json.load(f)}
    except (OSError, ValueError):
        return {'ok': False}


def update_request(msg, _progress):
    """Ask the updater to install the version the user tapped (it installs only what it checked)."""
    action = 'install' if msg.get('cmd') == 'update_install' else 'check'
    try:
        tmp = os.path.join(UPDATE_STATE, 'requests', f'.{action}.tmp')
        with open(tmp, 'w') as f:
            json.dump({'action': action, 'version': str(msg.get('version', ''))}, f)
        os.replace(tmp, os.path.join(UPDATE_STATE, 'requests', action))
        return {'ok': True}
    except OSError:
        return {'ok': False}


def reachable(url):
    """True once something answers at url (any HTTP status counts: the page itself decides)."""
    if not url:
        return False
    if url.startswith('file://'):
        return os.path.exists(urllib.parse.urlparse(url).path)
    try:
        urllib.request.urlopen(url, timeout=2).close()
        return True
    except urllib.error.HTTPError:
        return True
    except (OSError, ValueError):
        return False


def main():
    conf = read_conf()
    url = conf.get('URL', '')
    netease_url = conf.get('NETEASE_URL', 'https://music.163.com/').rstrip('/') + '/'
    command_file = conf.get(
        'MUSIC_COMMAND_FILE',
        os.path.join(os.environ.get('XDG_RUNTIME_DIR', '/tmp'),
                     'thinksmart-music-command.json'),
    )
    player_status_file = os.path.join(
        os.path.dirname(command_file), 'thinksmart-player-status.json'
    )
    app_command_file = os.path.join(os.path.dirname(command_file), 'thinksmart-app-command.json')
    browser_status_file = os.path.join(os.path.dirname(command_file), 'thinksmart-browser-status.json')
    # Extra environment for the WebKit/Mesa renderer, e.g. WEBKIT_ENV="WEBKIT_FORCE_VBLANK_TIMER=1";
    # set before the web process is spawned so it inherits them
    for item in conf.get('WEBKIT_ENV', '').split():
        key, _, value = item.partition('=')
        if key:
            os.environ[key] = value

    data_dir = os.path.expanduser('~/.local/share/thinksmart-kiosk')
    cache_dir = os.path.expanduser('~/.cache/thinksmart-kiosk')
    manager = WebKit2.WebsiteDataManager(base_data_directory=data_dir,
                                         base_cache_directory=cache_dir)
    manager.get_cookie_manager().set_persistent_storage(
        os.path.join(data_dir, 'cookies.sqlite'), WebKit2.CookiePersistentStorage.SQLITE)
    context = WebKit2.WebContext.new_with_website_data_manager(manager)
    # Keep a moderate resource cache without keeping entire previous applications.
    # Cookie/local-storage persistence above is independent of the cache policy.
    context.set_cache_model(WebKit2.CacheModel.DOCUMENT_BROWSER)

    # External websites use the local Mihomo proxy. Localhost and the LAN stay
    # direct so the voice UI and the Hub keep working even when an upstream proxy is offline.
    proxy = conf.get('PROXY', '').strip()
    if proxy:
        ignore_hosts = [host.strip() for host in conf.get('PROXY_BYPASS', '').split(',')
                        if host.strip()]
        proxy_settings = WebKit2.NetworkProxySettings.new(proxy, ignore_hosts)
        context.set_network_proxy_settings(WebKit2.NetworkProxyMode.CUSTOM, proxy_settings)

    # A kiosk has nobody to click "play": allow media with sound to autoplay
    policies = WebKit2.WebsitePolicies(autoplay=WebKit2.AutoplayPolicy.ALLOW)
    # The welcome page talks to us through window.webkit.messageHandlers.thinksmart (Wi-Fi setup)
    ucm = WebKit2.UserContentManager()
    ucm.register_script_message_handler('thinksmart')
    # External pages get only this fixed navigation action; they cannot ask the device to run
    # commands or open an arbitrary URL.
    ucm.register_script_message_handler('thinksmartNav')
    # The music overlay can request only fixed player actions and report a small sanitized
    # status snapshot. It cannot read files, run commands or navigate to arbitrary URLs.
    ucm.register_script_message_handler('thinksmartPlayer')
    try:
        with open(TOOLS_SCRIPT) as f:
            tools_source = f.read()
        ucm.add_script(WebKit2.UserScript.new(
            tools_source,
            WebKit2.UserContentInjectedFrames.TOP_FRAME,
            WebKit2.UserScriptInjectionTime.END,
            None,
            None,
        ))
    except OSError:
        pass
    view = WebKit2.WebView(web_context=context, website_policies=policies, user_content_manager=ucm)
    settings = view.get_settings()
    # Developer tools only when profiling: WEBKIT_ENV="... WEBKIT_INSPECTOR_HTTP_SERVER=127.0.0.1:9222",
    # then open http://127.0.0.1:9222 through an ssh tunnel
    settings.set_enable_developer_extras(bool(os.environ.get('WEBKIT_INSPECTOR_HTTP_SERVER')))
    settings.set_enable_smooth_scrolling(True)
    settings.set_media_playback_requires_user_gesture(False)
    settings.set_enable_page_cache(False)
    # GPU=never|on-demand|always in the conf. CPU rendering is the fallback default; GPU needs
    # the freedreno GMEM fix (kernel-build/mesa) or FD_MESA_DEBUG=sysmem, see README.
    policy = {
        'on-demand': WebKit2.HardwareAccelerationPolicy.ON_DEMAND,
        'always': WebKit2.HardwareAccelerationPolicy.ALWAYS,
    }.get(conf.get('GPU', 'never'), WebKit2.HardwareAccelerationPolicy.NEVER)
    settings.set_hardware_acceleration_policy(policy)
    # WEBKIT_FEATURES="-Name +Name": switch WebKit feature flags (names from
    # WebKit2.Settings.get_all_features()), e.g. to turn off partial-repaint damage tracking
    features = {}
    all_features = WebKit2.Settings.get_all_features()
    for i in range(all_features.get_length()):
        features[all_features.get(i).get_identifier()] = all_features.get(i)
    for item in conf.get('WEBKIT_FEATURES', '').split():
        name = item.lstrip('+-')
        if name in features:
            settings.set_feature_enabled(features[name], not item.startswith('-'))
        else:
            print(f'thinksmart-kiosk: unknown WebKit feature {name}', flush=True)

    # busy: the Wi-Fi sheet is open on the welcome page, don't switch pages under the user's fingers
    state = {
        'welcome': False,
        'tries': 0,
        'checking': False,
        'busy': False,
        'music_pending': None,
    }

    destinations = {
        'home': 'file://' + LAUNCHER,
        'launcher': 'file://' + LAUNCHER,
        'voice': conf.get('VOICE_URL', 'http://127.0.0.1:8090/'),
        'music': netease_url,
    }

    def app_kind(uri):
        parsed = urllib.parse.urlparse(uri)
        host = (parsed.hostname or '').lower()
        if host in {'music.163.com', 'www.music.163.com'}:
            return 'music'
        if uri.startswith(destinations['voice']):
            return 'voice'
        if parsed.scheme == 'file':
            return 'home'
        return 'web' if parsed.scheme in {'http', 'https'} else 'empty'

    navigator = None

    def report_browser_status():
        # Only lifecycle metadata; never URLs, page text, cookies or input contents.
        snapshot = {
            'updated': time.time(), 'pid': os.getpid(),
            'app': app_kind(view.get_uri() or ''), 'loading': view.is_loading(),
            'page_cache': settings.get_enable_page_cache(),
            'cache_model': context.get_cache_model().value_nick,
            'rendering': settings.get_hardware_acceleration_policy().value_nick,
            'switching': bool(navigator and navigator.switching),
            'recycled': navigator.recycled if navigator else 0,
            'last_termination': navigator.last_termination if navigator else '',
        }
        try:
            temporary = browser_status_file + '.tmp'
            with open(temporary, 'w', encoding='utf-8') as f:
                json.dump(snapshot, f)
            os.replace(temporary, browser_status_file)
        except OSError:
            pass

    def navigate_app(name):
        if not isinstance(name, str):
            return
        destination = destinations.get(name)
        if destination:
            state['welcome'] = False
            state['music_pending'] = None
            navigator.navigate(destination)

    def evaluate(source):
        view.evaluate_javascript(source, -1, None, None, None, None, None)

    def on_player_message(_ucm, result):
        if not (view.get_uri() or '').startswith(netease_url):
            return
        try:
            message = json.loads(result.get_js_value().to_string())
        except (ValueError, AttributeError):
            return
        if not isinstance(message, dict):
            return
        command = message.get('cmd')
        if command == 'control':
            action = str(message.get('action') or '')
            if action in {'toggle', 'pause', 'resume', 'next', 'previous', 'stop'}:
                print(f'thinksmart-kiosk: player control {action}', flush=True)
                evaluate(netease_control_script(action))
        elif command == 'seek':
            try:
                ratio = max(0.0, min(1.0, float(message.get('ratio'))))
            except (TypeError, ValueError):
                return
            evaluate(netease_seek_script(ratio))
        elif command == 'lyrics':
            evaluate(netease_open_lyrics_script())
        elif command == 'mode':
            mode = str(message.get('mode') or '')
            if mode in {'list', 'single', 'shuffle'}:
                print(f'thinksmart-kiosk: player mode {mode}', flush=True)
                evaluate(netease_set_mode_script(mode))
        elif command in {'queue_play', 'page_play'}:
            song_id = str(message.get('id') or '')
            if song_id.isdigit() and len(song_id) <= 20:
                print(f'thinksmart-kiosk: {command} {song_id}', flush=True)
                source = (netease_queue_play_script(song_id) if command == 'queue_play'
                          else netease_page_play_script(song_id))
                evaluate(source)
        elif command == 'browse_playlists':
            print('thinksmart-kiosk: browse playlists', flush=True)
            evaluate(netease_navigate_script('/my/'))
        elif command == 'open_playlist':
            playlist_id = str(message.get('id') or '')
            if playlist_id.isdigit() and len(playlist_id) <= 20:
                print(f'thinksmart-kiosk: open playlist {playlist_id}', flush=True)
                evaluate(netease_navigate_script('/playlist?id=' + playlist_id))
        elif command == 'playlist_play_all':
            playlist_id = str(message.get('id') or '')
            if playlist_id.isdigit() and len(playlist_id) <= 20:
                print(f'thinksmart-kiosk: play full playlist {playlist_id}', flush=True)
                evaluate(netease_playlist_play_all_script(playlist_id))
        elif command == 'status':
            allowed = {
                'title', 'artist', 'playing', 'elapsed', 'duration', 'mode',
                'queueCount', 'playlistCount', 'updated',
            }
            snapshot = {'updated': time.time()}
            for key in allowed:
                value = message.get(key)
                if isinstance(value, str):
                    snapshot[key] = value[:200]
                elif isinstance(value, (bool, int, float)) or value is None:
                    snapshot[key] = value
            try:
                temporary = player_status_file + '.tmp'
                with open(temporary, 'w', encoding='utf-8') as f:
                    json.dump(snapshot, f, ensure_ascii=False)
                os.replace(temporary, player_status_file)
            except OSError:
                pass

    def queue_music_command(message):
        """Validate one local voice command and schedule it on the official web player."""
        action = str(message.get('action') or '')
        query = str(message.get('query') or '').strip()[:160]
        if action not in {'open', 'play', 'pause', 'resume', 'next', 'previous', 'stop',
                          'browse_playlists', 'playlist_play_all'}:
            return
        if action == 'playlist_play_all':
            # The UI bridge sends id; the local diagnostic command reuses the plugin's
            # existing query field so the same validation path can be tested end to end.
            playlist_id = str(message.get('id') or message.get('query') or '')
            if (view.get_uri() or '').startswith(netease_url) and playlist_id.isdigit() and len(playlist_id) <= 20:
                evaluate(netease_playlist_play_all_script(playlist_id))
            return
        if action == 'browse_playlists':
            if (view.get_uri() or '').startswith(netease_url):
                evaluate(netease_navigate_script('/my/'))
            return
        if action == 'open':
            state['music_pending'] = None
            navigator.navigate(netease_url)
            return

        current = view.get_uri() or ''
        if action == 'play' and query:
            target = (netease_url + '#/search/m/?' +
                      urllib.parse.urlencode({'s': query, 'type': 1}))
            state['music_pending'] = {
                'kind': 'search',
                'ready': time.monotonic() + 2.5,
                'deadline': time.monotonic() + 40,
            }
            navigator.navigate(target)
            return

        control = 'resume' if action == 'play' else action
        state['music_pending'] = {
            'kind': 'control',
            'action': control,
            'ready': time.monotonic() + (0 if current.startswith(netease_url) else 2.5),
            'deadline': time.monotonic() + 40,
        }
        if not current.startswith(netease_url):
            navigator.navigate(netease_url)

    def poll_music_commands():
        """Read atomic commands from the Hub plugin; the file is local to this user session."""
        try:
            with open(app_command_file, encoding='utf-8') as f:
                message = json.load(f)
            os.unlink(app_command_file)
            if isinstance(message, dict):
                navigate_app(str(message.get('app') or ''))
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            pass
        try:
            with open(command_file, encoding='utf-8') as f:
                message = json.load(f)
            os.unlink(command_file)
            if isinstance(message, dict):
                queue_music_command(message)
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as error:
            print(f'thinksmart-kiosk: bad music command: {error}', flush=True)
            try:
                os.unlink(command_file)
            except OSError:
                pass

        pending = state.get('music_pending')
        if pending:
            now = time.monotonic()
            if now >= pending['deadline']:
                state['music_pending'] = None
            elif (now >= pending['ready'] and not navigator.switching and not view.is_loading()
                  and (view.get_uri() or '').startswith(netease_url)):
                source = (netease_search_autoplay_script() if pending['kind'] == 'search'
                          else netease_control_script(pending['action']))
                evaluate(source)
                state['music_pending'] = None
        return True

    def run_js(fn, obj):
        view.evaluate_javascript('window.%s && %s(%s)' % (fn, fn, json.dumps(obj, ensure_ascii=False)),
                                 -1, None, None, None, None, None)

    def on_message(_ucm, result):
        # Only our own local page may ask for this; other pages (http) can't navigate to file://
        if not (view.get_uri() or '').startswith('file://' + WELCOME):
            return
        try:
            msg = json.loads(result.get_js_value().to_string())
        except ValueError:
            return
        if msg.get('cmd') == 'busy':
            state['busy'] = bool(msg.get('value'))
            run_js('thinksmartReply', {'id': msg.get('id'), 'ok': True})
            return
        handler = {'scan': wifi_scan, 'connect': wifi_connect, 'forget': wifi_forget,
                   'update_status': update_status, 'update_install': update_request,
                   'update_check': update_request}.get(msg.get('cmd'))
        if handler is None:
            return

        def progress(stage):
            GLib.idle_add(run_js, 'thinksmartProgress', {'id': msg.get('id'), 'stage': stage})

        def work():
            r = handler(msg, progress)
            r['id'] = msg.get('id')
            # the address and Wi-Fi name may have just changed (not after the update polls: every 3 s)
            st = None if msg.get('cmd', '').startswith('update_') else page_status()

            def done():
                run_js('thinksmartReply', r)
                if st:
                    run_js('thinksmartStatus', st)
                return False
            GLib.idle_add(done)
        threading.Thread(target=work, daemon=True).start()

    ucm.connect('script-message-received::thinksmart', on_message)

    def on_navigation(_ucm, result):
        try:
            msg = json.loads(result.get_js_value().to_string())
        except ValueError:
            return
        if isinstance(msg, dict):
            navigate_app(msg.get('cmd'))

    ucm.connect('script-message-received::thinksmartNav', on_navigation)
    ucm.connect('script-message-received::thinksmartPlayer', on_player_message)

    def page_status():
        st = device_status()
        st.update(target=url, tries=state['tries'], help=conf.get('HELP_URL', ''))
        return st

    def show_welcome():
        state['welcome'] = True
        view.load_uri('file://' + WELCOME + '?' + urllib.parse.urlencode(page_status()))

    def on_load_failed(_view, _event, failing_uri, error):
        # Cancelled loads are our own navigations (e.g. switching to the welcome page)
        if (failing_uri.startswith('file://' + WELCOME) or
                error.matches(WebKit2.NetworkError.quark(), WebKit2.NetworkError.CANCELLED)):
            return False
        if navigator and navigator.switching:
            return True
        GLib.idle_add(show_welcome)
        return True  # no WebKit error page

    def check_target():
        """Every few seconds while the welcome page is up: retry the URL off the main thread."""
        if state['welcome'] and not state['checking']:
            state['checking'] = True

            def work():
                ok = reachable(url) and not needs_network_setup()
                st = None if ok else page_status()

                def done():
                    state['checking'] = False
                    if not state['welcome']:
                        return False
                    if ok and not state['busy']:
                        state['welcome'] = False
                        view.load_uri(url)
                    elif not ok:
                        state['tries'] += 1
                        st['tries'] = state['tries']
                        run_js('thinksmartStatus', st)
                    return False
                GLib.idle_add(done)
            threading.Thread(target=work, daemon=True).start()
        return True

    def reload():
        if url and not needs_network_setup():
            view.load_uri(url)
        else:
            show_welcome()
        return False

    def on_terminated(_reason):
        GLib.timeout_add_seconds(2, reload)

    sys.path.insert(0, os.path.dirname(TOOLS_SCRIPT))
    GLib.timeout_add_seconds(2, lambda: (report_browser_status(), True)[1])
    from kiosk_navigation import AppNavigator
    navigator = AppNavigator(view, app_kind, on_terminated, report_browser_status)
    view.connect('load-failed', on_load_failed)
    view.connect('context-menu', lambda *_args: True)  # no long-press menu
    # No pinch zoom on any page: WebKitGTK zooms with its own two-finger gesture on the view,
    # whatever the page's viewport tag or touch-action say (both are iOS-only in WebKit). GDK
    # marks the first finger on the screen as emulating the pointer; touches that land while
    # it is down are dropped before WebKit and its gestures see them, so the zoom gesture never
    # gets a second finger. Taps, scrolling and dragging with one finger are unchanged.
    # (The field, not event.get_pointer_emulated(): that flag is lost in the copy Python gets.)
    view.connect('touch-event', lambda _view, event: not event.touch.emulating_pointer)
    GLib.timeout_add_seconds(RETRY_SECONDS, check_target)
    GLib.timeout_add(250, poll_music_commands)

    window = Gtk.Window(title='ThinkSmart Kiosk')
    # A native in-window keyboard also works when Weston kiosk-shell has no
    # input-panel global. The module only handles input; it never logs field values.
    sys.path.insert(0, os.path.dirname(TOOLS_SCRIPT))
    from kiosk_keyboard import TouchKeyboard
    keyboard = TouchKeyboard(view)
    overlay = Gtk.Overlay()
    overlay.add(view)
    overlay.add_overlay(keyboard.toggle_button)
    layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    layout.pack_start(overlay, True, True, 0)
    layout.pack_end(keyboard.widget, False, False, 0)
    window.add(layout)
    window.connect('destroy', Gtk.main_quit)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM,
                        lambda: (Gtk.main_quit(), False)[1])
    window.fullscreen()
    window.show_all()
    reload()
    Gtk.main()


if __name__ == '__main__':
    main()
