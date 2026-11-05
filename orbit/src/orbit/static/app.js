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
  plan: 'M3 17l5-6 4 3 6-8M14 6h4v4',
  spending: 'M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Zm0 3h18M7 15h3',
  income: 'M12 19V5m0 0-5 5m5-5 5 5M5 21h14',
  wealth: 'M4 20V10m6 10V4m6 16v-7m4 7H2',
  tax: 'M7 3h7l5 5v13H7V3Zm7 0v5h5M10 13h6M10 17h6',
  documents: 'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z',
  money: 'M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Zm0 3h18M7 15h3',
  tasks: 'M9 11l2 2 4-4M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z',
  notes: 'M6 3h9l4 4v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Zm8 0v5h5M8.5 13h7M8.5 17h5',
  people: 'M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm-6 9a6 6 0 0 1 12 0M16 4.3a3.5 3.5 0 0 1 0 6.4M18 14.2A6 6 0 0 1 21 20',
  files: 'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z',
  settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm7.4-2a7.5 7.5 0 0 0 0-2l2-1.6-2-3.4-2.4 1a7.5 7.5 0 0 0-1.7-1L15 3h-4l-.4 3a7.5 7.5 0 0 0-1.7 1l-2.4-1-2 3.4 2 1.6a7.5 7.5 0 0 0 0 2l-2 1.6 2 3.4 2.4-1a7.5 7.5 0 0 0 1.7 1l.4 3h4l.4-3a7.5 7.5 0 0 0 1.7-1l2.4 1 2-3.4-2-1.6Z',
};
const icon = (n) => h('span', { html: `<svg viewBox="0 0 24 24"><path d="${ICONS[n]}"/></svg>`, style: { display: 'contents' } });

