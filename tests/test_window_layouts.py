"""Window layout persistence without changing mobile fingerprints or cookie data."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from storage import Store
from window_layout_manager import WindowLayoutManager
from multilogin_controller import MultiLoginController


class LayoutStoreTests(unittest.TestCase):
    def test_persists_windows_separately_without_creating_browser_profiles(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            site = store.create_site('Site', 'https://example.org')
            p1 = store.create_profile('Pixel', site['id'], 'Pixel 7')
            p2 = store.create_profile('Galaxy', site['id'], 'Galaxy S24')
            first = {'left': -200, 'top': 40, 'width': 420, 'height': 800}
            second = {'left': 600, 'top': 80, 'width': 480, 'height': 760}
            manager = WindowLayoutManager(root)
            self.assertIsNone(manager.get(p1['id']))
            self.assertEqual(manager.save(p1['id'], first), first)
            self.assertEqual(manager.save(p2['id'], second), second)
            loaded = WindowLayoutManager(root)
            self.assertEqual(loaded.get(p1['id']), first)
            self.assertEqual(loaded.get(p2['id']), second)
            self.assertEqual(store.profile(p1['id'])['device'], 'Pixel 7')
            self.assertEqual(store.profile(p2['id'])['device'], 'Galaxy S24')
            self.assertFalse((store.profiles_dir / p1['id']).exists())
            self.assertFalse((store.profiles_dir / p2['id']).exists())
            saved = json.loads((Path(root) / 'window-layouts.json').read_text())
            self.assertEqual(sorted(saved), ['profiles', 'version'])
            self.assertEqual(len(saved['profiles']), 2)

    def test_rejects_invalid_and_does_not_overwrite_corrupt_file(self):
        with tempfile.TemporaryDirectory() as root:
            store = WindowLayoutManager(root)
            valid = 'a' * 32
            for invalid in ({'left':0,'top':0,'width':10,'height':320},
                            {'left':0,'top':0,'width':500.5,'height':700},
                            {'left':False,'top':0,'width':500,'height':700},
                            {'left':20000,'top':0,'width':500,'height':700}):
                with self.assertRaises(ValueError):
                    store.save(valid, invalid)
            with self.assertRaises(ValueError):
                store.save('../invalid', {'left':0,'top':0,'width':500,'height':700})
            original = 'this-is-not-json'
            store.path.write_text(original)
            with self.assertRaisesRegex(ValueError, 'danificado'):
                store.save(valid, {'left':0,'top':0,'width':500,'height':700})
            self.assertEqual(store.path.read_text(), original)

    def test_chromium_window_capture_and_restore_do_not_inject_scripts(self):
        session = MagicMock()
        commands = []
        def send(method, params=None):
            commands.append((method, params))
            if method == 'Browser.getWindowForTarget':
                return {'windowId': 1, 'bounds': {
                    'left': 11, 'top': 22, 'width': 444, 'height': 777}}
            return {}
        session.send.side_effect = send
        page = SimpleNamespace(is_closed=lambda: False)
        context = MagicMock()
        context.pages = [page]
        context.new_cdp_session.return_value = session
        bounds = WindowLayoutManager.read_window(context)
        self.assertEqual(bounds, {'left':11,'top':22,'width':444,'height':777})
        self.assertTrue(WindowLayoutManager.apply_to_context(context, bounds))
        self.assertEqual([x[0] for x in commands],
                         ['Browser.getWindowForTarget',
                          'Browser.getWindowForTarget',
                          'Browser.setWindowBounds'])
        self.assertTrue(all(not name.startswith(('Runtime.', 'Page.'))
                            for name, _ in commands))
        self.assertEqual(session.detach.call_count, 2)

    def test_arrange_selected_also_saves_positions_per_profile(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            site = store.create_site('Site', 'https://example.org')
            profiles = [store.create_profile(str(i), site['id']) for i in range(2)]
            manager = MagicMock()
            manager.store = store
            manager.headless = False
            manager.window_layouts = WindowLayoutManager(root)
            manager.is_running.side_effect = lambda pid: True
            manager.contexts = {}
            for profile in profiles:
                cdps = MagicMock()
                cdps.send.side_effect = lambda command, payload=None: (
                    {'windowId': 9} if command == 'Browser.getWindowForTarget' else {})
                ctx = MagicMock()
                ctx.pages = [SimpleNamespace(is_closed=lambda: False)]
                ctx.new_cdp_session.return_value = cdps
                manager.contexts[profile['id']] = ctx
            result = MultiLoginController(manager).arrange_selected(
                [p['id'] for p in profiles], columns=2,
                work_area=(0, 0, 1200, 900))
            self.assertEqual(len(result['arranged']), 2)
            self.assertEqual(result['layout_warnings'], {})
            for index, profile in enumerate(profiles):
                self.assertEqual(
                    WindowLayoutManager(root).get(profile['id']),
                    {'left':index * 600,'top':0,'width':600,'height':900})


if __name__ == '__main__':
    unittest.main()
