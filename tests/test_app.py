import os
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from storage import Store
from browser_manager import BrowserManager


class WebFixture(BaseHTTPRequestHandler):
    def do_GET(self):
        page = b'''<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head><body><h1>Fixture mobile</h1></body></html>'''
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.send_header('Content-Length', str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def log_message(self, *args):
        pass


class StorageTests(unittest.TestCase):
    def test_validation_and_reload(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            with self.assertRaises(ValueError):
                store.create_site('Invalido', 'javascript:alert(1)')
            with self.assertRaises(ValueError):
                store.create_site('Invalido', 'https://user:password@example.org/')
            site = store.create_site('Site teste', 'https://example.org/')
            profile = store.create_profile('Conta 01', site['id'])
            store = Store(folder)
            self.assertEqual(store.site(site['id'])['name'], 'Site teste')
            self.assertEqual(store.profile(profile['id'])['name'], 'Conta 01')
            store.update_site(site['id'], 'Alterado', 'https://example.com')
            self.assertEqual(store.site(site['id'])['url'], 'https://example.com')
            with self.assertRaises(ValueError):
                store.delete_site(site['id'])
            store.delete_profile(profile['id'])
            store.delete_site(site['id'])


class LocalDeviceMetadataTests(unittest.TestCase):
    def test_models_and_edits_survive_local_server_restart(self):
        from storage import DEVICE_MODELS, DEFAULT_DEVICE
        self.assertGreaterEqual(len(DEVICE_MODELS), 40)
        self.assertEqual(DEFAULT_DEVICE, 'Pixel 7')
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            site = store.create_site('Catálogo', 'https://example.org')
            profiles = [
                store.create_profile(f'Conta {i}', site['id'],
                                     'Galaxy S24' if i % 2 else 'Pixel 7')
                for i in range(200)
            ]
            self.assertEqual(len({p['id'] for p in profiles}), 200)
            changed = store.update_profile(profiles[1]['id'], 'Editado',
                                           site['id'], 'Galaxy A55')
            self.assertEqual(changed['device'], 'Galaxy A55')
            with self.assertRaises(ValueError):
                store.create_profile('Invalido', site['id'], 'Model-Fake-999')
            reloaded = Store(folder)
            self.assertEqual(len(reloaded.profiles), 200)
            self.assertEqual(reloaded.profile(profiles[1]['id'])['device'], 'Galaxy A55')
            self.assertEqual(reloaded.profile(profiles[0]['id'])['device'], 'Pixel 7')


class FingerprintSnapshotTests(unittest.TestCase):
    def test_versioned_snapshot_is_stable_and_duplication_is_empty(self):
        import json
        from fingerprint_manager import FingerprintManager
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            site = store.create_site('Site', 'https://example.org')
            a = store.create_profile('Conta A', site['id'], 'Galaxy S24')
            snapshot = a['fingerprint']
            self.assertEqual(snapshot['preset'], 'Galaxy S24')
            self.assertEqual(snapshot['playwright_version'], '1.57.0')
            self.assertTrue(FingerprintManager.migrate_version(snapshot)['compatible'])
            b = store.duplicate_profile(a['id'])
            self.assertNotEqual(a['id'], b['id'])
            self.assertEqual(b['fingerprint']['preset'], 'Galaxy S24')
            self.assertFalse((store.profiles_dir / b['id']).exists())
            reloaded = Store(root)
            self.assertEqual(reloaded.profile(a['id'])['fingerprint'], snapshot)
            self.assertEqual(reloaded.profile(b['id'])['device'], 'Galaxy S24')
            reloaded.regenerate_fingerprint(a['id'])
            self.assertEqual(reloaded.profile(a['id'])['fingerprint']['reason'],
                             'user-explicit-regeneration')
            with self.assertRaises(ValueError):
                FingerprintManager.validate(snapshot, 'Pixel 7')
            with self.assertRaises(ValueError):
                FingerprintManager.validate({'preset': 'unlisted'})

    def test_old_profiles_migrate_without_changing_device_or_id(self):
        import json
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            site = store.create_site('Site', 'https://example.org')
            profile = store.create_profile('Original', site['id'], 'Pixel 5')
            settings = store.path
            record = json.loads(settings.read_text('utf-8'))
            del record['profiles'][0]['fingerprint']
            settings.write_text(json.dumps(record), encoding='utf-8')
            migrated = Store(root).profile(profile['id'])
            self.assertEqual(migrated['id'], profile['id'])
            self.assertEqual(migrated['device'], 'Pixel 5')
            self.assertEqual(migrated['fingerprint']['reason'], 'legacy-migration')

class RuntimeSessionStateTests(unittest.TestCase):
    def test_concurrent_limit_does_not_restrict_saved_profiles(self):
        from session_manager import SessionManager
        sessions = SessionManager(max_open=2)
        self.assertEqual(sessions.max_open, 2)
        sessions.begin('profile-a', 0)
        sessions.running('profile-a')
        self.assertEqual(sessions.describe('profile-a', True)['status'], 'running')
        self.assertIsNotNone(sessions.describe('profile-a', True)['started_at'])
        sessions.begin('profile-b', 1)
        sessions.running('profile-b')
        with self.assertRaises(ValueError):
            sessions.begin('profile-c', 2)
        sessions.stopping('profile-a')
        sessions.stopped('profile-a')
        self.assertEqual(sessions.describe('profile-a', False)['status'], 'stopped')
        sessions.begin('profile-c', 1)
        sessions.error('profile-c', ValueError('private url must never be logged'))
        details = sessions.describe('profile-c', False)
        self.assertEqual(details['status'], 'error')
        self.assertEqual(details['last_error_type'], 'ValueError')
        self.assertNotIn('private url', str(details))

class BrowserTests(unittest.TestCase):
    def test_mobile_cookie_isolation_and_persistence(self):
        fixture = ThreadingHTTPServer(('127.0.0.1', 0), WebFixture)
        Thread(target=fixture.serve_forever, daemon=True).start()
        try:
            url = f'http://127.0.0.1:{fixture.server_address[1]}/'
            with tempfile.TemporaryDirectory() as folder:
                store = Store(folder)
                site = store.create_site('Testes', url)
                p1 = store.create_profile('Primeiro', site['id'])
                p2 = store.create_profile('Segundo', site['id'])
                mgr = BrowserManager(store, headless=True,
                    executable_path=os.environ.get('MULTILOGIN_CHROMIUM_PATH'))
                try:
                    result = mgr.start(p1['id'])
                    context1 = mgr.contexts[p1['id']]
                    if result['warning']:
                        # O Chromium gerenciado neste ambiente pode bloquear TODA navegação
                        # por política administrativa. Ainda é possível testar mobile e cookies.
                        page1 = context1.new_page()
                        page1.set_content('<meta name="viewport" content="width=device-width, initial-scale=1"><h1>Fixture mobile</h1>')
                    else:
                        page1 = context1.pages[0]
                    details = page1.evaluate('''() => ({
                        mobile: /Android/.test(navigator.userAgent),
                        touch: navigator.maxTouchPoints > 0,
                        viewport: window.innerWidth,
                        scale: window.devicePixelRatio
                    })''')
                    self.assertTrue(details['mobile'], details)
                    self.assertTrue(details['touch'], details)
                    self.assertGreater(details['scale'], 1)
                    self.assertLess(details['viewport'], 500)
                    context1.add_cookies([{'name':'check_session', 'value':'first', 'url': url}])
                    mgr.start(p2['id'])
                    context2 = mgr.contexts[p2['id']]
                    self.assertFalse(any(c['name']=='check_session' for c in context2.cookies()))
                    context2.add_cookies([{'name':'check_session', 'value':'second', 'url': url}])
                    mgr.stop(p1['id'])
                    mgr.start(p1['id'])
                    context1 = mgr.contexts[p1['id']]
                    self.assertTrue(any(c['name']=='check_session' and c['value']=='first' for c in context1.cookies()))
                    self.assertTrue(any(c['name']=='check_session' and c['value']=='second' for c in context2.cookies()))
                    self.assertEqual(mgr.status()[p1['id']], 'running')
                    mgr.stop(p1['id'])
                    self.assertEqual(mgr.status()[p1['id']], 'stopped')
                finally:
                    mgr.stop_all()
        finally:
            fixture.shutdown()
            fixture.server_close()

    def test_per_profile_mobile_models_launch_and_persist(self):
        fixture = ThreadingHTTPServer(('127.0.0.1', 0), WebFixture)
        Thread(target=fixture.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as folder:
                store = Store(folder)
                site = store.create_site('Device test',
                    f'http://127.0.0.1:{fixture.server_address[1]}/')
                first = store.create_profile('First', site['id'], 'Pixel 7')
                second = store.create_profile('Second', site['id'], 'Galaxy S24')
                manager = BrowserManager(store, headless=True)
                try:
                    manager.start(first['id'])
                    manager.start(second['id'])
                    page_a = manager.contexts[first['id']].pages[0]
                    page_b = manager.contexts[second['id']].pages[0]
                    a = page_a.evaluate('navigator.userAgent')
                    b = page_b.evaluate('navigator.userAgent')
                    self.assertIn('Pixel 7', a)
                    self.assertIn('SM-S921', b)
                    self.assertNotEqual(manager.contexts[first['id']].pages[0].viewport_size,
                                        manager.contexts[second['id']].pages[0].viewport_size)
                    manager.stop(first['id'])
                    self.assertEqual(manager.status()[second['id']], 'running')
                    manager.stop(second['id'])
                finally:
                    manager.stop_all()
                # Re-read configuration from disk, not from the previous manager.
                reloaded = Store(folder)
                self.assertEqual(reloaded.profile(first['id'])['device'], 'Pixel 7')
                self.assertEqual(reloaded.profile(second['id'])['device'], 'Galaxy S24')
        finally:
            fixture.shutdown()
            fixture.server_close()

    def test_inspector_reads_actual_properties_without_injecting(self):
        fixture = ThreadingHTTPServer(('127.0.0.1', 0), WebFixture)
        Thread(target=fixture.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as root:
                store = Store(root)
                site = store.create_site('Site',
                    f'http://127.0.0.1:{fixture.server_address[1]}/')
                profile = store.create_profile('Audit', site['id'], 'Pixel 7')
                manager = BrowserManager(store, headless=True)
                try:
                    stopped = manager.inspect(profile['id'])
                    self.assertFalse(stopped['running'])
                    self.assertIsNone(stopped['observed'])
                    manager.start(profile['id'])
                    report = manager.inspect(profile['id'])
                    self.assertTrue(report['running'])
                    self.assertEqual(report['configured']['preset'], 'Pixel 7')
                    self.assertIn('Android', report['observed']['userAgent'])
                    self.assertIn('platform', report['observed'])
                    self.assertIn('webdriver', report['observed'])
                    self.assertIn('webgl', report['observed'])
                    self.assertIn('timezone', report['observed'])
                    self.assertTrue(report['comparisons']['userAgent'])
                    self.assertTrue(report['comparisons']['touch'])
                    self.assertTrue(report['comparisons']['viewportHeight'])
                    self.assertIn('platformCompatible', report['comparisons'])
                    self.assertEqual(
                        report['runtime_signals']['automation_exposed'],
                        report['observed']['webdriver'] is True)
                    if report['observed']['platform'] in (
                            'Win32', 'Win64', 'MacIntel', 'Linux x86_64',
                            'Linux i686', 'Linux x86'):
                        self.assertFalse(report['comparisons']['platformCompatible'])
                        self.assertFalse(report['consistent_for_tested_fields'])
                        self.assertTrue(
                            report['runtime_signals']['desktop_platform_with_mobile_user_agent'])
                    if report['observed']['userAgentData'] is not None:
                        self.assertTrue(report['comparisons']['clientHintsMobile'])
                        self.assertTrue(report['comparisons']['clientHintsPlatform'])
                    self.assertEqual(store.profile(profile['id'])['fingerprint'],
                                     stopped['configured'])
                finally:
                    manager.stop_all()
        finally:
            fixture.shutdown()
            fixture.server_close()

    def test_localstorage_isolation_and_persistence(self):
        fixture = ThreadingHTTPServer(('127.0.0.1', 0), WebFixture)
        Thread(target=fixture.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as folder:
                store = Store(folder)
                site = store.create_site('Teste', f'http://127.0.0.1:{fixture.server_address[1]}/')
                p1 = store.create_profile('Primeiro', site['id'])
                p2 = store.create_profile('Segundo', site['id'])
                mgr = BrowserManager(store, headless=True, executable_path=os.environ.get('MULTILOGIN_CHROMIUM_PATH'))
                try:
                    result = mgr.start(p1['id'])
                    if result['warning']:
                        self.skipTest('Navegação bloqueada pelo Chromium deste ambiente; testar localStorage no Windows.')
                    page1 = mgr.contexts[p1['id']].pages[0]
                    page1.evaluate("localStorage.setItem('owner', 'first')")
                    mgr.start(p2['id'])
                    page2 = mgr.contexts[p2['id']].pages[0]
                    self.assertIsNone(page2.evaluate("localStorage.getItem('owner')"))
                    page2.evaluate("localStorage.setItem('owner', 'second')")
                    mgr.stop(p1['id'])
                    mgr.start(p1['id'])
                    page1 = mgr.contexts[p1['id']].pages[0]
                    self.assertEqual(page1.evaluate("localStorage.getItem('owner')"), 'first')
                    self.assertEqual(page2.evaluate("localStorage.getItem('owner')"), 'second')
                finally:
                    mgr.stop_all()
        finally:
            fixture.shutdown()
            fixture.server_close()


if __name__ == '__main__':
    unittest.main()
