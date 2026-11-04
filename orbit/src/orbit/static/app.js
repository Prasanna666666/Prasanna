/* Orbit front end. No libraries, no network: it talks only to this server. */
(() => {
'use strict';

// ------------------------------------------------------------------ helpers
const $ = (s, el = document) => el.querySelector(s);
function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === false || v == null) continue;
    if (k === 'class') el.className = v;
    else if (k === 'html') el.innerHTML = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat(9)) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(kid));
  return el;
}
const ICONS = {
  home: 'M3 11.5 12 4l9 7.5M5.5 10v9a1 1 0 0 0 1 1H10v-5h4v5h3.5a1 1 0 0 0 1-1v-9',
  chat: 'M20 12a8 8 0 0 1-11.6 7.1L4 20l1-4.2A8 8 0 1 1 20 12Z',
  money: 'M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Zm0 3h18M7 15h3',
  tasks: 'M9 11l2 2 4-4M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z',
  notes: 'M6 3h9l4 4v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Zm8 0v5h5M8.5 13h7M8.5 17h5',
  people: 'M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm-6 9a6 6 0 0 1 12 0M16 4.3a3.5 3.5 0 0 1 0 6.4M18 14.2A6 6 0 0 1 21 20',
  files: 'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z',
  settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm7.4-2a7.5 7.5 0 0 0 0-2l2-1.6-2-3.4-2.4 1a7.5 7.5 0 0 0-1.7-1L15 3h-4l-.4 3a7.5 7.5 0 0 0-1.7 1l-2.4-1-2 3.4 2 1.6a7.5 7.5 0 0 0 0 2l-2 1.6 2 3.4 2.4-1a7.5 7.5 0 0 0 1.7 1l.4 3h4l.4-3a7.5 7.5 0 0 0 1.7-1l2.4 1 2-3.4-2-1.6Z',
};
const icon = (n) => h('span', { html: `<svg viewBox="0 0 24 24"><path d="${ICONS[n]}"/></svg>`, style: { display: 'contents' } });

let cur = 'EUR';
const money = (n, d = 0) => new Intl.NumberFormat(undefined, { style: 'currency', currency: cur, minimumFractionDigits: d, maximumFractionDigits: d }).format(n || 0);
const monthName = (ym) => new Date(ym + '-15').toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
const shortMonth = (ym) => new Date(ym + '-15').toLocaleDateString(undefined, { month: 'short' });
const PALETTE = ['#6366f1', '#ec4899', '#10b981', '#f59e0b', '#06b6d4', '#8b5cf6', '#f43f5e', '#84cc16', '#0ea5e9', '#d946ef', '#14b8a6', '#a3a3a3'];
const colour = (name) => { let x = 0; for (const c of String(name)) x = (x * 31 + c.charCodeAt(0)) >>> 0; return PALETTE[x % PALETTE.length]; };
const initials = (s) => String(s).split(/\s+/).map((w) => w[0]).slice(0, 2).join('');

async function api(path, body) {
  const opt = body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Orbit': '1' }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  const d = await r.json().catch(() => ({ ok: false, error: 'The server sent something unexpected.' }));
  if (!d.ok) throw new Error(d.error || 'Something went wrong.');
  return d;
}
const tool = (name, args = {}) => api('/api/tool', { name, args }).then((d) => d.data);
function toast(text, bad) {
  const t = h('div', { class: 'toast' + (bad ? ' err' : '') }, text);
  $('#toasts').append(t);
  setTimeout(() => t.remove(), bad ? 7000 : 3800);
}
const guard = (fn) => async (...a) => { try { return await fn(...a); } catch (e) { toast(e.message, true); } };

// ------------------------------------------------------------------ shell
const PAGES = [['home', 'Home'], ['money', 'Money'], ['chat', 'Ask Orbit'], ['tasks', 'Tasks'], ['notes', 'Notes'], ['people', 'People'], ['files', 'Files'], ['settings', 'Settings']];
const MENU = [['home', 'money', 'chat'], ['tasks', 'notes', 'people'], ['settings']];  // 'files' is reached from Money > Documents
function buildNav() {
  const label = Object.fromEntries(PAGES);
  $('#nav').replaceChildren(...MENU.flatMap((group, i) => [i ? h('div', { class: 'nav-gap' }) : null, ...group.map((id) => h('a', { class: 'nav-item', href: '#/' + id, 'data-id': id }, icon(id), h('span', {}, label[id])))]).filter(Boolean));
}
async function refreshStatus() {
  try {
    const s = await api('/api/status');
    $('#ai-pill').className = 'pill ' + (s.ai ? 'ok' : 'bad');
    $('#ai-text').textContent = s.ai ? 'Local model ready' : 'Model offline';
    $('#ai-pill').title = s.ai ? s.model : s.problem;
  } catch (_) { $('#ai-pill').className = 'pill bad'; $('#ai-text').textContent = 'Not responding'; }
}
const route = () => (location.hash.replace('#/', '') || 'home').split('?')[0];
async function render() {
  const wanted = route(), id = PAGES.some(([p]) => p === wanted) ? wanted : 'home';
  document.querySelectorAll('.nav-item').forEach((a) => a.classList.toggle('active', a.dataset.id === id));
  const main = $('#main');
  main.replaceChildren(h('div', { class: 'empty' }, 'Loading...'));
  main.style.animation = 'none'; void main.offsetWidth; main.style.animation = '';
  try { main.replaceChildren(await pages[id]()); } catch (e) { main.replaceChildren(h('div', { class: 'card' }, h('h2', {}, 'Something went wrong'), h('p', { class: 'muted' }, e.message))); }
}
const head = (title, sub, ...right) => h('div', { class: 'page-head' }, h('div', {}, h('h1', {}, title), sub && h('div', { class: 'sub' }, sub)), h('div', { class: 'row' }, ...right));

