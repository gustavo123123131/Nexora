'use strict';
const $ = selector => document.querySelector(selector);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let state = {sites:[], profiles:[]};
let page = 'profiles';
let busy = false;
let toastTimer = null;
let cloudMode = false;
let browserAvailable = true;
// Vercel defaults to passwordless browser-local metadata. Add ?storage=cloud to
// deliberately opt into the legacy authenticated PostgreSQL deployment.
const browserLocalMode = !['localhost', '127.0.0.1', '[::1]'].includes(location.hostname)
  && new URLSearchParams(location.search).get('storage') !== 'cloud';


async function api(route, body) {
  if (browserLocalMode) return globalThis.NexoraBrowserStore.request(route, body);
  const response = await fetch('/api/' + route, {
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? {} : {'Content-Type':'application/json'},
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: 'no-store', credentials: 'same-origin'
  });
  const data = await response.json();
  if (!response.ok) { const err = new Error(data.error || 'Não foi possível concluir a operação.'); err.status = response.status; throw err; }
  return data;
}
function toast(message, isError=false) {
  const el = $('#toast');
  el.textContent = message;
  el.className = 'toast visible' + (isError ? ' is-error' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.className = 'toast', 4500);
}
async function refresh() {
  try {
    state = await api('state');
    cloudMode = state.capabilities?.mode === 'vercel';
    browserAvailable = state.capabilities?.browser !== false;
    updateEnvironment();
    render();
  } catch (err) {
    if (err.status === 401 && cloudMode) return showLogin();
    toast('Não foi possível carregar os dados: ' + err.message, true);
  }
}
function render() {
  $('#navProfileCount').textContent = state.profiles.length;
  const active = browserLocalMode && globalThis.NexoraRemote?.connected
    ? state.profiles.filter(p => globalThis.NexoraRemote.isRunning(p.id)).length
    : state.profiles.filter(p => p.status === 'running').length;
  $('#statProfiles').textContent = state.profiles.length;
  $('#statActive').textContent = active;
  $('#statSites').textContent = state.sites.length;
  $('.nav-link[data-page="profiles"]').classList.toggle('is-active', page === 'profiles');
  $('.nav-link[data-page="sites"]').classList.toggle('is-active', page === 'sites');
  $('#profileContent').hidden = page !== 'profiles';
  $('#siteContent').hidden = page !== 'sites';
  $('#pageTitle').textContent = page === 'profiles' ? 'Seus perfis' : 'Sites cadastrados';
  $('#breadcrumbCurrent').textContent = page === 'profiles' ? 'Perfis' : 'Sites';
  $('#pageDescription').textContent = page === 'profiles'
    ? (browserAvailable ? 'Gerencie navegadores independentes com experiência mobile Android.' : 'Cadastre e organize perfis na nuvem. Navegadores externos ainda não estão conectados.')
    : 'Configure os endereços que serão abertos nos perfis.';
  $('#primaryAction').innerHTML = '<span class="plus">+</span> ' + (page === 'profiles' ? 'Criar perfil' : 'Adicionar site');
  renderProfiles();
  renderSites();
}
function renderProfiles() {
  const container = $('#profileList');
  if (!state.profiles.length) {
    container.innerHTML = `<div class="empty-state"><div class="empty-art">▣</div><h3>Nenhum perfil por enquanto</h3><p>${state.sites.length ? 'Crie seu primeiro perfil para configurar uma conta independente.' : 'Primeiro cadastre um site. Depois crie perfis independentes.'}</p><button class="btn btn-primary" data-action="${state.sites.length ? 'add-profile' : 'add-site'}">${state.sites.length ? 'Criar primeiro perfil' : 'Cadastrar primeiro site'} →</button></div>`;
    return;
  }
  container.innerHTML = state.profiles.map(profile => {
    const site = state.sites.find(s => s.id === profile.site_id);
    const remoteReady = browserLocalMode && !!globalThis.NexoraRemote?.connected;
    const running = remoteReady ? globalThis.NexoraRemote.isRunning(profile.id) : profile.status === 'running';
    const unavailable = browserLocalMode ? !remoteReady : (profile.status === 'unavailable' || !browserAvailable);
    let actions = '';
    if (browserLocalMode && !remoteReady) {
      actions = '<button class="btn btn-secondary" data-action="remote-connect">Conectar navegador</button>';
    } else if (remoteReady) {
      actions = `<button class="btn ${running ? 'btn-secondary' : 'btn-primary'}" data-action="${running ? 'remote-stop' : 'remote-start'}" data-id="${profile.id}">${running ? '■ Encerrar' : '▶ Abrir'}</button>`;
      if (running) actions += `<button class="btn btn-ghost" data-action="remote-view" data-id="${profile.id}">Ver navegador</button>`;
    } else if (unavailable) {
      actions = '<button class="btn btn-secondary" disabled>Navegador indisponível</button>';
    } else {
      actions = `<button class="btn ${running ? 'btn-secondary' : 'btn-primary'}" data-action="${running ? 'stop' : 'start'}" data-id="${profile.id}">${running ? '■ Encerrar' : '▶ Iniciar'}</button>`;
    }
    const status = unavailable ? '◌ Executor não conectado' : (running ? '● Em execução' : '○ Parado');
    const badge = unavailable ? 'unavailable' : (running ? 'running' : '');
    return `<article class="profile-card"><div class="profile-icon">▣</div><div class="profile-info"><div class="card-heading"><h3>${escapeHTML(profile.name)}</h3><span class="status-badge ${badge}">${status}</span></div><div class="card-info">${escapeHTML(site?.name || 'Site não encontrado')} · ${escapeHTML(site?.url || '')}</div></div><div class="card-actions">${actions}<button class="icon-button" data-action="delete-profile" data-id="${profile.id}" title="Excluir cadastro do perfil" aria-label="Excluir ${escapeHTML(profile.name)}">×</button></div></article>`;
  }).join('');
}
function renderSites() {
  const container = $('#siteList');
  if (!state.sites.length) {
    container.innerHTML = '<div class="empty-state"><div class="empty-art">◎</div><h3>Você ainda não cadastrou sites</h3><p>Adicione um endereço para selecioná-lo ao criar um perfil.</p><button class="btn btn-primary" data-action="add-site">+ Cadastrar site</button></div>';
    return;
  }
  container.innerHTML = state.sites.map(site => `<article class="site-card"><div class="site-icon">◎</div><div class="site-info"><div class="card-heading"><h3>${escapeHTML(site.name)}</h3></div><div class="card-info">${escapeHTML(site.url)}</div></div><div class="card-actions"><button class="btn btn-ghost" data-action="edit-site" data-id="${site.id}">Editar</button><button class="icon-button" data-action="delete-site" data-id="${site.id}" title="Excluir site" aria-label="Excluir ${escapeHTML(site.name)}">×</button></div></article>`).join('');
}
function openModal(kind, item) {
  const isSite = kind === 'site';
  $('#modal').hidden = false;
  $('#modalTitle').textContent = isSite ? (item ? 'Editar site' : 'Adicionar site') : 'Novo perfil';
  $('#modalDescription').textContent = isSite ? 'Defina o nome e o endereço para abrir no navegador.' : 'Os perfis são independentes; abertura do navegador depende do executor.';
  $('#modalSubmit').textContent = item ? 'Salvar alterações' : (isSite ? 'Adicionar site' : 'Criar perfil');
  $('#modalFields').innerHTML = isSite
    ? `<div class="field"><label for="fieldName">Nome do site</label><input id="fieldName" name="name" type="text" maxlength="80" placeholder="Ex.: Site principal" required value="${escapeHTML(item?.name || '')}"></div><div class="field"><label for="fieldUrl">Endereço (URL)</label><input id="fieldUrl" name="url" type="url" maxlength="2048" placeholder="https://exemplo.com" required value="${escapeHTML(item?.url || '')}"><div class="field-note">Use http:// ou https:// no endereço.</div></div>`
    : `<div class="field"><label for="fieldName">Nome do perfil</label><input id="fieldName" name="name" type="text" maxlength="80" placeholder="Ex.: Conta 01" required></div><div class="field"><label for="fieldSite">Site de destino</label><select id="fieldSite" name="site_id" required><option value="">Selecione um site</option>${state.sites.map(site => `<option value="${site.id}">${escapeHTML(site.name)}</option>`).join('')}</select><div class="field-note">${browserAvailable ? 'Chromium mobile · sessão persistente.' : 'Cadastro na nuvem · navegador remoto ainda não disponível.'}</div></div>`;
  $('#modalForm').dataset.kind = kind;
  $('#modalForm').dataset.id = item?.id || '';
  $('#fieldName').focus();
}
function closeModal(){ $('#modal').hidden = true; $('#modalForm').reset(); }
async function perform(route, payload, successText) {
  if (busy) return;
  busy = true;
  document.querySelectorAll('button[data-action], #modalSubmit').forEach(b => b.disabled = true);
  try {
    const result = await api(route, payload);
    await refresh();
    if (successText) toast(successText);
    if (result.warning) toast(result.warning, true);
    return true;
  } catch (err) {
    toast(err.message, true);
    return false;
  } finally {
    busy = false;
    document.querySelectorAll('button[data-action], #modalSubmit').forEach(b => b.disabled = false);
  }
}
document.addEventListener('click', async event => {
  const nav = event.target.closest('[data-page]');
  if (nav) {page=nav.dataset.page;render();return;}
  const btn = event.target.closest('[data-action]');
  if (!btn || busy) return;
  const action = btn.dataset.action;
  const id = btn.dataset.id;
  if (action === 'add-site') return openModal('site');
  if (action === 'add-profile') {
    if (!state.sites.length) { page='sites';render();toast('Cadastre um site antes de criar um perfil.');return openModal('site'); }
    return openModal('profile');
  }
  if (action === 'edit-site') return openModal('site', state.sites.find(s => s.id === id));
  if (action === 'visit') {
    const profile = state.profiles.find(p => p.id === id);
    const site = state.sites.find(s => s.id === profile?.site_id);
    if (!site) return toast('Site não encontrado.', true);
    if (!confirm('Abrir "' + site.name + '" numa aba comum? A aba NÃO terá cookies isolados de outras contas. Não é um teste válido de multi-login.')) return;
    window.open(site.url, '_blank', 'noopener,noreferrer');
    return;
  }
  if (action === 'remote-connect') return globalThis.NexoraRemote.connect();
  if (action === 'remote-start') {
    const profile = state.profiles.find(p => p.id === id);
    const site = state.sites.find(s => s.id === profile?.site_id);
    if (!site) return toast('Site não encontrado.', true);
    return globalThis.NexoraRemote.start(id, site.url);
  }
  if (action === 'remote-stop') return globalThis.NexoraRemote.stop(id);
  if (action === 'remote-view') return globalThis.NexoraRemote.view(id);
  if (action === 'start') return perform('profiles/start', {id}, 'Navegador iniciado. Faça login manualmente na janela aberta.');
  if (action === 'stop') return perform('profiles/stop', {id}, 'Perfil encerrado. Sessão salva.');
  if (action === 'delete-profile') {
    const profile = state.profiles.find(p => p.id === id);
    if (browserLocalMode && globalThis.NexoraRemote?.isRunning(id)) return toast('Encerre o navegador remoto deste perfil antes de excluir o cadastro.', true);
    if (confirm(`Excluir o perfil "${profile?.name || ''}"? ${browserLocalMode ? 'O cadastro neste navegador será removido, mas dados e cookies já salvos no executor REMOTO NÃO serão apagados.' : (browserAvailable ? 'Cookies e dados locais serão apagados definitivamente.' : 'O registro será removido do banco de dados.')}`)) return perform('profiles/delete', {id}, 'Perfil excluído.');
  }
  if (action === 'delete-site') {
    const site = state.sites.find(s => s.id === id);
    if (confirm(`Excluir o site "${site?.name || ''}"?`)) return perform('sites/delete', {id}, 'Site excluído.');
  }
});
$('#primaryAction').addEventListener('click', () => {
  if (page === 'sites') openModal('site');
  else if (!state.sites.length) {page='sites';render();toast('Cadastre um site antes de criar um perfil.');openModal('site');}
  else openModal('profile');
});
$('#modalClose').addEventListener('click', closeModal);
$('#modalCancel').addEventListener('click', closeModal);
$('#modal').addEventListener('click', event => {if (event.target.id === 'modal') closeModal();});
document.addEventListener('keydown', event => {if (event.key === 'Escape' && !$('#modal').hidden) closeModal();});
$('#modalForm').addEventListener('submit', async event => {
  event.preventDefault();
  if (busy) return;
  const form = event.currentTarget;
  const kind = form.dataset.kind;
  const id = form.dataset.id;
  const name = $('#fieldName').value;
  const payload = kind === 'site' ? {name, url:$('#fieldUrl').value} : {name, site_id:$('#fieldSite').value};
  const route = kind === 'site' ? (id ? 'sites/update':'sites/create') : 'profiles/create';
  if (id) payload.id = id;
  const ok = await perform(route, payload, 'Salvo com sucesso.');
  if (ok) closeModal();
});
function updateEnvironment() {
  $('#cloudNotice').hidden = browserAvailable;
  $('#logoutButton').hidden = browserLocalMode || !cloudMode;
  $('#runnerButton').hidden = !browserLocalMode;
  if (browserLocalMode) {
    $('#runnerButton').textContent = globalThis.NexoraRemote?.connected ? '◉ Navegador conectado' : 'Conectar navegador';
  }
  $('#importButton').hidden = !cloudMode;
  $('#runtimeStatus').textContent = browserLocalMode ? 'Cadastros neste navegador' : (cloudMode ? 'Painel hospedado na Vercel' : 'Executando localmente');
  $('#connectionLabel').textContent = browserLocalMode ? 'Modo sem senha' : (cloudMode ? 'Nuvem conectada' : 'Conexão local');
  $('#versionLabel').textContent = browserLocalMode ? 'Nexora · Vercel / dados locais' : (cloudMode ? 'Nexora · Vercel' : 'Nexora · modo local');
  $('#profileHelper').textContent = browserAvailable ? 'Dados isolados por perfil' : 'Executor não conectado';
  $('#cloudNotice p').textContent = browserLocalMode
    ? (globalThis.NexoraRemote?.connected
      ? 'Executor Chromium conectado: cada perfil tem uma sessão real separada. Os logins são guardados no volume persistente do executor, não na Vercel. O modo mobile é emulado.'
      : 'Perfis cadastrados neste navegador. Para fazer multi-login de verdade, conecte o executor Chromium remoto. A Vercel sozinha não mantém sessões independentes.')
    : 'Perfis e sites ficam no banco remoto, mas o navegador persistente exige um executor dedicado. A Vercel sozinha não abre sessões independentes.';
  $('.device-tile strong').textContent = browserAvailable ? 'Android Mobile' : 'Executor remoto';
  $('.device-tile span:last-child').textContent = browserAvailable ? 'Pixel 7 · Chromium' : 'Não conectado';
}
function showLogin(error='') {
  $('#mainShell').hidden = true;
  $('#loginScreen').hidden = false;
  $('#loginError').textContent = error;
}
function showApp() {
  $('#loginScreen').hidden = true;
  $('#mainShell').hidden = false;
}
$('#loginForm').addEventListener('submit', async event => {
  event.preventDefault();
  $('#loginError').textContent = '';
  try {
    await api('auth/login', {password:$('#loginPassword').value});
    $('#loginPassword').value = '';
    showApp();
    await refresh();
  } catch (err) {showLogin(err.message);}
});
$('#logoutButton').addEventListener('click', async () => {
  try {await api('auth/logout', {});} catch (e) {toast(e.message, true);}
  showLogin();
});
$('#importButton').addEventListener('click', () => $('#importFile').click());
$('#importFile').addEventListener('change', async event => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    if (file.size > 240000) throw new Error('O arquivo é muito grande para importar.');
    const settings = JSON.parse(await file.text());
    if (!confirm('Importar sites e perfis do settings.json? Cookies e logins locais NÃO serão transferidos.')) return;
    const result = await api('import', settings);
    toast(`${result.sites_importados} sites e ${result.perfis_importados} perfis importados.`);
    await refresh();
  } catch (err) {toast(err.message, true);}
  finally {event.target.value = '';}
});
async function initialize() {
  if (browserLocalMode) {
    cloudMode = true;
    browserAvailable = false;
    showApp();
    await refresh();
    await globalThis.NexoraRemote?.initialize();
    return;
  }
  try {
    const status = await api('auth/status');
    cloudMode = true;
    if (!status.authenticated) return showLogin();
    showApp();
    await refresh();
  } catch (err) {
    // Old local server has no /api/auth/status. Keep the legacy mode usable.
    if (err.status === 404) {showApp();await refresh();}
    else showLogin(err.message);
  }
}
initialize();
setInterval(() => {if (!busy && !document.hidden && !$('#mainShell').hidden) refresh();}, 10000);

// Called by remote_browser.js after a successful authenticated health check.
globalThis.NexoraUIRemoteConnection = function (connected) {
  browserAvailable = Boolean(connected);
  updateEnvironment();
  render();
};

// Remote Chromium controller reads ONLY metadata; session credentials stay in runner.
globalThis.NexoraGetProfiles = () => state.profiles.slice();
