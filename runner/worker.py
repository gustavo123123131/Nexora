"""Nexora remote Chromium worker for Linux containers OR Windows via Cloudflare.

All browser state is isolated under NEXORA_PROFILE_DIR/<profile-id>.
Remote control uses a high-entropy secret; never commit it to GitHub.
"""
import hmac
import json
import ipaddress
import locale
import os
import queue
import re
import threading
import time
from concurrent.futures import Future
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, Response, jsonify, request
from playwright.sync_api import sync_playwright, Error as PlaywrightError

app = Flask(__name__)
ID_RE = re.compile(r'^[0-9a-f]{32}$')
KEYS = {'Enter', 'Tab', 'Backspace', 'Escape', 'ArrowUp', 'ArrowDown',
        'ArrowLeft', 'ArrowRight', 'Home', 'End', 'Delete', 'ControlOrMeta+A'}
STORE = Path(os.environ.get('NEXORA_PROFILE_DIR', str(Path(__file__).resolve().parent / 'data' / 'profiles') if os.name == 'nt' else '/data/profiles'))
MAX_PROFILES = max(1, min(6, int(os.environ.get('NEXORA_MAX_PROFILES', '3'))))
# On Windows, this process belongs to the signed-in user's desktop session.
# The Linux xvfb test can explicitly opt into headed mode.
DESKTOP_MODE = os.name == 'nt' or os.environ.get('NEXORA_DESKTOP_MODE') == '1'
AUTOSAVE_SECONDS = 3



def valid_id(value):
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ValueError('ID de perfil inválido.')
    return value


def valid_url(value):
    if not isinstance(value, str) or not 8 <= len(value) <= 2048 or any(ord(c) < 33 for c in value):
        raise ValueError('URL inválida.')
    p = urlsplit(value)
    try:
        _port = p.port
    except ValueError:
        raise ValueError('Porta inválida.')
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('A URL deve ser HTTP(S), sem credenciais.')
    host = p.hostname.lower().rstrip('.')
    if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
        raise ValueError('Endereço local não permitido.')
    try:
        if not ipaddress.ip_address(host).is_global:
            raise ValueError('IP privado ou reservado não permitido.')
    except ValueError as exc:
        if 'não permitido' in str(exc):
            raise
    return value


