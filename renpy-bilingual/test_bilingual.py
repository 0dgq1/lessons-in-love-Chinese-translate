"""Run with python -m unittest test_bilingual -v; never contacts a live API."""
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.error
import ssl

sys.path.insert(0, str(Path(__file__).parent / 'game' / 'python-packages'))
import lil_bilingual as b

CONFIG = dict(enabled=True, provider='deepseek', base_url='https://api.deepseek.com',
              model='test-model', api_key='test-secret', timeout=30)


def response(data):
    return io.StringIO(json.dumps(data))


class ProviderTests(unittest.TestCase):
    def test_quality_prompt_and_glossary_without_extra_request(self):
        config = dict(CONFIG, quality_mode=True, glossary={'Sensei': '老师'})
        payload = {'choices': [{'finish_reason': 'stop', 'message': {'content': '老师'}}]}
        with patch.object(b.urllib.request, 'urlopen', return_value=response(payload)) as call:
            self.assertEqual(b.request_translation(config, 'Sensei'), '老师')
            body = json.loads(call.call_args.args[0].data)
            self.assertIn('老师', body['messages'][0]['content'])
            self.assertIn('idioms', body['messages'][0]['content'])
            self.assertEqual(body['thinking']['type'], 'disabled')
            self.assertEqual(call.call_count, 1)

    def test_tls_validation_and_certificate_failure(self):
        context = b.tls_context(CONFIG)
        self.assertIs(context, b.tls_context(CONFIG))
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertGreater(context.cert_store_stats()['x509_ca'], 0)
        error = urllib.error.URLError(ssl.SSLCertVerificationError(1, 'certificate failed'))
        with patch.object(b.urllib.request, 'urlopen', side_effect=error) as call:
            with self.assertRaisesRegex(b.TranslationError, 'HTTPS'):
                b.request_translation(CONFIG, 'Hello')
            self.assertEqual(call.call_count, 1)

    def test_deepseek_and_gemini(self):
        cases = [
            (CONFIG, {'choices': [{'finish_reason': 'stop', 'message': {'content': '你好'}}]}),
            (dict(CONFIG, provider='gemini'), {'candidates': [{'finishReason': 'STOP',
                'content': {'parts': [{'text': '你好'}]}}]})]
        for config, payload in cases:
            with patch.object(b.urllib.request, 'urlopen', return_value=response(payload)) as call:
                self.assertEqual(b.request_translation(config, 'Hello [name]'), '你好')
                req = call.call_args.args[0]
                self.assertNotIn('test-secret', req.full_url)
                self.assertIn('Hello [name]', req.data.decode())
                if config['provider'] == 'deepseek':
                    self.assertEqual(json.loads(req.data)['thinking'], {'type': 'disabled'})

    @patch.object(b.time, 'sleep')
    def test_retry_limit(self, sleep):
        for failure in (TimeoutError(), urllib.error.URLError('offline'),
                        urllib.error.HTTPError('url', 429, 'limited', {}, None)):
            with patch.object(b.urllib.request, 'urlopen', side_effect=failure) as call:
                with self.assertRaises(b.TranslationError):
                    b.request_translation(CONFIG, 'Hello')
                self.assertEqual(call.call_count, 3)

    def test_auth_empty_refusal_and_malformed(self):
        with patch.object(b.urllib.request, 'urlopen', side_effect=
                urllib.error.HTTPError('url', 401, 'unauthorized', {}, None)) as call:
            with self.assertRaises(b.TranslationError):
                b.request_translation(CONFIG, 'Hello')
            self.assertEqual(call.call_count, 1)
        for message in ({'content': ''}, {'content': None}, {'refusal': 'refused'}):
            payload = {'choices': [{'finish_reason': 'stop', 'message': message}]}
            with patch.object(b.urllib.request, 'urlopen', return_value=response(payload)):
                with self.assertRaises(b.TranslationError):
                    b.request_translation(CONFIG, 'Hello')
        with patch.object(b.urllib.request, 'urlopen', return_value=response({'promptFeedback': {}})):
            with self.assertRaises(b.TranslationError):
                b.request_translation(dict(CONFIG, provider='gemini'), 'Hello')


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        Path(self.tmp.name, 'bilingual_config.json').write_text(json.dumps(CONFIG), encoding='utf-8')
        self.queue = []
        self.refreshes = []
        self.runtime = b.Translator(self.tmp.name,
            lambda *args: self.queue.append(args), lambda: self.refreshes.append(True))

    def drain(self):
        deadline = time.monotonic() + 2
        while (self.runtime.busy or self.runtime.prefetch_busy) and time.monotonic() < deadline:
            time.sleep(.005)
        self.assertFalse(self.runtime.busy)
        self.assertFalse(self.runtime.prefetch_busy)
        while self.queue:
            fn, *args = self.queue.pop(0)
            fn(*args)

    def test_dedup_and_persistence(self):
        with patch.object(b, 'request_translation', return_value='你好') as call:
            for _ in range(20):
                self.runtime.activate('Hello')
            self.drain()
            self.assertEqual(call.call_count, 1)
        self.assertEqual(self.runtime.view('Hello'), ('你好', False))
        other = b.Translator(self.tmp.name, None, None)
        self.assertEqual(other.view('Hello'), ('你好', False))
        self.assertNotIn('test-secret', Path(self.runtime.cache_path).read_text(encoding='utf-8'))
        other.config['model'] = 'another-model'
        self.assertNotEqual(other.key('Hello'), self.runtime.key('Hello'))

    def test_glossary_loading_validation_and_cache_namespace(self):
        p = Path(self.tmp.name, 'bilingual_glossary.json')
        self.runtime.config['quality_mode'] = True
        original = self.runtime.key('Sensei')
        p.write_text(json.dumps({'Sensei': '老师'}), encoding='utf-8')
        loaded = b.Translator(self.tmp.name, None, None)
        loaded.config['quality_mode'] = True
        self.assertEqual(loaded.config['glossary'], {'Sensei': '老师'})
        self.assertNotEqual(loaded.key('Sensei'), original)
        loaded.config['glossary'] = {'B': '乙', 'A': '甲'}
        key = loaded.key('same')
        loaded.config['glossary'] = {'A': '甲', 'B': '乙'}
        self.assertEqual(key, loaded.key('same'))
        p.write_text('["invalid"]', encoding='utf-8')
        self.assertEqual(b.Translator(self.tmp.name, None, None).config['glossary'], {})

    def test_speed_mode_uses_short_prompt_and_ignores_glossary(self):
        self.assertEqual(b.translation_prompt(self.runtime.config), b.FAST_PROMPT)
        key = self.runtime.key('Sensei')
        self.runtime.config['glossary'] = {'Sensei': '老师'}
        self.assertEqual(self.runtime.key('Sensei'), key)
        self.runtime.config['quality_mode'] = True
        self.assertNotEqual(self.runtime.key('Sensei'), key)

    def test_latest_pending_and_no_stale_refresh(self):
        import threading
        started, release = threading.Event(), threading.Event()
        seen = []
        def translate(config, source):
            seen.append(source)
            if source == 'A':
                started.set()
                release.wait(2)
            return '译' + source
        with patch.object(b, 'request_translation', side_effect=translate):
            self.runtime.activate('A')
            self.assertTrue(started.wait(1))
            self.runtime.activate('B')
            self.runtime.activate('C')
            release.set()
            self.drain()
        self.assertEqual(seen, ['A', 'C'])
        self.assertEqual(len(self.refreshes), 1)
        self.assertEqual(self.runtime.view('C'), ('译C', False))
        self.assertNotIn(self.runtime.key('B'), self.runtime.states)

    def test_failure_manual_retry_and_missing_config(self):
        with patch.object(b, 'request_translation', side_effect=b.TranslationError('超时')):
            self.runtime.activate('A')
            self.drain()
        self.assertEqual(self.runtime.view('A'), ('超时', True))
        with patch.object(b, 'request_translation', return_value='成功'):
            self.runtime.activate('A', retry=True)
            self.drain()
        self.assertEqual(self.runtime.view('A'), ('成功', False))
        Path(self.tmp.name, 'bilingual_config.json').unlink()
        self.assertFalse(b.Translator(self.tmp.name, None, None).enabled)

    def test_invalid_config_and_cancelled_pending(self):
        for bad in ('[]', 'null', '{broken'):
            Path(self.tmp.name, 'bilingual_config.json').write_text(bad, encoding='utf-8')
            self.assertFalse(b.Translator(self.tmp.name, None, None).enabled)
        cached = self.runtime.key('cached')
        self.runtime.cache[cached] = '已有译文'
        # Emulate an occupied worker without starting a network request.
        self.runtime.busy = True
        self.runtime.activate('queued')
        queued = self.runtime.key('queued')
        self.runtime.activate('cached')
        self.assertIsNone(self.runtime.pending)
        self.assertNotIn(queued, self.runtime.states)
        self.runtime.activate('queued')
        self.assertEqual(self.runtime.pending[0], queued)
        self.runtime.suspend()
        self.assertIsNone(self.runtime.current)
        self.assertIsNone(self.runtime.pending)

    def test_prefetch_cache_and_no_duplicate_on_activation(self):
        with patch.object(b, 'request_translation', return_value='提前译文') as call:
            self.runtime.prefetch(['B', 'B', 'C'])
            self.drain()
            self.runtime.activate('B')
            self.assertEqual(self.runtime.view('B'), ('提前译文', False))
            self.assertEqual(call.call_count, 2)

    def test_prefetch_limit_disable_and_replace(self):
        self.runtime.config['prefetch_lines'] = 0
        self.runtime.prefetch(['A'])
        self.assertFalse(self.runtime.prefetch_busy)
        self.runtime.config['prefetch_lines'] = 2
        self.runtime.prefetch_busy = True
        self.runtime.prefetch(['A', 'B', 'C'])
        self.assertEqual([source for _, source in self.runtime.prefetch_jobs], ['A', 'B'])
        self.runtime.prefetch(['D'])
        self.assertEqual([source for _, source in self.runtime.prefetch_jobs], ['D'])
        self.runtime.suspend()
        self.assertEqual(self.runtime.prefetch_jobs, [])

    def test_prefetch_does_not_block_foreground(self):
        import threading
        started, release, foreground = threading.Event(), threading.Event(), threading.Event()
        def translate(config, source):
            if source == 'future':
                started.set()
                release.wait(2)
            else:
                foreground.set()
            return source
        with patch.object(b, 'request_translation', side_effect=translate) as call:
            self.runtime.prefetch(['future', 'unused'])
            self.assertTrue(started.wait(1))
            self.runtime.activate('current')
            self.assertTrue(foreground.wait(1))
            # Advancing onto an in-flight prefetched line must not call twice.
            self.runtime.activate('future')
            self.runtime.suspend()
            release.set()
            self.drain()
        self.assertEqual(call.call_count, 2)
        self.assertFalse(self.refreshes)

    def test_failed_prefetch_can_translate_on_demand(self):
        with patch.object(b, 'request_translation', side_effect=b.TranslationError('offline')):
            self.runtime.prefetch(['B'])
            self.drain()
        self.assertNotIn(self.runtime.key('B'), self.runtime.states)
        with patch.object(b, 'request_translation', return_value='success'):
            self.runtime.activate('B')
            self.drain()
        self.assertEqual(self.runtime.view('B'), ('success', False))