let cur = 'EUR';
const MAINS = ['sports', 'events', 'trips', 'cancellations', 'others'];
const MAIN_LABEL = { sports: 'Sports', events: 'Events', trips: 'Trips', cancellations: 'Cancellations', others: 'Others' };
const MAIN_COLOUR = { sports: '#10b981', events: '#ec4899', trips: '#6366f1', cancellations: '#f59e0b', others: '#94a3b8' };
const SUB_HINTS = ['tickets', 'flights', 'stay', 'travel', 'food', 'food and others', 'merchandise', 'insurance', 'refund', 'fees'];
const signed = (n, d = 2) => (n < 0 ? '−' : '') + money(Math.abs(n), d);
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
const PAGES = [['home', 'Home'], ['spending', 'Spending'], ['income', 'Income'], ['wealth', 'Wealth'], ['plan', 'Plan'], ['tax', 'Tax'], ['documents', 'Documents'], ['chat', 'Ask Orbit'], ['tasks', 'Tasks'], ['notes', 'Notes'], ['people', 'People'], ['files', 'Files'], ['money', 'Money'], ['settings', 'Settings']];
const MENU = [['home', 'spending', 'income', 'wealth'], ['plan', 'tax', 'documents'], ['chat', 'tasks', 'notes', 'people'], ['settings']];  // 'files' is reached from Documents; 'money' is the old address of Spending
function buildNav() {
  const label = Object.fromEntries(PAGES);
  $('#nav').replaceChildren(...MENU.flatMap((group, i) => [i ? h('div', { class: 'nav-gap' }) : null, ...group.map((id) => h('a', { class: 'nav-item', href: '#/' + id, 'data-id': id }, icon(id), h('span', {}, label[id])))]).filter(Boolean));
}
async function refreshStatus() {
  try {
    const s = await api('/api/status');
    $('#ai-pill').className = 'pill ' + (s.ai ? 'ok' : 'bad');
    $('#ai-text').textContent = s.ai ? 'Assistant ready' : 'Assistant off';
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
function barChart(trend, selected, onPick, key = 'spent') {
  const max = Math.max(...trend.map((t) => t[key]), 1);
  return h('div', { class: 'bars' }, trend.map((t, i) => h('div', { class: 'bar-col', title: `${monthName(t.month)}: ${money(t[key])}` },
    h('div', { class: 'bar-val num' }, t[key] ? money(t[key]) : ''),
    h('div', { class: 'bar' + (t.month === selected ? ' on' : ''), style: { height: Math.max((t[key] / max) * 100, 3) + '%', animationDelay: i * 50 + 'ms' }, onclick: () => onPick(t.month) }),
    h('div', { class: 'bar-label' }, shortMonth(t.month)))));
}

function changeNote(d) {
  const ch = d.before > 0 ? ((d.amount - d.before) / d.before) * 100 : null;
  return ch == null ? 'new' : Math.abs(ch) < 10 ? '' : ch > 100 ? '↑ 2×+' : `${ch >= 0 ? '↑' : '↓'} ${Math.abs(ch).toFixed(0)}%`;
}
/** Say what a check found in everyday words. */
function plain(m) {
  return String(m)
    .replace(/the balances do not add up at \d+ place\(s\)/, "the numbers don't add up")
    .replace(/opening balance and transactions do not add up to the closing balance.*/, "the numbers don't add up")
    .replace(/opening \+ transactions gives \S+ but the statement prints \S+/, "the total doesn't match")
    .replace(/two independent readings of the layout disagree.*/, "it could not be read reliably")
    .replace(/the layout of this file could not be understood/, "it could not be read")
    .replace(/line \d+ has an amount but no date/, 'a line has no date')
    .replace(/cannot tell whether .* is money in or out/, "it is unclear if a payment is money in or out")
    .replace(/line \d+: the figure .* sits in a column read as text/, 'a figure is in the wrong place')
    .replace(/the stored payments add up to .* but the statements say .*/, "the payments don't match the statements")
    .replace(/closing .* does not match the next opening .*/, "it does not join the next statement");
}
/** Monthly category tiles, shared by Home and Money. `isOn(category)` and `onTap(category)` are optional. */
function dailyTiles(daily, isOn, onTap) {
  const max = Math.max(...daily.map((d) => d.amount), 1);
  return h('div', { class: 'tiles' }, daily.map((d) => h(onTap ? 'button' : 'div', { class: 'tile' + (isOn && isOn(d.category) ? ' on' : ''), onclick: onTap ? () => onTap(d.category) : null },
    h('div', { class: 'row' }, h('span', { class: 'sw', style: { width: '10px', height: '10px', borderRadius: '4px', background: colour(d.category) } }), h('span', { class: 'tname' }, d.category)),
    h('div', { class: 'tamt num' }, money(d.amount)), h('div', { class: 'meter' }, h('i', { style: { width: (d.amount / max) * 100 + '%', background: colour(d.category) } })),
    h('div', { class: 'faint', style: { fontSize: '12.5px', marginTop: '8px' } }, changeNote(d)))));
}
/** The month to open on: the latest with data, unless it is the current month and only a few days old. */
function startMonth(trend) {
  // statements arrive after the month ends, so the newest month with data is the one to show
  return trend.length ? trend[trend.length - 1].month : new Date().toISOString().slice(0, 7);
}

// ------------------------------------------------------------------ pages
const pages = {};

pages.home = async () => {
  const d = await api('/api/home'); cur = d.currency;
  const b = d.briefing, hour = new Date().getHours(), month = startMonth(d.trend);
  const hello = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
  const [dueSoon, det, checks] = await Promise.all([tool('bills_due', { days: 21 }), tool('money_detective'), tool('files_to_check')]);
  const [daily, byMain, sum] = d.trend.length ? await Promise.all([tool('daily_spending', { month }), tool('spending_by_main', { month }), tool('spending_summary', { month })]) : [[], [], { income: 0 }];
  const ask = h('input', { class: 'field', placeholder: 'Ask anything…', style: { fontSize: '16px', padding: '16px 20px', borderRadius: '18px' } });
  ask.addEventListener('keydown', (e) => { if (e.key === 'Enter' && ask.value.trim()) { sessionStorage.setItem('orbit.ask', ask.value.trim()); location.hash = '#/chat'; } });
  const dayTotal = (byMain.find((m) => m.main === 'others') || { net: 0 }).net;
  const outings = byMain.filter((m) => m.main !== 'others').reduce((x, m) => x + m.net, 0);
  const before = daily.reduce((x, r) => x + r.before, 0), ch = before > 0 ? ((dayTotal - before) / before) * 100 : null;
  const link = (label, value, good) => h('a', { class: 'quiet', href: '#/spending' }, h('span', { class: 'faint' }, label), h('span', { class: 'num ' + (good ? 'good' : ''), style: { fontWeight: 650 } }, value));
  const money_ = d.trend.length ? [
    h('div', { class: 'card summary' },
      h('div', {}, h('div', { class: 'eyebrow' }, 'Monthly · ' + monthName(month)), h('div', { class: 'num', style: { fontSize: '44px', fontWeight: 750, letterSpacing: '-.03em', margin: '6px 0 4px' } }, money(dayTotal)),
        h('div', { class: 'muted' }, ch == null || Math.abs(ch) < 10 ? '\u00a0' : `${ch >= 0 ? '↑' : '↓'} ${Math.abs(ch).toFixed(0)}%`)),
      h('div', {}, h('div', { class: 'eyebrow' }, 'Money in'), h('div', { class: 'num good', style: { fontSize: '44px', fontWeight: 750, letterSpacing: '-.03em', margin: '6px 0 4px' } }, money(sum.income)),
        h('div', { class: 'muted' }, '\u00a0')),
      h('div', { class: 'quiets' }, link('One-time', signed(outings, 0)), h('a', { class: 'btn small', href: '#/spending', style: { alignSelf: 'flex-start' } }, 'Money'))),
    daily.length ? dailyTiles(daily.slice(0, 8), null, null) : null] :
    [h('div', { class: 'card welcome-card' }, h('div', { class: 'orb big' }), h('h2', {}, 'Welcome to Orbit'), h('p', { class: 'muted' }, 'Your money, tasks and notes. Private, on this Mac.'), h('a', { class: 'btn primary', href: '#/spending' }, 'Add my files'))];
  const tasksCard = h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'To do')),
    b.tasks_due.length ? h('div', { class: 'list' }, b.tasks_due.map((t) => h('div', { class: 'item' },
      h('button', { class: 'check', 'aria-label': 'Mark done', onclick: guard(async (e) => { await tool('complete_task', { id: t.id }); e.currentTarget.classList.add('done'); setTimeout(render, 350); }) }, h('span', { html: '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>', style: { display: 'contents' } })),
      h('div', { class: 'grow' }, h('div', { style: { fontWeight: 600 } }, t.title), h('div', { class: 'faint', style: { fontSize: '13px' } }, t.due || 'no date'))))) : h('div', { class: 'empty' }, 'All done.'));
  const bills = d.upcoming || [];
  const upCard = h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Coming up')),
    bills.length ? h('div', { class: 'list' }, bills.map((u) => h('div', { class: 'item' }, h('div', { class: 'avatar', style: { background: colour(u.merchant) } }, initials(u.merchant)),
      h('div', { class: 'grow' }, h('div', { style: { fontWeight: 600 } }, u.merchant), h('div', { class: 'faint', style: { fontSize: '13px' } }, u.in_days <= 0 ? 'now' : `in ${u.in_days} days`)), h('span', { class: 'num' }, money(u.amount))))) :
    b.upcoming_dates.length ? h('div', { class: 'list' }, b.upcoming_dates.map((u) => h('div', { class: 'item' }, h('div', { class: 'avatar', style: { background: colour(u.name) } }, initials(u.name)),
      h('div', { class: 'grow' }, h('div', { style: { fontWeight: 600 } }, `${u.name} · ${u.label}`), h('div', { class: 'faint', style: { fontSize: '13px' } }, u.in_days === 0 ? 'today' : `in ${u.in_days} days`)), u.turning ? h('span', { class: 'chip' }, `turning ${u.turning}`) : null))) : h('div', { class: 'empty' }, 'Nothing coming up.'));
  const attention = [
    ...dueSoon.items.slice(0, 3).map((b) => ({ k: b.kind === 'invoice' ? 'bill' : 'due', t: `${b.what} · ${money(b.amount, 2)} · ${b.in_days <= 0 ? 'now' : `in ${b.in_days} days`}` })),
    ...(checks.length ? [{ k: 'check', t: `${checks.length} file${checks.length === 1 ? '' : 's'} need a look` }] : []),
    ...det.items.slice(0, 3).map((x) => ({ k: x.kind, t: x.text }))];
  const attentionCard = attention.length ? h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Needs a look'), h('a', { href: '#/plan', class: 'faint', style: { fontSize: '13px' } }, 'Plan')),
    h('div', { class: 'list' }, attention.map((x) => h('div', { class: 'item' }, h('span', { class: 'chip' }, x.k), h('div', { class: 'grow' }, x.t))))) : null;
  return h('div', { class: 'stack' }, head(`${hello}.`, new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })), ask, ...money_.filter(Boolean), attentionCard, h('div', { class: 'grid g2' }, tasksCard, upCard));
};

