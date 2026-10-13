"""Nexora Vercel: authenticated serverless API for sites and profile metadata.

Vercel CANNOT host the existing persistent interactive Chromium sessions.
No button claims to start a browser in this deployment.
"""
import hashlib
import hmac
import os
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from flask import Flask, jsonify, make_response, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from cloud_store import CloudStore

app = Flask(__name__, static_folder=None)
SESSION_COOKIE = 'nexora_session'
SESSION_SECONDS = 8 * 60 * 60


def _config():
    password = os.environ.get('NEXORA_ACCESS_PASSWORD', '')
    secret = os.environ.get('NEXORA_SESSION_SECRET', '')
    # Fail closed. No embedded/default credentials in a public deployment.
    if len(password) < 12 or len(secret) < 32 or not (os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_URL')):
        return None
    return password, secret


def _serializer():
    password, secret = _config()
    derived = hmac.new(secret.encode(), password.encode(), hashlib.sha256).hexdigest()
    return URLSafeTimedSerializer(derived, salt='nexora-browser-metadata-v1')


def _logged_in():
    if _config() is None:
        return False
    value = request.cookies.get(SESSION_COOKIE, '')
    if not value:
        return False
    try:
        return _serializer().loads(value, max_age=SESSION_SECONDS) == {'v': 1}
    except (BadSignature, SignatureExpired):
        return False


def _reply(payload, status=200):
    return jsonify(payload), status


@app.after_request
def headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'DENY'
    return response


@app.before_request
def guard():
    if not request.path.startswith('/api/'):
        return _reply({'error': 'Rota não encontrada.'}, 404)
    if request.method not in ('GET', 'POST'):
        return _reply({'error': 'Método não permitido.'}, 405)
    # Browser always sends Origin for fetch() POST. Reject cross-site posts,
    # missing Origin and forged requests regardless of signed cookie.
    if request.method == 'POST':
        origin = request.headers.get('Origin', '')
        if not origin or origin not in ('https://' + request.host, 'http://' + request.host):
            return _reply({'error': 'Origem não autorizada.'}, 403)
        if request.mimetype != 'application/json':
            return _reply({'error': 'Envie JSON.'}, 415)
        size = request.content_length
        limit = 256 * 1024 if request.path == '/api/import' else 8192
        if size is None or size > limit or size < 0:
            return _reply({'error': 'Conteúdo inválido ou muito grande.'}, 413)
    if request.path == '/api/health' or request.path.startswith('/api/runner/'):
        # Remote runner has its OWN high-entropy authorization key. No password
        # for localStorage-only profile metadata.
        return None
    if _config() is None:
        return _reply({'error': 'Configure DATABASE_URL, NEXORA_ACCESS_PASSWORD (12+ caracteres) e NEXORA_SESSION_SECRET (32+ caracteres) na Vercel.'}, 503)
    if request.path in ('/api/auth/status', '/api/auth/login'):
        return None
    if not _logged_in():
        return _reply({'error': 'Faça login para acessar o Nexora.'}, 401)


@app.get('/api/health')
def health():
    return _reply({'ok': True, 'configured': _config() is not None, 'browser': 'unavailable'})


@app.get('/api/auth/status')
def auth_status():
    return _reply({'authenticated': _logged_in(), 'mode': 'vercel'})


@app.post('/api/auth/login')
def auth_login():
    body = request.get_json(silent=True) or {}
    candidate = body.get('password', '') if isinstance(body, dict) else ''
    if not isinstance(candidate, str) or not hmac.compare_digest(candidate, _config()[0]):
        return _reply({'error': 'Senha incorreta.'}, 401)
    response = make_response(jsonify({'ok': True}))
    response.set_cookie(SESSION_COOKIE, _serializer().dumps({'v': 1}), max_age=SESSION_SECONDS,
                        httponly=True, secure=True, samesite='Strict', path='/')
    return response


@app.post('/api/auth/logout')
def auth_logout():
    response = make_response(jsonify({'ok': True}))
    response.delete_cookie(SESSION_COOKIE, path='/', secure=True, samesite='Strict')
    return response


@app.route('/api/<path:route>', methods=['GET', 'POST'])
def api_route(route):
    if request.method == 'GET' and route != 'state':
        return _reply({'error': 'Rota não encontrada.'}, 404)
    if request.method == 'POST' and route == 'state':
        return _reply({'error': 'Método não permitido.'}, 405)
    if route in ('profiles/start', 'profiles/stop'):
        return _reply({'error': 'A Vercel não mantém navegadores Chromium persistentes. É necessário conectar um executor de navegadores externo.'}, 501)
    routes = {'sites/create', 'sites/update', 'sites/delete', 'profiles/create', 'profiles/delete', 'import'}
    if route != 'state' and (route not in routes or request.method != 'POST'):
        return _reply({'error': 'Rota não encontrada.'}, 404)
    body = request.get_json(silent=True) if request.method == 'POST' else {}
    if not isinstance(body, dict):
        return _reply({'error': 'Formato JSON inválido.'}, 400)
    try:
        factory = app.config.get('STORE_FACTORY', CloudStore)
        with factory() as store:
            if route == 'state':
                result = store.state()
            elif route == 'sites/create':
                result = store.create_site(body.get('name'), body.get('url'))
            elif route == 'sites/update':
                result = store.update_site(body.get('id'), body.get('name'), body.get('url'))
            elif route == 'sites/delete':
                result = store.delete_site(body.get('id'))
            elif route == 'profiles/create':
                result = store.create_profile(body.get('name'), body.get('site_id'))
            elif route == 'profiles/delete':
                result = store.delete_profile(body.get('id'))
            else:
                result = store.import_settings(body)
        return _reply(result)
    except (ValueError, LookupError, TypeError) as exc:
        return _reply({'error': str(exc)}, 400)
    except Exception:
        # Do not expose database URLs, credentials or connection errors to the client.
        app.logger.exception('Nexora cloud data operation failed')
        return _reply({'error': 'Falha no banco de dados. Verifique a configuração e os logs da Vercel.'}, 503)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@app.route('/api/runner/<path:route>', methods=['GET', 'POST'])
def remote_runner(route):
    """Vercel HTTPS proxy; no CORS and no secret embedded in frontend code.

    Never allow arbitrary URLs or redirects: this holds session credentials.
    """
    base = os.environ.get('NEXORA_RUNNER_URL', '').rstrip('/')
    if route == 'config':
        return _reply({'configured': _valid_runner_base(base)})
    if not _valid_runner_base(base):
        return _reply({'error': 'Configure NEXORA_RUNNER_URL na Vercel para conectar o executor Chromium.'}, 503)
    allowed_get = route == 'health' or bool(re.fullmatch(r'(status|frame)/[0-9a-f]{32}', route))
    allowed_post = route in ('start', 'stop', 'act')
    if not (allowed_get if request.method == 'GET' else allowed_post):
        return _reply({'error': 'Operação do executor não encontrada.'}, 404)
    token = request.headers.get('Authorization', '')
    if not re.fullmatch(r'Bearer [A-Za-z0-9_\-!@#$%^&*+=:.]{32,256}', token):
        return _reply({'error': 'Conecte a chave privada do executor antes de abrir perfis.'}, 401)
    headers = {'Authorization': token, 'Accept': 'application/json, image/jpeg'}
    body = request.get_data() if request.method == 'POST' else None
    if body is not None:
        headers['Content-Type'] = 'application/json'
    upstream = urllib.request.Request(base + '/v1/' + route, data=body, headers=headers,
                                      method=request.method)
    try:
        response = urllib.request.build_opener(_NoRedirect()).open(upstream, timeout=18)
        with response:
            content = response.read(1500001)
            if len(content) > 1500000:
                return _reply({'error': 'Resposta do executor acima do limite.'}, 502)
            mime = response.headers.get('Content-Type', 'application/json')
            if not mime.startswith(('application/json', 'image/jpeg')):
                return _reply({'error': 'Resposta inesperada do executor.'}, 502)
            return app.response_class(content, status=response.status, content_type=mime)
    except urllib.error.HTTPError as exc:
        try:
            message = exc.read(8192).decode('utf-8')
            import json
            payload = json.loads(message)
            error = str(payload.get('error', 'Erro do executor.'))[:300]
        except Exception:
            error = 'Falha na comunicação com executor.'
        return _reply({'error': error}, exc.code if 400 <= exc.code < 600 else 502)
    except (urllib.error.URLError, TimeoutError, OSError):
        return _reply({'error': 'Executor indisponível. Confira o deploy no Railway.'}, 503)


def _valid_runner_base(value):
    try:
        parsed = urlsplit(value)
        return (parsed.scheme == 'https' and bool(parsed.hostname)
                and not parsed.username and not parsed.password
                and not parsed.path.strip('/') and not parsed.query and not parsed.fragment)
    except ValueError:
        return False
