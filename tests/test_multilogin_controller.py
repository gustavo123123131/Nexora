"""ProxyBet-inspired native window and selected-session tests.

No real sites, credentials or user account files are used.
"""
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from storage import Store
from multilogin_controller import MultiLoginController


class FakeBrowserManager:
    def __init__(self, store, fail_id=None):
        self.store = store
        self.active = set()
        self.fail_id = fail_id
        self.headless = False
        self.contexts = {}

    def is_running(self, pid):
        return pid in self.active

    def start(self, pid):
        if pid == self.fail_id:
            raise RuntimeError('private: must not leak secret!')
        if pid in self.active:
            return {'already_open': True}
        self.active.add(pid)
        return {'already_open': False}

    def stop(self, pid):
        if pid not in self.active:
            return False
        self.active.remove(pid)
        return True


class MultiLoginControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        site = self.store.create_site('Teste', 'https://example.org/')
        self.profiles = [self.store.create_profile('Perfil ' + str(i), site['id'], 'Pixel 7')
                         for i in range(3)]
        self.ids = [item['id'] for item in self.profiles]
        self.manager = FakeBrowserManager(self.store)
        self.controller = MultiLoginController(self.manager)

    def test_separate_persistent_mobile_profiles_with_selected_start_stop(self):
        a, b, c = self.ids
        mobile_snapshot = self.store.profile(a)['fingerprint']
        result = self.controller.start_selected([a, b])
        self.assertEqual(result['started'], [a, b])
        self.assertEqual(result['errors'], {})
        self.assertEqual(self.controller.start_selected([a])['already_open'], [a])
        stop = self.controller.stop_selected([a, c])
        self.assertEqual(stop['stopped'], [a])
        self.assertEqual(stop['already_stopped'], [c])
        self.assertTrue(self.manager.is_running(b))
        # Opening/closing groups does not recreate or edit mobile descriptors.
        self.assertEqual(Store(self.temp.name).profile(a)['fingerprint'], mobile_snapshot)

    def test_one_failure_does_not_close_other_profiles_or_leak_messages(self):
        a, b, c = self.ids
        self.manager.fail_id = b
        result = self.controller.start_selected([a, b, c])
        self.assertEqual(result['started'], [a, c])
        self.assertEqual(result['errors'], {b: 'RuntimeError'})
        self.assertNotIn('private', str(result))
        self.assertTrue(self.manager.is_running(a))
        self.assertTrue(self.manager.is_running(c))

    def test_selection_rejects_duplicates_unknown_and_invalid_types(self):
        a = self.ids[0]
        for ids in ([], [a, a], ['../data'], [True], [a] * 13, [0],
                    ['f' * 32]):
            with self.subTest(ids=ids):
                with self.assertRaises(ValueError):
                    self.controller.start_selected(ids)
        with self.assertRaises(ValueError):
            self.controller.arrange_selected([a], columns='3')

    def test_tile_commands_change_only_chromium_window_bounds(self):
        a, b, c = self.ids
        self.manager.active.update(self.ids)
        calls = []
        for pid in self.ids:
            page = SimpleNamespace(is_closed=lambda: False)
            session = MagicMock()
            session.send.side_effect = lambda method, params=None, _pid=pid: (
                {'windowId': 12} if method == 'Browser.getWindowForTarget'
                else calls.append((_pid, method, params)) or {})
            context = MagicMock()
            context.pages = [page]
            context.new_cdp_session.return_value = session
            self.manager.contexts[pid] = context

        result = self.controller.arrange_selected([a, b, c],
                                                  columns=2,
                                                  work_area=(0, 0, 1200, 900))
        self.assertEqual(result['arranged'], self.ids)
        self.assertEqual(result['errors'], {})
        self.assertEqual(len(calls), 3)
        bounds = [call[2]['bounds'] for call in calls]
        self.assertEqual((bounds[0]['left'], bounds[0]['top']), (0, 0))
        self.assertEqual((bounds[1]['left'], bounds[1]['top']), (600, 0))
        self.assertEqual((bounds[2]['left'], bounds[2]['top']), (0, 450))
        self.assertTrue(all(call[1] == 'Browser.setWindowBounds' for call in calls))
        for pid in self.ids:
            self.manager.contexts[pid].new_cdp_session.return_value.detach.assert_called_once()
        # The mobile profile configuration is not touched by window resizing.
        self.assertEqual(self.store.profile(a)['device'], 'Pixel 7')

    def test_headless_and_stopped_windows_fail_cleanly(self):
        a = self.ids[0]
        with self.assertRaisesRegex(ValueError, 'Abra os navegadores'):
            self.controller.arrange_selected([a], work_area=(0, 0, 1200, 900))
        self.manager.active.add(a)
        self.manager.headless = True
        with self.assertRaisesRegex(ValueError, 'interface visual'):
            self.controller.arrange_selected([a], work_area=(0, 0, 1200, 900))


if __name__ == '__main__':
    unittest.main()