pages.chat = async () => {
  const { history } = await api('/api/history');
  const msgs = h('div', { class: 'msgs', id: 'msgs' });
  const input = h('textarea', { rows: 1, placeholder: 'Ask anything…' });
  const sendBtn = h('button', { class: 'send', 'aria-label': 'Send' }, h('span', { html: '<svg viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6"/></svg>', style: { display: 'contents' } }));
  let busy = false;
  const scroll = () => { msgs.scrollTop = msgs.scrollHeight; };
  const bubble = (role, text, tags) => { const b = h('div', { class: 'bubble ' + role }, text, tags && tags.length ? h('div', { class: 'tags' }, tags.map((t) => h('span', { class: 'chip' }, t))) : null); msgs.append(b); scroll(); return b; };
  const welcome = () => h('div', { class: 'welcome' }, h('div', { class: 'orb' }), h('h2', {}, 'How can I help?'), h('div', { class: 'muted' }, 'Private, on this Mac.'),
    h('div', { class: 'suggest', style: { justifyContent: 'center', marginTop: '22px' } }, ['How much did I spend last month?', 'What are my regular payments?', "What's on today?"].map((q) => h('button', { onclick: () => send(q) }, q))));
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
  return h('div', {}, head('Ask Orbit', null, h('button', { class: 'btn ghost', onclick: guard(async () => { await api('/api/chat/reset', {}); render(); }) }, 'New chat')),
    h('div', { class: 'chat' }, msgs, h('div', { class: 'composer' }, input, sendBtn)));
};

