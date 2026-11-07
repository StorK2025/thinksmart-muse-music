"""Exercise installer orchestration in a temp filesystem with fake OS services.

No apt, account, systemd, network or real /etc operation is permitted here.
The real file copying, configuration migration and transaction restore run.
"""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import configure_hub
import setup


@unittest.skipUnless(sys.platform == 'linux', 'Linux filesystem/account semantics')
class InstallFlowChecks(unittest.TestCase):
    def exercise(self, fail=False):
        import yaml
        with tempfile.TemporaryDirectory() as td, ExitStack() as stack:
            root = Path(td)
            def mapped(value):
                p = Path(value)
                text = str(p)
                for prefix in ('/etc/', '/var/', '/usr/local/', '/opt/', '/run/'):
                    if text.startswith(prefix):
                        return root / text.lstrip('/')
                return p
            stack.enter_context(patch.object(setup, 'Path', mapped))
            for constant in ('STATE', 'SDK_PREFIX', 'ASSETS', 'MARKER', 'OWNERSHIP'):
                stack.enter_context(patch.object(setup, constant, mapped(getattr(setup, constant))))
            # Ownership changes are privileged OS operations, not what this test targets.
            stack.enter_context(patch.object(os, 'chown'))
            hub = root / 'hub'
            (hub / 'data').mkdir(parents=True)
            conf = hub / 'data/.config.yaml'
            before = 'selected_module: {LLM: Original, ASR: SherpaXASR, TTS: EdgeTTS}\n'
            conf.write_text(before)
            kiosk = mapped('/usr/local/bin/thinksmart-kiosk.py')
            kiosk.parent.mkdir(parents=True)
            kiosk.write_text('original kiosk')
            screen_conf = mapped('/etc/thinksmart-kiosk.conf')
            screen_conf.parent.mkdir(parents=True)
            screen_conf.write_text('ROTATION=90\n')
            account = SimpleNamespace(pw_uid=1000, pw_gid=1000)
            users = {}
            def user(name):
                if name not in users:
                    raise KeyError(name)
                return users[name]
            import pwd, grp
            stack.enter_context(patch.object(pwd, 'getpwnam', side_effect=user))
            stack.enter_context(patch.object(grp, 'getgrgid', return_value=SimpleNamespace(gr_name='fixture-group')))
            stack.enter_context(patch.object(grp, 'getgrall', return_value=[]))
            stack.enter_context(patch.object(setup, 'fetch_sdk', return_value=root / 'source'))
            sdk = mapped('/opt/musegadget/venv/site-packages/musegadget')
            stack.enter_context(patch.object(setup, 'sdk_dir', return_value=sdk))
            calls = []
            def fake_run(*args, **kwargs):
                words = list(map(str, args))
                calls.append(words)
                if words[0] == 'useradd':
                    users['musebridge'] = SimpleNamespace(pw_uid=999, pw_gid=1000, pw_shell='/usr/sbin/nologin')
                    mapped('/var/lib/musebridge').mkdir(parents=True)
                elif words[0] == 'bash' and words[1].endswith('/linux/install.sh'):
                    sdk.mkdir(parents=True)
                    for name in ('network.py', 'service.py', 'link_client.py'):
                        (sdk / name).write_text('original SDK')
                    unit = mapped('/etc/systemd/system/musegadget.service')
                    unit.parent.mkdir(parents=True)
                    unit.write_text('fake official unit')
                    mapped('/usr/local/bin/musegadget').symlink_to(sdk / 'service.py')
                elif len(words) > 1 and words[1].endswith('/scripts/configure_hub.py'):
                    configure_hub.configure(Path(words[2]))
                return '' if kwargs.get('capture') else 0
            stack.enter_context(patch.object(setup, 'run', side_effect=fake_run))
            # The only direct subprocess call in install() checks sudo rights.
            def permission_call(args, **kwargs):
                self.assertEqual(args, ['sudo', '-n', '-l', '-U', 'musebridge'])
                return SimpleNamespace(returncode=1)
            stack.enter_context(patch.object(setup.subprocess, 'run', side_effect=permission_call))
            health = stack.enter_context(patch.object(setup, 'wait_healthy',
                side_effect=RuntimeError('synthetic health failure') if fail else None))
            args = SimpleNamespace(user='fixture-user', proxy='http://127.0.0.1:7890')
            if fail:
                with self.assertRaisesRegex(RuntimeError, 'synthetic health failure'):
                    setup.install(args, account, hub)
                self.assertEqual(conf.read_text(), before)
                self.assertEqual(kiosk.read_text(), 'original kiosk')
                self.assertFalse(mapped('/usr/local/bin/musegadget').is_symlink())
                self.assertFalse(setup.MARKER.exists())
                self.assertTrue(sdk.exists())  # Rollback never wipes account/SDK data.
            else:
                setup.install(args, account, hub)
                self.assertEqual(yaml.safe_load(conf.read_text())['selected_module']['LLM'], 'Muse')
                self.assertTrue((hub / 'core/providers/llm/muse/muse.py').exists())
                self.assertTrue((setup.ASSETS / 'launcher.html').exists())
                self.assertTrue(setup.MARKER.exists())
                installed = json.loads(setup.MARKER.read_text())
                self.assertEqual(installed['user'], 'fixture-user')
                setup.restore(installed['backup'])
                self.assertEqual(conf.read_text(), before)
                self.assertEqual(kiosk.read_text(), 'original kiosk')
            self.assertEqual(health.call_count, 1)
            self.assertTrue(calls)

    def test_fresh_install_and_manual_restore(self):
        self.exercise()

    def test_failed_start_automatically_restores_configuration(self):
        self.exercise(fail=True)


if __name__ == '__main__':
    unittest.main()