// ------------------------------------------------------------------ charts
function donut(data) {
  const total = data.reduce((s, d) => s + d.value, 0) || 1, R = 70, C = 2 * Math.PI * R;
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 190 190'); svg.setAttribute('class', 'donut');
  svg.innerHTML = `<circle cx="95" cy="95" r="${R}" stroke="var(--surface-2)"/>`;
  let acc = 0;
  data.forEach((d) => {
    const len = (d.value / total) * C, c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    c.setAttribute('cx', 95); c.setAttribute('cy', 95); c.setAttribute('r', R); c.setAttribute('stroke', d.colour);
    c.setAttribute('stroke-dasharray', `0 ${C}`); c.setAttribute('stroke-dashoffset', -acc); c.setAttribute('transform', 'rotate(-90 95 95)');
    svg.append(c); acc += len;
    requestAnimationFrame(() => requestAnimationFrame(() => c.setAttribute('stroke-dasharray', `${Math.max(len - 3, 0.1)} ${C}`)));
  });
  const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
  t.setAttribute('x', 95); t.setAttribute('y', 92); t.setAttribute('text-anchor', 'middle'); t.setAttribute('fill', 'var(--ink)'); t.setAttribute('font-size', 22); t.setAttribute('font-weight', 700);
  t.textContent = money(total); svg.append(t);
  const t2 = t.cloneNode(); t2.setAttribute('y', 112); t2.setAttribute('font-size', 12); t2.setAttribute('font-weight', 500); t2.setAttribute('fill', 'var(--faint)'); t2.textContent = 'spent'; svg.append(t2);
  return svg;
}
function barChart(trend, selected, onPick) {
  const max = Math.max(...trend.map((t) => t.spent), 1);
  return h('div', { class: 'bars' }, trend.map((t, i) => h('div', { class: 'bar-col', title: `${monthName(t.month)}: spent ${money(t.spent)}, income ${money(t.income)}` },
    h('div', { class: 'bar-val num' }, t.spent ? money(t.spent) : ''),
    h('div', { class: 'bar' + (t.month === selected ? ' on' : ''), style: { height: Math.max((t.spent / max) * 100, 3) + '%', animationDelay: i * 50 + 'ms' }, onclick: () => onPick(t.month) }),
    h('div', { class: 'bar-label' }, shortMonth(t.month)))));
}

// ------------------------------------------------------------------ pages
const pages = {};

