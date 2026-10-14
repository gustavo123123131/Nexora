/* Nexora remote Chromium viewer. Supports direct free Cloudflare Quick Tunnel
 * (CORS restricted to the Nexora origin) and legacy Vercel proxy.
 * Sessions run in a real Chromium worker, never in an iframe.
 */
(() => {
  'use strict';
  const STORAGE_KEY = 'nexora.runner-key';
  const TUNNEL_KEY = 'nexora.tunnel-url';
  const running = new Set();
  let secret = sessionStorage.getItem(STORAGE_KEY) || '';
  let tunnelUrl = sessionStorage.getItem(TUNNEL_KEY) || '';
  let activeId = null;
  let configured = false;
  let objectUrl = null;
  let pollTimer = null;
  let busy = false;

  function validateTunnelUrl(text) {
    // Accept a full pasted console line or terminal output, extracting only
    // its one Cloudflare URL. Never forward arbitrary domains or pasted text.
    const raw = String(text ?? '').trim();
    const urls = [...new Set((raw.match(/https:\/\/[a-z0-9-]+\.trycloudflare\.com(?=$|[\s\/?#"'<>])/gi) || [])
      .map(url => url.toLowerCase()))];
    let candidate;
    if (urls.length === 1) {
      candidate = urls[0];
    } else if (!urls.length && /^[a-z0-9-]+\.trycloudflare\.com\/?$/i.test(raw)) {
      candidate = 'https://' + raw;
    } else {
      throw new Error('Cole a URL https://...trycloudflare.com exibida na janela preta. Copiar somente o endereço é suficiente.');
    }
    let parsed;
    try { parsed = new URL(candidate); }
    catch (_) { throw new Error('Endereço do Cloudflare inválido.'); }
    if (parsed.protocol !== 'https:' || !/^[a-z0-9-]+\.trycloudflare\.com$/i.test(parsed.hostname)
      || parsed.username || parsed.password || parsed.port || parsed.pathname !== '/'
      || parsed.search || parsed.hash) {
      throw new Error('O endereço precisa terminar em .trycloudflare.com.');
    }
    return parsed.origin;
  }

  const api = async (route, body, image = false) => {
    if (route === 'config' && tunnelUrl) return {configured: true, direct: true};
    const direct = Boolean(tunnelUrl);
    const headers = secret ? {Authorization: 'Bearer ' + secret} : {};
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const response = await fetch(direct ? tunnelUrl + '/v1/' + route : '/api/runner/' + route, {
      method: body === undefined ? 'GET' : 'POST',
      headers,
      cache: 'no-store',
      credentials: direct ? 'omit' : 'same-origin',
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
    desktop: false,
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
      configured = Boolean(config.configured);
      if (!configured) {
        document.querySelector('#runnerButton').title = 'Inicie INICIAR_EXECUTOR_WINDOWS.bat no seu PC e conecte a URL do Cloudflare Tunnel.';
      }
      if (secret && configured) await authenticate();
    } catch (error) {
      console.info('Executor do Nexora ainda não configurado.');
    }
  }

  async function authenticate() {
    const info = await api('health');
    if (!info.browser || !info.ok) throw new Error('Executor não suporta Chromium remoto.');
    remote.desktop = info.desktop === true;
    remote.connected = true;
    await fetchStatuses();
    refreshPanel();
  }

  async function connect() {
    // Quick Tunnel uses a NEW URL whenever Windows restarts. Prompting for it
    // here avoids Vercel environment-variable edits and redeployment.
    const answer = prompt(
      'Cole a URL https://...trycloudflare.com exibida pelo INICIAR_EXECUTOR_WINDOWS.bat:',
      tunnelUrl || '');
    if (answer === null) return;
    let nextUrl;
    try { nextUrl = validateTunnelUrl(answer.trim()); }
    catch (error) { alert(error.message); return; }

    const nextKey = prompt(
      'Cole a chave NEXORA_RUNNER_KEY exibida no terminal do executor (não envie essa chave para ninguém):',
      secret || '');
    if (nextKey === null) return;
    if (nextKey.trim().length < 32) {
      alert('A chave deve ter pelo menos 32 caracteres.');
      return;
    }

    const oldUrl = tunnelUrl;
    const oldKey = secret;
    tunnelUrl = nextUrl;
    secret = nextKey.trim();
    remote.connected = false;
    running.clear();
    refreshPanel();
    try {
      await authenticate();
      sessionStorage.setItem(TUNNEL_KEY, tunnelUrl);
      sessionStorage.setItem(STORAGE_KEY, secret);
      alert(remote.desktop
        ? 'Conexão verificada! Clique em Iniciar perfil: uma janela REAL do Chromium vai abrir na área de trabalho do Windows.'
        : 'Conexão verificada! Clique em Abrir no perfil para iniciar o Chromium independente.');
    } catch (error) {
      tunnelUrl = oldUrl;
      secret = oldKey;
      remote.connected = false;
      refreshPanel();
      alert('Falha ao conectar: ' + error.message + '. Verifique se o executor e a janela do túnel estão abertos.');
    }
  }

  async function fetchStatuses() {
    const profiles = globalThis.NexoraGetProfiles?.() || [];
    if (!profiles.length) {
      running.clear();
      refreshPanel();
      return;
    }
    try {
      // The Windows executor enumerates ACTIVE contexts in one request.
      // 5,000 saved registrations still cost one tunnel round trip.
      const result = await api('statuses');
      if (!Array.isArray(result.running_ids)) throw new Error('Legacy runner');
      const saved = new Set(profiles.map(profile => profile.id));
      running.clear();
      for (const id of result.running_ids) if (saved.has(id)) running.add(id);
    } catch (_) {
      // Older executors still work. Bound concurrency on their legacy route.
      for (let i = 0; i < profiles.length; i += 10) {
        await Promise.all(profiles.slice(i, i + 10).map(async profile => {
          try {
            const status = await api('status/' + profile.id);
            if (status.running) running.add(profile.id);
            else running.delete(profile.id);
          } catch (_) { running.delete(profile.id); }
        }));
      }
    }
    refreshPanel();
  }

  async function start(id, url, device = 'Pixel 7') {
    if (!remote.connected) return connect();
    try {
      const response = await api('start', {id, url, device});
      if (!response.running) throw new Error('O executor não confirmou a abertura.');
      running.add(id);
      refreshPanel();
      if (remote.desktop || response.desktop) {
        // Do not open the embedded screenshot viewer on Windows.
        // The local Playwright worker already launched a real OS window.
        globalThis.NexoraUIRemoteNotice?.('Chromium aberto na área de trabalho do Windows.');
      } else {
        view(id);
      }
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
    if (remote.desktop) return alert('Esta sessão já está em uma janela independente do Chromium no Windows. Use a barra de tarefas ou Alt+Tab para encontrá-la.');
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
  document.querySelector('#remoteShowText')?.addEventListener('change', event => {
    document.querySelector('#remoteText').type = event.target.checked ? 'text' : 'password';
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
