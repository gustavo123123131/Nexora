const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const remoteCode = fs.readFileSync(path.join(__dirname, '..', 'public', 'remote_browser.js'), 'utf8');

function createSandbox(prompts) {
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
        json: async () => ({ok:true,browser:true}),
        blob: async () => new Blob([])
      };
    },
    NexoraGetProfiles: () => [],
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
