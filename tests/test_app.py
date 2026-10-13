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