async function moneyPage(title, allowed) {
  const [trend0, settings] = await Promise.all([tool('monthly_trend', { months: 12 }), api('/api/settings')]);
  cur = settings.currency;
  const now = new Date().toISOString().slice(0, 7);
  let month = location.hash.split('?m=')[1] || startMonth(trend0);
  let tab = allowed[0]; const openCats = new Set(); const openEvents = new Set();
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
      status.replaceChildren(h('div', { style: { fontWeight: 650 } }, `Added ${r.new_transactions} payments from ${r.files} file${r.files === 1 ? '' : 's'}.`),
        ...r.problems.map((p) => h('div', { class: 'bad' }, p)), r.files_with_no_transactions.length ? h('div', { class: 'muted' }, 'Could not read: ' + r.files_with_no_transactions.join(', ')) : null);
      if (r.files) draw(true);
    }
  }
  async function draw(refreshTrend) {
    const trend = refreshTrend ? await tool('monthly_trend', { months: 12 }) : trend0;
    const [sum, merchants, recurring, todo, slips, docs, docTotals, txs, evs, byMain, daily, inc, checks, ver, cc, pf] = await Promise.all([
      tool('spending_summary', { month }), tool('top_merchants', { month, limit: 8 }), tool('recurring_payments'), tool('uncategorised_spending'),
      tool('list_payslips', { limit: 12 }), tool('finance_documents', { limit: 200 }), tool('finance_document_totals', { by: 'kind' }),
      tool('list_transactions', { since: month + '-01', until: month + '-31', limit: 400 }), tool('list_events'), tool('spending_by_main', { month }), tool('daily_spending', { month }), tool('income_summary', { month }), tool('files_to_check'), tool('verification_report'), tool('currencies'), tool('month_proof', { month })]);
    const curChips = cc.currencies.length > 1 || cc.currencies.some((c) => c.currency !== cc.main) ? h('div', { class: 'seg' }, [...cc.currencies, { currency: 'ALL', payments: 0, label: 'In euros' }].map((c) => h('button', { class: c.currency === cc.viewing ? 'on' : '', title: c.currency === 'ALL' ? 'Show everything in euros' : `${c.payments} payments`,
      onclick: guard(async () => { await api('/api/settings', { view_currency: c.currency }); location.reload(); }) }, c.label || c.currency))) : null;
    const nav = h('div', { class: 'monthnav' }, h('button', { 'aria-label': 'Previous month', onclick: () => step(-1) }, '‹'), h('span', {}, monthName(month)), h('button', { 'aria-label': 'Next month', onclick: () => step(1) }, '›'));
    function step(n) { const d = new Date(month + '-15'); d.setMonth(d.getMonth() + n); month = d.toISOString().slice(0, 7); openCats.clear(); draw(false); }
    const dayTotal = (byMain.find((m) => m.main === 'others') || { net: 0 }).net;
    const outingTotal = byMain.filter((m) => m.main !== 'others').reduce((x, m) => x + m.net, 0);
    const proofChip = pf.proven ? null : h('button', { class: 'proof bad', title: pf.reasons.join('\n'),
      onclick: () => alert('Not proven:\n\n' + pf.reasons.map((r) => '• ' + r).join('\n')) }, '⚠ Check this month · tap to see why');  // nothing is shown for a month that is fine
    const hero = h('div', { class: 'card hero' }, h('div', { class: 'eyebrow' }, 'Spent · ' + monthName(month), ' ', proofChip), h('div', { class: 'big num' }, money(dayTotal + outingTotal)),
      h('div', { class: 'meta' }, h('div', {}, h('div', { class: 'k' }, 'Monthly'), h('div', { class: 'v num' }, money(dayTotal))), h('div', {}, h('div', { class: 'k' }, 'One-time'), h('div', { class: 'v num' }, signed(outingTotal, 0))),
        h('div', {}, h('div', { class: 'k' }, 'Money in'), h('div', { class: 'v num' }, money(sum.income)))));
    const trendCard = h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Month by month'), h('span', { class: 'faint', style: { fontSize: '13px' } }, 'tap a bar')),
      trend.length ? barChart(trend.slice(-8), month, (m) => { month = m; openCats.clear(); draw(false); }) : h('div', { class: 'empty' }, 'No data yet.'));
    const maxM = Math.max(...merchants.map((x) => x.spent), 1);
    const recCard = h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Repeating payments'), recurring.length ? h('span', { class: 'chip' }, `≈ ${money(recurring.reduce((s, r) => s + r.per_month, 0))}/mo`) : null),
      recurring.length ? h('div', { class: 'list' }, recurring.slice(0, 8).map((r) => h('div', { class: 'item' }, h('span', { class: 'sw', style: { width: '10px', height: '10px', borderRadius: '4px', background: colour(r.merchant), flex: 'none' } }),
        h('div', { class: 'grow', style: { textTransform: 'capitalize', fontWeight: 600 } }, r.merchant, h('div', { class: 'faint', style: { fontSize: '12px', textTransform: 'none', fontWeight: 400 } }, `${r.times} payments · last ${r.last}`)), h('div', { class: 'num', style: { fontWeight: 650 } }, money(r.typical_amount, 2))))) : h('div', { class: 'empty' }, 'None found yet.'));
    const slipCard = slips.length ? h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Payslips')), h('table', { class: 'table' },
      h('thead', {}, h('tr', {}, ['Period', 'Gross', 'Tax', 'Pension', 'Net'].map((x, i) => h('th', { class: i ? 'r' : '' }, x)))),
      h('tbody', {}, slips.map((s) => h('tr', {}, h('td', {}, s.period ? monthName(s.period) : s.name), ...[s.gross, s.tax, s.pension].map((v) => h('td', { class: 'r num' }, v != null ? money(v, 2) : '-')), h('td', { class: 'r num', style: { fontWeight: 650 } }, money(s.net, 2))))))) : null;
    const KIND = { invoice: '#6366f1', receipt: '#10b981', payslip: '#ec4899', tax: '#f59e0b', insurance: '#06b6d4', contract: '#8b5cf6', bank_statement: '#a3a3a3', other: '#a3a3a3' };
    const other = docs.filter((d) => !['bank_statement', 'payslip'].includes(d.kind));
    const docCard = docs.length ? h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Other files'), h('div', { class: 'row' }, docTotals.map((t) => h('span', { class: 'chip' }, `${t.grp} ${money(t.total)}`)))),
      other.length ? h('table', { class: 'table' }, h('thead', {}, h('tr', {}, ['', 'From', 'Date', 'Due', 'Total'].map((x, i) => h('th', { class: i === 4 ? 'r' : '' }, x)))),
        h('tbody', {}, other.slice(0, 30).map((d) => h('tr', {}, h('td', {}, h('span', { class: 'chip', style: { background: 'transparent', border: '1px solid var(--line-strong)', color: KIND[d.kind] || 'var(--muted)' } }, h('span', { class: 'sw', style: { background: KIND[d.kind] || '#999' } }), d.kind)),
          h('td', {}, h('div', { style: { fontWeight: 600 } }, d.party || d.title || d.name), d.summary ? h('div', { class: 'faint', style: { fontSize: '12px' } }, d.summary) : null), h('td', { class: 'num' }, d.date || '-'), h('td', { class: 'num' }, d.due_date || '-'),
          h('td', { class: 'r num', style: { fontWeight: 650 } }, d.total != null ? money(d.total, 2) : '-'))))) : h('div', { class: 'empty' }, 'Nothing else yet.')) : null;
    // ---- day to day: category tiles; tap one to see its payments
    const payRow = (t) => h('div', { class: 'pay' }, h('span', { class: 'num faint', style: { width: '48px' } }, t.day.slice(5)), h('span', { class: 'grow', style: { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, t.note || '-'),
      t.event ? h('span', { class: 'chip' }, t.event) : null, t.currency !== cur ? h('span', { class: 'faint', style: { fontSize: '12.5px' } }, new Intl.NumberFormat(undefined, { style: 'currency', currency: t.currency }).format(t.original)) : null, h('span', { class: 'num ' + (t.kind === 'income' ? 'good' : ''), style: { fontWeight: 600 } }, (t.kind === 'income' ? '+' : '−') + money(t.amount, 2)));
    const tiles = dailyTiles(daily, (c) => openCats.has(c), (c) => { openCats.has(c) ? openCats.delete(c) : openCats.add(c); draw(false); });
    const opened = daily.filter((d) => openCats.has(d.category)).map((d) => h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', { style: { textTransform: 'capitalize' } }, d.category), h('span', { class: 'chip' }, money(d.amount))),
      h('div', { class: 'list' }, txs.filter((t) => !t.event && t.kind === 'expense' && (t.category === 'other' ? 'unsorted' : t.category) === d.category).map(payRow))));
    const q = h('input', { class: 'field', placeholder: 'Search payments', style: { maxWidth: '280px' } });
    const listBox = h('div', { class: 'list' });
    const fillAll = () => { const f = q.value.toLowerCase(); listBox.replaceChildren(...txs.filter((t) => !f || (t.note + t.category + (t.event || '')).toLowerCase().includes(f)).slice(0, 200).map(payRow)); };
    q.addEventListener('input', fillAll); fillAll();
    const allPay = h('details', { class: 'card fold' }, h('summary', {}, h('span', { style: { fontWeight: 650, fontSize: '17px' } }, 'All payments'), h('span', { class: 'faint' }, ` · ${txs.length} this month`)), h('div', { style: { height: '14px' } }), q, h('div', { style: { height: '10px' } }), listBox);
    const dailyPane = [daily.length ? tiles : h('div', { class: 'card empty' }, 'Nothing spent this month.'), ...opened, trendCard, allPay];

    // ---- trips & events: found by the model from your statements; tap a card for its lines
    const evCard = (ev) => { const open = openEvents.has(ev.id);
      return h('div', { class: 'card event' + (open ? ' open' : '') },
        h('button', { class: 'evhead', onclick: () => { open ? openEvents.delete(ev.id) : openEvents.add(ev.id); draw(false); } },
          h('div', { class: 'grow', style: { textAlign: 'left' } }, h('div', { style: { fontSize: '17px', fontWeight: 700, letterSpacing: '-.01em' } }, ev.name),
            h('div', { class: 'faint', style: { fontSize: '13px' } }, ev.first ? (ev.first === ev.last ? ev.first : `${ev.first} to ${ev.last}`) : '')),
          h('div', { class: 'num ' + (ev.total < 0 ? 'good' : ''), style: { fontSize: '22px', fontWeight: 750 } }, signed(ev.total)), h('span', { class: 'chev' }, open ? '▾' : '▸')),
        open ? h('div', { class: 'evbody' }, h('div', { class: 'lines' }, ev.lines.map((l) => h('div', { class: 'line' }, h('span', { style: { textTransform: 'capitalize' } }, l.sub), h('span', { class: 'num ' + (l.amount < 0 ? 'good' : '') }, signed(l.amount)))))) : null); };
    const sections = MAINS.filter((m) => m !== 'others').map((m) => { const list = evs.filter((e) => e.main === m); if (!list.length) return null; const net = list.reduce((x, e) => x + e.total, 0);
      return h('div', { class: 'stack', style: { gap: '12px' } }, h('div', { class: 'row' }, h('span', { class: 'sw', style: { width: '12px', height: '12px', borderRadius: '4px', background: MAIN_COLOUR[m] } }), h('h2', {}, MAIN_LABEL[m]), h('span', { class: 'chip' }, signed(net, 0))), ...list.map(evCard)); });
    const eventsPane = evs.length ? [...sections, h('div', { class: 'muted', style: { textAlign: 'center', fontSize: '14px' } }, 'Not right? Tell Orbit in ', h('a', { href: '#/chat' }, 'chat'), '.')]
      : [h('div', { class: 'card welcome-card' }, h('h2', {}, 'No trips or events yet'), h('p', { class: 'muted' }, 'Tickets, flights and hotels are grouped here for you.'))];

    // ---- income: how much came in, from where, and the payslip
    const incChange = inc.before > 0 ? ((inc.total - inc.before) / inc.before) * 100 : null;
    const sl = inc.payslip;
    const incomePane = [
      h('div', { class: 'card summary' }, h('div', {}, h('div', { class: 'eyebrow' }, 'Money in · ' + monthName(month)), h('div', { class: 'num good', style: { fontSize: '46px', fontWeight: 750, letterSpacing: '-.03em', margin: '6px 0 4px' } }, money(inc.total)),
        h('div', { class: 'muted' }, incChange == null ? 'salary, interest and other income' : Math.abs(incChange) < 5 ? 'about the same as last month' : `${incChange >= 0 ? '↑' : '↓'} ${Math.abs(incChange).toFixed(0)}% compared with last month`))),
      inc.sources.length ? dailyTiles(inc.sources.map((x) => ({ category: x.source, amount: x.amount, before: x.before, payments: x.payments })), null, null) : h('div', { class: 'card empty' }, 'No money in this month.'),
      sl ? h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Payslip · ' + monthName(sl.period))),
        h('div', { class: 'lines' }, [['Gross', sl.gross], ['Tax', sl.tax], ['Pension', sl.pension], ['Holiday pay', sl.holiday]].filter(([, v]) => v != null).map(([k, v]) => h('div', { class: 'line' }, h('span', {}, k), h('span', { class: 'num' }, money(v, 2)))),
          h('div', { class: 'line total' }, h('span', {}, 'Paid out (net)'), h('span', { class: 'num good' }, money(sl.net, 2))))) : null,
      trend.length ? h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, 'Money in, month by month'), h('span', { class: 'faint', style: { fontSize: '13px' } }, 'tap a bar')),
        barChart(trend.slice(-8), month, (m) => { month = m; openCats.clear(); draw(false); }, 'income')) : null,
      slips.length > 1 ? h('details', { class: 'card fold' }, h('summary', {}, h('span', { style: { fontWeight: 650, fontSize: '17px' } }, 'All payslips'), h('span', { class: 'faint' }, ` · ${slips.length}`)), h('div', { style: { height: '12px' } }), slipCard) : null];
    // ---- every verifier agent, in words
    const LEVEL = { ok: ['✓', 'good'], warn: ['!', ''], fail: ['✗', 'bad'] };
    const statusCard = ver.problems.length ? h('div', { class: 'card' }, h('h2', { style: { marginBottom: '8px' } }, `${ver.problems.length} thing${ver.problems.length === 1 ? '' : 's'} to look at`),
        h('div', { class: 'list' }, ver.problems.slice(0, 8).map((p) => h('div', { class: 'item' }, h('span', { class: LEVEL[p.level][1], style: { fontWeight: 700, width: '18px' } }, LEVEL[p.level][0]),
          h('div', { class: 'grow' }, h('div', { style: { fontWeight: 600 } }, plain(p.message)), h('div', { class: 'faint', style: { fontSize: '12.5px' } }, p.subject)))))) :
      ver.passed ? h('div', { class: 'card' }, h('div', { class: 'row' }, h('span', { class: 'tick' }, '✓'), h('div', { style: { fontWeight: 650, fontSize: '18px' } }, 'Everything adds up'))) : null;
    const detailsFold = Object.keys(ver.summary).length ? h('details', { class: 'card fold' }, h('summary', {}, h('span', { style: { fontWeight: 650, fontSize: '17px' } }, 'Details')),
      h('div', { style: { height: '12px' } }), h('div', { class: 'lines' }, Object.entries(ver.summary).map(([agent, c]) => h('div', { class: 'line' }, h('span', { style: { textTransform: 'capitalize' } }, agent),
        h('span', { class: 'num' }, h('span', { class: 'good' }, `✓ ${c.ok}`), c.warn ? h('span', { style: { color: 'var(--warn)', marginLeft: '12px' } }, `! ${c.warn}`) : null, c.fail ? h('span', { class: 'bad', style: { marginLeft: '12px' } }, `✗ ${c.fail}`) : null))))) : null;
    // ---- honesty about files: what could not be proven correct is said out loud and is NOT in the totals
    const bad = checks.filter((c) => c.status === 'needs_check'), unproven = checks.filter((c) => c.status === 'unverified');
    const checkNote = bad.length ? h('div', { class: 'note-banner', style: { background: 'rgba(244,63,94,.1)', borderColor: 'rgba(244,63,94,.3)', flexDirection: 'column', alignItems: 'flex-start', gap: '6px' } },
        h('b', {}, `${bad.length} file${bad.length === 1 ? '' : 's'} left out`),
        ...bad.slice(0, 4).map((c) => h('div', { class: 'muted', style: { fontSize: '14px' } }, `${c.file}: ${plain(c.issues) || 'could not be read'}`))) :
      unproven.length ? h('div', { class: 'note-banner' }, h('div', { class: 'grow' }, h('b', {}, `${unproven.length} file${unproven.length === 1 ? '' : 's'} not double-checked`))) : null;
    const empty = !trend.length && !docs.length && !slips.length;
    const tabs = [['daily', 'Monthly'], ['income', 'Income'], ['events', 'One-time'], ['regular', 'Regular'], ['documents', 'Files' + (ver.problems.length ? ` · ${ver.problems.length}` : '')]];
    const tabBar = allowed.length < 2 ? null : h('div', { class: 'seg' }, tabs.filter(([id]) => allowed.includes(id)).map(([id, label]) => h('button', { class: tab === id ? 'on' : '', onclick: () => { tab = id; draw(false); } }, label)));
    const content = { daily: dailyPane, income: incomePane, events: eventsPane, regular: [recCard],
      documents: [statusCard, docCard, detailsFold, h('div', { class: 'muted', style: { textAlign: 'center' } }, h('a', { href: '#/files' }, 'Search all files'))] }[tab];
    const searchBox = h('input', { class: 'field', placeholder: 'Search payments (shop, words, …) and press Enter', style: { width: '100%' } }), results = h('div', { class: 'stack' });
    searchBox.addEventListener('keydown', guard(async (e) => {
      if (e.key !== 'Enter') return;
      const q = searchBox.value.trim();
      if (!q) { results.replaceChildren(); return; }
      const rows = await tool('list_transactions', { query: q, limit: 40 });
      const spent = rows.filter((r) => r.kind === 'expense').reduce((x, r) => x + r.amount, 0);
      results.replaceChildren(h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, `${rows.length} found`), rows.length ? h('span', { class: 'chip' }, 'spent ' + money(spent, 2)) : null),
        rows.length ? h('div', { class: 'list' }, rows.map((r) => h('div', { class: 'item' }, h('div', { class: 'faint', style: { width: '92px', whiteSpace: 'nowrap' } }, r.day), h('div', { class: 'grow' }, r.note), h('div', { class: 'num ' + (r.kind === 'income' ? 'good' : '') }, (r.kind === 'income' ? '+' : '') + money(r.amount, 2))))) : h('div', { class: 'empty' }, 'No payments match.')));
    }));
    const first = h('div', { class: 'card welcome-card' }, h('div', { class: 'orb big' }), h('h2', {}, 'Add your money'),
      h('p', { class: 'muted' }, 'Put your PDFs in your finance folder, then press the button.'),
      h('div', {}, importBtn));
    wrap.replaceChildren(...[head(title, null, empty ? null : curChips, empty ? null : nav, empty ? null : importBtn), status, empty ? null : checkNote, empty ? first : (title === 'Documents' ? null : hero), empty || title !== 'Spending' ? null : searchBox, empty || title !== 'Spending' ? null : results, empty ? null : tabBar, ...(empty ? [] : content)].filter(Boolean));
  }
  await draw(false); poll();
  return wrap;
}
pages.spending = () => moneyPage('Spending', ['daily', 'events', 'regular']);
pages.money = pages.spending;
pages.income = () => moneyPage('Income', ['income']);
pages.documents = () => moneyPage('Documents', ['documents']);