def host_browser_locale():
    """Resolve the real user's OS language (BCP47), never impersonate a locale.

    Playwright otherwise may omit Accept-Language while navigator.language is
    still populated, so we explicitly pass the OS value to keep both aligned.
    """
    if os.name == 'nt':
        import ctypes
        buffer = ctypes.create_unicode_buffer(85)
        if ctypes.windll.kernel32.GetUserDefaultLocaleName(buffer, len(buffer)):
            language = buffer.value
            if re.fullmatch(r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', language):
                return language
    try:
        language = locale.getlocale()[0]
    except (ValueError, TypeError):
        language = None
    if language:
        language = language.replace('_', '-')
        if re.fullmatch(r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', language):
            return language
    # If the OS reports only C/POSIX, Chromium defaults to en-US in its JS
    # environment; explicitly use that same browser default for HTTP headers.
    return 'en-US'


def chromium_launch_options(pw):
    """Preserve the actual Pixel 7 Playwright device profile in both modes."""
    device = pw.devices['Pixel 7']
    options = {key: value for key, value in device.items()
               if key != 'default_browser_type'}
    # Use the actual OS language so navigator.language and Accept-Language
    # agree. Do not force a different geographic timezone or impersonate Android
    # hardware: emulation is still Chromium on the host operating system.
    # The outer OS window needs room for the device viewport AND browser UI.
    viewport = device['viewport']
    outer_width = viewport['width'] + 150
    outer_height = viewport['height'] + 155
    window_size = f'--window-size={outer_width},{outer_height}'
    args = [] if os.name == 'nt' else ['--no-sandbox', '--disable-dev-shm-usage']
    if DESKTOP_MODE:
        args.append(window_size)
    options.update(
        headless=not DESKTOP_MODE,
        accept_downloads=DESKTOP_MODE,
        args=args,
    )
    language = host_browser_locale()
    if language:
        options['locale'] = language
    return options


class BrowserWorker:
    """All Playwright calls run on ONE dedicated Python thread."""
    def __init__(self):
        self.jobs = queue.Queue()
        self.contexts = {}
        self.cookie_backups = {}
        self.thread = threading.Thread(target=self._serve, daemon=True, name='playwright-worker')
        self.thread.start()

    def _serve(self):
        playwright = None
        try:
            next_backup = time.monotonic() + AUTOSAVE_SECONDS
            while True:
                try:
                    func, args, future = self.jobs.get(timeout=1)
                except queue.Empty:
                    func = None
                if func is not None and not future.cancelled():
                    try:
                        if playwright is None:
                            playwright = sync_playwright().start()
                        value = getattr(self, func)(playwright, *args)
                        future.set_result(value)
                    except BaseException as exc:
                        future.set_exception(exc)
                if playwright is not None and time.monotonic() >= next_backup:
                    # In native Windows mode there is NO screenshot polling:
                    # save session cookies periodically while users browse
                    # directly in visible Chromium windows.
                    self._autosave()
                    next_backup = time.monotonic() + AUTOSAVE_SECONDS
        finally:
            for context in self.contexts.values():
                try:
                    context.close()
                except Exception:
                    pass
            if playwright:
                playwright.stop()

    def _autosave(self):
        for pid, context in list(self.contexts.items()):
            try:
                self._save_cookies(context, pid)
            except PlaywrightError:
                # Closing a native window manually can close its context.
                self.contexts.pop(pid, None)
                self.cookie_backups.pop(pid, None)
            except (OSError, ValueError) as exc:
                app.logger.warning('Nao foi possivel salvar cookies do perfil %s: %s', pid, exc)

    def run(self, func, *args):
        future = Future()
        self.jobs.put((func, args, future))
        return future.result(timeout=30)

    def page(self, pid):
        context = self.contexts.get(pid)
        if context is None:
            raise LookupError('Perfil parado. Clique em Abrir.')
        if context.pages:
            pages = [p for p in context.pages if not p.is_closed()]
            if pages:
                return pages[-1]
        return context.new_page()

    def status(self, pw, pid):
        context = self.contexts.get(pid)
        if context is None:
            return {'running': False}
        try:
            context.cookies()
            return {'running': True}
        except PlaywrightError:
            self.contexts.pop(pid, None)
            return {'running': False}

    def _cookie_path(self, pid):
        return STORE / pid / '.nexora-session-cookies.json'

    def _save_cookies(self, context, pid):
        """Persist session cookies as well as persistent cookies, atomically.
        A context's session cookies can otherwise disappear on browser restart.
        """
        encoded = json.dumps(context.cookies(), ensure_ascii=False, sort_keys=True).encode('utf-8')
        if self.cookie_backups.get(pid) == encoded:
            return
        target = self._cookie_path(pid)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name('.nexora-session-cookies.tmp')
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, target)
            os.chmod(target, 0o600)
            self.cookie_backups[pid] = encoded
        finally:
            if temp.exists():
                temp.unlink()

    def _restore_cookies(self, context, pid):
        path = self._cookie_path(pid)
        if not path.exists():
            return
        cookies = json.loads(path.read_text('utf-8'))
        if not isinstance(cookies, list):
            raise ValueError('Backup de cookies inválido.')
        prepared = []
        for item in cookies:
            if not isinstance(item, dict):
                raise ValueError('Cookie inválido no backup.')
            cookie = dict(item)
            if cookie.get('expires', 0) <= 0:
                cookie.pop('expires', None)  # Restore as session cookie.
            prepared.append(cookie)
        if prepared:
            context.add_cookies(prepared)
        self.cookie_backups[pid] = json.dumps(cookies, ensure_ascii=False,
                                             sort_keys=True).encode('utf-8')

    def start(self, pw, pid, url):
        if self.status(pw, pid)['running']:
            return {'running': True, 'already_open': True, 'desktop': DESKTOP_MODE}
        if len(self.contexts) >= MAX_PROFILES:
            raise ValueError(f'Limite de {MAX_PROFILES} navegadores simultâneos.')
        STORE.mkdir(parents=True, exist_ok=True)
        profile_dir = STORE / pid
        profile_dir.mkdir(exist_ok=True)
        opts = chromium_launch_options(pw)
        context = pw.chromium.launch_persistent_context(str(profile_dir), **opts)
        self.contexts[pid] = context
        try:
            self._restore_cookies(context, pid)
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(8000)
            page.goto(url, wait_until='domcontentloaded', timeout=12000)
            if DESKTOP_MODE:
                page.bring_to_front()
            return {'running': True, 'already_open': False, 'desktop': DESKTOP_MODE}
        except PlaywrightError:
            # A failed navigation must not discard the browser / persistent data.
            return {'running': True, 'already_open': False, 'desktop': DESKTOP_MODE,
                    'warning': 'Janela iniciada, mas o site não terminou de carregar.'}
        except Exception:
            try:
                context.close()
            finally:
                self.contexts.pop(pid, None)
            raise

    def _cookie_names_for_test(self, pw, pid):
        """Internal smoke-test helper; never exposed as an HTTP route."""
        context = self.contexts[pid]
        return [item['name'] for item in context.cookies()]

    def _page_url_for_test(self, pw, pid):
        """Read a headed Chromium page over Playwright, no screenshot."""
        page = self.page(pid)
        return {'url': page.url, 'input_count': page.locator('input').count()}

    def stop(self, pw, pid):
        context = self.contexts.get(pid)
        if context is None:
            return {'running': False}
        # If cookie backup fails, leave the browser running rather than
        # silently discarding the session.
        self._save_cookies(context, pid)
        context.close()
        self.contexts.pop(pid, None)
        self.cookie_backups.pop(pid, None)
        return {'running': False}

    def frame(self, pw, pid):
        screenshot = self.page(pid).screenshot(type='jpeg', quality=68, timeout=8000,
                                              animations='disabled', scale='css')
        self._save_cookies(self.contexts[pid], pid)
        return screenshot

    def act(self, pw, pid, data):
        page = self.page(pid)
        kind = data.get('type')
        if kind == 'click':
            x, y = data.get('x'), data.get('y')
            if not isinstance(x, (int, float)) or not isinstance(y, (int, float)) or not 0 <= x <= 500 or not 0 <= y <= 1200:
                raise ValueError('Coordenadas inválidas.')
            page.mouse.click(x, y)
        elif kind == 'type':
            content = data.get('text')
            if not isinstance(content, str) or len(content) > 2048:
                raise ValueError('Texto inválido.')
            page.keyboard.insert_text(content)
        elif kind == 'key':
            key = data.get('key')
            if key not in KEYS:
                raise ValueError('Tecla não permitida.')
            page.keyboard.press(key)
        elif kind == 'scroll':
            delta = data.get('delta')
            if not isinstance(delta, int) or abs(delta) > 900:
                raise ValueError('Rolagem inválida.')
            page.mouse.wheel(0, delta)
        elif kind == 'back':
            page.go_back(wait_until='domcontentloaded', timeout=8000)
        elif kind == 'reload':
            page.reload(wait_until='domcontentloaded', timeout=8000)
        else:
            raise ValueError('Ação desconhecida.')
        return {'ok': True}


worker = BrowserWorker()


PANEL_ORIGIN = os.environ.get('NEXORA_PANEL_ORIGIN', 'https://nexora-ebon-eight.vercel.app').rstrip('/')


@app.before_request
def security():
    # The Vercel frontend can call a temporary Cloudflare Tunnel directly,
    # so its changing URL never needs to be entered into Vercel env vars.
    # Only the exact trusted panel origin receives browser CORS permission.
    origin = request.headers.get('Origin', '')
    if request.method == 'OPTIONS':
        if origin != PANEL_ORIGIN:
            return jsonify(error='Origem não autorizada.'), 403
        return app.response_class(status=204)
    if origin and origin != PANEL_ORIGIN:
        return jsonify(error='Origem não autorizada.'), 403
    if request.path == '/healthz':
        return None
    secret = os.environ.get('NEXORA_RUNNER_KEY', '')
    if len(secret) < 32:
        return jsonify(error='Configure NEXORA_RUNNER_KEY (32+ caracteres) no executor.'), 503
    provided = request.headers.get('Authorization', '')
    if not provided.startswith('Bearer ') or not hmac.compare_digest(provided[7:], secret):
        return jsonify(error='Chave de executor inválida.'), 401
    if request.method == 'POST' and (request.mimetype != 'application/json'
                                      or (request.content_length or 0) > 8192):
        return jsonify(error='Requisição inválida.'), 415


@app.after_request
def headers(response):
    if request.headers.get('Origin') == PANEL_ORIGIN:
        response.headers['Access-Control-Allow-Origin'] = PANEL_ORIGIN
        response.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Max-Age'] = '600'
        response.headers['Vary'] = 'Origin'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@app.get('/healthz')
def public_health():
    return jsonify(healthy=True)


@app.get('/v1/health')
def health():
    return jsonify(ok=True, browser=True, mode='remote', desktop=DESKTOP_MODE,
                   device='Pixel 7', max_profiles=MAX_PROFILES)


@app.get('/v1/status/<pid>')
def status(pid):
    try:
        return jsonify(worker.run('status', valid_id(pid)))
    except Exception:
        return jsonify(error='Não foi possível verificar o perfil.'), 503


@app.post('/v1/start')
def start():
    try:
        data = request.get_json()
        return jsonify(worker.run('start', valid_id(data.get('id')), valid_url(data.get('url'))))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except Exception:
        app.logger.exception('Falha ao iniciar Chromium')
        return jsonify(error='Falha ao abrir Chromium no executor. Verifique o serviço.'), 503


@app.post('/v1/stop')
def stop():
    try:
        data = request.get_json()
        return jsonify(worker.run('stop', valid_id(data.get('id'))))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except Exception:
        return jsonify(error='Falha ao encerrar perfil.'), 503


@app.get('/v1/frame/<pid>')
def frame(pid):
    try:
        shot = worker.run('frame', valid_id(pid))
        return Response(shot, content_type='image/jpeg')
    except (LookupError, ValueError) as exc:
        return jsonify(error=str(exc)), 404
    except Exception:
        return jsonify(error='Não foi possível capturar navegador.'), 503


@app.post('/v1/act')
def act():
    try:
        data = request.get_json()
        if not isinstance(data, dict):
            raise ValueError('Ação inválida.')
        return jsonify(worker.run('act', valid_id(data.get('id')), data))
    except (LookupError, ValueError) as exc:
        return jsonify(error=str(exc)), 400
    except Exception:
        return jsonify(error='Não foi possível interagir com navegador.'), 503


if __name__ == '__main__':
    port = int(os.environ.get('PORT', '8080'))
    app.run(host=os.environ.get('NEXORA_BIND', '127.0.0.1'), port=port, threaded=True)
