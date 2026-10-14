"""Persist native Chromium window bounds without changing mobile emulation.

Adapted conceptually from the window_bounds_by_idx + CDP getter in the
user-supplied LIXOCPA source; all code here is an independent implementation.

Only coordinates and native window size are saved. Playwright viewport,
touch support, device scale factor, UA, cookies and site content are untouched.
"""
import json
import os
import re
import threading
from pathlib import Path


_VALID_ID = re.compile(r'^[0-9a-f]{32}$')
_FIELDS = ('left', 'top', 'width', 'height')


class WindowLayoutManager:
    def __init__(self, root):
        self.path = Path(root) / 'window-layouts.json'
        self._lock = threading.Lock()

    @staticmethod
    def validate(profile_id, bounds):
        if not isinstance(profile_id, str) or not _VALID_ID.fullmatch(profile_id):
            raise ValueError('Identificador de perfil inválido.')
        if not isinstance(bounds, dict):
            raise ValueError('Posição de janela inválida.')
        if any(type(bounds.get(name)) is not int for name in _FIELDS):
            raise ValueError('Dimensões de janela inválidas.')
        result = {name: bounds[name] for name in _FIELDS}
        if not (-16000 <= result['left'] <= 16000
                and -16000 <= result['top'] <= 16000
                and 300 <= result['width'] <= 8192
                and 300 <= result['height'] <= 8192):
            raise ValueError('Janela fora dos limites permitidos.')
        return result

    def _read_unlocked(self):
        if not self.path.is_file():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            raise ValueError('Arquivo de posições danificado. Faça backup antes de corrigir.')
        if not isinstance(data, dict) or data.get('version') != 1:
            raise ValueError('Versão de posições de janela inválida.')
        layouts = data.get('profiles')
        if not isinstance(layouts, dict):
            raise ValueError('Arquivo de posições não contém perfis válidos.')
        return layouts

    def get(self, profile_id):
        if not _VALID_ID.fullmatch(str(profile_id)):
            raise ValueError('Identificador de perfil inválido.')
        with self._lock:
            record = self._read_unlocked().get(profile_id)
        if record is None:
            return None
        return self.validate(profile_id, record)

    def save(self, profile_id, bounds):
        clean = self.validate(profile_id, bounds)
        with self._lock:
            data = self._read_unlocked()
            data[profile_id] = clean
            self.path.parent.mkdir(parents=True, exist_ok=True)
            target = self.path.with_suffix('.tmp')
            encoded = json.dumps({'version': 1, 'profiles': data},
                                 ensure_ascii=False, indent=2).encode('utf-8')
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(target, self.path)
            finally:
                if target.exists():
                    target.unlink()
        return clean

    @staticmethod
    def read_window(context):
        """Query CDP for native window bounds; no page JS or fingerprint patch."""
        page = next((p for p in context.pages if not p.is_closed()), None)
        if page is None:
            raise ValueError('Nenhuma janela ativa para capturar.')
        session = context.new_cdp_session(page)
        try:
            try:
                info = session.send('Browser.getWindowForTarget', {})
            except Exception:
                target = session.send('Target.getTargetInfo', {})
                target_id = target.get('targetInfo', {}).get('targetId')
                if not target_id:
                    raise ValueError('O Chromium não informou o target da janela.')
                info = session.send('Browser.getWindowForTarget',
                                    {'targetId': target_id})
            return info.get('bounds', {})
        finally:
            try:
                session.detach()
            except Exception:
                pass

    @classmethod
    def apply_to_context(cls, context, bounds):
        page = next((p for p in context.pages if not p.is_closed()), None)
        if page is None:
            return False
        session = context.new_cdp_session(page)
        try:
            result = session.send('Browser.getWindowForTarget', {})
            session.send('Browser.setWindowBounds', {
                'windowId': result['windowId'],
                'bounds': dict(bounds, windowState='normal'),
            })
            return True
        finally:
            try:
                session.detach()
            except Exception:
                pass
