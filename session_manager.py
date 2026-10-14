"""Runtime session state for the localhost Chromium launcher.

This registry only reports verified browser state. Registrations are never
capped; MULTILOGIN_MAX_OPEN bounds the number of concurrent native contexts.
"""
import os
from datetime import datetime, timezone


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class SessionManager:
    def __init__(self, max_open=None):
        raw = os.environ.get('MULTILOGIN_MAX_OPEN', '6') if max_open is None else max_open
        try:
            selected = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError('MULTILOGIN_MAX_OPEN precisa ser um número inteiro.') from exc
        self.max_open = max(1, min(12, selected))
        self.states = {}
        self.started_at = {}
        self.last_error = {}

    def begin(self, profile_id, current_running):
        if current_running >= self.max_open:
            raise ValueError(f'Limite de {self.max_open} navegadores simultâneos. Encerre um perfil antes de iniciar outro.')
        if self.states.get(profile_id) in ('starting', 'stopping'):
            raise ValueError('Operação de sessão já em andamento.')
        self.states[profile_id] = 'starting'
        self.last_error.pop(profile_id, None)

    def running(self, profile_id):
        self.states[profile_id] = 'running'
        self.started_at[profile_id] = _utc_now()
        self.last_error.pop(profile_id, None)

    def stopping(self, profile_id):
        self.states[profile_id] = 'stopping'

    def stopped(self, profile_id):
        self.states[profile_id] = 'stopped'
        self.started_at.pop(profile_id, None)

    def error(self, profile_id, error):
        self.states[profile_id] = 'error'
        self.started_at.pop(profile_id, None)
        # Record only the exception type, never URLs, cookies or credentials.
        self.last_error[profile_id] = type(error).__name__

    def describe(self, profile_id, is_running):
        if is_running:
            state = 'running'
        elif self.states.get(profile_id) == 'error':
            state = 'error'
        else:
            state = 'stopped'
        return {
            'id': profile_id,
            'status': state,
            'started_at': self.started_at.get(profile_id) if is_running else None,
            'last_error_type': self.last_error.get(profile_id) if state == 'error' else None,
        }
