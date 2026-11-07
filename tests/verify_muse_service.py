"""Regression checks for reordered Muse events and local stream lifecycle."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import unittest

path = Path(__file__).resolve().parents[1] / 'sdk' / 'muse-service.py'
spec = importlib.util.spec_from_file_location('muse_service_candidate', path)
service = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = service
spec.loader.exec_module(service)
from musegadget.muse_turn import MuseTurn


def event(name, seq, mid=None, chat='test-chat', **fields):
    return {'type': 'event', 'event': name, 'seq': seq,
            'payload': {'session_id': chat, **({'message_id': mid} if mid else {}), **fields}}


ACK = {'message_id': 'user-now', 'session_id': 'test-chat', 'is_thread': True}


class ReaderChecks(unittest.TestCase):
    def reader(self):
        return service._ReplyReader(MuseTurn('test-chat'))

    def answer(self, reader, seq=591, mid='assistant-now'):
        reader.take(event('delta.message_start', seq, mid))
        reader.take(event('delta.text_append', seq+1, mid, text='正确回答'))
        reader.take(event('delta.message_done', seq+2, mid))

    def test_late_user_echo_after_ack(self):
        r = self.reader()
        r.take(event('agent.status', 582, activity_code='thinking'))
        r.acknowledge(ACK, fresh=False)
        r.take(event('task.status', 586, status='running'))
        r.take(event('message.user', 573, 'user-now'))
        self.answer(r)
        self.assertEqual(service._reply_text(r.turn), '正确回答')

    def test_late_user_echo_before_ack(self):
        r = self.reader()
        r.take(event('agent.status', 582, activity_code='thinking'))
        r.take(event('message.user', 573, 'user-now'))
        r.acknowledge(ACK, fresh=False)
        self.answer(r)
        self.assertEqual(service._reply_text(r.turn), '正确回答')

    def test_old_echo_cannot_reopen_after_another_user(self):
        r = self.reader()
        r.acknowledge(ACK, fresh=False)
        r.take(event('message.user', 573, 'user-now'))
        r.take(event('message.user', 580, 'another-request'))
        r.take(event('message.user', 573, 'user-now'))
        self.answer(r)
        self.assertEqual(service._reply_text(r.turn), '')

    def test_other_chat_cannot_poison_user_order(self):
        r = self.reader()
        r.acknowledge(ACK, fresh=False)
        r.take(event('message.user', 999, 'user-now', chat='some-other-chat'))
        r.take(event('message.user', 573, 'user-now'))
        self.answer(r)
        self.assertEqual(service._reply_text(r.turn), '正确回答')

    def test_duplicate_delta_is_not_spoken_twice(self):
        r = self.reader()
        r.acknowledge(ACK, fresh=False)
        r.take(event('message.user', 573, 'user-now'))
        delta = event('delta.text_append', 592, 'assistant-now', text='一次')
        r.take(delta)
        r.take(delta)
        self.assertEqual(service._reply_text(r.turn), '一次')


class LifecycleChecks(unittest.IsolatedAsyncioTestCase):
    async def test_text_stream_arrives_before_task_finishes(self):
        queue = asyncio.Queue()
        frames = []
        class Session:
            async def subscribe_chat(self, sid, opened=None):
                opened.set()
                while True:
                    yield await queue.get()
        async def send():
            queue.put_nowait(event('agent.status', 582, activity_code='thinking'))
            queue.put_nowait(event('message.user', 573, 'user-now'))
            queue.put_nowait(event('delta.text_append', 592, 'assistant-now', text='流式回答'))
            return {'ok': True, 'response': ACK}
        async def emit(frame):
            frames.append(frame)
            if frame['type'] == 'reply':
                queue.put_nowait(event('delta.message_done', 593, 'assistant-now'))
                queue.put_nowait(event('task.status', 594, status='completed'))
        result = await service.send_and_wait(Session(), send, 'test-chat', 3, emit=emit)
        self.assertEqual(result.get('reply'), '流式回答')
        self.assertTrue(any(f.get('text') == '流式回答' for f in frames))
        self.assertFalse(result.get('partial'))

    async def test_client_disconnect_cancels_waiter(self):
        cancelled = asyncio.Event()
        class WaitingService(service.Service):
            async def _local_request(self, line, *, emit=None):
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
        class Writer:
            closed = False
            def close(self): self.closed = True
            def write(self, data): pass
            async def drain(self): pass
        reader = asyncio.StreamReader()
        reader.feed_data(json.dumps({'message':'hello','wait':120,'stream':True}).encode()+b'\n')
        reader.feed_eof()
        writer = Writer()
        await asyncio.wait_for(WaitingService(identity=None, executor=None)._handle_local(reader, writer), 3)
        self.assertTrue(cancelled.is_set())
        self.assertTrue(writer.closed)


if __name__ == '__main__':
    unittest.main()