class LookaheadTests(unittest.TestCase):
    def node(self, kind, **attrs):
        obj = type(kind, (), {})()
        obj.next = None
        for name, value in attrs.items():
            setattr(obj, name, value)
        return obj

    def test_straight_line_and_boundaries(self):
        nodes = [self.node('Say', what='current'), self.node('Show'),
                 self.node('Say', what='next'), self.node('Say', what='Hello [name]'),
                 self.node('Say', what='last'), self.node('Menu'), self.node('Say', what='unselected')]
        for left, right in zip(nodes, nodes[1:]):
            left.next = right
        self.assertEqual(b.lookahead_texts(nodes[0], 3), ['next', 'last'])
        self.assertEqual(b.lookahead_texts(nodes[0], 1), ['next'])
        for kind in ('If', 'Python', 'Jump', 'Call', 'Return', 'Label'):
            nodes[1] = self.node(kind)
            nodes[0].next = nodes[1]
            nodes[1].next = nodes[2]
            self.assertEqual(b.lookahead_texts(nodes[0], 3), [])

    def test_audio_and_cycle(self):
        head = self.node('Say', what='current')
        audio = self.node('UserStatement', line='play music "song.ogg"')
        future = self.node('Say', what='literal [[brackets]')
        head.next, audio.next, future.next = audio, future, audio
        self.assertEqual(b.lookahead_texts(head, 3), ['literal [brackets]'])


if __name__ == '__main__':
    unittest.main()
