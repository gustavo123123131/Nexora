"""Run with: python -m unittest discover -s tests -p test_cloud.py -v
Requires Flask; PostgreSQL integration must additionally be tested with a real Neon DB.
"""
import json
import os
import unittest
from unittest.mock import patch

from app import app


class FakeStore:
    sites = []
    profiles = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def state(self):
        return {'sites': self.sites, 'profiles': [{**p, 'status': 'unavailable'} for p in self.profiles],
                'capabilities': {'mode': 'vercel', 'browser': False}}

    def create_site(self, name, url):
        from storage import validate_name, validate_url
        site = {'id': 'a' * 32, 'name': validate_name(name), 'url': validate_url(url)}
        self.sites.append(site)
        return site

    def create_profile(self, name, site_id):
        from storage import validate_name
        if site_id not in [s['id'] for s in self.sites]:
            raise ValueError('Selecione um site cadastrado.')
        profile = {'id': 'b' * 32, 'name': validate_name(name), 'site_id': site_id}
        self.profiles.append(profile)
        return profile


class CloudAuthAndRoutes(unittest.TestCase):
    def setUp(self):
        FakeStore.sites, FakeStore.profiles = [], []
        self.env = patch.dict(os.environ, {
            'DATABASE_URL': 'postgresql://placeholder/unused',
            'NEXORA_ACCESS_PASSWORD': 'some-long-private-password',
            'NEXORA_SESSION_SECRET': 'a' * 40,
        })
        self.env.start()
        app.config['TESTING'] = True
        app.config['STORE_FACTORY'] = FakeStore
        self.client = app.test_client()

    def tearDown(self):
        app.config.pop('STORE_FACTORY', None)
        self.env.stop()

    def post(self, path, body, origin='http://localhost'):
        return self.client.post(path, data=json.dumps(body), content_type='application/json',
                                headers={'Origin': origin})

    def test_unauthorized_and_csrf(self):
        self.assertEqual(self.client.get('/api/state').status_code, 401)
        self.assertEqual(self.post('/api/auth/login', {'password': 'bad'}).status_code, 401)
        self.assertEqual(self.post('/api/auth/login', {'password': 'some-long-private-password'},
                                   origin='https://evil.example').status_code, 403)
        self.assertEqual(self.post('/api/auth/login', {'password': 'some-long-private-password'}).status_code, 200)
        self.assertEqual(self.client.get('/api/auth/status').json['authenticated'], True)
        self.assertEqual(self.post('/api/sites/create', {'name': 'bad', 'url': 'javascript:alert(1)'}).status_code, 400)
        self.assertEqual(self.post('/api/sites/create', {'name': 'Site', 'url': 'https://example.com'}).status_code, 200)
        self.assertEqual(self.post('/api/profiles/create', {'name': 'A', 'site_id': 'a' * 32}).status_code, 200)
        state = self.client.get('/api/state').json
        self.assertFalse(state['capabilities']['browser'])
        self.assertEqual(state['profiles'][0]['status'], 'unavailable')
        self.assertEqual(self.post('/api/profiles/start', {'id': 'b' * 32}).status_code, 501)
        self.assertEqual(self.post('/api/auth/logout', {}).status_code, 200)
        self.assertEqual(self.client.get('/api/state').status_code, 401)

    def test_missing_secrets_fail_closed(self):
        with patch.dict(os.environ, {'NEXORA_ACCESS_PASSWORD': ''}):
            self.assertEqual(self.client.get('/api/state').status_code, 503)
            self.assertFalse(self.client.get('/api/health').json['configured'])


if __name__ == '__main__':
    unittest.main()
