"""Selected-profile session and window coordination for localhost Chromium.

Inspired by the public *interfaces* of ProxyBet's session:start,
session:stop and screens:*, not copied from its protected implementation.
Existing Playwright mobile emulation, profile directories and cookies remain
owned by BrowserManager. Never copy credentials between profiles.
"""
import math
import os
import re

PROFILE_ID = re.compile(r'^[0-9a-f]{32}$')
MAX_SELECTION = 12


def _validated_ids(ids, store):
    if (not isinstance(ids, list) or not 1 <= len(ids) <= MAX_SELECTION
            or any(not isinstance(item, str) or not PROFILE_ID.fullmatch(item)
                   for item in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError('Selecione entre 1 e 12 perfis diferentes e válidos.')
    known = {profile['id'] for profile in store.profiles}
    if any(item not in known for item in ids):
        raise ValueError('Um ou mais perfis selecionados não existem.')
    return ids


def _desktop_work_area():
    """Return Windows primary monitor usable area; do not guess window metrics."""
    if os.name != 'nt':
        raise ValueError('Organização de janelas disponível somente no Windows.')
    import ctypes
    from ctypes import wintypes

    area = wintypes.RECT()
    if ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(area), 0):
        return (area.left, area.top, area.right - area.left,
                area.bottom - area.top)
    raise OSError('O Windows não informou a área útil do monitor.')


class MultiLoginController:
    def __init__(self, manager):
        self.manager = manager
        self.store = manager.store

    def start_selected(self, ids):
        ids = _validated_ids(ids, self.store)
        started, already_open, failures = [], [], {}
        for profile_id in ids:
            try:
                result = self.manager.start(profile_id)
                if result.get('already_open'):
                    already_open.append(profile_id)
                else:
                    started.append(profile_id)
            except Exception as exc:
                # Do not emit navigation URLs, cookies or exception arguments.
                failures[profile_id] = type(exc).__name__
                if isinstance(exc, ValueError):
                    # The session cap is expected; stop trying after it hits.
                    if 'Limite de' in str(exc):
                        break
        processed = set(started + already_open) | set(failures)
        return {
            'started': started,
            'already_open': already_open,
            'errors': failures,
            'not_attempted': [pid for pid in ids if pid not in processed],
        }

    def stop_selected(self, ids):
        ids = _validated_ids(ids, self.store)
        stopped, already_stopped, failures = [], [], {}
        for profile_id in ids:
            try:
                if self.manager.stop(profile_id):
                    stopped.append(profile_id)
                else:
                    already_stopped.append(profile_id)
            except Exception as exc:
                failures[profile_id] = type(exc).__name__
        return {
            'stopped': stopped,
            'already_stopped': already_stopped,
            'errors': failures,
        }

    def arrange_selected(self, ids, columns=None, *, work_area=None):
        """Arrange native Chromium windows, keeping mobile viewports unchanged.

        Browser.* Chrome DevTools Protocol calls affect window bounds only:
        no JS injection, device identity changes or network interception.
        """
        ids = _validated_ids(ids, self.store)
        if columns is not None and (type(columns) is not int or not 1 <= columns <= 4):
            raise ValueError('Número de colunas precisa estar entre 1 e 4.')
        running = [pid for pid in ids if self.manager.is_running(pid)]
        if not running:
            raise ValueError('Abra os navegadores selecionados antes de organizá-los.')
        if getattr(self.manager, 'headless', False):
            raise ValueError('Organização de janelas exige Chromium com interface visual.')
        x, y, width, height = _desktop_work_area() if work_area is None else work_area
        if (not all(type(n) is int for n in (x, y, width, height))
                or width < 420 or height < 520):
            raise ValueError('Área da tela inválida ou insuficiente.')
        col_count = columns or min(len(running), 3)
        row_count = math.ceil(len(running) / col_count)
        tile_width = width // col_count
        tile_height = height // row_count
        if tile_width < 300 or tile_height < 300:
            raise ValueError('Não há espaço suficiente para organizar as janelas.')
        arranged, errors = [], {}
        for index, pid in enumerate(running):
            context = self.manager.contexts[pid]
            session = None
            try:
                page = next((p for p in context.pages if not p.is_closed()), None)
                if page is None:
                    raise ValueError('Esse perfil não possui uma janela aberta.')
                session = context.new_cdp_session(page)
                window_id = session.send('Browser.getWindowForTarget')['windowId']
                left = x + (index % col_count) * tile_width
                top = y + (index // col_count) * tile_height
                bounds = {'left': left, 'top': top,
                          'width': tile_width, 'height': tile_height,
                          'windowState': 'normal'}
                session.send('Browser.setWindowBounds',
                             {'windowId': window_id, 'bounds': bounds})
                arranged.append(pid)
            except Exception as exc:
                errors[pid] = type(exc).__name__
            finally:
                if session is not None:
                    try:
                        session.detach()
                    except Exception:
                        pass
        return {
            'arranged': arranged,
            'not_running': [pid for pid in ids if pid not in running],
            'errors': errors,
            'columns': col_count,
        }
