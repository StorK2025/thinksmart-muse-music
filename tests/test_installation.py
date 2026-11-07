import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import configure_hub
from transaction import Transaction
import setup

spec = importlib.util.spec_from_file_location('proxy_setup', ROOT / 'scripts/install-proxy.py')
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)


class InstallationChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_hub_change_preserves_login_and_asr_and_stops_api_routing(self):
        import yaml
        data = self.root / 'data'
        data.mkdir()
        original = {'admin': {'password_hash': 'synthetic-hash'},
                    'selected_module': {'ASR': 'SherpaXASR', 'TTS': 'EdgeTTS', 'LLM': 'OldModel'},
                    'LLM': {'OldModel': {'api_key': 'synthetic-not-a-real-key'}},
                    'Intent': {'function_call': {'functions': ['other_tool']}},
                    'chat_history': {'summary': True}}
        config = data / '.config.yaml'
        config.write_text(yaml.safe_dump(original))
        sessions = data / 'agent_sessions.json'
        sessions.write_text(json.dumps({'last_model': {'synthetic-device': {'model': 'OldModel'}},
                                       'unrelated': 'kept'}))
        txn = Transaction(self.root / 'backup')
        txn.backup([config, sessions])
        configure_hub.configure(data)
        changed = yaml.safe_load(config.read_text())
        self.assertEqual(changed['selected_module']['LLM'], 'Muse')
        self.assertEqual(changed['selected_module']['ASR'], 'SherpaXASR')
        self.assertEqual(changed['admin'], original['admin'])
        self.assertEqual(changed['LLM']['OldModel'], original['LLM']['OldModel'])
        self.assertFalse(changed['chat_history']['summary'])
        self.assertEqual(changed['Intent']['function_call']['functions'], ['play_music'])
        self.assertEqual(json.loads(sessions.read_text())['last_model']['synthetic-device']['model'], 'Muse')
        Transaction.restore(txn.directory)
        self.assertEqual(yaml.safe_load(config.read_text()), original)
        self.assertEqual(json.loads(sessions.read_text())['last_model']['synthetic-device']['model'], 'OldModel')

    def test_multiple_devices_fail_before_mutation(self):
        data = self.root
        config = data / '.config.yaml'
        config.write_text('selected_module: {LLM: OldModel}\n')
        before = config.read_bytes()
        (data / 'agent_sessions.json').write_text(json.dumps({'last_model': {'a': {}, 'b': {}}}))
        with self.assertRaises(ValueError):
            configure_hub.configure(data)
        self.assertEqual(config.read_bytes(), before)

    def test_rollback_removes_only_new_files_and_restores_original(self):
        old, added, untouched = [self.root / n for n in ('old', 'added', 'untouched')]
        old.write_text('original')
        untouched.write_text('do not change')
        txn = Transaction(self.root / 'backup')
        txn.backup([old, added])
        old.write_text('new')
        added.write_text('new file')
        Transaction.restore(txn.directory)
        self.assertEqual(old.read_text(), 'original')
        self.assertFalse(added.exists())
        self.assertEqual(untouched.read_text(), 'do not change')

    def test_rollback_cannot_traverse_backup_paths(self):
        original = self.root / 'original'
        original.write_text('keep')
        txn = Transaction(self.root / 'backup')
        txn.backup([original])
        manifest = txn.directory / 'manifest.json'
        entries = json.loads(manifest.read_text())
        entries[0]['file'] = '../other.backup'
        manifest.write_text(json.dumps(entries))
        with self.assertRaises(ValueError):
            Transaction.restore(txn.directory)
        self.assertEqual(original.read_text(), 'keep')

    def test_symlink_restoration_does_not_modify_target(self):
        target, link = self.root / 'target', self.root / 'link'
        target.write_text('private')
        try:
            link.symlink_to(target)
        except OSError:
            self.skipTest('OS does not allow unprivileged symlinks')
        txn = Transaction(self.root / 'backup')
        txn.backup([link])
        link.unlink()
        link.write_text('replacement')
        Transaction.restore(txn.directory)
        self.assertTrue(link.is_symlink())
        self.assertEqual(target.read_text(), 'private')

    def test_new_sdk_symlink_is_removed_on_rollback(self):
        target, link = self.root / 'target', self.root / 'link'
        target.write_text('keep SDK')
        txn = Transaction(self.root / 'backup')
        txn.backup([link])
        try:
            link.symlink_to(target)
        except OSError:
            self.skipTest('OS does not allow unprivileged symlinks')
        Transaction.restore(txn.directory)
        self.assertFalse(link.is_symlink())
        self.assertEqual(target.read_text(), 'keep SDK')

    def test_proxy_rejects_shell_and_systemd_injection_and_credentials(self):
        self.assertEqual(setup.proxy_environment(''), {})
        self.assertEqual(setup.proxy_environment('http://127.0.0.1:7890')['HTTPS_PROXY'], 'http://127.0.0.1:7890')
        for value in ['http://user:pass@localhost:7890', 'http://localhost:7890\nBAD=value',
                      'http://localhost:7890/;echo', 'http://localhost', 'http://localhost:99999',
                      'http://localhost:7890/?a=b', 'socks5://localhost:7890']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                setup.proxy_environment(value)

    def test_kiosk_preserves_rotation_but_music_uses_direct_network(self):
        result = setup.config_kiosk('ROTATION=90\nGPU=on-demand\nPROXY="http://example:1234"\n', 1001)
        self.assertIn('ROTATION=90', result)
        self.assertIn('GPU=on-demand', result)
        self.assertIn('PROXY=""', result)
        self.assertNotIn('example', result)
        self.assertIn('/run/user/1001/', result)

    def test_proxy_import_disables_exposed_listeners_and_preserves_selection(self):
        c = proxy.sanitize({'proxies': [{'name': 'synthetic', 'type': 'direct'}],
            'allow-lan': True, 'external-controller': '0.0.0.0:9090',
            'external-controller-tls': '0.0.0.0:9443', 'tun': {'enable': True},
            'listeners': [{'port': 1234}], 'dns': {'listen': '0.0.0.0:53'}})
        self.assertEqual(c['external-controller'], '127.0.0.1:9090')
        self.assertFalse(c['allow-lan'])
        self.assertFalse(c['tun']['enable'])
        self.assertNotIn('listeners', c)
        self.assertNotIn('listen', c['dns'])
        self.assertTrue(c['profile']['store-selected'])


if __name__ == '__main__':
    unittest.main()
