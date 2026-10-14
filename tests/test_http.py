import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class HttpTests(unittest.TestCase):
    def test_http_crud_origin_and_persistence(self):
        port = free_port()
        with tempfile.TemporaryDirectory() as folder:
            env = dict(os.environ, MULTILOGIN_PORT=str(port), MULTILOGIN_DATA_DIR=folder, MULTILOGIN_NO_OPEN='1')
            process = subprocess.Popen([sys.executable, str(ROOT / 'server.py')], env=env,
                                       cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            base = f'http://127.0.0.1:{port}'

            def req(path, body=None, origin=True):
                headers = {}
                if body is not None:
                    headers['Content-Type'] = 'application/json'
                    if origin:
                        headers['Origin'] = base
                request = urllib.request.Request(base + path,
                    data=json.dumps(body).encode('utf-8') if body is not None else None, headers=headers)
                with urllib.request.urlopen(request, timeout=4) as response:
                    return response.status, response.read(), response.headers

            try:
                for _ in range(35):
                    try:
                        req('/api/state')
                        break
                    except urllib.error.URLError:
                        time.sleep(.1)
                else:
                    self.fail('Servidor local não iniciou')
                code, page, headers = req('/')
                self.assertEqual(code, 200)
                self.assertIn(b'Nexora', page)
                self.assertIn('text/html', headers.get('Content-Type'))
                self.assertIn('application/javascript', req('/app.js')[2]['Content-Type'])
                self.assertIn('text/css', req('/style.css')[2]['Content-Type'])
                self.assertIn('application/javascript', req('/local_store.js')[2]['Content-Type'])
                catalog = json.loads(req('/device_catalog.json')[1])
                self.assertGreaterEqual(len(catalog['devices']), 40)
                self.assertIn('Galaxy S24', catalog['devices'])
                self.assertEqual(json.loads(req('/api/state')[1])['profiles'], [])
                with self.assertRaises(urllib.error.HTTPError) as error:
                    req('/api/sites/create', {'name':'Bloqueio','url':'https://example.com'}, origin=False)
                self.assertEqual(error.exception.code, 403)
                site = json.loads(req('/api/sites/create', {'name':'Teste','url':'https://example.com'})[1])
                profile = json.loads(req('/api/profiles/create', {'name':'Conta 1', 'site_id':site['id']})[1])
                initial_state = json.loads(req('/api/state')[1])
                self.assertEqual(initial_state['sites'][0]['name'], 'Teste')
                self.assertEqual(initial_state['profiles'][0]['status'], 'stopped')
                self.assertEqual(initial_state['profiles'][0]['device'], 'Pixel 7')
                sessions = json.loads(req('/api/sessions')[1])
                self.assertGreaterEqual(sessions['max_simultaneous'], 1)
                self.assertEqual(sessions['sessions'][0]['status'], 'stopped')
                # Selected-session endpoints are opt-in; they must not start
                # a browser for malformed ids or a layout-only request.
                with self.assertRaises(urllib.error.HTTPError) as error:
                    req('/api/sessions/start-selected', {'ids': [profile['id'], profile['id']]})
                self.assertEqual(error.exception.code, 400)
                with self.assertRaises(urllib.error.HTTPError) as error:
                    req('/api/windows/arrange-selected', {'ids': [profile['id']]})
                self.assertEqual(error.exception.code, 400)
                self.assertEqual(json.loads(req('/api/sessions/stop-selected',
                                              {'ids': [profile['id']]})[1])['already_stopped'],
                                 [profile['id']])
                changed = json.loads(req('/api/profiles/update', {
                    'id':profile['id'], 'name':'Conta Alterada',
                    'site_id':site['id'], 'device':'Galaxy S24'})[1])
                self.assertEqual(changed['device'], 'Galaxy S24')
                current = json.loads(req('/api/state')[1])['profiles'][0]
                self.assertEqual(current['device'], 'Galaxy S24')
                self.assertEqual(current['name'], 'Conta Alterada')
                self.assertEqual(current['fingerprint_version'], 1)
                inspection = json.loads(req('/api/profiles/inspect/' + profile['id'])[1])
                self.assertFalse(inspection['running'])
                self.assertIsNone(inspection['observed'])
                self.assertEqual(inspection['configured']['preset'], 'Galaxy S24')
                with self.assertRaises(urllib.error.HTTPError) as missing_confirmation:
                    req('/api/profiles/regenerate', {'id': profile['id']})
                self.assertEqual(missing_confirmation.exception.code, 400)
                cloned = json.loads(req('/api/profiles/duplicate', {'id': profile['id']})[1])
                self.assertNotEqual(cloned['id'], profile['id'])
                self.assertEqual(cloned['device'], 'Galaxy S24')
                self.assertFalse((Path(folder) / 'profiles' / cloned['id']).exists())
                exported = json.loads(req('/api/profiles/export/' + profile['id'])[1])
                self.assertEqual(exported['fingerprint']['preset'], 'Galaxy S24')
                self.assertTrue(all(key not in exported for key in ('cookies', 'password', 'localStorage', 'tokens')))
                imported = json.loads(req('/api/profiles/import-config', {
                    'configuration': exported})[1])
                self.assertNotEqual(imported['id'], profile['id'])
                self.assertEqual(imported['device'], 'Galaxy S24')
                self.assertFalse((Path(folder) / 'profiles' / imported['id']).exists())
                req('/api/profiles/delete', {'id':imported['id']})
                changed = json.loads(req('/api/profiles/regenerate', {
                    'id':profile['id'], 'confirmed':True})[1])
                self.assertEqual(changed['fingerprint']['reason'],
                                 'user-explicit-regeneration')
                req('/api/profiles/delete', {'id':cloned['id']})
                site = json.loads(req('/api/sites/update', {'id':site['id'],'name':'Novo nome', 'url':'https://example.org'})[1])
                self.assertEqual(site['name'], 'Novo nome')
                with self.assertRaises(urllib.error.HTTPError) as error:
                    req('/api/sites/delete', {'id':site['id']})
                self.assertEqual(error.exception.code, 400)
                req('/api/profiles/delete', {'id':profile['id']})
                req('/api/sites/delete', {'id':site['id']})
                self.assertEqual(json.loads(req('/api/state')[1])['sites'], [])
                self.assertEqual(json.loads(req('/api/state')[1])['profiles'], [])
            finally:
                process.terminate()
                try:
                    process.communicate(timeout=4)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()


if __name__ == '__main__':
    unittest.main()
