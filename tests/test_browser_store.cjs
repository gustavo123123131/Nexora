/* Run with: node --test tests/test_browser_store.cjs
 * Verifies metadata only. It does NOT test Chromium isolation. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'public', 'local_store.js'), 'utf8');
const frontend = fs.readFileSync(path.join(root, 'public', 'app.js'), 'utf8');
const remote = fs.readFileSync(path.join(root, 'public', 'remote_browser.js'), 'utf8');
const page = fs.readFileSync(path.join(root, 'public', 'index.html'), 'utf8');
const deviceCatalog = JSON.parse(fs.readFileSync(path.join(root, 'public', 'device_catalog.json'), 'utf8'));
const memory = new Map();
const {randomFillSync} = require('node:crypto');

function browserStore() {
  const sandbox = {
    globalThis: {},
    localStorage: {
      getItem: key => memory.get(key) ?? null,
      setItem: (key, value) => memory.set(key, value)
    },
    crypto: {getRandomValues: bytes => randomFillSync(bytes)},
    URL
  };
  vm.runInNewContext(source, sandbox, {filename: 'local_store.js'});
  return sandbox.globalThis.NexoraBrowserStore;
}

test('scripts are valid JavaScript', () => {
  assert.doesNotThrow(() => new vm.Script(frontend));
  assert.doesNotThrow(() => new vm.Script(source));
  assert.doesNotThrow(() => new vm.Script(remote));
  assert.match(page, /id="remoteViewer"/);
  assert.match(page, /src="\/remote_browser\.js"/);
});

test('metadata persists, but sessions cannot be falsely launched', () => {
  memory.clear();
  const store = browserStore();
  const site = store.request('sites/create', {name:'Teste', url:'https://example.org'});
  const profile = store.request('profiles/create', {name:'Conta 1', site_id:site.id});
  const result = browserStore().request('state');
  assert.equal(result.sites[0].id, site.id);
  assert.equal(result.profiles[0].id, profile.id);
  assert.equal(result.profiles[0].status, 'unavailable');
  assert.equal(result.capabilities.browser, false);
  assert.equal(result.capabilities.storage, 'browser');
  assert.throws(() => store.request('profiles/start', {id:profile.id}), /executor remoto/);
  assert.throws(() => store.request('sites/delete', {id:site.id}), /perfis vinculados/);
  assert.throws(() => store.request('sites/create', {name:'Bad', url:'javascript:alert(1)'}), /URL inválida|Use uma URL/);
  assert.throws(() => store.request('sites/create', {name:'Bad', url:'https://u:p@example.org'}), /sem credenciais/);
  store.request('profiles/delete', {id:profile.id});
  store.request('sites/delete', {id:site.id});
  assert.equal(store.request('state').sites.length, 0);
});

test('import is transactional and does not store cookies', () => {
  memory.clear();
  const store = browserStore();
  const id = 'a'.repeat(32);
  const p = 'b'.repeat(32);
  const settings = {sites:[{id, name:'Site importado', url:'https://example.org',cookies:'secret'}],
                    profiles:[{id:p,name:'Conta antiga',site_id:id,cookies:'secret'}]};
  const imported = store.request('import', settings);
  assert.equal(imported.sites_importados, 1);
  assert.equal(imported.perfis_importados, 1);
  assert.equal(store.request('import', settings).sites_importados, 0);
  assert.doesNotMatch(Array.from(memory.values()).join('\n'), /secret/);
  assert.throws(() => store.request('import', {sites:[],profiles:[{id:'c'.repeat(32),name:'Bad',site_id:'d'.repeat(32)}]}), /inexistente/);
  assert.equal(store.request('state').profiles.length, 1);
});


test('device model is independently chosen, edited and retained across reloads', () => {
  memory.clear();
  const store = browserStore();
  assert.ok(store.devices.includes('Pixel 7'));
  assert.ok(store.devices.includes('Pixel 5'));
  assert.ok(store.devices.includes('Galaxy S9+'));
  const site = store.request('sites/create', {name: 'Independent', url: 'https://example.org'});
  const first = store.request('profiles/create', {
    name: 'Account 1', site_id: site.id, device: 'Pixel 5'
  });
  const second = store.request('profiles/create', {
    name: 'Account 2', site_id: site.id, device: 'Galaxy S9+'
  });
  const storeReload = browserStore();
  const values = storeReload.request('state').profiles;
  assert.equal(values.find(p => p.id === first.id).device, 'Pixel 5');
  assert.equal(values.find(p => p.id === second.id).device, 'Galaxy S9+');

  storeReload.request('profiles/update', {
    id: first.id, name: 'Account 1 edited', site_id: site.id, device: 'Nexus 5'
  });
  const after = browserStore().request('state').profiles;
  assert.equal(after.find(p => p.id === first.id).device, 'Nexus 5');
  assert.equal(after.find(p => p.id === second.id).device, 'Galaxy S9+');
  assert.throws(() => store.request('profiles/create', {
    name: 'Invalid', site_id: site.id, device: '--no-sandbox'
  }), /dispositivo válido/);
  assert.throws(() => store.request('profiles/update', {
    id: second.id, name: 'Invalid', site_id: site.id, device: 'iPhone 15'
  }), /dispositivo válido/);
  assert.equal(browserStore().request('state').profiles.find(p => p.id === second.id).device,
               'Galaxy S9+');
});

test('legacy profiles and imports default to Pixel 7 without losing IDs or records', () => {
  memory.clear();
  const store = browserStore();
  const site = store.request('sites/create', {name: 'Old', url: 'https://example.org'});
  const profile = store.request('profiles/create', {name: 'Old profile', site_id:site.id});
  assert.equal(profile.device, 'Pixel 7');
  const old = JSON.parse(memory.get('nexora.site-profiles.v1'));
  delete old.profiles[0].device;
  memory.set('nexora.site-profiles.v1', JSON.stringify(old));
  const result = browserStore().request('state').profiles[0];
  assert.equal(result.id, profile.id);
  assert.equal(result.device, 'Pixel 7');
  const imported = store.request('import', {
    sites:[], profiles:[{id:'e'.repeat(32),name:'Imported',site_id:site.id}]
  });
  assert.equal(imported.perfis_importados,1);
  assert.equal(browserStore().request('state').profiles.find(p => p.id === 'e'.repeat(32)).device,
               'Pixel 7');
});

test('the expanded official catalog is accepted and persists per profile', () => {
  memory.clear();
  const store = browserStore();
  store.configureDevices(deviceCatalog);
  assert.equal(store.devices.length, 50);
  assert.ok(store.devices.includes('Galaxy S24'));
  assert.ok(store.devices.includes('Galaxy A55'));
  assert.ok(store.devices.includes('Galaxy Tab S9'));
  const site = store.request('sites/create', {name:'Catalog',url:'https://example.org'});
  const profile = store.request('profiles/create', {
    name:'Android profile',site_id:site.id,device:'Galaxy S24'
  });
  assert.equal(browserStore().request('state').profiles[0].device, 'Galaxy S24');
  assert.equal(profile.device,'Galaxy S24');
  assert.throws(() => store.request('profiles/create',{
    name:'Invalid',site_id:site.id,device:'Unlisted Model'
  }), /dispositivo válido/);
});

test('many registrations remain saved across panel reloads', () => {
  memory.clear();
  const store = browserStore();
  const site = store.request('sites/create', {name:'Site',url:'https://example.org'});
  for (let i = 0; i < 200; i++) {
    store.request('profiles/create', {name:'Conta '+i,site_id:site.id,
      device: i % 2 ? 'Pixel 7' : 'Galaxy S5'});
  }
  const profiles = browserStore().request('state').profiles;
  assert.equal(profiles.length, 200);
  assert.equal(new Set(profiles.map(profile => profile.id)).size, 200);
  assert.equal(profiles[0].name,'Conta 0');
  assert.equal(profiles[199].name,'Conta 199');
  assert.equal(profiles[0].device,'Galaxy S5');
  assert.equal(profiles[199].device,'Pixel 7');
  assert.ok(memory.get('nexora.site-profiles.v1').length < 1_000_000);
});
