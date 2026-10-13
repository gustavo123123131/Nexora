"""Nexora Vercel: authenticated serverless API for sites and profile metadata.

Vercel CANNOT host the existing persistent interactive Chromium sessions.
No button claims to start a browser in this deployment.
"""
import hashlib
import hmac
import os

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
    if request.path == '/api/health':
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
