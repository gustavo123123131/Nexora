const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const remoteCode = fs.readFileSync(path.join(__dirname, '..', 'public', 'remote_browser.js'), 'utf8');

function createSandbox(prompts, {desktop = false, profiles = [], activeIds = []} = {}) {
  const records = [];
  const alerts = [];
  const store = new Map();
  const sandbox = {
    URL,
    document: {
      addEventListener() {},
      querySelector(selector) {
        return {title:'', textContent:'', hidden:false, addEventListener() {}};
      }
    },
    sessionStorage: {
      getItem: k => store.get(k) ?? null,
      setItem: (k,v) => store.set(k,v)
    },
    prompt: () => prompts.shift(),
    alert: message => alerts.push(message),
    setInterval: () => 1,
    clearInterval() {},
    console: {info() {}},
    fetch: async (target, options) => {
      records.push({target, options});
      return {
        ok:true,
        status:200,
        json: async () => target.endsWith('/v1/start') ? {running: true, desktop} :
          target.endsWith('/v1/statuses') ? {running_ids: activeIds} : {ok:true,browser:true,desktop},
        blob: async () => new Blob([])
      };
    },
    NexoraGetProfiles: () => profiles,
    NexoraUIRemoteConnection() {}
  };
  vm.runInNewContext(remoteCode, sandbox, {filename:'remote_browser.js'});
  return {remote:sandbox.NexoraRemote,records,alerts,store};
}

test('Cloudflare URL is validated before any secret is sent to it', async () => {
  const scene = createSandbox(['https://attacker.example']);
  await scene.remote.connect();
  assert.equal(scene.remote.connected,false);
  assert.equal(scene.records.length,0);
  assert.match(scene.alerts[0], /trycloudflare/);
});

test('connects directly to temporary tunnel with Bearer key and no Vercel redeploy', async () => {
  const url='https://example-random.trycloudflare.com';
  const key='a'.repeat(48);
  const scene=createSandbox([url,key]);
  await scene.remote.connect();
  assert.equal(scene.remote.connected,true);
  assert.equal(scene.records.length,1);
  assert.equal(scene.records[0].target,url+'/v1/health');
  assert.equal(scene.records[0].options.headers.Authorization,'Bearer '+key);
  assert.equal(scene.records[0].options.credentials,'omit');
  assert.equal(scene.store.get('nexora.tunnel-url'),url);
  assert.equal(scene.store.get('nexora.runner-key'),key);
});


test('accepts the tunnel URL copied together with console labels', async () => {
  const url = 'https://queue-julia-communist-exceptions.trycloudflare.com';
  const key = 'a'.repeat(48);
  const copied = 'URL DO TUNEL (cole em Conectar navegador no Nexora):\n' +
    url + '\nCHAVE PRIVADA (nao compartilhar): [redacted]';
  const scene = createSandbox([copied, key]);
  await scene.remote.connect();
  assert.equal(scene.remote.connected, true);
  assert.equal(scene.records[0].target, url + '/v1/health');
});

test('accepts a trycloudflare hostname without https scheme', async () => {
  const url = 'https://queue-julia-communist-exceptions.trycloudflare.com';
  const key = 'a'.repeat(48);
  const scene = createSandbox(['queue-julia-communist-exceptions.trycloudflare.com', key]);
  await scene.remote.connect();
  assert.equal(scene.remote.connected, true);
  assert.equal(scene.records[0].target, url + '/v1/health');
});


test('headed Windows profile opens on desktop without screenshot viewer', async () => {
  const url = 'https://example-random.trycloudflare.com';
  const key = 'k'.repeat(48);
  const scene = createSandbox([url, key], {desktop: true});
  await scene.remote.connect();
  assert.equal(scene.remote.desktop, true);
  const id = 'a'.repeat(32);
  await scene.remote.start(id, 'https://www.example.com/');
  assert.equal(scene.remote.isRunning(id), true);
  assert.ok(scene.records.some(record => record.target === url + '/v1/start'));
  assert.ok(!scene.records.some(record => record.target.includes('/v1/frame/')),
    'starting a Windows profile should not request embedded screenshot frames');
});


test('forwards selected device model for each independent profile', async () => {
  const url = 'https://example-random.trycloudflare.com';
  const scene = createSandbox([url, 'c'.repeat(48)], {desktop: true});
  await scene.remote.connect();
  await scene.remote.start('a'.repeat(32), 'https://example.com/a', 'Pixel 5');
  await scene.remote.start('b'.repeat(32), 'https://example.com/b', 'Galaxy S9+');
  const starts = scene.records.filter(record => record.target.endsWith('/v1/start'));
  assert.equal(starts.length, 2);
  assert.equal(JSON.parse(starts[0].options.body).device, 'Pixel 5');
  assert.equal(JSON.parse(starts[1].options.body).device, 'Galaxy S9+');
  assert.notEqual(JSON.parse(starts[0].options.body).id, JSON.parse(starts[1].options.body).id);
  assert.ok(!scene.records.some(record => record.target.includes('/v1/frame/')));
});

test('bulk status checks do not make a request per saved profile', async () => {
  const profiles = Array.from({length:600}, (_,i) => ({id: i.toString(16).padStart(32,'0')}));
  const scene = createSandbox(['https://example-random.trycloudflare.com','a'.repeat(48)], {
    desktop:true, profiles, activeIds:[profiles[0].id,profiles[590].id]
  });
  await scene.remote.connect();
  assert.equal(scene.remote.isRunning(profiles[0].id),true);
  assert.equal(scene.remote.isRunning(profiles[590].id),true);
  assert.equal(scene.remote.isRunning(profiles[1].id),false);
  assert.equal(scene.records.filter(record=>record.target.endsWith('/v1/statuses')).length,1);
  assert.equal(scene.records.filter(record=>record.target.includes('/v1/status/')).length,0);
});