pages.home = async () => {
  const d = await api('/api/home'); cur = d.currency;
  const b = d.briefing, m = b.money, hour = new Date().getHours();
  const hello = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
  const ask = h('input', { class: 'field', placeholder: 'Ask Orbit anything: "how much did I spend on food last month?"', style: { fontSize: '16px', padding: '16px 20px', borderRadius: '18px' } });
  ask.addEventListener('keydown', (e) => { if (e.key === 'Enter' && ask.value.trim()) { sessionStorage.setItem('orbit.ask', ask.value.trim()); location.hash = '#/chat'; } });
  const tile = (label, value, sub, cls) => h('div', { class: 'card' }, h('div', { class: 'eyebrow' }, label), h('div', { class: 'num ' + (cls || ''), style: { fontSize: '30px', fontWeight: 700, margin: '6px 0 2px', letterSpacing: '-.02em' } }, value), h('div', { class: 'muted', style: { fontSize: '13px' } }, sub));
  return h('div', { class: 'stack' },
    head(`${hello}.`, new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })),
    ask,
    d.trend.length ? h('div', { class: 'grid g3' },
      tile('Spent in ' + monthName(m.month).split(' ')[0], money(m.spent), 'so far this month'),
      tile('Money in', money(m.income), 'this month', 'good'),
      tile('To do', String(b.tasks_due.length), b.tasks_due.length ? 'due or overdue' : 'all clear')) :
      h('div', { class: 'card welcome-card' }, h('div', { class: 'orb big' }), h('h2', {}, 'Welcome to Orbit'), h('p', { class: 'muted' }, 'Your private assistant for money, tasks, notes and people. Everything stays on this Mac.'), h('a', { class: 'btn primary', href: '#/money' }, 'Add my finance files')),
    d.trend.length ? h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Spending, last months'), h('a', { href: '#/money', class: 'chip' }, 'Open Money')), barChart(d.trend, d.trend[d.trend.length - 1].month, () => { location.hash = '#/money'; })) : null,
    h('div', { class: 'grid g2' },
      h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Needs attention')),
        b.tasks_due.length ? h('div', { class: 'list' }, b.tasks_due.map((t) => h('div', { class: 'item' },
          h('button', { class: 'check', 'aria-label': 'Mark done', onclick: guard(async (e) => { await tool('complete_task', { id: t.id }); e.currentTarget.classList.add('done'); setTimeout(render, 350); }) }, h('span', { html: '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>', style: { display: 'contents' } })),
          h('div', { class: 'grow' }, h('div', { style: { fontWeight: 600 } }, t.title), h('div', { class: 'faint', style: { fontSize: '13px' } }, t.due || 'no date'))))) : h('div', { class: 'empty' }, 'Nothing due. Enjoy it.')),
      h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Coming up')),
        b.upcoming_dates.length ? h('div', { class: 'list' }, b.upcoming_dates.map((u) => h('div', { class: 'item' },
          h('div', { class: 'avatar', style: { background: colour(u.name) } }, initials(u.name)),
          h('div', { class: 'grow' }, h('div', { style: { fontWeight: 600 } }, `${u.name} · ${u.label}`), h('div', { class: 'faint', style: { fontSize: '13px' } }, u.in_days === 0 ? 'today' : `in ${u.in_days} days`)),
          u.turning ? h('span', { class: 'chip' }, `turning ${u.turning}`) : null))) : h('div', { class: 'empty' }, 'No birthdays or dates in the next two weeks.'))));
};

pages.chat = async () => {
  const { history } = await api('/api/history');
  const msgs = h('div', { class: 'msgs', id: 'msgs' });
  const input = h('textarea', { rows: 1, placeholder: 'Ask about your money, tasks, notes, people...' });
  const sendBtn = h('button', { class: 'send', 'aria-label': 'Send' }, h('span', { html: '<svg viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6"/></svg>', style: { display: 'contents' } }));
  let busy = false;
  const scroll = () => { msgs.scrollTop = msgs.scrollHeight; };
  const bubble = (role, text, tags) => { const b = h('div', { class: 'bubble ' + role }, text, tags && tags.length ? h('div', { class: 'tags' }, tags.map((t) => h('span', { class: 'chip' }, t))) : null); msgs.append(b); scroll(); return b; };
  const welcome = () => h('div', { class: 'welcome' }, h('div', { class: 'orb' }), h('h2', {}, 'How can I help?'), h('div', { class: 'muted' }, 'Everything runs on this Mac. Nothing is sent anywhere.'),
    h('div', { class: 'suggest', style: { justifyContent: 'center', marginTop: '22px' } }, ['How much did I spend last month?', 'Which subscriptions do I pay?', 'What invoices are due?', "What's on today?"].map((q) => h('button', { onclick: () => send(q) }, q))));
  if (!history.length) msgs.append(welcome()); else history.forEach((m) => bubble(m.role === 'user' ? 'user' : 'bot', m.content));
  async function send(text) {
    text = (text || input.value).trim();
    if (!text || busy) return;
    busy = true; sendBtn.disabled = true; input.value = ''; input.style.height = ''; msgs.querySelector('.welcome')?.remove();
    bubble('user', text);
    const typing = h('div', { class: 'bubble bot' }, h('div', { class: 'typing' }, h('i'), h('i'), h('i'))); msgs.append(typing); scroll();
    try {
      const r = await api('/api/chat', { text });
      typing.remove(); bubble('bot', r.reply || '(no answer)', [r.agent + ' agent', ...(r.tools || [])]);
    } catch (e) { typing.remove(); bubble('bot', e.message); }
    busy = false; sendBtn.disabled = false; input.focus();
  }
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });
  input.addEventListener('input', () => { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 140) + 'px'; });
  sendBtn.addEventListener('click', () => send());
  const pending = sessionStorage.getItem('orbit.ask'); sessionStorage.removeItem('orbit.ask');
  if (pending) setTimeout(() => send(pending), 50);
  return h('div', {}, head('Ask Orbit', 'Private, on-device. It uses your tasks, notes, people and money.', h('button', { class: 'btn ghost', onclick: guard(async () => { await api('/api/chat/reset', {}); render(); }) }, 'New chat')),
    h('div', { class: 'chat' }, msgs, h('div', { class: 'composer' }, input, sendBtn)));
};

