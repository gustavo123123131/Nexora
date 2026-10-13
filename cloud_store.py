"""Nexora cloud: persistent profile *metadata* only (no cookies, no browser state).

DATABASE_URL must refer to an external PostgreSQL database, e.g. Neon.
"""
import os
import re
from uuid import uuid4

from storage import validate_name, validate_url

IDENTIFIER = re.compile(r'^[0-9a-f]{32}$')


class CloudStore:
    def __init__(self):
        url = os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_URL')
        if not url:
            raise RuntimeError('Banco não configurado. Defina DATABASE_URL na Vercel.')
        import psycopg
        from psycopg.rows import dict_row
        self.conn = psycopg.connect(url, connect_timeout=7, sslmode='require', row_factory=dict_row)
        try:
            # IF NOT EXISTS allows the first deployment to initialize an empty database.
            with self.conn.cursor() as cursor:
                cursor.execute('''CREATE TABLE IF NOT EXISTS nexora_sites (
                    id text PRIMARY KEY, name text NOT NULL, url text NOT NULL
                )''')
                cursor.execute('''CREATE TABLE IF NOT EXISTS nexora_profiles (
                    id text PRIMARY KEY, name text NOT NULL,
                    site_id text NOT NULL REFERENCES nexora_sites(id) ON DELETE RESTRICT
                )''')
            self.conn.commit()
        except Exception:
            self.conn.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        self.conn.close()

    def state(self):
        with self.conn.cursor() as cur:
            cur.execute('SELECT id, name, url FROM nexora_sites ORDER BY name, id')
            sites = cur.fetchall()
            cur.execute('SELECT id, name, site_id FROM nexora_profiles ORDER BY name, id')
            profiles = [{**row, 'status': 'unavailable'} for row in cur.fetchall()]
        return {'sites': sites, 'profiles': profiles,
                'capabilities': {'browser': False, 'mode': 'vercel', 'reason': 'Nenhum executor remoto de navegador foi configurado.'}}

    def create_site(self, name, url):
        item = {'id': uuid4().hex, 'name': validate_name(name), 'url': validate_url(url)}
        with self.conn.cursor() as cur:
            cur.execute('INSERT INTO nexora_sites (id,name,url) VALUES (%s,%s,%s)',
                        (item['id'], item['name'], item['url']))
        return item

    def update_site(self, site_id, name, url):
        name, url = validate_name(name), validate_url(url)
        with self.conn.cursor() as cur:
            cur.execute('UPDATE nexora_sites SET name=%s, url=%s WHERE id=%s RETURNING id,name,url',
                        (name, url, site_id))
            item = cur.fetchone()
        if item is None:
            raise LookupError('Site não encontrado.')
        return item

    def delete_site(self, site_id):
        with self.conn.cursor() as cur:
            cur.execute('SELECT EXISTS(SELECT 1 FROM nexora_profiles WHERE site_id=%s) AS used', (site_id,))
            if cur.fetchone()['used']:
                raise ValueError('Este site está vinculado a perfis. Exclua os perfis primeiro.')
            cur.execute('DELETE FROM nexora_sites WHERE id=%s RETURNING id', (site_id,))
            if cur.fetchone() is None:
                raise LookupError('Site não encontrado.')
        return {'ok': True}

    def create_profile(self, name, site_id):
        name = validate_name(name, 'nome do perfil')
        with self.conn.cursor() as cur:
            cur.execute('SELECT id FROM nexora_sites WHERE id=%s', (site_id,))
            if cur.fetchone() is None:
                raise ValueError('Selecione um site cadastrado.')
            item = {'id': uuid4().hex, 'name': name, 'site_id': site_id}
            cur.execute('INSERT INTO nexora_profiles (id,name,site_id) VALUES (%s,%s,%s)',
                        (item['id'], item['name'], item['site_id']))
        return {**item, 'status': 'unavailable'}

    def delete_profile(self, profile_id):
        with self.conn.cursor() as cur:
            cur.execute('DELETE FROM nexora_profiles WHERE id=%s RETURNING id', (profile_id,))
            if cur.fetchone() is None:
                raise LookupError('Perfil não encontrado.')
        return {'ok': True}

    def import_settings(self, data):
        """Opt-in import of old settings.json. Does not upload Chromium profiles/cookies."""
        sites, profiles = data.get('sites'), data.get('profiles')
        if not isinstance(sites, list) or not isinstance(profiles, list) or len(sites) > 500 or len(profiles) > 500:
            raise ValueError('Arquivo inválido ou muito grande (limite: 500 sites e 500 perfis).')
        prepared_sites, prepared_profiles = [], []
        for item in sites:
            if not isinstance(item, dict) or not IDENTIFIER.fullmatch(str(item.get('id', ''))):
                raise ValueError('ID de site inválido no arquivo.')
            prepared_sites.append((item['id'], validate_name(item.get('name')), validate_url(item.get('url'))))
        for item in profiles:
            if (not isinstance(item, dict) or not IDENTIFIER.fullmatch(str(item.get('id', '')))
                    or not IDENTIFIER.fullmatch(str(item.get('site_id', '')))):
                raise ValueError('ID de perfil inválido no arquivo.')
            prepared_profiles.append((item['id'], validate_name(item.get('name'), 'nome do perfil'), item['site_id']))
        with self.conn.cursor() as cur:
            new_sites, new_profiles = 0, 0
            for item in prepared_sites:
                cur.execute('INSERT INTO nexora_sites (id,name,url) VALUES (%s,%s,%s) ON CONFLICT(id) DO NOTHING', item)
                new_sites += cur.rowcount
            for item in prepared_profiles:
                cur.execute('INSERT INTO nexora_profiles (id,name,site_id) VALUES (%s,%s,%s) ON CONFLICT(id) DO NOTHING', item)
                new_profiles += cur.rowcount
        return {'ok': True, 'sites_importados': new_sites, 'perfis_importados': new_profiles,
                'aviso': 'Importadas somente configurações; cookies, logins e sessões do Chromium não foram transferidos.'}
