/* Lumo front end. Plain JavaScript, no libraries. All dynamic text is added with textContent (never innerHTML). */
(() => {
  'use strict';
  const token = document.querySelector('meta[name="lumo-token"]').content;
  const $ = (s) => document.querySelector(s);
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const SHOW_TRACE = new URLSearchParams(location.search).has('trace');  // the step-by-step panel is for debugging: off unless asked for
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
    const root = el('div', 'gallery'), head = el('div', 'gal-head'), readings = el('div', 'readings'), grid = el('div', 'grid');
    root.append(head, readings, grid); host.append(root);
    return { root, head, readings, grid, ids: [], total: 0, more: null, group: -1 };
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
    const g = msg.gallery; g.ids = []; g.grid.replaceChildren(); g.total = d.total; g.rid = d.rid || '';
    g.head.replaceChildren(el('span', 'count', d.kind === 'count' ? `${d.total.toLocaleString()} photos` : `${d.total.toLocaleString()} photo${d.total === 1 ? '' : 's'}`));
    addTiles(g, d.ids);
    showReadings(g, d.groups || []);
    showMore(g);
  }
  // Every way the query could be read, with how many photos each finds: pick one to see its photos.
  function showReadings(g, groups) {
    g.readings.replaceChildren();
    if (groups.length < 2) return;
    groups.forEach((r, i) => {
      const b = el('button', 'reading' + (i === 0 ? ' active' : ''), `${r.label} \u00b7 ${r.count.toLocaleString()}`);
      b.type = 'button';
      b.addEventListener('click', async () => {
        g.readings.querySelectorAll('.reading').forEach((x) => x.classList.remove('active'));
        b.classList.add('active');
        g.group = i; g.ids = []; g.grid.replaceChildren();
        try {
          const data = await (await api(`/api/results?conv=${encodeURIComponent(conv)}&rid=${encodeURIComponent(g.rid || '')}&offset=0&group=${i}`)).json();
          g.total = data.total;
          g.head.replaceChildren(el('span', 'count', `${data.total.toLocaleString()} photo${data.total === 1 ? '' : 's'}`));
          addTiles(g, data.ids);
        } catch (_) { /* keep what is shown */ }
        showMore(g);
      });
      g.readings.append(b);
    });
  }
  function showMore(g) {
    if (g.more) g.more.remove();
    if (g.ids.length < g.total) {
      g.more = el('button', 'pill more', g.ids.length ? 'Show more' : 'Show these photos');
      g.more.type = 'button';
      g.more.addEventListener('click', async () => {
        g.more.disabled = true;
        try {
          const r = await api(`/api/results?conv=${encodeURIComponent(conv)}&rid=${encodeURIComponent(g.rid || '')}&offset=${g.ids.length}&group=${g.group}`);
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
  function showStatus(msg, text) {            // what it is doing right now, under the dots, until the answer starts
    if (!msg.typing.isConnected) return;
    let line = msg.text.querySelector('.stage');
    if (!line) { line = el('div', 'stage'); msg.text.append(line); }
    line.textContent = text + '\u2026';
  }
  function handle(msg, event, d) {
    if (event !== 'status') { const s = msg.text.querySelector('.stage'); if (s) s.remove(); }  // the answer has started: no more progress line
    if (event === 'status') showStatus(msg, d.text);
    else if (event === 'preview') showPreview(msg, d.ids, d.total);
    else if (event === 'delta') { msg.raw += d.text; msg.text.classList.add('streaming'); renderText(msg.text, msg.raw); }
    else if (event === 'reply') { msg.raw = d.text; renderText(msg.text, d.text); }
    else if (event === 'results') showResults(msg, d);
    else if (event === 'notes') addNotes(msg, d);
    else if (event === 'error') { msg.text.classList.remove('streaming'); msg.text.replaceChildren(); msg.body.append(el('div', 'error', d.message)); }
    else if (event === 'done') {
      msg.text.classList.remove('streaming');
      if (msg.gallery && !msg.gallery.total) { msg.gallery.root.remove(); msg.gallery = null; }  // a preview that was not confirmed
      if (d.kind !== 'error' && d.text) history.push({ role: 'assistant', text: d.record || d.text });
      if (SHOW_TRACE) addTrace(msg, d);
      const who = d.timings && d.timings.understood === 'cloud' ? '  \u00b7  \u2601 cloud understood the request' : (d.timings && d.timings.understood === 'local' ? '  \u00b7  understood locally' : '');
      if (d.took >= 0.01) msg.body.append(el('div', 'meta', d.took < 0.2 ? 'instant' : `answered in ${d.took.toFixed(1)}s${breakdown(d)}${who}`));
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
  let notReady = false;  // the library is still loading: a question would only time out, so the box waits
  function setBusy(on) { busy = on; document.body.classList.toggle('busy', on); send.disabled = notReady || (!on && !input.value.trim()); }

  async function ask(text) {
    text = text.trim();
    if (!text || busy || notReady) return;
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
  function autosize() { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 150) + 'px'; send.disabled = notReady || (!busy && !input.value.trim()); }
  input.addEventListener('input', autosize);
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); ask(input.value); } });
  form.addEventListener('submit', (e) => { e.preventDefault(); if (busy && controller) controller.abort(); else ask(input.value); });
  $('#newchat').addEventListener('click', newChat);
  $('#topsearch').addEventListener('submit', (e) => { e.preventDefault(); const t = $('#topq').value.trim(); if (!t) return; $('#topq').value = ''; go('search'); ask(t); });
  document.addEventListener('keydown', (e) => {
    if (!lb.hidden) { if (e.key === 'Escape') lbClose(); else if (e.key === 'ArrowLeft') lbStep(-1); else if (e.key === 'ArrowRight') lbStep(1); return; }
    if (e.key === '/' && !/^(INPUT|TEXTAREA)$/.test(document.activeElement ? document.activeElement.tagName : '')) { e.preventDefault(); (where().page === 'search' ? input : $('#topq')).focus(); }
  });

  // ---------------------------------------------------------------- navigation, theme and the browsing pages
  const SVG = 'http://www.w3.org/2000/svg';
  const icon = (d) => { const svg = document.createElementNS(SVG, 'svg'), path = document.createElementNS(SVG, 'path'); svg.setAttribute('viewBox', '0 0 24 24'); path.setAttribute('d', d); svg.append(path); return svg; };
  const NAV = [
    ['search', 'Search', 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14ZM21 21l-4.3-4.3'],
    ['library', 'Library', 'M4 5h16v14H4V5Zm0 10 4-4 4 4 3-3 5 5M9 9h.01'],
    ['trips', 'Trips', 'M2 14l20-8-8 20-3-9-9-3Z'],
    ['places', 'Places', 'M12 21s-7-5.3-7-11a7 7 0 0 1 14 0c0 5.7-7 11-7 11ZM12 12a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z'],
    ['people', 'People', 'M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm-6 9a6 6 0 0 1 12 0M16 4.3a3.5 3.5 0 0 1 0 6.4M18 14.2A6 6 0 0 1 21 20'],
  ];
  const PAGES = NAV.map((n) => n[0]);
  const THEME_ICONS = { dark: 'M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z', light: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4', auto: 'M12 3a9 9 0 1 0 0 18V3Z' };
  function setupTheme() {
    let mode = 'dark'; try { mode = localStorage.getItem('lumo.theme') || 'dark'; } catch (_) { /* private window */ }
    const apply = () => { document.documentElement.dataset.theme = mode; $('#theme').replaceChildren(icon(THEME_ICONS[mode])); $('#theme').title = 'Theme: ' + mode; };
    $('#theme').addEventListener('click', () => { mode = mode === 'auto' ? 'dark' : mode === 'dark' ? 'light' : 'auto'; try { localStorage.setItem('lumo.theme', mode); } catch (_) { /* ignore */ } apply(); });
    apply();
  }
  $('#nav').replaceChildren(...NAV.map(([id, label, d]) => { const a = el('a', 'nav-item'); a.href = '#/' + id; a.dataset.id = id; a.append(icon(d), el('span', '', label)); return a; }));
  function where() {
    const [page, query] = location.hash.replace(/^#\/?/, '').split('?');
    return { page: PAGES.includes(page) ? page : 'search', params: Object.fromEntries(new URLSearchParams(query || '')) };
  }
  function go(page, params) {
    const clean = Object.fromEntries(Object.entries(params || {}).filter(([, v]) => v));
    const qs = new URLSearchParams(clean).toString(), target = '#/' + page + (qs ? '?' + qs : '');
    if (location.hash === target) render(); else location.hash = target;
  }
  const getJson = async (path) => (await api(path)).json();
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const monthLabel = (ym) => MONTHS[+ym.slice(5, 7) - 1] || ym;
  const pageHead = (title, sub, ...right) => { const head = el('div', 'page-head'), left = el('div'); left.append(el('h1', '', title)); if (sub) left.append(el('div', 'sub', sub)); head.append(left, ...right); return head; };
  const seg = (options, current, pick) => { const box = el('div', 'seg'); for (const [value, label] of options) { const b = el('button', value === current ? 'on' : '', label); b.type = 'button'; b.addEventListener('click', () => pick(value)); box.append(b); } return box; };
  const tag = (label, clear) => { const b = el('button', 'tag', label + ' \u00d7'); b.type = 'button'; b.title = 'Remove this filter'; b.addEventListener('click', clear); return b; };
  const dateRange = (a, b) => (a === b ? a : `${a} \u2192 ${b}`);
  function coverCard(id, title, subtitle, count, onClick) {
    const card = el('button', 'cover'); card.type = 'button';
    const img = new Image(); img.alt = ''; img.decoding = 'async'; img.loading = 'lazy'; img.onload = () => card.classList.add('loaded'); img.src = photoUrl(id, 'thumb');
    const label = el('div', 'label'); label.append(el('b', '', title), el('span', '', subtitle));
    card.append(img, label); if (count != null) card.append(el('span', 'badge', count.toLocaleString()));
    card.addEventListener('click', onClick); return card;
  }
  let libSeq = 0;
  async function showLibrary(params) {
    const host = $('#page-library'), mine = ++libSeq;
    host.replaceChildren(el('div', 'empty', 'Loading\u2026'));
    const [tl, people] = await Promise.all([getJson('/api/timeline'), params.person ? getJson('/api/people') : Promise.resolve([])]);
    if (mine !== libSeq) return;
    const filters = ['year', 'month', 'place', 'person', 'from', 'to'].reduce((o, k) => (params[k] ? { ...o, [k]: params[k] } : o), {});
    const change = (c) => go('library', { ...params, ...c });
    const sub = el('div', 'sub', ''), grid = el('div', 'pgrid'), sentinel = el('div', 'sentinel'), moreBtn = el('button', 'pill more', 'Show more'); moreBtn.type = 'button';
    const head = el('div', 'page-head'), left = el('div'); left.append(el('h1', '', 'Library'), sub); head.append(left);
    const facets = el('div', 'facets');
    facets.append(seg([['', `All \u00b7 ${tl.total.toLocaleString()}`], ...tl.years.map((y) => [y.year, `${y.year} \u00b7 ${y.total.toLocaleString()}`])], params.year || '', (v) => change({ year: v, month: '', from: '', to: '', trip: '' })));
    const yr = tl.years.find((y) => y.year === params.year);
    if (yr) facets.append(seg([['', 'All months'], ...yr.months.slice().reverse().map((m) => [m.month, `${monthLabel(m.month)} \u00b7 ${m.n}`])], params.month || '', (v) => change({ month: v })));
    const tags = el('div', 'tagrow');
    if (params.place) tags.append(tag(params.place, () => change({ place: '' })));
    if (params.person) tags.append(tag((people.find((p) => String(p.id) === params.person) || {}).name || 'Person', () => change({ person: '', name: '' })));
    if (params.from || params.to) tags.append(tag(params.trip ? `${params.trip} \u00b7 ${dateRange(params.from, params.to)}` : dateRange(params.from, params.to), () => change({ from: '', to: '', trip: '' })));
    host.replaceChildren(head, facets, tags, grid, sentinel, moreBtn);
    const g = { ids: [], grid }; let total = 0, loading = false;
    async function more() {
      if (loading || mine !== libSeq || (total && g.ids.length >= total)) return;
      loading = true;
      try {
        const d = await getJson('/api/library?' + new URLSearchParams({ ...filters, offset: String(g.ids.length) }));
        if (mine !== libSeq) return;
        total = d.total; addTiles(g, d.ids);
        sub.textContent = total ? `${total.toLocaleString()} photo${total === 1 ? '' : 's'}` : '';
        if (!total) grid.replaceWith(el('div', 'empty', 'No photos match.'));
      } catch (_) { /* keep what is shown */ }
      loading = false; moreBtn.hidden = g.ids.length >= total;
    }
    moreBtn.addEventListener('click', more);
    new IntersectionObserver((entries) => { if (entries.some((x) => x.isIntersecting)) more(); }, { rootMargin: '600px' }).observe(sentinel);
    await more();
  }
  async function showTrips() {
    const host = $('#page-trips'); host.replaceChildren(el('div', 'empty', 'Loading\u2026'));
    const trips = await getJson('/api/trips');
    const body = [pageHead('Trips', trips.length ? `${trips.length} trips and occasions, newest first` : '')];
    if (!trips.length) body.push(el('div', 'empty', 'No trips yet. They appear once photos have dates and places.'));
    let year = '';
    const cards = el('div', 'cards'); body.push(cards);
    for (const t of trips) {
      if (t.start.slice(0, 4) !== year) { year = t.start.slice(0, 4); cards.append(el('div', 'band wide', year)); }
      cards.append(coverCard(t.cover, t.title, dateRange(t.start, t.stop), t.n, () => go('library', { from: t.start, to: t.stop, trip: t.title })));
    }
    host.replaceChildren(...body);
  }
  async function showPlaces() {
    const host = $('#page-places'); host.replaceChildren(el('div', 'empty', 'Loading\u2026'));
    const places = await getJson('/api/places');
    const cards = el('div', 'cards'), filter = el('input', 'field'); filter.type = 'search'; filter.placeholder = 'Find a place\u2026';
    const fill = () => { const f = filter.value.trim().toLowerCase(); cards.replaceChildren(...places.filter((p) => !f || p.place.toLowerCase().includes(f)).map((p) => coverCard(p.cover, p.place.split(',')[0], p.country || p.place, p.n, () => go('library', { place: p.place })))); };
    filter.addEventListener('input', fill); fill();
    host.replaceChildren(pageHead('Places', places.length ? `${places.length} places` : ''), ...(places.length ? [filter, el('div', 'band', ''), cards] : [el('div', 'empty', 'No places yet. Photos with a location appear here.')]));
  }
  function faceStyle(node, id, box) {          // the clearest face of a person, zoomed into the photo it comes from
    node.style.backgroundImage = `url("${photoUrl(id, 'thumb')}")`;
    const [x1, y1, x2, y2] = box, w = Math.max(x2 - x1, y2 - y1) * 1.7;
    if (!(w < 0.98)) { node.style.backgroundSize = 'cover'; node.style.backgroundPosition = 'center'; return; }
    const pos = (c) => Math.min(100, Math.max(0, ((c - w / 2) / (1 - w)) * 100));
    node.style.backgroundSize = `${100 / w}% ${100 / w}%`; node.style.backgroundPosition = `${pos((x1 + x2) / 2)}% ${pos((y1 + y2) / 2)}%`;
  }
  async function showPeople() {
    const host = $('#page-people'); host.replaceChildren(el('div', 'empty', 'Loading\u2026'));
    const people = await getJson('/api/people'), grid = el('div', 'people');
    people.forEach((p, i) => {
      const b = el('button', 'person'), face = el('div', 'face'); b.type = 'button'; faceStyle(face, p.cover, p.box);
      b.append(face, el('b', '', p.name || `Person ${i + 1}`), el('span', '', `${p.n.toLocaleString()} photo${p.n === 1 ? '' : 's'}`));
      b.addEventListener('click', () => go('library', { person: String(p.id) })); grid.append(b);
    });
    host.replaceChildren(pageHead('People', people.length ? `${people.length} people found in your photos` : ''), people.length ? grid : el('div', 'empty', 'No people yet. Faces are grouped while your library is indexed.'));
  }
  async function render() {
    const { page, params } = where();
    document.body.dataset.page = page;
    document.querySelectorAll('.nav-item').forEach((a) => a.classList.toggle('active', a.dataset.id === page));
    for (const id of PAGES) $('#page-' + id).hidden = id !== page;
    try {
      if (page === 'library') await showLibrary(params); else if (page === 'trips') await showTrips(); else if (page === 'places') await showPlaces(); else if (page === 'people') await showPeople();
    } catch (e) { const host = $('#page-' + page); host.replaceChildren(el('div', 'empty', `Could not load this page: ${e.message}`)); }
    if (page !== 'search') window.scrollTo({ top: 0 });
  }

  // ---------------------------------------------------------------- status chips + first screen
  function chip(label, state, action) {
    const c = el('span', `chip ${state}`); c.append(el('span', 'dot'), label);
    if (action) { const b = el('button', '', action.text); b.type = 'button'; b.addEventListener('click', action.run); c.append(b); }
    return c;
  }
  async function setCloud(on) {
    try {
      const r = await (await api('/api/cloud', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ on }) })).json();
      if (!r.ok) alert(r.error);
    } catch (e) { /* the next status refresh shows the truth */ }
    refreshStatus();
  }
  async function refreshStatus() {
    try {
      const s = await (await api('/api/status')).json();
      const chips = [chip(s.search_ready ? 'Search ready' : (s.warm_problem ? 'Search unavailable' : 'Search warming up'), s.search_ready ? 'ok' : (s.warm_problem ? 'bad' : 'warn')),
                     chip(s.ai ? s.model : 'AI offline', s.ai ? 'ok' : 'bad'),
                     ...(s.cloud && s.cloud.state === 'connected' ? [chip('Cloud on \u00b7 $' + Number(s.cloud.spent || 0).toFixed(2) + ' of $' + Number(s.cloud.cap || 0).toFixed(0), 'ok', { text: 'Turn off', run: () => setCloud(false) })]
                       : s.cloud && s.cloud.state === 'down' ? [chip('Cloud not connected: local only', 'warn', { text: 'Turn off', run: () => setCloud(false) })]
                       : s.cloud && s.cloud.state === 'local' ? [chip('Local only', 'ok', { text: 'Use cloud', run: () => setCloud(true) })] : []),
                     ];
      $('#build').textContent = s.build ? `build ${s.build}` : '';
      if (s.photos) chips.push(chip(`${s.photos.toLocaleString()} photos`, 'ok'));
      if (s.indexing) chips.push(chip('Indexing', 'warn'));
      else if (s.paused_for_chat) chips.push(chip('Indexing paused', 'warn', { text: 'Resume', run: async () => { await api('/api/scan/resume', { method: 'POST' }); refreshStatus(); } }));
      $('#chips').replaceChildren(...chips);
      notReady = !s.search_ready && !s.warm_problem;
      input.placeholder = notReady ? 'Getting ready\u2026' : 'Ask for photos, or ask anything\u2026';
      send.disabled = notReady || (!busy && !input.value.trim());
      $('#warm').textContent = s.warm_problem ? `Image search could not start: ${s.warm_problem}` : (!s.ai ? 'The AI model is not reachable. Is Ollama running?' : (notReady ? 'Getting ready: loading your library into memory. You can ask as soon as this message goes away.' : 'Warming up: the first answer can take a little longer.'));
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
  setupTheme(); window.addEventListener('hashchange', render); render();
  autosize(); refreshStatus(); loadIdeas(); setInterval(refreshStatus, 4000); if (where().page === 'search') input.focus();
})();
