/* Nexora remote Chrome viewer. Actions are authenticated and proxied via
 * Vercel to a persistent Chromium worker. No fake browser or iframe.
 */
(() => {
  'use strict';
  const STORAGE_KEY = 'nexora.runner-key';
  const running = new Set();
  let secret = sessionStorage.getItem(STORAGE_KEY) || '';
  let activeId = null;
  let objectUrl = null;
  let pollTimer = null;
  let busy = false;

  const api = async (route, body, image = false) => {
    const headers = secret ? {Authorization: 'Bearer ' + secret} : {};
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const response = await fetch('/api/runner/' + route, {
      method: body === undefined ? 'GET' : 'POST',
      headers,
      cache: 'no-store',
      credentials: 'same-origin',
      body: body === undefined ? undefined : JSON.stringify(body)
    });
    if (!response.ok) {
      let message = 'Executor indisponível (HTTP ' + response.status + ')';
      try {const error = await response.json(); message = error.error || message;} catch (_) {}
      throw new Error(message);
    }
    return image ? response.blob() : response.json();
  };

  const remote = {
    connected: false,
    isRunning: id => running.has(id),
    initialize,
    connect,
    start,
    stop,
    view
  };
  globalThis.NexoraRemote = remote;

  function refreshPanel() {
    globalThis.NexoraUIRemoteConnection?.(remote.connected);
    const count = document.querySelector('#statActive');
    if (count && remote.connected) count.textContent = running.size;
  }

  async function initialize() {
    try {
      const config = await api('config');
      if (!config.configured) {
        document.querySelector('#runnerButton').title = 'Configure NEXORA_RUNNER_URL na Vercel e instale o executor em um servidor com armazenamento persistente.';
      }
      if (secret) await authenticate();
    } catch (error) {
      console.info('Executor do Nexora ainda não configurado.');
    }
  }

  async function authenticate() {
    const info = await api('health');
    if (!info.browser || !info.ok) throw new Error('Executor não suporta Chromium remoto.');
    remote.connected = true;
    await fetchStatuses();
    refreshPanel();
  }

  async function connect() {
    const value = prompt('Digite a chave privada NEXORA_RUNNER_KEY do seu executor Chromium (não é senha do painel):',
      secret || '');
    if (value === null) return;
    if (value.trim().length < 32) {
      alert('A chave do executor deve ter ao menos 32 caracteres.');
      return;
    }
    const old = secret;
    secret = value.trim();
    try {
      await authenticate();
      sessionStorage.setItem(STORAGE_KEY, secret);
      alert('Executor Chromium conectado! Você já pode clicar em Abrir.');
    } catch (error) {
      secret = old;
      remote.connected = false;
      refreshPanel();
      alert('Não foi possível conectar o executor: ' + error.message);
    }
  }

  async function fetchStatuses() {
    const profiles = globalThis.NexoraGetProfiles?.() || [];
    await Promise.all(profiles.map(async profile => {
      try {
        const status = await api('status/' + profile.id);
        if (status.running) running.add(profile.id);
        else running.delete(profile.id);
      } catch (_) {running.delete(profile.id);}
    }));
    refreshPanel();
  }

  async function start(id, url) {
    if (!remote.connected) return connect();
    try {
      const response = await api('start', {id, url});
      if (!response.running) throw new Error('O executor não confirmou a abertura.');
      running.add(id);
      refreshPanel();
      view(id);
      if (response.warning) alert(response.warning);
    } catch (error) {alert('Não foi possível abrir o perfil: ' + error.message);}
  }

  async function stop(id) {
    if (!remote.connected || !running.has(id)) return;
    if (!confirm('Encerrar este navegador? Os cookies salvos no volume persistente continuarão disponíveis.')) return;
    try {
      await api('stop', {id});
      running.delete(id);
      if (activeId === id) hideViewer();
      refreshPanel();
    } catch (error) {alert('Falha ao encerrar: ' + error.message);}
  }

  function hideViewer() {
    activeId = null;
    clearInterval(pollTimer);
    pollTimer = null;
    const viewer = document.querySelector('#remoteViewer');
    if (viewer) viewer.hidden = true;
    const img = document.querySelector('#remoteFrame');
    if (img) img.removeAttribute('src');
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = null;
  }

  function view(id) {
    if (!running.has(id)) return alert('Abra o perfil antes de visualizar.');
    hideViewer();
    activeId = id;
    document.querySelector('#remoteViewer').hidden = false;
    document.querySelector('#remoteFrame').alt = 'Tela do navegador remoto';
    pollFrame();
    pollTimer = setInterval(() => {
      if (activeId && !document.hidden) pollFrame();
    }, 1800);
  }

  async function pollFrame() {
    if (!activeId || busy) return;
    busy = true;
    const id = activeId;
    try {
      const blob = await api('frame/' + id, undefined, true);
      if (!blob.type.startsWith('image/jpeg')) throw new Error('Imagem inválida.');
      if (activeId !== id) return;
      const url = URL.createObjectURL(blob);
      document.querySelector('#remoteFrame').src = url;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      objectUrl = url;
      document.querySelector('#remoteError').textContent = '';
    } catch (error) {
      document.querySelector('#remoteError').textContent = error.message;
    } finally {busy = false;}
  }

  async function action(type, extra = {}) {
    if (!activeId || !remote.connected) return;
    try {
      await api('act', {id: activeId, type, ...extra});
      await pollFrame();
    } catch (error) {
      document.querySelector('#remoteError').textContent = error.message;
    }
  }

  document.addEventListener('click', async event => {
    if (event.target.closest('#runnerButton')) return connect();
    if (event.target.closest('#remoteClose')) return hideViewer();
    if (event.target.closest('#remoteReload')) return action('reload');
    if (event.target.closest('#remoteBack')) return action('back');
    if (event.target.closest('#remoteScrollDown')) return action('scroll', {delta: 500});
    if (event.target.closest('#remoteScrollUp')) return action('scroll', {delta: -500});
    if (event.target.closest('#remoteEnter')) return action('key', {key: 'Enter'});
    if (event.target.closest('#remoteTab')) return action('key', {key: 'Tab'});
    if (event.target.closest('#remoteBackspace')) return action('key', {key: 'Backspace'});
    if (event.target.closest('#remoteSendText')) {
      const input = document.querySelector('#remoteText');
      const content = input.value;
      input.value = '';
      if (content) await action('type', {text: content});
    }
    if (event.target.id === 'remoteFrame') {
      const img = event.target;
      const bounds = img.getBoundingClientRect();
      if (!bounds.width || !img.naturalWidth) return;
      const x = (event.clientX - bounds.left) * img.naturalWidth / bounds.width;
      const y = (event.clientY - bounds.top) * img.naturalHeight / bounds.height;
      await action('click', {x: Math.round(x), y: Math.round(y)});
    }
  });
  document.querySelector('#remoteText')?.addEventListener('keydown', event => {
    if (event.key === 'Enter') {
      event.preventDefault();
      document.querySelector('#remoteSendText').click();
    }
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && activeId) hideViewer();
  });
  setInterval(async () => {
    if (remote.connected && !document.hidden) await fetchStatuses();
  }, 16000);
})();
