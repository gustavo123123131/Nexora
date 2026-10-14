"""Compatibility with the user-supplied LIXOCPA mobile instance settings.

Never use exported cookies, account identities, bank records, proxy
credentials or external sites in test data.
"""
import tempfile
import unittest
from unittest.mock import patch

from lixocpa_import import (build_legacy_mobile_plan,
                            import_legacy_mobile_settings)
from storage import Store
from multilogin_controller import MultiLoginController


class LegacySettingsTests(unittest.TestCase):
    def sample(self, mode='celular'):
        # Mirrors the structure in LIXOCPA/Criar_Mae/settings/settings.json.
        return {'url': 'https://example.org,https://example.com/path',
                'mode': mode, 'count': 2, 'headless': False,
                'proxy_raw': 'DO_NOT_COPY', 'fake_private_token': 'DO_NOT_COPY'}

    def test_preview_retains_mobile_only(self):
        p = build_legacy_mobile_plan(self.sample())
        self.assertEqual(p['profiles_to_create'], 4)
        self.assertEqual(p['count_per_url'], 2)
        self.assertEqual(p['device'], 'Pixel 7')
        self.assertNotIn('DO_NOT_COPY', str(p))
        self.assertEqual(len(p['urls']), 2)

    def test_legacy_app_settings_stay_accurately_labeled(self):
        # Criar_Filha uses "app" in the original settings.json.
        p = build_legacy_mobile_plan(self.sample(mode='app'))
        self.assertEqual(p['mode'], 'app')
        self.assertTrue(any('WebView não é reproduzido' in w for w in p['warnings']))

    def test_import_creates_new_persistent_snapshots_only(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            existing = store.create_site('Já salvo', 'https://example.org')
            old_profile = store.create_profile('Conta original', existing['id'], 'Galaxy S24')
            old_snapshot = old_profile['fingerprint']
            result = import_legacy_mobile_settings(store, self.sample())
            self.assertEqual(result['sites_created'], 1)
            self.assertEqual(result['profiles_created'], 4)
            self.assertEqual(len(store.profiles), 5)
            self.assertEqual(len(store.sites), 2)
            self.assertEqual(store.profile(old_profile['id'])['fingerprint'], old_snapshot)
            self.assertTrue(all(store.profile(pid)['device'] == 'Pixel 7'
                                for pid in result['profile_ids']))
            self.assertNotIn('DO_NOT_COPY', str(store.profiles))
            self.assertNotIn('DO_NOT_COPY', str(store.sites))
            reloaded = Store(folder)
            self.assertEqual(len(reloaded.profiles), 5)
            self.assertEqual(reloaded.profile(old_profile['id'])['fingerprint'], old_snapshot)
            self.assertTrue(all(not (store.profiles_dir / pid).exists()
                                for pid in result['profile_ids']))

    def test_reject_invalid_modes_urls_and_large_batches(self):
        for config in (None, [], {'url':'javascript:alert(1)', 'count':2},
                       {'url':'https://test.invalid', 'mode':'desktop'},
                       {'url':'https://test.invalid', 'mode':'app', 'count':100},
                       {'url':'https://test.invalid', 'mode':'celular', 'count':True},
                       {'url':'https://test.invalid,https://test.invalid', 'mode':'app'}):
            with self.subTest(config=config):
                with self.assertRaises(ValueError):
                    build_legacy_mobile_plan(config)

    def test_failed_import_rolls_back_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            config = self.sample()
            original = store.create_profile
            calls = [0]
            def fail_second(*args, **kwargs):
                calls[0] += 1
                if calls[0] == 2:
                    raise RuntimeError('synthetic error')
                return original(*args, **kwargs)
            with patch.object(store, 'create_profile', side_effect=fail_second):
                with self.assertRaises(RuntimeError):
                    import_legacy_mobile_settings(store, config)
            self.assertEqual(Store(folder).profiles, [])
            self.assertEqual(Store(folder).sites, [])

    def test_profile_start_spacing_does_not_modify_mobile_snapshots(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            site = store.create_site('Teste', 'https://example.org')
            items = [store.create_profile(str(i), site['id']) for i in range(3)]
            ids = [p['id'] for p in items]
            expected = [p['fingerprint'] for p in items]

            class Dummy:
                def __init__(self): self.store=store; self.active=set()
                def start(self, pid):
                    if pid in self.active: return {'already_open': True}
                    self.active.add(pid); return {'already_open': False}
                def stop(self, pid): self.active.remove(pid); return True
            manager = Dummy()
            controller = MultiLoginController(manager)
            with patch('multilogin_controller.time.sleep') as sleep:
                result = controller.start_selected(ids, interval_ms=250)
                self.assertEqual(result['started'], ids)
                self.assertEqual(sleep.call_count, 2)
                sleep.assert_any_call(.25)
            for p, snap in zip(items, expected):
                self.assertEqual(store.profile(p['id'])['fingerprint'], snap)
            for invalid in (-1, 1000, True, '500'):
                with self.assertRaises(ValueError):
                    controller.start_selected(ids, interval_ms=invalid)


if __name__ == '__main__':
    unittest.main()