pages.money = async () => {
  const [trend0, settings] = await Promise.all([tool('monthly_trend', { months: 12 }), api('/api/settings')]);
  cur = settings.currency;
  const now = new Date().toISOString().slice(0, 7);
  const latest = trend0.length ? trend0[trend0.length - 1].month : now;
  // early in a month the current month is too short to read: open the last complete one instead
  const prevOfLatest = trend0.length > 1 ? trend0[trend0.length - 2].month : latest;
  let month = location.hash.split('?m=')[1] || (latest === now && new Date().getDate() < 10 ? prevOfLatest : latest);
  let tab = 'overview';
  const wrap = h('div', { class: 'stack' });
  const importBtn = h('button', { class: 'btn primary', onclick: guard(startImport) }, 'Read my files');
  const status = h('div', { class: 'card', style: { display: 'none' } });
  async function startImport() {
    await api('/api/import', {}); poll();
  }
  async function poll() {
    const s = await api('/api/import');
    status.style.display = s.running || s.result || s.error ? '' : 'none';
    if (s.running) {
      importBtn.disabled = true; importBtn.textContent = 'Reading...';
      status.replaceChildren(h('div', { class: 'row' }, h('span', { class: 'chip' }, 'In progress'), h('div', { class: 'grow muted' }, s.progress || 'Starting...')), h('div', { class: 'progress' }));
      setTimeout(poll, 1500); return;
    }
    importBtn.disabled = false; importBtn.textContent = 'Read my files';
    if (s.error) status.replaceChildren(h('div', { class: 'bad', style: { fontWeight: 600 } }, s.error));
    else if (s.result) {
      const r = s.result;
      status.replaceChildren(h('div', { style: { fontWeight: 650 } }, `Read ${r.files} new file(s): ${r.new_transactions} new transactions, ${r.payslips} payslip(s).`),
        ...r.problems.map((p) => h('div', { class: 'bad' }, p)), r.files_with_no_transactions.length ? h('div', { class: 'muted' }, 'No transactions found in: ' + r.files_with_no_transactions.join(', ') + '. Scanned or password-protected PDFs cannot be read.') : null);
      if (r.files) draw(true);
    }
  }
  async function draw(refreshTrend) {
    const trend = refreshTrend ? await tool('monthly_trend', { months: 12 }) : trend0;
    const [sum, merchants, recurring, todo, slips, docs, docTotals, txs] = await Promise.all([
      tool('spending_summary', { month }), tool('top_merchants', { month, limit: 8 }), tool('recurring_payments'), tool('uncategorised_spending'),
      tool('list_payslips', { limit: 12 }), tool('finance_documents', { limit: 200 }), tool('finance_document_totals', { by: 'kind' }),
      tool('list_transactions', { since: month + '-01', until: month + '-31', limit: 300 })]);
    const idx = trend.findIndex((t) => t.month === month), prev = idx > 0 ? trend[idx - 1] : null;
    const delta = prev && prev.spent ? ((sum.spent - prev.spent) / prev.spent) * 100 : null;
    const nav = h('div', { class: 'monthnav' }, h('button', { 'aria-label': 'Previous month', onclick: () => step(-1) }, '‹'), h('span', {}, monthName(month)), h('button', { 'aria-label': 'Next month', onclick: () => step(1) }, '›'));
    function step(n) { const d = new Date(month + '-15'); d.setMonth(d.getMonth() + n); month = d.toISOString().slice(0, 7); draw(false); }
    const cats = sum.by_category.map((c) => ({ name: c.category, value: c.spent, colour: colour(c.category) }));
    const hero = h('div', { class: 'card hero' }, h('div', { class: 'eyebrow' }, 'Spent in ' + monthName(month)), h('div', { class: 'big num' }, money(sum.spent)),
      delta != null ? h('span', { class: 'delta' }, `${delta > 0 ? '↑' : '↓'} ${Math.abs(delta).toFixed(0)}% vs ${shortMonth(prev.month)}`) : null,
      h('div', { class: 'meta' }, h('div', {}, h('div', { class: 'k' }, 'Income'), h('div', { class: 'v num' }, money(sum.income))), h('div', {}, h('div', { class: 'k' }, 'Net'), h('div', { class: 'v num' }, money(sum.net))),
        h('div', {}, h('div', { class: 'k' }, 'Transactions'), h('div', { class: 'v num' }, String(txs.length)))));
    const maxM = Math.max(...merchants.map((x) => x.spent), 1);
    const catCard = h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Where it went')),
      cats.length ? h('div', { class: 'donut-wrap' }, donut(cats), h('div', { class: 'legend' }, cats.slice(0, 9).map((c) => h('div', { class: 'legend-row' }, h('span', { class: 'sw', style: { background: c.colour } }), h('span', { class: 'nm' }, c.name), h('span', { class: 'amt num' }, money(c.value)))))) : h('div', { class: 'empty' }, 'Nothing spent this month.'));
    const trendCard = h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Month by month'), h('span', { class: 'faint', style: { fontSize: '13px' } }, 'tap a bar')),
      trend.length ? barChart(trend, month, (m) => { month = m; draw(false); }) : h('div', { class: 'empty' }, 'No data yet. Read your finance files to begin.'));
    const merchCard = h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Top merchants')),
      merchants.length ? h('div', { class: 'list' }, merchants.map((x) => h('div', { class: 'item' }, h('div', { class: 'avatar', style: { background: colour(x.merchant) } }, initials(x.merchant)),
        h('div', { class: 'grow' }, h('div', { style: { fontWeight: 600, textTransform: 'capitalize' } }, x.merchant), h('div', { class: 'meter' }, h('i', { style: { width: (x.spent / maxM) * 100 + '%' } }))),
        h('div', { style: { textAlign: 'right' } }, h('div', { class: 'num', style: { fontWeight: 650 } }, money(x.spent)), h('div', { class: 'faint', style: { fontSize: '12px' } }, x.times + '×'))))) : h('div', { class: 'empty' }, 'No spending yet.'));
    const recCard = h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Repeating payments'), recurring.length ? h('span', { class: 'chip' }, `≈ ${money(recurring.reduce((s, r) => s + r.per_month, 0))}/mo`) : null),
      recurring.length ? h('div', { class: 'list' }, recurring.slice(0, 8).map((r) => h('div', { class: 'item' }, h('span', { class: 'sw', style: { width: '10px', height: '10px', borderRadius: '4px', background: colour(r.merchant), flex: 'none' } }),
        h('div', { class: 'grow', style: { textTransform: 'capitalize', fontWeight: 600 } }, r.merchant, h('div', { class: 'faint', style: { fontSize: '12px', textTransform: 'none', fontWeight: 400 } }, `${r.times} payments · last ${r.last}`)), h('div', { class: 'num', style: { fontWeight: 650 } }, money(r.typical_amount, 2))))) : h('div', { class: 'empty' }, 'None found yet.'));
    const CATS = ['groceries', 'food', 'transport', 'fuel', 'shopping', 'utilities', 'rent', 'emi', 'insurance', 'medical', 'education', 'travel', 'entertainment', 'subscriptions', 'cash', 'investments', 'transfers', 'fees'];
    const sortCard = todo.length ? h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('div', {}, h('h2', {}, 'Help me sort these'), h('div', { class: 'muted', style: { fontSize: '13px' } }, 'Pick once; every payment to that merchant follows, now and in future.'))),
      h('div', { class: 'list' }, todo.slice(0, 6).map((t) => { const sel = h('select', { class: 'field', style: { width: '170px' } }, h('option', { value: '' }, 'Category...'), CATS.map((c) => h('option', { value: c }, c)));
        sel.addEventListener('change', guard(async () => { if (!sel.value) return; await tool('set_category', { merchant: t.merchant, category: sel.value }); toast(`${t.merchant} → ${sel.value}`); draw(false); }));
        return h('div', { class: 'item' }, h('div', { class: 'grow' }, h('div', { style: { fontWeight: 600, textTransform: 'capitalize' } }, t.merchant), h('div', { class: 'faint', style: { fontSize: '12px' } }, `${t.times}× · ${money(t.spent)}`)), sel); }))) : null;
    const slipCard = slips.length ? h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Payslips')), h('table', { class: 'table' },
      h('thead', {}, h('tr', {}, ['Period', 'Gross', 'Tax', 'Pension', 'Net'].map((x, i) => h('th', { class: i ? 'r' : '' }, x)))),
      h('tbody', {}, slips.map((s) => h('tr', {}, h('td', {}, s.period ? monthName(s.period) : s.name), ...[s.gross, s.tax, s.pension].map((v) => h('td', { class: 'r num' }, v != null ? money(v, 2) : '-')), h('td', { class: 'r num', style: { fontWeight: 650 } }, money(s.net, 2))))))) : null;
    const KIND = { invoice: '#6366f1', receipt: '#10b981', payslip: '#ec4899', tax: '#f59e0b', insurance: '#06b6d4', contract: '#8b5cf6', bank_statement: '#a3a3a3', other: '#a3a3a3' };
    const other = docs.filter((d) => !['bank_statement', 'payslip'].includes(d.kind));
    const docCard = docs.length ? h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Invoices, receipts and other files'), h('div', { class: 'row' }, docTotals.map((t) => h('span', { class: 'chip' }, `${t.grp} ${money(t.total)}`)))),
      other.length ? h('table', { class: 'table' }, h('thead', {}, h('tr', {}, ['', 'From', 'Date', 'Due', 'Total'].map((x, i) => h('th', { class: i === 4 ? 'r' : '' }, x)))),
        h('tbody', {}, other.slice(0, 30).map((d) => h('tr', {}, h('td', {}, h('span', { class: 'chip', style: { background: 'transparent', border: '1px solid var(--line-strong)', color: KIND[d.kind] || 'var(--muted)' } }, h('span', { class: 'sw', style: { background: KIND[d.kind] || '#999' } }), d.kind)),
          h('td', {}, h('div', { style: { fontWeight: 600 } }, d.party || d.title || d.name), d.summary ? h('div', { class: 'faint', style: { fontSize: '12px' } }, d.summary) : null), h('td', { class: 'num' }, d.date || '-'), h('td', { class: 'num' }, d.due_date || '-'),
          h('td', { class: 'r num', style: { fontWeight: 650 } }, d.total != null ? money(d.total, 2) : '-'))))) : h('div', { class: 'empty' }, 'Only statements and payslips so far.')) : null;
    const q = h('input', { class: 'field', placeholder: 'Search transactions', style: { maxWidth: '280px' } });
    const body = h('tbody', {});
    const fill = () => { const f = q.value.toLowerCase(); body.replaceChildren(...txs.filter((t) => !f || (t.note + t.category).toLowerCase().includes(f)).slice(0, 200).map((t) => h('tr', {}, h('td', { class: 'num faint' }, t.day.slice(5)), h('td', {}, t.note || '-'), h('td', {}, h('span', { class: 'chip', style: { background: 'transparent', border: '1px solid var(--line-strong)', color: 'var(--muted)' } }, h('span', { class: 'sw', style: { background: colour(t.category) } }), t.category)),
      h('td', { class: 'r num ' + (t.kind === 'income' ? 'good' : ''), style: { fontWeight: 600 } }, (t.kind === 'income' ? '+' : '−') + money(t.amount, 2))))); };
    q.addEventListener('input', fill); fill();
    const txCard = h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Transactions'), q), txs.length ? h('table', { class: 'table' }, h('thead', {}, h('tr', {}, ['Date', 'Description', 'Category', ''].map((x, i) => h('th', { class: i === 3 ? 'r' : '' }, x)))), body) : h('div', { class: 'empty' }, 'No transactions this month.'));
    const empty = !trend.length && !docs.length && !slips.length;
    const tabs = [['overview', 'Overview'], ['spending', 'Spending'], ['regular', 'Regular payments' + (recurring.length ? ` · ${recurring.length}` : '')], ['documents', 'Documents' + (docs.length + slips.length ? ` · ${docs.length + slips.length}` : '')]];
    const tabBar = h('div', { class: 'seg' }, tabs.map(([id, label]) => h('button', { class: tab === id ? 'on' : '', onclick: () => { tab = id; draw(false); } }, label)));
    const content = { overview: [h('div', { class: 'grid g2' }, catCard, trendCard), sortCard], spending: [merchCard, txCard], regular: [recCard],
      documents: [slipCard, docCard, h('div', { class: 'muted', style: { textAlign: 'center' } }, 'Looking for another kind of file? ', h('a', { href: '#/files' }, 'Search all documents'))] }[tab];
    const first = h('div', { class: 'card welcome-card' }, h('div', { class: 'orb big' }), h('h2', {}, 'Let’s bring in your money'),
      h('p', { class: 'muted' }, 'Put your bank statements, payslips, invoices and receipts (PDF) in your finance folder, then press the button. Orbit reads them privately on this Mac.'),
      h('ol', { class: 'steps' }, h('li', {}, 'Copy your PDFs into the finance folder'), h('li', {}, 'Press “Read my files”'), h('li', {}, 'Come back in a few minutes: your money is ready')),
      h('div', {}, importBtn));
    wrap.replaceChildren(...[head('Money', empty ? null : 'Everything stays on this Mac.', empty ? null : nav, empty ? null : importBtn), status, empty ? first : hero, empty ? null : tabBar, ...(empty ? [] : content)].filter(Boolean));
  }
  await draw(false); poll();
  return wrap;
};

