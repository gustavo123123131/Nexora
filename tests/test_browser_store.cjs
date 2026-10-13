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
const memory = new Map();
let counter = 0;

function browserStore() {
  const sandbox = {
    globalThis: {},
    localStorage: {
      getItem: key => memory.get(key) ?? null,
      setItem: (key, value) => memory.set(key, value)
    },
    crypto: {getRandomValues: bytes => {
      for (let i = 0; i < bytes.length; i++) bytes[i] = (counter++ * 31) % 256;
      return bytes;
    }},
    URL
  };
  vm.runInNewContext(source, sandbox, {filename: 'local_store.js'});
  return sandbox.globalThis.NexoraBrowserStore;
}

test('scripts are valid JavaScript', () => {
  assert.doesNotThrow(() => new vm.Script(frontend));
  assert.doesNotThrow(() => new vm.Script(source));
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
