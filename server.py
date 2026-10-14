"""Painel local HTTP; sem serviços externos e sem dependências web."""
import json
import os
import re
import signal
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from storage import Store
from browser_manager import BrowserManager
from device_profile_manager import DeviceProfileManager

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / 'public'
DATA = Path(os.environ.get('MULTILOGIN_DATA_DIR', str(ROOT / 'data')))
PORT = int(os.environ.get('MULTILOGIN_PORT', '3000'))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Não registra corpo, cookies nem URLs de navegação em logs.
        if os.environ.get('MULTILOGIN_VERBOSE') == '1':
            super().log_message(fmt, *args)

    def headers_common(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")

    def send_json(self, code, data):
        payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.headers_common()
        self.end_headers()
        self.wfile.write(payload)

    def valid_host(self):
        return self.headers.get('Host', '') in (
            f'127.0.0.1:{PORT}', f'localhost:{PORT}'
        )

    def do_GET(self):
        if not self.valid_host():
            return self.send_json(403, {'error': 'Host não autorizado.'})
        route = urlsplit(self.path).path
        if route == '/api/state':
            statuses = self.server.manager.status()
            return self.send_json(200, {
                'sites': self.server.store.sites,
                'profiles': [{
                    **{k: v for k, v in profile.items() if k != 'fingerprint'},
                    'device': profile.get('device', 'Pixel 7'),
                    'fingerprint_version': profile.get('fingerprint', {}).get('version'),
                    'status': statuses.get(profile['id'], 'stopped')
                } for profile in self.server.store.profiles]
            })
        if route == '/api/sessions':
            return self.send_json(200, {
                'sessions': self.server.manager.session_details(),
                'max_simultaneous': self.server.manager.sessions.max_open
            })
        export_match = re.fullmatch(r'/api/profiles/export/([0-9a-f]{32})', route)
        if export_match:
            try:
                return self.send_json(200, self.server.device_profiles.export_configuration(export_match.group(1)))
            except (ValueError, LookupError) as exc:
                return self.send_json(400, {'error': str(exc)})
        match = re.fullmatch(r'/api/profiles/inspect/([0-9a-f]{32})', route)
        if match:
            try:
                return self.send_json(200, self.server.manager.inspect(match.group(1)))
            except (ValueError, LookupError) as exc:
                return self.send_json(400, {'error': str(exc)})
            except Exception as exc:
                print(f'[fingerprint-inspect] {type(exc).__name__}', file=sys.stderr)
                return self.send_json(503, {'error': 'Não foi possível ler o navegador.'})
        files = {'/': ('index.html', 'text/html; charset=utf-8'),
                 '/app.js': ('app.js', 'application/javascript; charset=utf-8'),
                 '/local_store.js': ('local_store.js', 'application/javascript; charset=utf-8'),
                 '/remote_browser.js': ('remote_browser.js', 'application/javascript; charset=utf-8'),
                 '/device_catalog.json': ('device_catalog.json', 'application/json; charset=utf-8'),
                 '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if route not in files:
            return self.send_json(404, {'error': 'Não encontrado.'})
        name, content_type = files[route]
        payload = (PUBLIC / name).read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.headers_common()
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        if not self.valid_host():
            return self.send_json(403, {'error': 'Host não autorizado.'})
        origin = self.headers.get('Origin', '')
        if origin not in (f'http://127.0.0.1:{PORT}', f'http://localhost:{PORT}'):
            return self.send_json(403, {'error': 'Origem não autorizada.'})
        if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
            return self.send_json(415, {'error': 'Envie JSON.'})
        try:
            size = int(self.headers.get('Content-Length', '-1'))
            if not 0 <= size <= 8192:
                return self.send_json(413, {'error': 'Conteúdo inválido ou muito grande.'})
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError('Formato inválido.')
            route = urlsplit(self.path).path
            store = self.server.store
            manager = self.server.manager
            if route == '/api/sites/create':
                data = store.create_site(body.get('name'), body.get('url'))
            elif route == '/api/sites/update':
                data = store.update_site(body.get('id'), body.get('name'), body.get('url'))
            elif route == '/api/sites/delete':
                store.delete_site(body.get('id'))
                data = {'ok': True}
            elif route == '/api/profiles/create':
                data = self.server.device_profiles.create(
                    body.get('name'), body.get('site_id'), body.get('device'))
            elif route == '/api/profiles/update':
                data = self.server.device_profiles.update(
                    body.get('id'), body.get('name'), body.get('site_id'), body.get('device'))
            elif route == '/api/profiles/duplicate':
                data = self.server.device_profiles.duplicate_configuration(body.get('id'))
            elif route == '/api/profiles/import-config':
                data = self.server.device_profiles.import_configuration(body.get('configuration'))
            elif route == '/api/profiles/regenerate':
                data = self.server.device_profiles.regenerate(
                    body.get('id'), confirmed=body.get('confirmed') is True)
            elif route == '/api/profiles/delete':
                self.server.device_profiles.delete(body.get('id'))
                data = {'ok': True}
            elif route == '/api/profiles/start':
                data = manager.start(body.get('id'))
            elif route == '/api/profiles/stop':
                data = {'stopped': manager.stop(body.get('id'))}
            else:
                return self.send_json(404, {'error': 'Operação não encontrada.'})
            return self.send_json(200, data)
        except (ValueError, LookupError, TypeError) as ex:
            return self.send_json(400, {'error': str(ex)})
        except Exception as ex:
            # Não mostra stack traces, caminhos internos ou credenciais no navegador.
            print(f'[erro interno] {type(ex).__name__}: {ex}', file=sys.stderr)
            return self.send_json(500, {'error': 'Não foi possível concluir a operação. Consulte o terminal.'})


class LocalServer(HTTPServer):
    allow_reuse_address = True

    def __init__(self, port=PORT, data_dir=DATA, manager=None):
        super().__init__(('127.0.0.1', port), Handler)
        self.store = Store(data_dir)
        self.manager = manager if manager is not None else BrowserManager(self.store)
        self.device_profiles = DeviceProfileManager(self.store, self.manager)


def main():
    server = LocalServer()
    print('\n' + '=' * 52)
    print(' MULTILOGIN MOBILE  |  Painel local')
    print(f' Acesse: http://127.0.0.1:{PORT}')
    print(' Use Ctrl+C para encerrar e fechar os perfis.')
    print('=' * 52 + '\n', flush=True)
    if os.environ.get('MULTILOGIN_NO_OPEN') != '1':
        threading.Timer(0.9, lambda: webbrowser.open(f'http://127.0.0.1:{PORT}')).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        print('Encerrando navegadores...', flush=True)
        server.manager.stop_all()
        server.server_close()


if __name__ == '__main__':
    main()