pages.tasks = async () => {
  const tasks = await tool('list_tasks', { status: 'open', limit: 200 }), today = new Date().toISOString().slice(0, 10);
  const title = h('input', { class: 'field', placeholder: 'Add a task or reminder...', style: { flex: 1 } }), due = h('input', { class: 'field', type: 'date', style: { width: '170px' } });
  const rec = h('select', { class: 'field', style: { width: '140px' } }, ['none', 'daily', 'weekly', 'monthly', 'yearly'].map((r) => h('option', { value: r }, r === 'none' ? 'No repeat' : r)));
  const add = guard(async () => { if (!title.value.trim()) return; await tool('add_task', { title: title.value.trim(), due: due.value || undefined, recurrence: rec.value }); render(); });
  title.addEventListener('keydown', (e) => { if (e.key === 'Enter') add(); });
  const groups = [['Overdue', (t) => t.due && t.due.slice(0, 10) < today], ['Today', (t) => t.due && t.due.slice(0, 10) === today], ['Upcoming', (t) => t.due && t.due.slice(0, 10) > today], ['Someday', (t) => !t.due]];
  return h('div', { class: 'stack' }, head('Tasks', `${tasks.length} open`),
    h('div', { class: 'card row' }, title, due, rec, h('button', { class: 'btn primary', onclick: add }, 'Add')),
    ...groups.map(([name, f]) => { const items = tasks.filter(f); return items.length ? h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', { class: name === 'Overdue' ? 'bad' : '' }, name), h('span', { class: 'chip' }, String(items.length))),
      h('div', { class: 'list' }, items.map((t) => h('div', { class: 'item' }, h('button', { class: 'check', 'aria-label': 'Mark done', onclick: guard(async (e) => { await tool('complete_task', { id: t.id }); e.currentTarget.classList.add('done'); setTimeout(render, 300); }) }, h('span', { html: '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>', style: { display: 'contents' } })),
        h('div', { class: 'grow' }, h('div', { style: { fontWeight: 600 } }, t.title), h('div', { class: 'faint', style: { fontSize: '13px' } }, [t.due || 'no date', t.recurrence !== 'none' ? '↻ ' + t.recurrence : ''].filter(Boolean).join(' · '))),
        h('button', { class: 'btn ghost small', onclick: guard(async () => { await tool('delete_task', { id: t.id }); render(); }) }, 'Delete'))))) : null; }),
    tasks.length ? null : h('div', { class: 'empty' }, 'Nothing to do. Add something above.'));
};

