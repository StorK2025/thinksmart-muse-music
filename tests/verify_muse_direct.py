"""Exercise direct routing, framed replies, cancellation and request privacy."""
import importlib.util
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import types
import unittest
from unittest import mock


class Logger:
    def bind(self, **kw): return self
    def info(self, *a): pass
    def warning(self, *a): pass


for name in ['config', 'core', 'core.providers', 'core.providers.llm']:
    sys.modules.setdefault(name, types.ModuleType(name))
log_module = types.ModuleType('config.logger')
log_module.setup_logging = lambda: Logger()
sys.modules['config.logger'] = log_module
base_module = types.ModuleType('core.providers.llm.base')
base_module.LLMProviderBase = object
sys.modules['core.providers.llm.base'] = base_module
spec = importlib.util.spec_from_file_location('muse_direct_candidate', Path(__file__).resolve().parents[1] / 'hub' / 'muse_llm.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DirectChecks(unittest.TestCase):
    def setUp(self):
        # The provider runs on Linux; Windows uses TCP socketpair underneath
        # these transport tests, with the socket constructor replaced below.
        family = mock.patch.object(module.socket, 'AF_UNIX', getattr(socket, 'AF_UNIX', socket.AF_INET), create=True)
        family.start()
        self.addCleanup(family.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.provider = module.LLMProvider({'state_dir': self.temp.name})

    def test_latest_utterance_only_and_session_reused(self):
        dialogue = [{'role':'system','content':'DO NOT SEND THIS'},
                    {'role':'user','content':'old user message'},
                    {'role':'assistant','content':'old assistant reply'},
                    {'role':'user','content':json.dumps({'speaker':'test','content':'当前问题'})}]
        self.assertEqual(module.latest_question(dialogue), '当前问题')
        sid = self.provider._session()
        other = module.LLMProvider({'state_dir': self.temp.name})
        self.assertEqual(other._session(), sid)

    def test_local_music_commands(self):
        for text, expected in [
            ('请播放蔡依林的舞娘', ('play_music', {'song_name':'蔡依林的舞娘'})),
            ('我想听海阔天空', ('play_music', {'song_name':'海阔天空'})),
            ('暂停音乐', ('play_music', {'song_name':'暂停'})),
            ('继续播放', ('play_music', {'song_name':'继续'})),
        ]:
            with self.subTest(text=text): self.assertEqual(module.local_command(text), expected)

    def test_questions_and_followups_go_to_muse(self):
        for text in ['你好，请介绍自己','为什么天空是蓝色的','我想听你介绍自己','推荐一首蔡依林的歌','继续','请解释怎么播放音乐']:
            with self.subTest(text=text): self.assertIsNone(module.local_command(text))
        with mock.patch.object(self.provider, 'response', return_value=iter(['Muse reply'])) as route:
            self.assertEqual(list(self.provider.response_with_functions('c',[{'role':'user','content':'你好'}])), [('Muse reply',None)])
            self.assertEqual(route.call_count, 1)

    def test_only_enabled_tools_execute(self):
        functions = [{'type':'function','function':{'name':'play_music'}}]
        result = list(self.provider.response_with_functions('c',[{'role':'user','content':'暂停音乐'}],functions))
        self.assertEqual(result[0][1][0].function.name, 'play_music')
        with mock.patch.object(self.provider, 'response', return_value=iter(['Muse reply'])) as route:
            result = list(self.provider.response_with_functions('c',[{'role':'user','content':'暂停音乐'}],[]))
            self.assertEqual(result, [('Muse reply',None)])
            self.assertEqual(route.call_count, 1)

    def exchange(self, frames):
        client, peer = socket.socketpair()
        requests = []
        class Client:
            def connect(self, path): pass
            def __getattr__(self, name): return getattr(client, name)
            def fileno(self): return client.fileno()
        def server():
            try:
                data = b''
                while b'\n' not in data: data += peer.recv(4096)
                requests.append(json.loads(data))
                payload = b''.join((json.dumps(f,ensure_ascii=False)+'\n').encode() for f in frames)
                for i in range(0,len(payload),7): peer.sendall(payload[i:i+7])
            finally: peer.close()
        worker = threading.Thread(target=server, daemon=True)
        worker.start()
        with mock.patch.object(module.socket, 'socket', return_value=Client()):
            text = ''.join(self.provider.response('c',[{'role':'system','content':'private old prompt'}, {'role':'user','content':'当前问题'}]))
        worker.join(2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(requests),1)
        self.assertEqual(requests[0]['message'],'当前问题')
        self.assertTrue(requests[0]['stream'])
        return text

    def test_stream_and_final_replay_are_spoken_once(self):
        text = self.exchange([{'type':'accepted'}, {'type':'reply','text':'你好，'},
                              {'type':'reply','text':'你好，世界。'},
                              {'type':'done','ok':True,'reply':'你好，世界。'}])
        self.assertEqual(text,'你好，世界。')

    def test_legacy_reply_and_uncertain_delivery(self):
        self.assertEqual(self.exchange([{'ok':True,'reply':'完整回答'}]),'完整回答')
        text = self.exchange([{'type':'done','ok':False,'sent':'unknown'}])
        self.assertIn('可能',text)
        self.assertIn('没有重复发送',text)

    def test_abort_stops_local_wait_without_sending_again(self):
        client, peer = socket.socketpair()
        class Client:
            def connect(self,path): pass
            def __getattr__(self,name):return getattr(client,name)
            def fileno(self):return client.fileno()
        with mock.patch.object(module.socket,'socket',return_value=Client()):
            generator = self.provider.response('test-connection',[{'role':'user','content':'测试'}])
            self.assertEqual(next(generator),'')
            peer.recv(4096)
            self.provider.abort(types.SimpleNamespace(session_id='test-connection'))
            self.assertEqual(list(generator),[])
        self.assertFalse(self.provider._active)
        peer.close()


if __name__ == '__main__':
    unittest.main()
