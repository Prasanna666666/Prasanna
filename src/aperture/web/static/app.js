/* Lumo front end. Plain JavaScript, no libraries. All dynamic text is added with textContent (never innerHTML). */
(() => {
  'use strict';
  const token = document.querySelector('meta[name="lumo-token"]').content;
  const $ = (s) => document.querySelector(s);
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const photoUrl = (id, kind) => `/api/photo/${id}/${kind}?t=${encodeURIComponent(token)}`;
  const api = (path, opts = {}) => fetch(path, { ...opts, headers: { 'X-Lumo-Token': token, ...(opts.headers || {}) } });
  const uid = () => (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2));

  const thread = $('#thread'), welcome = $('#welcome'), input = $('#input'), send = $('#send'), form = $('#composer');
  let conv = uid(), history = [], controller = null, busy = false, stick = true;

  // ---------------------------------------------------------------- small helpers
  const sparkle = () => { const a = el('div', 'avatar'); a.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2l2.2 6.3L21 10l-6.8 1.7L12 18l-2.2-6.3L3 10l6.8-1.7z"/></svg>'; return a; };
  const scrollDown = (force) => { if (force || stick) window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' }); };
  window.addEventListener('scroll', () => { stick = window.innerHeight + window.scrollY >= document.body.scrollHeight - 160; }, { passive: true });

  // markdown-lite, built with DOM nodes: **bold**, `code`, - lists, paragraphs
  function inline(parent, text) {
    const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
    let last = 0, m;
    while ((m = re.exec(text))) {
      if (m.index > last) parent.append(text.slice(last, m.index));
      const tok = m[0];
      parent.append(tok.startsWith('**') ? el('strong', '', tok.slice(2, -2)) : el('code', '', tok.slice(1, -1)));
      last = m.index + tok.length;
    }
    if (last < text.length) parent.append(text.slice(last));
  }
  function renderText(node, text) {
    node.replaceChildren();
    let list = null;
    for (const para of text.split(/\n{2,}/)) {
      list = null;
      const lines = para.split('\n');
      let p = null;
      for (const line of lines) {
        const li = /^\s*[-*]\s+(.*)$/.exec(line);
        if (li) {
          if (!list) { list = el('ul'); node.append(list); p = null; }
          const item = el('li'); inline(item, li[1]); list.append(item);
        } else {
          list = null;
          if (!p) { p = el('p'); node.append(p); } else p.append(el('br'));
          inline(p, line);
        }
      }
    }
  }

  // ---------------------------------------------------------------- photos
  function makeGallery(host) {
    const root = el('div', 'gallery'), head = el('div', 'gal-head'), grid = el('div', 'grid');
    root.append(head, grid); host.append(root);
    return { root, head, grid, ids: [], total: 0, more: null };
  }
  function addTiles(g, ids) {
    for (const id of ids) {
      const t = el('button', 'tile'); t.type = 'button'; t.setAttribute('aria-label', 'Open photo');
      const img = new Image(); img.alt = ''; img.decoding = 'async'; img.loading = 'lazy';
      img.onload = () => t.classList.add('loaded');
      img.onerror = () => t.classList.add('missing', 'loaded');
      img.src = photoUrl(id, 'thumb');
      t.append(img);
      g.ids.push(id);
      const at = g.ids.length - 1;
      t.addEventListener('click', () => openLightbox(g.ids, at));
      g.grid.append(t);
    }
  }
  function showPreview(msg, ids, total) {
    msg.gallery = msg.gallery || makeGallery(msg.body);
    const g = msg.gallery; g.ids = []; g.grid.replaceChildren();
    g.head.replaceChildren(el('span', 'count', `${total.toLocaleString()} quick matches`), el('span', 'refining', 'checking with the AI'));
    addTiles(g, ids);
  }
  function showResults(msg, d) {
    msg.gallery = msg.gallery || makeGallery(msg.body);
    const g = msg.gallery; g.ids = []; g.grid.replaceChildren(); g.total = d.total;
    g.head.replaceChildren(el('span', 'count', d.kind === 'count' ? `${d.total.toLocaleString()} photos` : `${d.total.toLocaleString()} photo${d.total === 1 ? '' : 's'}`));
    addTiles(g, d.ids);
    if (g.more) g.more.remove();
    if (g.ids.length < g.total) {
      g.more = el('button', 'pill more', g.ids.length ? 'Show more' : 'Show these photos');
      g.more.type = 'button';
      g.more.addEventListener('click', async () => {
        g.more.disabled = true;
        try {
          const r = await api(`/api/results?conv=${encodeURIComponent(conv)}&offset=${g.ids.length}`);
          const data = await r.json();
          addTiles(g, data.ids);
        } catch (_) { /* keep what is shown */ }
        if (g.ids.length >= g.total) g.more.remove(); else g.more.disabled = false;
      });
      g.root.append(g.more);
    }
  }

  // ---------------------------------------------------------------- lightbox
  const lb = $('#lightbox'), lbImg = $('#lb-img'), lbCap = $('#lb-cap');
  let lbIds = [], lbAt = 0;
  async function openLightbox(ids, at) { lbIds = ids; lbAt = at; lb.hidden = false; document.body.style.overflow = 'hidden'; await showLightbox(); }
  async function showLightbox() {
    const id = lbIds[lbAt];
    lbImg.onerror = () => { lbImg.onerror = null; lbImg.src = photoUrl(id, 'thumb'); };
    lbImg.src = photoUrl(id, 'preview');
    lbCap.textContent = '';
    try {
      const r = await api(`/api/item/${id}`);
      if (!r.ok || lbIds[lbAt] !== id) return;
      const d = await r.json();
      const parts = [d.taken && String(d.taken).slice(0, 10), d.place, d.camera].filter(Boolean);
      lbCap.replaceChildren(el('b', '', d.name || ''), parts.length ? '  ·  ' + parts.join('  ·  ') : '');
    } catch (_) { /* caption is optional */ }
  }
  const lbStep = (n) => { lbAt = (lbAt + n + lbIds.length) % lbIds.length; showLightbox(); };
  const lbClose = () => { lb.hidden = true; document.body.style.overflow = ''; lbImg.removeAttribute('src'); };
  $('#lb-close').addEventListener('click', lbClose);
  $('#lb-prev').addEventListener('click', () => lbStep(-1));
  $('#lb-next').addEventListener('click', () => lbStep(1));
  lb.addEventListener('click', (e) => { if (e.target === lb) lbClose(); });

  // ---------------------------------------------------------------- conversation
  function addUser(text) {
    const m = el('div', 'msg user'); m.append(el('div', 'bubble', text)); thread.append(m); return m;
  }
  function addBot() {
    const m = el('div', 'msg bot'), body = el('div', 'body'), text = el('div', 'text');
    const typing = el('span', 'typing'); typing.append(el('i'), el('i'), el('i')); text.append(typing);
    body.append(text); m.append(sparkle(), body); thread.append(m);
    return { root: m, body, text, typing, gallery: null, raw: '' };
  }
  function handle(msg, event, d) {
    if (event === 'preview') showPreview(msg, d.ids, d.total);
    else if (event === 'delta') { msg.raw += d.text; msg.text.classList.add('streaming'); renderText(msg.text, msg.raw); }
    else if (event === 'reply') { msg.raw = d.text; renderText(msg.text, d.text); }
    else if (event === 'results') showResults(msg, d);
    else if (event === 'notes') addNotes(msg, d);
    else if (event === 'error') { msg.text.classList.remove('streaming'); msg.text.replaceChildren(); msg.body.append(el('div', 'error', d.message)); }
    else if (event === 'done') {
      msg.text.classList.remove('streaming');
      if (msg.gallery && !msg.gallery.total) { msg.gallery.root.remove(); msg.gallery = null; }  // a preview that was not confirmed
      if (d.kind !== 'error' && d.text) history.push({ role: 'assistant', text: d.text });
      addTrace(msg, d);
      if (d.took >= 0.01) msg.body.append(el('div', 'meta', d.took < 0.2 ? 'instant' : `answered in ${d.took.toFixed(1)}s${breakdown(d)}`));
    }
    if (event === 'results') addNotes(msg, d);
    scrollDown();
  }
  const STEP_NAMES = { route: 'deciding', decide: 'deciding', context: 'library lookup', plan: 'AI plan', dates: 'date check', tools: 'tools', search: 'search', first_words: 'first words' };
  function breakdown(d) {                      // when an answer is slow, show where the time went
    if (d.took < 3 || !d.timings) return '';
    const parts = Object.entries(d.timings).filter(([, v]) => v >= 0.1).map(([k, v]) => `${STEP_NAMES[k] || k} ${v.toFixed(1)}s`);
    return parts.length ? `  \u00b7  ${parts.join('  \u00b7  ')}` : '';
  }
  function addTrace(msg, d) {                  // "How I answered": exactly what each step was given and what it returned
    if (!d.trace || !d.trace.length) return;
    const box = el('details', 'trace'), head = el('summary', '', `How I answered (${d.trace.length} step${d.trace.length === 1 ? '' : 's'})`);
    box.append(head);
    d.trace.forEach((c, i) => {
      box.append(el('h4', '', `Step ${i + 1}${c.tools && c.tools.length ? '  \u00b7  tools: ' + c.tools.join(', ') : ''}`));
      box.append(el('div', 'lbl', 'Instructions it was given'), el('pre', '', c.system || '(none)'));
      box.append(el('div', 'lbl', 'Conversation'), el('pre', '', (c.messages || []).map((m) => `${m.role}: ${m.text}`).join('\n')));
      const out = [c.output, ...(c.tool_calls || []).map((t) => `tool call: ${t.name}(${JSON.stringify(t.arguments)})`)].filter(Boolean).join('\n');
      box.append(el('div', 'lbl', 'What it answered'), el('pre', '', out || '(nothing)'));
    });
    msg.body.append(box);
  }
  function addNotes(msg, d) {
    for (const t of d.notes || []) msg.body.append(el('div', 'note', t));
    for (const t of d.warnings || []) msg.body.append(el('div', 'note warn', t));
  }
  function parseBlock(block) {
    let event = 'message', data = '';
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      else if (line.startsWith('data:')) data += line.slice(5).trim();
    }
    return [event, data ? JSON.parse(data) : {}];
  }
  function setBusy(on) { busy = on; document.body.classList.toggle('busy', on); send.disabled = !on && !input.value.trim(); }

  async function ask(text) {
    text = text.trim();
    if (!text || busy) return;
    welcome.hidden = true;
    addUser(text);
    const bot = addBot();
    history.push({ role: 'user', text });
    input.value = ''; autosize(); setBusy(true); stick = true; scrollDown(true);
    controller = new AbortController();
    try {
      const res = await fetch('/api/chat', {
        method: 'POST', signal: controller.signal,
        headers: { 'Content-Type': 'application/json', 'X-Lumo-Token': token },
        body: JSON.stringify({ message: text, conv, history: history.slice(0, -1).slice(-8).map((h) => [h.role, h.text]) }),
      });
      if (!res.ok || !res.body) throw new Error(`The server answered ${res.status}`);
      const reader = res.body.getReader(), dec = new TextDecoder();
      let buf = '';
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let i;
        while ((i = buf.indexOf('\n\n')) >= 0) {
          const [event, data] = parseBlock(buf.slice(0, i)); buf = buf.slice(i + 2);
          handle(bot, event, data);
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') handle(bot, 'error', { message: `Lumo could not answer: ${err.message}` });
    } finally {
      bot.text.classList.remove('streaming'); if (bot.typing.isConnected) bot.typing.remove();
      setBusy(false); controller = null; input.focus();
    }
  }

  function newChat() {                       // instant: nothing is asked of the server
    if (controller) controller.abort();
    conv = uid(); history = []; thread.replaceChildren(); welcome.hidden = false; setBusy(false);
    input.value = ''; autosize(); window.scrollTo({ top: 0 }); input.focus();
  }

  // ---------------------------------------------------------------- composer
  function autosize() { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 150) + 'px'; send.disabled = !busy && !input.value.trim(); }
  input.addEventListener('input', autosize);
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); ask(input.value); } });
  form.addEventListener('submit', (e) => { e.preventDefault(); if (busy && controller) controller.abort(); else ask(input.value); });
  $('#newchat').addEventListener('click', newChat);
  document.addEventListener('keydown', (e) => {
    if (!lb.hidden) { if (e.key === 'Escape') lbClose(); else if (e.key === 'ArrowLeft') lbStep(-1); else if (e.key === 'ArrowRight') lbStep(1); return; }
    if (e.key === '/' && document.activeElement !== input) { e.preventDefault(); input.focus(); }
  });

  // ---------------------------------------------------------------- status chips + first screen
  function chip(label, state, action) {
    const c = el('span', `chip ${state}`); c.append(el('span', 'dot'), label);
    if (action) { const b = el('button', '', action.text); b.type = 'button'; b.addEventListener('click', action.run); c.append(b); }
    return c;
  }
  async function refreshStatus() {
    try {
      const s = await (await api('/api/status')).json();
      const chips = [chip(s.search_ready ? 'Search ready' : (s.warm_problem ? 'Search unavailable' : 'Search warming up'), s.search_ready ? 'ok' : (s.warm_problem ? 'bad' : 'warn')),
                     chip(s.ai ? s.model : 'AI offline', s.ai ? 'ok' : 'bad'),
                     ];
      $('#build').textContent = s.build ? `build ${s.build}` : '';
      if (s.photos) chips.push(chip(`${s.photos.toLocaleString()} photos`, 'ok'));
      if (s.indexing) chips.push(chip('Indexing', 'warn'));
      else if (s.paused_for_chat) chips.push(chip('Indexing paused', 'warn', { text: 'Resume', run: async () => { await api('/api/scan/resume', { method: 'POST' }); refreshStatus(); } }));
      $('#chips').replaceChildren(...chips);
      $('#warm').textContent = s.warm_problem ? `Image search could not start: ${s.warm_problem}` : (!s.ai ? 'The AI model is not reachable. Is Ollama running?' : 'Warming up: the first answer can take a little longer.');
      document.body.classList.toggle('warming', !s.search_ready || !s.ai);
    } catch (_) { $('#chips').replaceChildren(chip('Lumo is not responding', 'bad')); }
  }
  async function loadIdeas() {
    let ideas = [];
    try { ideas = (await (await api('/api/suggestions')).json()).ideas || []; } catch (_) { /* none */ }
    $('#ideas').replaceChildren(...ideas.slice(0, 6).map((t) => { const b = el('button', 'idea', t); b.type = 'button'; b.addEventListener('click', () => ask(t)); return b; }));
  }
  const h = new Date().getHours();
  $('#greeting').textContent = h < 5 ? 'Hello' : h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
  autosize(); refreshStatus(); loadIdeas(); setInterval(refreshStatus, 4000); input.focus();
})();