pages.notes = async () => {
  let query = '';
  const grid = h('div', { class: 'masonry' }), search = h('input', { class: 'field', placeholder: 'Search notes', style: { maxWidth: '300px' } });
  const load = guard(async () => { const notes = await tool('search_notes', { query, limit: 200 }); grid.replaceChildren(...notes.map((n) => h('div', { class: 'card note' }, n.title ? h('h3', {}, n.title) : null, h('p', {}, n.body),
    h('div', { class: 'row', style: { marginTop: '14px' } }, h('div', { class: 'grow row', style: { flexWrap: 'wrap', gap: '6px' } }, (n.tags || '').split(',').filter(Boolean).map((t) => h('span', { class: 'chip' }, t))), h('button', { class: 'btn ghost small', onclick: guard(async () => { await tool('delete_note', { id: n.id }); load(); }) }, 'Delete'))))); if (!notes.length) grid.append(h('div', { class: 'empty' }, 'No notes yet.')); });
  search.addEventListener('input', () => { query = search.value; load(); });
  const t = h('input', { class: 'field', placeholder: 'Title (optional)' }), body = h('textarea', { class: 'field', placeholder: 'Write a note...' }), tags = h('input', { class: 'field', placeholder: 'Tags, comma separated' });
  await load();
  return h('div', { class: 'stack' }, head('Notes', null, search, h('button', { class: 'btn', onclick: guard(async () => { const r = await api('/api/notes/tag', {}); toast(`Tagged ${r.tagged} note(s)`); load(); }) }, 'Auto-tag'), h('button', { class: 'btn', onclick: guard(async () => { const r = await api('/api/notes/import', {}); toast(`Imported: ${r.new ?? 0} new`); load(); }) }, 'Import Apple Notes')),
    h('div', { class: 'card stack', style: { gap: '12px' } }, t, body, h('div', { class: 'row' }, tags, h('button', { class: 'btn primary', onclick: guard(async () => { if (!body.value.trim()) return; await tool('add_note', { title: t.value, body: body.value, tags: tags.value }); t.value = body.value = tags.value = ''; load(); }) }, 'Save'))), grid);
};