pages.plan = async () => {
  const [yo, goals, fc, tl, look, det, nw, inv, bud, bills] = await Promise.all([tool('yearly_overview'), tool('list_goals'), tool('forecast', { months: 6 }), tool('timeline'), tool('suggestions'), tool('money_detective'), tool('net_worth'), tool('investments'), tool('budget_progress'), tool('bills_due')]);
  cur = yo.currency || cur;
  const row = (...cells) => h('div', { class: 'item' }, ...cells);
  const yearTable = yo.years.length ? h('div', { class: 'list' },
    row(h('div', { class: 'grow faint' }, 'Year'), ...['Salary', 'Spent', 'Saved', 'Kept'].map((t) => h('div', { class: 'faint', style: { width: '96px', textAlign: 'right' } }, t))),
    ...yo.years.slice().reverse().map((y) => row(h('div', { class: 'grow', style: { fontWeight: 650 } }, y.year + (y.months < 12 ? ` · ${y.months} mo` : '')),
      h('div', { class: 'num', style: { width: '96px', textAlign: 'right' } }, money(y.salary)), h('div', { class: 'num', style: { width: '96px', textAlign: 'right' } }, money(y.spent)),
      h('div', { class: 'num ' + (y.saved >= 0 ? 'good' : 'bad'), style: { width: '96px', textAlign: 'right' } }, signed(y.saved, 0)),
      h('div', { class: 'num', style: { width: '96px', textAlign: 'right' } }, y.savings_rate == null ? '–' : y.savings_rate + '%')))) : h('div', { class: 'empty' }, 'No data yet.');
  const budCat = h('input', { class: 'field', placeholder: 'Category (groceries…)', style: { flex: 1 } }), budAmt = h('input', { class: 'field', type: 'number', placeholder: 'Per month', style: { width: '130px' } });
  const addBudget = guard(async () => { if (!budCat.value.trim() || !(+budAmt.value > 0)) return; await tool('set_budget', { category: budCat.value.trim(), monthly_amount: +budAmt.value }); render(); });
  const name = h('input', { class: 'field', placeholder: 'Save for…', style: { flex: 1 } }), target = h('input', { class: 'field', type: 'number', placeholder: 'Amount', style: { width: '130px' } }), by = h('input', { class: 'field', type: 'date', style: { width: '160px' } });
  const addGoal = guard(async () => { if (!name.value.trim() || !(+target.value > 0)) return; await tool('add_goal', { name: name.value.trim(), target: +target.value, by: by.value || undefined }); render(); });
  const goalList = goals.goals.length ? h('div', { class: 'list' }, goals.goals.map((g) => h('div', { class: 'item', style: { display: 'block' } },
    h('div', { class: 'row' }, h('div', { class: 'grow', style: { fontWeight: 650 } }, g.name), h('span', { class: 'num' }, money(g.target)),
      g.on_track === undefined ? null : h('span', { class: 'chip', style: g.on_track ? '' : 'background: var(--bad-soft, #fde8ec); color: var(--bad)' }, g.on_track ? 'on track' : 'behind'),
      h('button', { class: 'btn ghost small', onclick: guard(async () => { await tool('delete_goal', { id: g.id }); render(); }) }, 'Remove')),
    g.percent == null ? null : h('div', { class: 'progress', style: { marginTop: '8px' } }, h('i', { style: { width: Math.min(100, g.percent) + '%' } })),
    h('div', { class: 'faint', style: { fontSize: '13px', marginTop: '4px' } }, [g.percent == null ? 'No balance yet' : `${g.percent}% · ${money(g.have)} now`, g.by ? `by ${g.by}` : '', g.needed_per_month ? `${money(g.needed_per_month)}/month needed` : ''].filter(Boolean).join(' · '))))) : h('div', { class: 'empty' }, 'No goals yet.');
  const fcCard = fc.months.length ? h('div', { class: 'list' }, fc.months.map((m) => row(h('div', { class: 'grow' }, monthName(m.month)), h('div', { class: 'num faint' }, (m.income - m.spent >= 0 ? '+' : '') + signed(m.income - m.spent, 0)), h('div', { class: 'num', style: { width: '110px', textAlign: 'right', fontWeight: 650 } }, m.balance == null ? '' : money(m.balance))))) : h('div', { class: 'empty' }, fc.note);
  const lookItems = [...look.items.map((x) => ({ k: x.topic, t: x.text })), ...det.items.map((x) => ({ k: x.kind, t: x.text }))];
  const card = (title, ...body) => h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, title)), ...body);
  return h('div', { class: 'stack' }, head('Plan', nw.latest == null ? '' : `${money(nw.latest)} in all accounts`),
    bills.items.length ? card('Coming up', h('div', { class: 'list' }, bills.items.slice(0, 8).map((b) => row(h('div', { class: 'grow' }, h('div', { style: { fontWeight: 650 } }, b.what), h('div', { class: 'faint', style: { fontSize: '13px' } }, b.in_days <= 0 ? 'now' : `in ${b.in_days} days · ${b.due}`)), h('div', { class: 'num' }, money(b.amount, 2)))))) : null,
    card('Years', yearTable),
    card('Budgets', h('div', { class: 'row', style: { marginBottom: '12px' } }, budCat, budAmt, h('button', { class: 'btn primary', onclick: addBudget }, 'Set')),
      bud.budgets.length ? h('div', { class: 'list' }, bud.budgets.map((b) => h('div', { class: 'item', style: { display: 'block' } }, h('div', { class: 'row' }, h('div', { class: 'grow', style: { fontWeight: 650 } }, b.category.charAt(0).toUpperCase() + b.category.slice(1)),
        h('span', { class: 'num ' + (b.over ? 'bad' : '') }, `${money(b.spent)} of ${money(b.budget)}`)), h('div', { class: 'progress', style: { marginTop: '8px' } }, h('i', { style: { width: Math.min(100, b.percent || 0) + '%', background: b.over ? 'var(--bad)' : '' } }))))) : h('div', { class: 'empty' }, 'No budgets yet.')),
    card('Goals', h('div', { class: 'row', style: { marginBottom: '12px' } }, name, target, by, h('button', { class: 'btn primary', onclick: addGoal }, 'Add')), goalList),
    card('Next months', h('div', { class: 'faint', style: { fontSize: '13px', marginBottom: '8px' } }, fc.months.length ? 'An estimate from your last six months' : ''), fcCard),
    lookItems.length ? card('Worth a look', h('div', { class: 'list' }, lookItems.slice(0, 12).map((x) => row(h('span', { class: 'chip' }, x.k), h('div', { class: 'grow' }, x.t))))) : null,
    inv.contributed_by_year.length ? card('Invested', h('div', { class: 'list' }, inv.contributed_by_year.slice().reverse().map((y) => row(h('div', { class: 'grow' }, y.year), h('div', { class: 'num' }, money(y.contributed))))), h('div', { class: 'faint', style: { fontSize: '13px', marginTop: '8px' } }, inv.note)) : null,
    card('Timeline', tl.items.length ? h('div', { class: 'list' }, tl.items.slice(0, 20).map((x) => row(h('div', { class: 'faint', style: { width: '104px', whiteSpace: 'nowrap' } }, x.date), h('div', { class: 'grow' }, x.what)))) : h('div', { class: 'empty' }, 'Nothing yet.')));
};

