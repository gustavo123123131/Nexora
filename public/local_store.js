/* Nexora: browser-local metadata mode for Vercel.
   Saves ONLY site/profile labels and URLs in this browser origin.
   This does NOT create separate Chromium sessions or store site logins. */
(function () {
  'use strict';
  const KEY = 'nexora.site-profiles.v1';
  const HEX_ID = /^[a-f0-9]{32}$/;

  function read() {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { sites: [], profiles: [] };
    let data;
    try { data = JSON.parse(raw); } catch (_) {
      throw new Error('Dados locais ilegíveis. Faça backup antes de limpar os dados do navegador.');
    }
    if (!data || !Array.isArray(data.sites) || !Array.isArray(data.profiles)) {
      throw new Error('Formato dos dados locais inválido.');
    }
    return data;
  }
  function save(data) {
    try { localStorage.setItem(KEY, JSON.stringify(data)); }
    catch (_) { throw new Error('Não foi possível salvar neste navegador. Verifique se o armazenamento está disponível.'); }
  }
  function name(value) {
    if (typeof value !== 'string' || !value.trim() || value.trim().length > 80 ||
        /[\u0000-\u001f]/.test(value)) throw new Error('Informe um nome válido com até 80 caracteres.');
    return value.trim();
  }
  function url(value) {
    if (typeof value !== 'string' || value.length > 2048 || /[\u0000-\u0020\\]/.test(value))
      throw new Error('URL inválida.');
    let parsed;
    try { parsed = new URL(value); } catch (_) { throw new Error('URL inválida. Use https:// ou http://.'); }
    if (!['http:', 'https:'].includes(parsed.protocol) || !parsed.hostname ||
        parsed.username || parsed.password || parsed.hostname.endsWith('.'))
      throw new Error('Use uma URL http(s) válida, sem credenciais.');
    return value.trim();
  }
  function id() {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    return Array.from(bytes, n => n.toString(16).padStart(2, '0')).join('');
  }
  function requireId(value) {
    if (typeof value !== 'string' || !HEX_ID.test(value)) throw new Error('ID inválido.');
    return value;
  }
  function state(data) {
    return {
      sites: data.sites,
      profiles: data.profiles.map(p => ({ ...p, status: 'unavailable' })),
      capabilities: {
        mode: 'vercel', browser: false, storage: 'browser',
        reason: 'Cadastros guardados somente neste navegador. Nenhum executor remoto foi conectado.'
      }
    };
  }
  function request(route, body) {
    const data = read();
    if (route === 'state') return state(data);
    if (!body || typeof body !== 'object' || Array.isArray(body)) throw new Error('Dados inválidos.');
    if (route === 'sites/create') {
      const site = { id: id(), name: name(body.name), url: url(body.url) };
      data.sites.push(site); save(data); return site;
    }
    if (route === 'sites/update') {
      const item = data.sites.find(s => s.id === requireId(body.id));
      if (!item) throw new Error('Site não encontrado.');
      const updated = { ...item, name: name(body.name), url: url(body.url) };
      data.sites = data.sites.map(s => s.id === item.id ? updated : s);
      save(data); return updated;
    }
    if (route === 'sites/delete') {
      const siteId = requireId(body.id);
      if (data.profiles.some(p => p.site_id === siteId)) throw new Error('Exclua os perfis vinculados primeiro.');
      if (!data.sites.some(s => s.id === siteId)) throw new Error('Site não encontrado.');
      data.sites = data.sites.filter(s => s.id !== siteId); save(data); return { ok: true };
    }
    if (route === 'profiles/create') {
      if (!data.sites.some(s => s.id === body.site_id)) throw new Error('Selecione um site cadastrado.');
      const profile = { id: id(), name: name(body.name), site_id: body.site_id };
      data.profiles.push(profile); save(data); return { ...profile, status: 'unavailable' };
    }
    if (route === 'profiles/delete') {
      const profileId = requireId(body.id);
      if (!data.profiles.some(p => p.id === profileId)) throw new Error('Perfil não encontrado.');
      data.profiles = data.profiles.filter(p => p.id !== profileId); save(data); return { ok: true };
    }
    if (route === 'import') {
      if (!Array.isArray(body.sites) || !Array.isArray(body.profiles) ||
          body.sites.length > 500 || body.profiles.length > 500)
        throw new Error('Arquivo settings.json inválido (até 500 sites e 500 perfis).');
      const next = { sites: [...data.sites], profiles: [...data.profiles] };
      let sites = 0, profiles = 0;
      for (const s of body.sites) {
        if (!s || typeof s !== 'object') throw new Error('Site inválido.');
        const value = { id: requireId(s.id), name: name(s.name), url: url(s.url) };
        if (!next.sites.some(existing => existing.id === value.id)) { next.sites.push(value); sites++; }
      }
      for (const p of body.profiles) {
        if (!p || typeof p !== 'object') throw new Error('Perfil inválido.');
        const value = { id: requireId(p.id), name: name(p.name), site_id: requireId(p.site_id) };
        if (!next.sites.some(s => s.id === value.site_id)) throw new Error('Perfil referencia um site inexistente.');
        if (!next.profiles.some(existing => existing.id === value.id)) { next.profiles.push(value); profiles++; }
      }
      save(next);
      return { ok: true, sites_importados: sites, perfis_importados: profiles };
    }
    if (route === 'profiles/start' || route === 'profiles/stop') {
      throw new Error('Não existe executor remoto. Uma aba comum não isola cookies de perfis.');
    }
    throw new Error('Operação não disponível.');
  }
  globalThis.NexoraBrowserStore = Object.freeze({ request });
})();