pages.people = async () => {
  const [people, dates] = await Promise.all([tool('list_people'), tool('upcoming_dates', { days: 60 })]);
  const name = h('input', { class: 'field', placeholder: 'Name' }), rel = h('input', { class: 'field', placeholder: 'Relation (mother, friend...)' }), about = h('input', { class: 'field', placeholder: 'About (health notes, likes...)' }), bday = h('input', { class: 'field', type: 'date', title: 'Birthday' });
  return h('div', { class: 'stack' }, head('People', `${people.length} people`),
    h('div', { class: 'card row', style: { flexWrap: 'wrap' } }, name, rel, about, bday, h('button', { class: 'btn primary', onclick: guard(async () => { if (!name.value.trim()) return; const p = await tool('add_person', { name: name.value, relation: rel.value, about: about.value }); if (bday.value) await tool('add_important_date', { person_id: p.id, label: 'Birthday', date: bday.value }); render(); }) }, 'Add')),
    h('div', { class: 'grid g-main' }, h('div', { class: 'grid g2' }, people.map((p) => h('div', { class: 'card person' }, h('div', { class: 'avatar', style: { background: colour(p.name), width: '48px', height: '48px', fontSize: '17px' } }, initials(p.name)),
      h('div', { class: 'grow' }, h('div', { style: { fontWeight: 650 } }, p.name), h('div', { class: 'muted', style: { fontSize: '13px' } }, [p.relation, p.about].filter(Boolean).join(' · '))), h('button', { class: 'btn ghost small', onclick: guard(async () => { await tool('delete_person', { id: p.id }); render(); }) }, 'Remove')))),
      h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Next 60 days')), dates.length ? h('div', { class: 'list' }, dates.map((d) => h('div', { class: 'item' }, h('div', { class: 'grow' }, h('div', { style: { fontWeight: 600 } }, `${d.name} · ${d.label}`), h('div', { class: 'faint', style: { fontSize: '13px' } }, d.in_days === 0 ? 'today' : `in ${d.in_days} days`)), d.turning ? h('span', { class: 'chip' }, `turning ${d.turning}`) : null))) : h('div', { class: 'empty' }, 'Nothing coming up.'))));
};

pages.files = async () => {
  let mode = 'finance', q = '';
  const out = h('div', { class: 'card' }), search = h('input', { class: 'field', placeholder: 'Search by name, supplier or words', style: { maxWidth: '340px' } });
  const seg = h('div', { class: 'seg' });
  const load = guard(async () => {
    seg.replaceChildren(...[['finance', 'Finance files'], ['all', 'All documents']].map(([id, label]) => h('button', { class: mode === id ? 'on' : '', onclick: () => { mode = id; load(); } }, label)));
    if (mode === 'finance') { const docs = await tool('finance_documents', { party: q, limit: 200 });
      out.replaceChildren(docs.length ? h('table', { class: 'table' }, h('thead', {}, h('tr', {}, ['Type', 'From / title', 'Date', 'Reference', 'Total'].map((x, i) => h('th', { class: i === 4 ? 'r' : '' }, x)))), h('tbody', {}, docs.map((d) => h('tr', {}, h('td', {}, h('span', { class: 'chip' }, d.kind)), h('td', {}, h('div', { style: { fontWeight: 600 } }, d.party || d.title || d.name), d.summary ? h('div', { class: 'faint', style: { fontSize: '12px' } }, d.summary) : null), h('td', { class: 'num' }, d.date || '-'), h('td', { class: 'num faint' }, d.reference || '-'), h('td', { class: 'r num', style: { fontWeight: 650 } }, d.total != null ? money(d.total, 2) : '-'))))) : h('div', { class: 'empty' }, 'No finance files yet. Put PDFs in your finance folder, then use "Read my files" on the Money page.')); }
    else { const docs = await tool('search_documents', { query: q, limit: 25 });
      out.replaceChildren(docs.length ? h('div', { class: 'list' }, docs.map((d) => h('div', { class: 'item' }, h('div', { class: 'grow' }, h('div', { style: { fontWeight: 600 } }, d.name), h('div', { class: 'muted', style: { fontSize: '13px' } }, d.snippet)), h('span', { class: 'chip' }, d.kind)))) : h('div', { class: 'empty' }, 'No documents found.')); }
  });
  search.addEventListener('input', () => { q = search.value; load(); });
  await load();
  const s = await api('/api/settings'); cur = s.currency;
  return h('div', { class: 'stack' }, head('Files', 'Everything the offline parser has read.', seg, search), out);
};

pages.settings = async () => {
  const s = await api('/api/settings'), cu = h('input', { class: 'field', value: s.currency, maxlength: 5 }), mo = h('input', { class: 'field', value: s.model }), ho = h('input', { class: 'field', value: s.ollama_host });
  const lab = (t, el) => h('label', { style: { display: 'block' } }, h('div', { class: 'eyebrow', style: { marginBottom: '6px' } }, t), el);
  return h('div', { class: 'stack', style: { maxWidth: '640px' } }, head('Settings'),
    h('div', { class: 'card stack', style: { gap: '16px' } }, lab('Currency code', cu), lab('Local model (Ollama)', mo), lab('Ollama address', ho),
      h('div', {}, h('button', { class: 'btn primary', onclick: guard(async () => { await api('/api/settings', { currency: cu.value, model: mo.value, ollama_host: ho.value }); cur = cu.value.toUpperCase(); toast('Saved'); refreshStatus(); }) }, 'Save'))),
    h('div', { class: 'card muted' }, `Your data lives in ${s.data} (encrypted when the key is set). The model runs on this Mac and Orbit makes no internet requests.`));
};

// ------------------------------------------------------------------ start
buildNav(); refreshStatus(); setInterval(refreshStatus, 20000);
api('/api/settings').then((s) => { cur = s.currency; }).finally(() => { window.addEventListener('hashchange', render); render(); });
})();