pages.wealth = async () => {
  const [w, accounts, holdings] = await Promise.all([tool('wealth_summary'), tool('accounts_overview'), tool('list_holdings')]);
  const row = (...cells) => h('div', { class: 'item' }, ...cells);
  const card = (title, ...body) => h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, title)), ...body);
  const kind = h('select', { class: 'field', style: { width: '140px' } }, [['investment', 'Investment'], ['asset', 'Asset'], ['debt', 'Debt']].map(([v, t]) => h('option', { value: v }, t)));
  const name = h('input', { class: 'field', placeholder: 'Name (ETF, house, loan…)', style: { flex: 1 } });
  const value = h('input', { class: 'field', type: 'number', placeholder: 'Value', style: { width: '120px' } });
  const units = h('input', { class: 'field', type: 'number', placeholder: 'or Units', style: { width: '100px' } }), price = h('input', { class: 'field', type: 'number', placeholder: 'Price', style: { width: '100px' } });
  const add = guard(async () => {
    if (!name.value.trim() || !(+value.value > 0 || (+units.value > 0 && +price.value > 0))) return;
    await tool('add_holding', { name: name.value.trim(), kind: kind.value, ...(+units.value > 0 && +price.value > 0 ? { units: +units.value, price: +price.value } : { value: +value.value }) });
    render();
  });
  const parts = [['Accounts', w.accounts], ['Investments', w.investments], ['Assets', w.assets], ['Debts', w.debts ? -w.debts : 0]].filter(([, v]) => v);
  return h('div', { class: 'stack' }, head('Wealth', null),
    h('div', { class: 'card hero' }, h('div', { class: 'eyebrow' }, 'Net worth'), h('div', { class: 'big num' }, w.net_worth == null ? '–' : money(w.net_worth)),
      h('div', { class: 'meta' }, parts.map(([k, v]) => h('div', {}, h('div', { class: 'k' }, k), h('div', { class: 'v num' }, signed(v, 0)))))),
    w.series.length > 1 ? card('Accounts over time', barChart(w.series.slice(-12).map((x) => ({ month: x.month, nw: x.eur })), w.series[w.series.length - 1].month, () => {}, 'nw')) : null,
    card('Accounts', accounts.length ? h('div', { class: 'list' }, accounts.map((a) => row(h('div', { class: 'grow' }, h('div', { style: { fontWeight: 650 } }, a.label + ' · ' + a.currency), h('div', { class: 'faint', style: { fontSize: '13px' } }, 'as of ' + a.as_of)),
      a.proven ? null : h('span', { class: 'chip' }, 'check'), h('div', { class: 'num', style: { fontWeight: 650 } }, a.eur == null ? a.balance.toLocaleString() : money(a.eur))))) : h('div', { class: 'empty' }, 'No account balances yet. They come from your statements.')),
    card('You added', h('div', { class: 'faint', style: { fontSize: '13px', marginBottom: '10px' } }, 'Values you typed in. Update them when they change.'),
      h('div', { class: 'row', style: { marginBottom: '12px', flexWrap: 'wrap' } }, kind, name, value, units, price, h('button', { class: 'btn primary', onclick: add }, 'Add')),
      holdings.length ? h('div', { class: 'list' }, holdings.map((x) => row(h('span', { class: 'chip' }, x.kind), h('div', { class: 'grow' }, h('div', { style: { fontWeight: 650 } }, x.name), h('div', { class: 'faint', style: { fontSize: '13px' } }, (x.units ? `${x.units} × ${x.price} · ` : '') + 'as of ' + x.as_of)),
        h('div', { class: 'num' }, (x.kind === 'debt' ? '−' : '') + money(x.value)),
        h('button', { class: 'btn ghost small', onclick: guard(async () => { const v = prompt('New ' + (x.units ? 'price per unit' : 'value') + ' for ' + x.name, x.units ? x.price : x.value); if (v == null || isNaN(+v)) return; await tool('update_holding', { id: x.id, ...(x.units ? { price: +v } : { value: +v }) }); render(); }) }, 'Update'),
        h('button', { class: 'btn ghost small', onclick: guard(async () => { await tool('delete_holding', { id: x.id }); render(); }) }, 'Remove')))) : h('div', { class: 'empty' }, 'Nothing added yet.')),
    h('div', { class: 'muted', style: { fontSize: '13px', textAlign: 'center' } }, w.note));
};

pages.tax = async () => {
  const yo = await tool('yearly_overview');
  const years = yo.years.map((y) => y.year).reverse();
  let year = location.hash.split('?y=')[1] || years[0] || String(new Date().getFullYear());
  const wrap = h('div', { class: 'stack' });
  async function draw() {
    const t = await tool('tax_summary', { year }); cur = t.currency || cur;
    const rows = [];
    const a = t.annual_statement;
    if (a) rows.push(['Annual statement · gross', money(a.gross)], ['Annual statement · tax withheld', money(a.tax_withheld)], ['Annual statement · net', money(a.net)]);
    if (t.payslips.count) rows.push([`Payslips (${t.payslips.count}) · gross`, money(t.payslips.gross)], ['Payslips · tax withheld', money(t.payslips.tax_withheld)], ['Payslips · pension', money(t.payslips.pension)]);
    rows.push(['Interest received', money(t.interest_received, 2)], ['Paid into investments', money(t.paid_into_investments)], ['Insurance paid', money(t.insurance_paid)]);
    t.balances_on_1_january.forEach((b) => rows.push([`Balance on 1 January · …${b.account}`, money(b.balance)]));
    t.tax_letters.forEach((l) => rows.push([`Tax letter ${l.date} · ${l.party || l.name}`, money(l.amount, 2)]));
    const picker = h('div', { class: 'seg' }, (years.length ? years : [year]).map((y) => h('button', { class: y === year ? 'on' : '', onclick: () => { year = y; draw(); } }, y)));
    wrap.replaceChildren(head('Tax', 'Facts for your return, from your documents', picker, h('a', { class: 'btn primary', href: '/report/' + year, target: '_blank' }, 'Print year report')),
      h('div', { class: 'card' }, h('div', { class: 'list' }, rows.map(([k, v]) => h('div', { class: 'item' }, h('div', { class: 'grow' }, k), h('div', { class: 'num', style: { fontWeight: 650 } }, v))))),
      h('div', { class: 'muted', style: { fontSize: '13px', textAlign: 'center' } }, t.note));
  }
  await draw();
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
    tasks.length ? null : h('div', { class: 'empty' }, 'Nothing to do.'));
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
      out.replaceChildren(docs.length ? h('table', { class: 'table' }, h('thead', {}, h('tr', {}, ['Type', 'From / title', 'Date', 'Reference', 'Total'].map((x, i) => h('th', { class: i === 4 ? 'r' : '' }, x)))), h('tbody', {}, docs.map((d) => h('tr', {}, h('td', {}, h('span', { class: 'chip' }, d.kind)), h('td', {}, h('div', { style: { fontWeight: 600 } }, d.party || d.title || d.name), d.summary ? h('div', { class: 'faint', style: { fontSize: '12px' } }, d.summary) : null), h('td', { class: 'num' }, d.date || '-'), h('td', { class: 'num faint' }, d.reference || '-'), h('td', { class: 'r num', style: { fontWeight: 650 } }, d.total != null ? money(d.total, 2) : '-'))))) : h('div', { class: 'empty' }, 'No files yet.')); }
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
