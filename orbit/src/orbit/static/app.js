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
        for (const kid of kids.flat(9))
            if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(kid));
        return el;
    }
    const ICONS = {
        home: 'M3 11.5 12 4l9 7.5M5.5 10v9a1 1 0 0 0 1 1H10v-5h4v5h3.5a1 1 0 0 0 1-1v-9',
        chat: 'M20 12a8 8 0 0 1-11.6 7.1L4 20l1-4.2A8 8 0 1 1 20 12Z',
        plan: 'M3 17l5-6 4 3 6-8M14 6h4v4',
        expenses: 'M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Zm0 3h18M7 15h3',
        savings:
            'M12 5c4.4 0 8 1.1 8 2.5S16.4 10 12 10 4 8.9 4 7.5 7.6 5 12 5Zm8 2.5v4c0 1.4-3.6 2.5-8 2.5s-8-1.1-8-2.5v-4m16 4v4c0 1.4-3.6 2.5-8 2.5s-8-1.1-8-2.5v-4',
        investments: 'M3 17l5-6 4 3 6-8M14 6h4v4M3 21h18',
        networth: 'M4 20V10m6 10V4m6 16v-7m4 7H2',
        search: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14ZM21 21l-4.3-4.3',
        sun: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4',
        moon: 'M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z',
        auto: 'M12 3a9 9 0 1 0 0 18V3Z',
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
        settings:
            'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm7.4-2a7.5 7.5 0 0 0 0-2l2-1.6-2-3.4-2.4 1a7.5 7.5 0 0 0-1.7-1L15 3h-4l-.4 3a7.5 7.5 0 0 0-1.7 1l-2.4-1-2 3.4 2 1.6a7.5 7.5 0 0 0 0 2l-2 1.6 2 3.4 2.4-1a7.5 7.5 0 0 0 1.7 1l.4 3h4l.4-3a7.5 7.5 0 0 0 1.7-1l2.4 1 2-3.4-2-1.6Z',
    };
    const icon = (n) =>
        h('span', { html: `<svg viewBox="0 0 24 24"><path d="${ICONS[n]}"/></svg>`, style: { display: 'contents' } });

    let cur = 'EUR';
    const MAINS = ['sports', 'events', 'trips', 'cancellations', 'others'];
    const MAIN_LABEL = {
        sports: 'Sports',
        events: 'Events',
        trips: 'Trips',
        cancellations: 'Cancellations',
        others: 'Others',
    };
    const MAIN_COLOUR = {
        sports: '#10b981',
        events: '#ec4899',
        trips: '#6366f1',
        cancellations: '#f59e0b',
        others: '#94a3b8',
    };
    const signed = (n, d = 2) => (n < 0 ? '−' : '') + money(Math.abs(n), d);
    const money = (n, d = 0) =>
        new Intl.NumberFormat(undefined, {
            style: 'currency',
            currency: cur,
            minimumFractionDigits: d,
            maximumFractionDigits: d,
        }).format(n || 0);
    const monthName = (ym) => new Date(ym + '-15').toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
    const shortMonth = (ym) => new Date(ym + '-15').toLocaleDateString(undefined, { month: 'short' });
    const PALETTE = [
        '#6366f1',
        '#ec4899',
        '#10b981',
        '#f59e0b',
        '#06b6d4',
        '#8b5cf6',
        '#f43f5e',
        '#84cc16',
        '#0ea5e9',
        '#d946ef',
        '#14b8a6',
        '#a3a3a3',
    ];
    const colour = (name) => {
        let x = 0;
        for (const c of String(name)) x = (x * 31 + c.charCodeAt(0)) >>> 0;
        return PALETTE[x % PALETTE.length];
    };
    const initials = (s) =>
        String(s)
            .split(/\s+/)
            .map((w) => w[0])
            .slice(0, 2)
            .join('');

    async function api(path, body) {
        const opt =
            body === undefined
                ? {}
                : {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json', 'X-Orbit': '1' },
                      body: JSON.stringify(body),
                  };
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
    const guard =
        (fn) =>
        async (...a) => {
            try {
                return await fn(...a);
            } catch (e) {
                toast(e.message, true);
            }
        };

    // ------------------------------------------------------------------ shell
    const PAGES = [
        ['home', 'Home'],
        ['income', 'Income'],
        ['expenses', 'Expenses'],
        ['savings', 'Savings'],
        ['investments', 'Investments'],
        ['networth', 'Net worth'],
        ['plan', 'Plan'],
        ['documents', 'Documents'],
        ['chat', 'Ask'],
        ['tasks', 'Tasks'],
        ['notes', 'Notes'],
        ['people', 'People'],
        ['files', 'Files'],
        ['settings', 'Settings'],
    ];
    const MENU = [
        ['home', 'income', 'expenses', 'savings', 'investments', 'networth', 'plan', 'documents'],
        ['chat', 'tasks', 'notes', 'people'],
        ['settings'],
    ]; // 'files' is reached from Documents
    const ALIAS = { money: 'expenses', spending: 'expenses', wealth: 'networth', tax: 'plan' }; // old addresses still work
    function buildNav() {
        const label = Object.fromEntries(PAGES);
        $('#nav').replaceChildren(
            ...MENU.flatMap((group, i) => [
                i ? h('div', { class: 'nav-gap' }) : null,
                ...group.map((id) =>
                    h(
                        'a',
                        { class: 'nav-item' + (i ? ' minor' : ''), href: '#/' + id, 'data-id': id, title: label[id] },
                        icon(id),
                        h('span', {}, label[id])
                    )
                ),
            ]).filter(Boolean)
        );
    }
    function applyTheme(mode) {
        document.documentElement.dataset.theme = mode;
        const b = $('#theme');
        if (b) {
            b.replaceChildren(icon(mode === 'dark' ? 'moon' : mode === 'light' ? 'sun' : 'auto'));
            b.title = 'Theme: ' + mode;
        }
    }
    function setupTheme() {
        let mode = 'dark';
        try {
            mode = localStorage.getItem('orbit.theme') || 'dark';
        } catch (_) {
            /* private window */
        }
        applyTheme(mode);
        const b = $('#theme');
        if (!b) return;
        b.addEventListener('click', () => {
            mode = mode === 'auto' ? 'dark' : mode === 'dark' ? 'light' : 'auto';
            try {
                localStorage.setItem('orbit.theme', mode);
            } catch (_) {
                /* ignore */
            }
            applyTheme(mode);
        });
    }
    async function refreshStatus() {
        try {
            const s = await api('/api/status');
            $('#ai-pill').className = 'pill ' + (s.ai ? 'ok' : 'bad');
            $('#ai-text').textContent = s.ai ? 'Assistant ready' : 'Assistant off';
            $('#ai-top').className = 'status ' + (s.ai ? 'ok' : 'bad');
            $('#ai-top').textContent = s.ai ? 'Assistant ready' : 'Assistant off';
            $('#ai-pill').title = s.ai ? s.model : s.problem;
        } catch (_) {
            $('#ai-pill').className = 'pill bad';
            $('#ai-text').textContent = 'Not responding';
        }
    }
    const route = () => (location.hash.replace('#/', '') || 'home').split('?')[0];
    async function render() {
        const wanted = ALIAS[route()] || route(),
            id = PAGES.some(([p]) => p === wanted) ? wanted : 'home';
        document.body.dataset.page = id;
        if (id === 'chat' && corner.open) setCorner(false);
        document.querySelectorAll('.nav-item').forEach((a) => a.classList.toggle('active', a.dataset.id === id));
        const main = $('#main');
        main.replaceChildren(h('div', { class: 'empty' }, 'Loading...'));
        main.style.animation = 'none';
        void main.offsetWidth;
        main.style.animation = '';
        try {
            main.replaceChildren(await pages[id]());
        } catch (e) {
            main.replaceChildren(
                h('div', { class: 'card' }, h('h2', {}, 'Something went wrong'), h('p', { class: 'muted' }, e.message))
            );
        }
    }
    const head = (title, sub, ...right) =>
        h(
            'div',
            { class: 'page-head' },
            h('div', {}, h('h1', {}, title), sub && h('div', { class: 'sub' }, sub)),
            h('div', { class: 'row' }, ...right)
        );

    // ------------------------------------------------------------------ small components
    const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;
    /** Numbers that count up when they appear (not for people who asked for less motion). */
    function countUp(el, value, fmt) {
        if (REDUCED || !Number.isFinite(value)) {
            el.textContent = fmt(value);
            return el;
        }
        const t0 = performance.now(),
            ms = 650;
        const tick = (t) => {
            const k = Math.min(1, (t - t0) / ms);
            el.textContent = fmt(value * (1 - Math.pow(1 - k, 3)));
            if (k < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
        return el;
    }
    /** A small area chart of a few numbers, drawn in the accent colours. */
    function sparkline(values, w = 280, hgt = 70) {
        const v = values.length > 1 ? values : [0, ...values, 0],
            max = Math.max(...v, 1),
            min = Math.min(...v, 0);
        const x = (i) => (i / (v.length - 1)) * w,
            y = (n) => hgt - 6 - ((n - min) / (max - min || 1)) * (hgt - 14);
        const line = v.map((n, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(n).toFixed(1)}`).join(' ');
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('viewBox', `0 0 ${w} ${hgt}`);
        svg.setAttribute('class', 'spark');
        svg.setAttribute('preserveAspectRatio', 'none');
        svg.innerHTML =
            `<defs><linearGradient id="sg" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".45"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient></defs>` +
            `<path d="${line} L${w} ${hgt} L0 ${hgt} Z" fill="url(#sg)"/><path d="${line}" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>`;
        return svg;
    }
    /** One big number with a label: the building block of the overview rows. */
    const stat = (label, value, sub, href, tone) =>
        h(
            href ? 'a' : 'div',
            { class: 'stat', href },
            h('div', { class: 'eyebrow' }, label),
            h('div', { class: 'stat-v num ' + (tone || '') }, value),
            sub ? h('div', { class: 'stat-sub' }, sub) : null
        );
    const section = (title, ...body) =>
        h('section', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', {}, title)), ...body);

    // ------------------------------------------------------------------ category look
    const CATS = {
        groceries: ['#22c55e', 'M3 4h2l2.4 11h10.2l2-8H6.2M9 20h.01M17 20h.01'],
        food: ['#f97316', 'M7 3v8a2 2 0 0 0 2 2v8M5 3v6M9 3v6M17 3c-2 2-2.5 5-2.5 8h2.5v10'],
        rent: ['#a855f7', 'M3 11.5 12 4l9 7.5M5.5 10v9a1 1 0 0 0 1 1H10v-5h4v5h3.5a1 1 0 0 0 1-1v-9'],
        insurance: ['#14b8a6', 'M12 3 4.5 6v5.5c0 4.4 3 8.2 7.5 9.5 4.5-1.3 7.5-5.1 7.5-9.5V6L12 3Z'],
        shopping: ['#ec4899', 'M5 8h14l-1 12H6L5 8Zm4 0V7a3 3 0 0 1 6 0v1'],
        utilities: ['#eab308', 'M13 2 4 14h7l-1 8 9-12h-7l1-8Z'],
        subscriptions: ['#6366f1', 'M17 2l3 3-3 3M20 5H8a4 4 0 0 0-4 4v1M7 22l-3-3 3-3M4 19h12a4 4 0 0 0 4-4v-1'],
        transport: ['#0ea5e9', 'M5 16V8a3 3 0 0 1 3-3h8a3 3 0 0 1 3 3v8H5Zm0 0v2m14-2v2M8 12h.01M16 12h.01'],
        fuel: [
            '#f59e0b',
            'M5 21V5a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v16M3 21h14M15 8h2a2 2 0 0 1 2 2v6a1.5 1.5 0 0 0 3 0V9l-3-3',
        ],
        medical: ['#f43f5e', 'M12 21s-7-4.4-9-9a5 5 0 0 1 9-3 5 5 0 0 1 9 3c-2 4.6-9 9-9 9ZM12 9v6M9 12h6'],
        salary: ['#10b981', 'M4 8h16v11H4V8Zm5 0V6a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M4 13h16'],
        interest: ['#06b6d4', 'M19 5 5 19M7 7h.01M17 17h.01'],
        investments: ['#8b5cf6', 'M3 17l5-6 4 3 6-8M14 6h4v4'],
        cash: [
            '#84cc16',
            'M12 5v14M9 8.5a3 3 0 0 1 3-1.5c2 0 3 1 3 2.5s-1 2-3 2.5-3 1-3 2.5 1 2.5 3 2.5a3 3 0 0 0 3-1.5',
        ],
        refund: ['#38bdf8', 'M4 12a8 8 0 1 0 3-6.2M4 4v4h4'],
        trips: ['#3b82f6', 'M2 14l20-8-8 20-3-9-9-3Z'],
        events: ['#ec4899', 'M3 9a2 2 0 0 0 0 6v3h18v-3a2 2 0 0 0 0-6V6H3v3Zm10-3v12'],
        sports: ['#22c55e', 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18'],
        cancellations: ['#ef4444', 'M6 6l12 12M18 6 6 18'],
        transfers: ['#94a3b8', 'M7 7h13l-3-3M17 17H4l3 3'],
        other: ['#94a3b8', 'M5 12h.01M12 12h.01M19 12h.01'],
    };
    const catColor = (n) => (CATS[String(n).toLowerCase()] || [colour(n)])[0];
    /** A coloured rounded square with the category's icon: the same look wherever a category appears. */
    const catBadge = (name, size = 40) => {
        const k = CATS[String(name).toLowerCase()] || [colour(name), CATS.other[1]];
        return h('span', {
            class: 'cat-badge',
            style: `width:${size}px;height:${size}px;--c:${k[0]}`,
            html: `<svg viewBox="0 0 24 24"><path d="${k[1]}"/></svg>`,
        });
    };
    /** Money in against money spent, month by month, as two soft areas. */
    function areaChart(trend) {
        const w = 640,
            hgt = 230,
            pad = { l: 10, r: 22, t: 14, b: 28 };
        const rows = trend.slice(-12),
            max = Math.max(...rows.flatMap((t) => [t.spent, t.income]), 1);
        const x = (i) => pad.l + (i * (w - pad.l - pad.r)) / Math.max(rows.length - 1, 1),
            y = (v) => hgt - pad.b - (v / max) * (hgt - pad.b - pad.t);
        const line = (k) => rows.map((t, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(t[k]).toFixed(1)}`).join(' ');
        const area = (k) =>
            `${line(k)} L${x(rows.length - 1).toFixed(1)} ${hgt - pad.b} L${x(0).toFixed(1)} ${hgt - pad.b} Z`;
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('viewBox', `0 0 ${w} ${hgt}`);
        svg.setAttribute('class', 'area');
        const grid = [0, 1, 2, 3]
            .map((i) => {
                const gy = pad.t + (i * (hgt - pad.b - pad.t)) / 3;
                return `<line x1="${pad.l}" x2="${w - pad.r}" y1="${gy}" y2="${gy}" class="grid"/>`;
            })
            .join('');
        const labels = rows
            .map((t, i) =>
                i % 2 === (rows.length - 1) % 2
                    ? `<text x="${x(i)}" y="${hgt - 8}" text-anchor="middle" class="axis">${new Date(t.month + '-15').toLocaleDateString(undefined, { month: 'short' })}</text>`
                    : ''
            )
            .join('');
        const dots = (k, c) =>
            rows
                .map(
                    (t, i) =>
                        `<circle cx="${x(i)}" cy="${y(t[k])}" r="4" fill="${c}" class="pt"><title>${monthName(t.month)} · ${k === 'spent' ? 'spent' : 'in'} ${money(t[k])}</title></circle>`
                )
                .join('');
        svg.innerHTML =
            `<defs><linearGradient id="ga" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#ff5fa2" stop-opacity=".45"/><stop offset="1" stop-color="#ff5fa2" stop-opacity="0"/></linearGradient>` +
            `<linearGradient id="gb" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#22d3ee" stop-opacity=".4"/><stop offset="1" stop-color="#22d3ee" stop-opacity="0"/></linearGradient></defs>${grid}` +
            `<path d="${area('income')}" fill="url(#gb)"/><path d="${line('income')}" fill="none" stroke="#22d3ee" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>` +
            `<path d="${area('spent')}" fill="url(#ga)"/><path d="${line('spent')}" fill="none" stroke="#ff5fa2" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>${dots('income', '#22d3ee')}${dots('spent', '#ff5fa2')}${labels}`;
        return h(
            'div',
            {},
            svg,
            h(
                'div',
                { class: 'chart-legend' },
                h('span', {}, h('i', { style: { background: '#ff5fa2' } }), 'Spent'),
                h('span', {}, h('i', { style: { background: '#22d3ee' } }), 'Money in')
            )
        );
    }
    /** The donut with its legend: where the month's money went. */
    function spendDonut(rows) {
        const data = rows.map((d) => ({ label: d.category, value: d.amount, colour: catColor(d.category) })),
            total = data.reduce((x, d) => x + d.value, 0) || 1;
        return h(
            'div',
            { class: 'donut-wrap' },
            donut(data),
            h(
                'div',
                { class: 'legend' },
                data
                    .slice(0, 7)
                    .map((d) =>
                        h(
                            'div',
                            { class: 'legend-row' },
                            h('span', { class: 'sw', style: { background: d.colour } }),
                            h('span', { class: 'nm' }, d.label),
                            h('span', { class: 'amt num' }, money(d.value)),
                            h(
                                'span',
                                { class: 'faint small', style: { width: '40px', textAlign: 'right' } },
                                Math.round((d.value / total) * 100) + '%'
                            )
                        )
                    )
            )
        );
    }

    /** Columns made of coloured parts (salary, bonus, other), tallest = the biggest month. */
    function stackedBars(rows, parts) {
        const max = Math.max(...rows.map((r) => r.total), 1);
        return h(
            'div',
            {},
            h(
                'div',
                { class: 'bars' },
                rows.map((r) =>
                    h(
                        'div',
                        { class: 'bar-col', title: `${monthName(r.month)} · ${money(r.total)}` },
                        h('div', { class: 'bar-val' }, r.total ? money(r.total) : ''),
                        h(
                            'div',
                            { class: 'stackbar', style: { height: (r.total / max) * 100 + '%' } },
                            parts.map(([k, , c]) =>
                                r[k] ? h('i', { style: { flexGrow: String(r[k]), background: c } }) : null
                            )
                        ),
                        h(
                            'div',
                            { class: 'bar-label' },
                            new Date(r.month + '-15').toLocaleDateString(undefined, { month: 'short' })
                        )
                    )
                )
            ),
            h(
                'div',
                { class: 'chart-legend' },
                parts.map(([, label, c]) => h('span', {}, h('i', { style: { background: c } }), label))
            )
        );
    }
    /** Bars that can go below zero: green when money was kept, red when more went out than came in. */
    function signedBars(rows) {
        const top = Math.max(...rows.map((r) => r.value), 0),
            bottom = Math.min(...rows.map((r) => r.value), 0),
            span = top - bottom || 1,
            zero = (top / span) * 100;
        return h(
            'div',
            { class: 'sbars' },
            h('div', { class: 'szero', style: { top: zero + '%' } }),
            rows.map((r) => {
                const height = (Math.abs(r.value) / span) * 100;
                return h(
                    'div',
                    {
                        class: 'scol',
                        title: `${monthName(r.month)} · ${signed(r.value, 0)}${r.rate == null ? '' : ' · ' + r.rate + '%'}`,
                    },
                    h('i', {
                        class: r.value >= 0 ? 'pos' : 'neg',
                        style: { height: height + '%', top: r.value >= 0 ? zero - height + '%' : zero + '%' },
                    }),
                    h(
                        'span',
                        { class: 'slabel' },
                        new Date(r.month + '-15').toLocaleDateString(undefined, { month: 'short' })
                    )
                );
            })
        );
    }
    const rate = (n) => (n == null ? '–' : n + '%');
    const emptyCard = (text) =>
        h(
            'div',
            { class: 'card welcome-card' },
            h('div', { class: 'orb big' }),
            h('h2', {}, 'Nothing here yet'),
            h('p', { class: 'muted' }, text),
            h('a', { class: 'btn primary', href: '#/documents' }, 'Add my files')
        );
    const heroOf = (eyebrow, bigText, meta) =>
        h(
            'div',
            { class: 'card hero' },
            h('div', { class: 'eyebrow' }, eyebrow),
            h('div', { class: 'big num' }, bigText),
            h(
                'div',
                { class: 'meta' },
                meta.map(([k, v]) => h('div', {}, h('div', { class: 'k' }, k), h('div', { class: 'v num' }, v)))
            )
        );

    // ------------------------------------------------------------------ charts
    function donut(data) {
        const total = data.reduce((s, d) => s + d.value, 0) || 1,
            R = 70,
            C = 2 * Math.PI * R;
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('viewBox', '0 0 190 190');
        svg.setAttribute('class', 'donut');
        svg.innerHTML = `<circle cx="95" cy="95" r="${R}" stroke="var(--surface-2)"/>`;
        let acc = 0;
        data.forEach((d) => {
            const len = (d.value / total) * C,
                c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
            c.setAttribute('cx', 95);
            c.setAttribute('cy', 95);
            c.setAttribute('r', R);
            c.setAttribute('stroke', d.colour);
            c.setAttribute('stroke-dasharray', `0 ${C}`);
            c.setAttribute('stroke-dashoffset', -acc);
            c.setAttribute('transform', 'rotate(-90 95 95)');
            svg.append(c);
            acc += len;
            requestAnimationFrame(() =>
                requestAnimationFrame(() => c.setAttribute('stroke-dasharray', `${Math.max(len - 3, 0.1)} ${C}`))
            );
        });
        const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        t.setAttribute('x', 95);
        t.setAttribute('y', 92);
        t.setAttribute('text-anchor', 'middle');
        t.setAttribute('fill', 'var(--ink)');
        t.setAttribute('font-size', 22);
        t.setAttribute('font-weight', 700);
        t.textContent = money(total);
        svg.append(t);
        const t2 = t.cloneNode();
        t2.setAttribute('y', 112);
        t2.setAttribute('font-size', 12);
        t2.setAttribute('font-weight', 500);
        t2.setAttribute('fill', 'var(--faint)');
        t2.textContent = 'spent';
        svg.append(t2);
        return svg;
    }
    function barChart(trend, selected, onPick, key = 'spent') {
        const max = Math.max(...trend.map((t) => t[key]), 1);
        return h(
            'div',
            { class: 'bars' },
            trend.map((t, i) =>
                h(
                    'div',
                    { class: 'bar-col', title: `${monthName(t.month)}: ${money(t[key])}` },
                    h('div', { class: 'bar-val num' }, t[key] ? money(t[key]) : ''),
                    h('div', {
                        class: 'bar' + (t.month === selected ? ' on' : ''),
                        style: { height: Math.max((t[key] / max) * 100, 3) + '%', animationDelay: i * 50 + 'ms' },
                        onclick: () => onPick(t.month),
                    }),
                    h('div', { class: 'bar-label' }, shortMonth(t.month))
                )
            )
        );
    }

    function changeNote(d) {
        const ch = d.before > 0 ? ((d.amount - d.before) / d.before) * 100 : null;
        return ch == null
            ? 'new'
            : Math.abs(ch) < 10
              ? ''
              : ch > 100
                ? '↑ 2×+'
                : `${ch >= 0 ? '↑' : '↓'} ${Math.abs(ch).toFixed(0)}%`;
    }
    /** Say what a check found in everyday words. */
    function plain(m) {
        return String(m)
            .replace(/the balances do not add up at \d+ place\(s\)/, "the numbers don't add up")
            .replace(
                /opening balance and transactions do not add up to the closing balance.*/,
                "the numbers don't add up"
            )
            .replace(/opening \+ transactions gives \S+ but the statement prints \S+/, "the total doesn't match")
            .replace(/two independent readings of the layout disagree.*/, 'it could not be read reliably')
            .replace(/the layout of this file could not be understood/, 'it could not be read')
            .replace(/line \d+ has an amount but no date/, 'a line has no date')
            .replace(/cannot tell whether .* is money in or out/, 'it is unclear if a payment is money in or out')
            .replace(/line \d+: the figure .* sits in a column read as text/, 'a figure is in the wrong place')
            .replace(
                /the stored payments add up to .* but the statements say .*/,
                "the payments don't match the statements"
            )
            .replace(/closing .* does not match the next opening .*/, 'it does not join the next statement');
    }
    /** Monthly category tiles, shared by Home and Money. `isOn(category)` and `onTap(category)` are optional. */
    function dailyTiles(daily, isOn, onTap) {
        const max = Math.max(...daily.map((d) => d.amount), 1);
        return h(
            'div',
            { class: 'tiles' },
            daily.map((d) =>
                h(
                    onTap ? 'button' : 'div',
                    {
                        class: 'tile' + (isOn && isOn(d.category) ? ' on' : ''),
                        onclick: onTap ? () => onTap(d.category) : null,
                    },
                    h('div', { class: 'row' }, catBadge(d.category, 34), h('span', { class: 'tname' }, d.category)),
                    h('div', { class: 'tamt num' }, money(d.amount)),
                    h(
                        'div',
                        { class: 'meter' },
                        h('i', { style: { width: (d.amount / max) * 100 + '%', background: catColor(d.category) } })
                    ),
                    h('div', { class: 'faint', style: { fontSize: '12.5px', marginTop: '8px' } }, changeNote(d))
                )
            )
        );
    }
    /** The month to open on: the latest with data, unless it is the current month and only a few days old. */
    function startMonth(trend) {
        // statements arrive after the month ends, so the newest month with data is the one to show
        return trend.length ? trend[trend.length - 1].month : new Date().toISOString().slice(0, 7);
    }

    // ------------------------------------------------------------------ finding things
    /** Go to the Payments list with some filters already chosen (a shop, a category, a month). */
    function goExplore(filters) {
        try {
            sessionStorage.setItem('orbit.explore', JSON.stringify(filters || {}));
        } catch (_) {
            /* private window */
        }
        if (ALIAS[route()] === 'expenses' || route() === 'expenses') render();
        else location.hash = '#/expenses';
    }
    const PAGE_LINKS = [
        [
            'Home',
            'home',
            () => {
                location.hash = '#/home';
            },
        ],
        [
            'Income',
            'income',
            () => {
                location.hash = '#/income';
            },
        ],
        [
            'Expenses',
            'expenses',
            () => {
                location.hash = '#/expenses';
            },
        ],
        ['Payments', 'search', () => goExplore({})],
        [
            'Savings',
            'savings',
            () => {
                location.hash = '#/savings';
            },
        ],
        [
            'Investments',
            'investments',
            () => {
                location.hash = '#/investments';
            },
        ],
        [
            'Net worth',
            'networth',
            () => {
                location.hash = '#/networth';
            },
        ],
        [
            'Plan',
            'plan',
            () => {
                location.hash = '#/plan';
            },
        ],
        [
            'Tax',
            'documents',
            () => {
                location.hash = '#/tax';
            },
        ],
        [
            'Documents',
            'documents',
            () => {
                location.hash = '#/documents';
            },
        ],
        ['Ask Orbit', 'chat', () => setCorner(true)],
        [
            'Tasks',
            'tasks',
            () => {
                location.hash = '#/tasks';
            },
        ],
        [
            'Notes',
            'notes',
            () => {
                location.hash = '#/notes';
            },
        ],
        [
            'People',
            'people',
            () => {
                location.hash = '#/people';
            },
        ],
        [
            'Settings',
            'settings',
            () => {
                location.hash = '#/settings';
            },
        ],
    ];

    /** A side panel with everything known about one payment. */
    async function openPayment(id) {
        const d = await tool('payment_detail', { id });
        const close = () => {
            ov.remove();
            document.removeEventListener('keydown', onKey);
        };
        const onKey = (e) => {
            if (e.key === 'Escape') close();
        };
        const line = (k, v) =>
            v == null || v === ''
                ? null
                : h('div', { class: 'kv' }, h('span', { class: 'faint' }, k), h('span', {}, v));
        const foreign =
            d.currency !== cur
                ? new Intl.NumberFormat(undefined, { style: 'currency', currency: d.currency }).format(d.original)
                : null;
        const ov = h(
            'div',
            {
                class: 'overlay right',
                onclick: (e) => {
                    if (e.target === ov) close();
                },
            },
            h(
                'aside',
                { class: 'drawer' },
                h(
                    'div',
                    { class: 'row between' },
                    h('div', { class: 'eyebrow' }, 'Payment'),
                    h('button', { class: 'btn ghost small', onclick: close }, 'Close')
                ),
                h(
                    'div',
                    { class: 'row', style: { gap: '14px', marginTop: '10px' } },
                    catBadge(d.category, 52),
                    h(
                        'div',
                        {},
                        h(
                            'div',
                            { class: 'drawer-amt num ' + (d.kind === 'income' ? 'good' : '') },
                            (d.kind === 'income' ? '+' : '−') + money(d.amount, 2)
                        ),
                        foreign ? h('div', { class: 'faint' }, 'originally ' + foreign) : null
                    )
                ),
                h('div', { class: 'drawer-note' }, d.note || '(no description)'),
                h(
                    'div',
                    { class: 'chips' },
                    h('span', { class: 'chip' }, d.category),
                    d.is_transfer ? h('span', { class: 'chip' }, 'between your accounts') : null,
                    d.event ? h('span', { class: 'chip' }, d.event + (d.sub ? ' · ' + d.sub : '')) : null,
                    d.same_amount_this_month
                        ? h(
                              'span',
                              { class: 'chip bad' },
                              `${d.same_amount_this_month} more of exactly this amount this month`
                          )
                        : null
                ),
                h(
                    'div',
                    { class: 'kvs' },
                    line('Date', d.day),
                    line('Account', d.account),
                    line('From file', d.file),
                    line('Shop / payee', d.merchant),
                    line('Category chosen by', d.category_chosen_by),
                    line('Balance after', d.balance_after == null ? null : money(d.balance_after, 2)),
                    d.refund_of ? line('Refund of', `${d.refund_of.day} · ${money(d.refund_of.amount, 2)}`) : null,
                    ...d.refunded_by.map((r) => line('Refunded on', `${r.day} · ${money(r.amount, 2)}`))
                ),
                d.merchant
                    ? h(
                          'button',
                          {
                              class: 'btn primary',
                              style: { marginTop: '18px' },
                              onclick: () => {
                                  close();
                                  goExplore({ q: d.merchant });
                              },
                          },
                          `All payments to ${d.merchant}`
                      )
                    : null
            )
        );
        document.body.append(ov);
        document.addEventListener('keydown', onKey);
    }

    /** One search box for everything: pages, payments, shops, files, people, notes, tasks. Opens with Cmd/Ctrl+K or "/". */
    function openPalette() {
        if ($('.palette')) return;
        const input = h('input', {
            class: 'palette-input',
            placeholder: 'Search payments, shops, files, people… or jump to a page',
            autocomplete: 'off',
            spellcheck: 'false',
        });
        const list = h('div', { class: 'palette-list' });
        let items = [],
            active = 0,
            seq = 0;
        const close = () => {
            ov.remove();
            document.removeEventListener('keydown', onKey, true);
        };
        const run = (it) => {
            close();
            it.run();
        };
        const paint = () => {
            list.replaceChildren(
                ...(items.length
                    ? items.map((it, i) =>
                          it.head
                              ? h('div', { class: 'palette-head' }, it.head)
                              : h(
                                    'button',
                                    {
                                        class: 'palette-item' + (i === active ? ' on' : ''),
                                        'data-i': i,
                                        onclick: () => run(it),
                                        onmouseenter: () => {
                                            active = i;
                                            mark();
                                        },
                                    },
                                    it.cat
                                        ? catBadge(it.cat, 30)
                                        : h('span', {
                                              class: 'cat-badge',
                                              style: '--c:#8b5cf6;width:30px;height:30px',
                                              html: `<svg viewBox="0 0 24 24"><path d="${ICONS[it.icon] || ICONS.search}"/></svg>`,
                                          }),
                                    h(
                                        'span',
                                        { class: 'grow' },
                                        h('div', { class: 'strong' }, it.label),
                                        it.sub ? h('div', { class: 'faint small' }, it.sub) : null
                                    ),
                                    it.right ? h('span', { class: 'num faint' }, it.right) : null
                                )
                      )
                    : [h('div', { class: 'empty' }, 'No results')])
            );
            list.querySelector('.on')?.scrollIntoView({ block: 'nearest' });
        };
        const mark = () =>
            list.querySelectorAll('.palette-item').forEach((b) => b.classList.toggle('on', +b.dataset.i === active));
        const pageItems = (q) =>
            PAGE_LINKS.filter(([n]) => !q || n.toLowerCase().includes(q)).map(([n, ico, go]) => ({
                label: n,
                sub: 'Go to',
                icon: ico,
                run: go,
            }));
        const firstReal = () => {
            active = Math.max(
                0,
                items.findIndex((x) => !x.head)
            );
        };
        const search = async () => {
            const q = input.value.trim().toLowerCase(),
                mine = ++seq;
            if (q.length < 2) {
                items = [{ head: 'Jump to' }, ...pageItems(q)];
                firstReal();
                paint();
                return;
            }
            const r = await tool('search_everything', { query: q });
            if (mine !== seq) return;
            const pg = pageItems(q);
            const ask = {
                label: `Ask Orbit: “${input.value.trim()}”`,
                sub: 'Chat',
                icon: 'chat',
                run: () => askOrbit(input.value.trim()),
            };
            items = [
                ...(pg.length ? [{ head: 'Pages' }, ...pg.slice(0, 4)] : []),
                ...(r.merchants.length
                    ? [
                          { head: 'Shops and payees' },
                          ...r.merchants.map((m) => ({
                              label: m.merchant,
                              sub: `${m.payments} payments`,
                              right: money(m.spent),
                              cat: 'other',
                              run: () => goExplore({ q: m.merchant }),
                          })),
                      ]
                    : []),
                ...(r.payments.length
                    ? [
                          { head: 'Payments' },
                          ...r.payments.map((p) => ({
                              label: p.note,
                              sub: `${p.day} · ${p.category}`,
                              right: (p.kind === 'income' ? '+' : '−') + money(p.amount, 2),
                              cat: p.category,
                              run: () => openPayment(p.id),
                          })),
                      ]
                    : []),
                ...(r.documents.length
                    ? [
                          { head: 'Files' },
                          ...r.documents.map((d) => ({
                              label: d.party || d.name,
                              sub: `${d.kind} · ${d.date || ''}`,
                              right: d.total ? money(d.total, 2) : '',
                              icon: 'documents',
                              run: () => {
                                  location.hash = '#/documents';
                              },
                          })),
                      ]
                    : []),
                ...(r.people.length
                    ? [
                          { head: 'People' },
                          ...r.people.map((p) => ({
                              label: p.name,
                              sub: p.relation,
                              icon: 'people',
                              run: () => {
                                  location.hash = '#/people';
                              },
                          })),
                      ]
                    : []),
                ...(r.notes.length
                    ? [
                          { head: 'Notes' },
                          ...r.notes.map((n) => ({
                              label: n.title,
                              icon: 'notes',
                              run: () => {
                                  location.hash = '#/notes';
                              },
                          })),
                      ]
                    : []),
                ...(r.tasks.length
                    ? [
                          { head: 'Tasks' },
                          ...r.tasks.map((t) => ({
                              label: t.title,
                              sub: t.due || '',
                              icon: 'tasks',
                              run: () => {
                                  location.hash = '#/tasks';
                              },
                          })),
                      ]
                    : []),
                { head: 'Or ask' },
                ask,
            ];
            firstReal();
            paint();
        };
        let timer;
        input.addEventListener('input', () => {
            clearTimeout(timer);
            timer = setTimeout(guard(search), 140);
        });
        const move = (d) => {
            const idx = items.map((x, i) => (x.head ? -1 : i)).filter((i) => i >= 0);
            if (!idx.length) return;
            active = idx[(idx.indexOf(active) + d + idx.length) % idx.length];
            mark();
            list.querySelector('.on')?.scrollIntoView({ block: 'nearest' });
        };
        const onKey = (e) => {
            if (e.key === 'Escape') {
                e.preventDefault();
                close();
            } else if (e.key === 'ArrowDown') {
                e.preventDefault();
                move(1);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                move(-1);
            } else if (e.key === 'Enter' && items[active] && !items[active].head) {
                e.preventDefault();
                run(items[active]);
            }
        };
        const ov = h(
            'div',
            {
                class: 'overlay top',
                onclick: (e) => {
                    if (e.target === ov) close();
                },
            },
            h(
                'div',
                { class: 'palette' },
                h('div', { class: 'palette-bar' }, icon('search'), input, h('kbd', {}, 'esc')),
                list
            )
        );
        document.body.append(ov);
        document.addEventListener('keydown', onKey, true);
        items = [{ head: 'Jump to' }, ...pageItems('')];
        firstReal();
        paint();
        input.focus();
    }
    document.addEventListener('keydown', (e) => {
        const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || '');
        if ((e.key === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !typing)) {
            e.preventDefault();
            openPalette();
        }
    });

    /** Every payment, with filters: words, month, category, money in or out, newest or largest; a page at a time, with totals for the whole selection. */
    function paymentsExplorer(months, categories, initial) {
        const st = { q: '', month: '', category: '', kind: '', sort: 'date', ...initial };
        const rows = h('div', { class: 'list' }),
            summary = h('div', { class: 'explore-sum' }),
            more = h('button', { class: 'btn', style: { display: 'none', margin: '16px auto 0' } }, 'Show more'),
            chips = h('div', { class: 'chips' });
        let offset = 0;
        const select = (key, options, all) => {
            const el = h(
                'select',
                { class: 'field slim' },
                h('option', { value: '' }, all),
                options.map((o) => h('option', { value: o.v }, o.t))
            );
            el.value = st[key];
            el.addEventListener('change', () => {
                st[key] = el.value;
                load(true);
            });
            return el;
        };
        const q = h('input', { class: 'field slim grow', placeholder: 'Search words, shop, event…', value: st.q });
        q.addEventListener('input', () => {
            clearTimeout(q.t);
            q.t = setTimeout(() => {
                st.q = q.value.trim();
                load(true);
            }, 250);
        });
        const seg = (key, opts) => {
            const el = h(
                'div',
                { class: 'seg' },
                opts.map(([v, t]) =>
                    h(
                        'button',
                        {
                            class: st[key] === v ? 'on' : '',
                            onclick: () => {
                                st[key] = v;
                                [...el.children].forEach((b, i) => b.classList.toggle('on', opts[i][0] === v));
                                load(true);
                            },
                        },
                        t
                    )
                )
            );
            return el;
        };
        const monthSel = select(
                'month',
                months
                    .slice()
                    .reverse()
                    .map((m) => ({ v: m, t: monthName(m) })),
                'All time'
            ),
            catSel = select(
                'category',
                categories.map((c) => ({ v: c, t: c.charAt(0).toUpperCase() + c.slice(1) })),
                'Any category'
            );
        const row = (t) =>
            h(
                'button',
                { class: 'xrow', onclick: guard(() => openPayment(t.id)) },
                catBadge(t.category, 38),
                h(
                    'span',
                    { class: 'grow' },
                    h('div', { class: 'xnote' }, t.note || '-'),
                    h('div', { class: 'faint small' }, [t.day, t.category, t.event].filter(Boolean).join(' · '))
                ),
                t.currency !== cur
                    ? h(
                          'span',
                          { class: 'faint small' },
                          new Intl.NumberFormat(undefined, { style: 'currency', currency: t.currency }).format(
                              t.original
                          )
                      )
                    : null,
                h(
                    'span',
                    { class: 'num strong ' + (t.kind === 'income' ? 'good' : '') },
                    (t.kind === 'income' ? '+' : '−') + money(t.amount, 2)
                )
            );
        async function load(reset) {
            if (reset) {
                offset = 0;
                rows.replaceChildren();
            }
            const { q: words, ...rest } = st;
            const r = await tool('explore_payments', {
                ...Object.fromEntries(Object.entries(rest).filter(([, v]) => v)),
                ...(words ? { query: words } : {}),
                limit: 40,
                offset,
            });
            rows.append(...r.rows.map(row));
            offset += r.rows.length;
            summary.replaceChildren(
                ...[
                    h('span', { class: 'strong' }, `${r.count.toLocaleString()} payment${r.count === 1 ? '' : 's'}`),
                    r.spent ? h('span', { class: 'chip bad' }, 'spent ' + money(r.spent, 2)) : null,
                    r.income ? h('span', { class: 'chip good-chip' }, 'in ' + money(r.income, 2)) : null,
                ].filter(Boolean)
            );
            chips.replaceChildren(
                ...[
                    ['month', st.month ? monthName(st.month) : ''],
                    ['category', st.category],
                    ['q', st.q ? `“${st.q}”` : ''],
                ]
                    .filter(([, v]) => v)
                    .map(([k, v]) =>
                        h(
                            'button',
                            {
                                class: 'chip btnlike',
                                onclick: () => {
                                    st[k] = '';
                                    if (k === 'q') q.value = '';
                                    monthSel.value = st.month;
                                    catSel.value = st.category;
                                    load(true);
                                },
                            },
                            v + ' ×'
                        )
                    )
            );
            more.style.display = r.more ? '' : 'none';
            if (!r.rows.length && reset) rows.append(h('div', { class: 'empty' }, 'No payments match.'));
        }
        more.addEventListener(
            'click',
            guard(() => load(false))
        );
        load(true);
        return h(
            'div',
            { class: 'stack' },
            h(
                'div',
                { class: 'card filters' },
                h('div', { class: 'row', style: { flexWrap: 'wrap' } }, q, monthSel, catSel),
                h(
                    'div',
                    { class: 'row between', style: { flexWrap: 'wrap', marginTop: '12px' } },
                    seg('kind', [
                        ['', 'All'],
                        ['expense', 'Spent'],
                        ['income', 'Money in'],
                    ]),
                    seg('sort', [
                        ['date', 'Newest'],
                        ['amount', 'Largest'],
                    ])
                )
            ),
            h('div', { class: 'row between' }, summary, chips),
            h('div', { class: 'card' }, rows, h('div', { class: 'row', style: { justifyContent: 'center' } }, more))
        );
    }

    // ------------------------------------------------------------------ pages
    const pages = {};

    pages.home = async () => {
        const d = await api('/api/home');
        cur = d.currency;
        const b = d.briefing,
            hour = new Date().getHours(),
            month = startMonth(d.trend),
            has = d.trend.length > 0;
        const hello = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
        const [dueSoon, det, checks, nw, yo, inv] = await Promise.all([
            tool('bills_due', { days: 21 }),
            tool('money_detective'),
            tool('files_to_check'),
            tool('wealth_summary'),
            tool('yearly_overview'),
            tool('investments_overview'),
        ]);
        const [daily, byMain, sum] = has
            ? await Promise.all([
                  tool('daily_spending', { month }),
                  tool('spending_by_main', { month }),
                  tool('spending_summary', { month }),
              ])
            : [[], [], { income: 0 }];
        const monthly = (byMain.find((m) => m.main === 'others') || { net: 0 }).net,
            oneTime = byMain.filter((m) => m.main !== 'others').reduce((x, m) => x + m.net, 0),
            spent = monthly + oneTime;
        const before = daily.reduce((x, r) => x + r.before, 0),
            delta = before > 0 ? ((monthly - before) / before) * 100 : null;
        const ask = h('input', { class: 'field ask', placeholder: 'Ask anything about your money…' });
        ask.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && ask.value.trim()) {
                askOrbit(ask.value.trim());
                ask.value = '';
            }
        });
        const big = h('div', { class: 'big num' });
        countUp(big, spent, (v) => money(v));
        const hero = h(
            'div',
            { class: 'card hero' },
            h(
                'div',
                { class: 'hero-top' },
                h(
                    'div',
                    {},
                    h('div', { class: 'eyebrow' }, 'Spent · ' + monthName(month)),
                    big,
                    delta == null || Math.abs(delta) < 10
                        ? null
                        : h(
                              'span',
                              { class: 'delta' },
                              `${delta >= 0 ? '↑' : '↓'} ${Math.abs(delta).toFixed(0)}% monthly vs before`
                          )
                ),
                h('div', { class: 'hero-spark' }, sparkline(d.trend.slice(-8).map((t) => t.spent)))
            ),
            h(
                'div',
                { class: 'meta' },
                h('div', {}, h('div', { class: 'k' }, 'Monthly'), h('div', { class: 'v num' }, money(monthly))),
                h('div', {}, h('div', { class: 'k' }, 'One-time'), h('div', { class: 'v num' }, signed(oneTime, 0))),
                h('div', {}, h('div', { class: 'k' }, 'Money in'), h('div', { class: 'v num' }, money(sum.income)))
            )
        );
        const year = yo.years[yo.years.length - 1];
        const stats = h(
            'div',
            { class: 'grid g4' },
            stat(
                'Net worth',
                nw.net_worth == null ? '–' : money(nw.net_worth),
                nw.net_worth == null ? 'Comes from your statements' : `Cash ${money(nw.accounts || 0)}`,
                '#/networth'
            ),
            stat(
                year ? `Kept in ${year.year}` : 'Kept',
                year && year.savings_rate != null ? year.savings_rate + '%' : '–',
                year ? `${signed(year.saved, 0)} saved` : '',
                '#/savings',
                year && year.saved < 0 ? 'bad' : 'good'
            ),
            stat(
                'Investments',
                money(inv.value),
                inv.gain == null ? `${money(inv.contributed_total)} paid in` : `${signed(inv.gain, 0)} gain / loss`,
                '#/investments',
                inv.gain == null ? '' : inv.gain >= 0 ? 'good' : 'bad'
            ),
            stat(
                'Due in 3 weeks',
                money(dueSoon.total),
                `${dueSoon.items.length} payment${dueSoon.items.length === 1 ? '' : 's'}`,
                '#/plan'
            )
        );
        const attention = [
            ...dueSoon.items
                .filter((x) => x.kind === 'invoice')
                .slice(0, 2)
                .map((x) => ({
                    k: 'bill',
                    t: `${x.what} · ${money(x.amount, 2)} · ${x.in_days <= 0 ? 'now' : `in ${x.in_days} days`}`,
                })),
            ...(checks.length
                ? [{ k: 'check', t: `${checks.length} file${checks.length === 1 ? '' : 's'} need a look` }]
                : []),
            ...det.items.slice(0, 3).map((x) => ({ k: x.kind, t: x.text })),
        ].slice(0, 4);
        const attentionCard = attention.length
            ? section(
                  'Needs a look',
                  h(
                      'div',
                      { class: 'list' },
                      attention.map((x) =>
                          h(
                              'div',
                              { class: 'item' },
                              h('span', { class: 'chip' }, x.k),
                              h('div', { class: 'grow', style: { fontSize: '14.5px' } }, x.t)
                          )
                      )
                  )
              )
            : null;
        const tasks = b.tasks_due.slice(0, 4);
        const dates =
            d.upcoming && d.upcoming.length
                ? d.upcoming.slice(0, 3).map((u) => ({
                      n: u.merchant,
                      s: u.in_days <= 0 ? 'now' : `in ${u.in_days} days`,
                      a: money(u.amount),
                  }))
                : b.upcoming_dates.slice(0, 3).map((u) => ({
                      n: `${u.name} · ${u.label}`,
                      s: u.in_days === 0 ? 'today' : `in ${u.in_days} days`,
                      a: u.turning ? `turning ${u.turning}` : '',
                  }));
        const today = section(
            'Today',
            tasks.length || dates.length
                ? h(
                      'div',
                      { class: 'list' },
                      ...tasks.map((t) =>
                          h(
                              'div',
                              { class: 'item' },
                              h(
                                  'button',
                                  {
                                      class: 'check',
                                      'aria-label': 'Mark done',
                                      onclick: guard(async (e) => {
                                          await tool('complete_task', { id: t.id });
                                          e.currentTarget.classList.add('done');
                                          setTimeout(render, 350);
                                      }),
                                  },
                                  h('span', {
                                      html: '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
                                      style: { display: 'contents' },
                                  })
                              ),
                              h(
                                  'div',
                                  { class: 'grow' },
                                  h('div', { style: { fontWeight: 600 } }, t.title),
                                  h('div', { class: 'faint small' }, t.due || 'no date')
                              )
                          )
                      ),
                      ...dates.map((u) =>
                          h(
                              'div',
                              { class: 'item' },
                              h('div', { class: 'avatar', style: { background: colour(u.n) } }, initials(u.n)),
                              h(
                                  'div',
                                  { class: 'grow' },
                                  h('div', { style: { fontWeight: 600 } }, u.n),
                                  h('div', { class: 'faint small' }, u.s)
                              ),
                              h('span', { class: 'num' }, u.a)
                          )
                      )
                  )
                : h('div', { class: 'empty' }, 'Nothing today.')
        );
        const go = (label, sub, ic, color, act) =>
            h(
                'button',
                { class: 'short', onclick: act },
                h('span', {
                    class: 'cat-badge',
                    style: `--c:${color};width:44px;height:44px`,
                    html: `<svg viewBox="0 0 24 24"><path d="${ICONS[ic] || CATS[ic][1]}"/></svg>`,
                }),
                h('span', { class: 'short-t' }, label),
                h('span', { class: 'faint small' }, sub)
            );
        const shortcuts = h(
            'div',
            { class: 'shorts' },
            go('Income', 'Salary, bonus, other', 'income', '#10b981', () => {
                location.hash = '#/income';
            }),
            go('Expenses', 'Monthly, recurring, one-offs', 'expenses', '#f43f5e', () => {
                location.hash = '#/expenses';
            }),
            go('Savings', 'Saved and savings rate', 'savings', '#14b8a6', () => {
                location.hash = '#/savings';
            }),
            go('Investments', 'Paid in, value, gain', 'investments', '#8b5cf6', () => {
                location.hash = '#/investments';
            }),
            go('Net worth', 'Cash, investments, debts', 'networth', '#0ea5e9', () => {
                location.hash = '#/networth';
            }),
            go('Plan', 'Goals, budgets, tax', 'plan', '#f59e0b', () => {
                location.hash = '#/plan';
            })
        );
        const welcome = h(
            'div',
            { class: 'card welcome-card' },
            h('div', { class: 'orb big' }),
            h('h2', {}, 'Welcome to Orbit'),
            h('p', { class: 'muted' }, 'Your money, private on this Mac. Add your statements to begin.'),
            h('a', { class: 'btn primary', href: '#/expenses' }, 'Add my files')
        );
        return h(
            'div',
            { class: 'stack' },
            head(
                `${hello}.`,
                new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })
            ),
            ask,
            ...(has
                ? [
                      hero,
                      stats,
                      shortcuts,
                      h(
                          'div',
                          { class: 'grid g2' },
                          section('Money in and out', areaChart(d.trend)),
                          daily.length
                              ? section(
                                    'Where it went',
                                    spendDonut(daily),
                                    h('a', { class: 'more', href: '#/expenses' }, 'All spending →')
                                )
                              : null
                      ),
                  ]
                : [welcome]),
            h('div', { class: 'grid g2' }, ...[attentionCard, today].filter(Boolean))
        );
    };

    // ------------------------------------------------------------------ the chat: one conversation, in a corner panel and on its own page
    const IDEAS = {
        home: ['How much did I spend last month?', 'What is my savings rate this year?', "What's my net worth?"],
        income: ['How much did I earn this year?', 'Did I get a bonus this year?', 'What was my salary last month?'],
        expenses: [
            'How much did I spend last month?',
            'What are my regular payments?',
            'What was my biggest payment this year?',
        ],
        savings: [
            "What's my savings rate this year?",
            'Which month did I save the most?',
            'Am I saving more than last year?',
        ],
        investments: [
            'How much did I invest this year?',
            'What is my investment gain or loss?',
            'What interest did I earn?',
        ],
        networth: ["What's my net worth?", 'How much cash do I have?', 'What do I owe?'],
        plan: ['Am I on track for my goals?', 'What bills are coming up?', 'Show my budgets'],
        documents: [
            'Which invoices are still unpaid?',
            'What does my insurance cost per year?',
            'Find my latest tax letter',
        ],
        tasks: ["What's on today?", 'What is overdue?'],
        notes: ['What did I write about my trip?'],
        people: ['Whose birthday is next?'],
        settings: ['What can you do?'],
    };
    /** The conversation itself: bubbles with an avatar, a typing indicator, suggested questions and a message box. Both copies talk to the same server-side chat. */
    function buildChat(compact) {
        const msgs = h('div', { class: 'msgs' });
        const input = h('textarea', {
            rows: 1,
            placeholder: 'Ask anything about your money…',
            'aria-label': 'Message',
        });
        const sendBtn = h(
            'button',
            { class: 'send', 'aria-label': 'Send', type: 'button' },
            h('span', {
                html: '<svg viewBox="0 0 24 24"><path d="M12 19V5M5 12l7-7 7 7"/></svg>',
                style: { display: 'contents' },
            })
        );
        let busy = false;
        const scroll = () => {
            msgs.scrollTop = msgs.scrollHeight;
        };
        const avatar = () => h('span', { class: 'orb tiny', 'aria-hidden': 'true' });
        const say = (role, text, tags) => {
            const bubble = h(
                'div',
                { class: 'bubble ' + role },
                text,
                tags && tags.length
                    ? h(
                          'div',
                          { class: 'tags' },
                          tags.map((t) => h('span', { class: 'chip' }, t))
                      )
                    : null
            );
            const row = h('div', { class: 'msg ' + role }, role === 'bot' ? avatar() : null, bubble);
            msgs.append(row);
            scroll();
            return row;
        };
        const welcome = () =>
            h(
                'div',
                { class: 'welcome' },
                h('div', { class: 'orb' }),
                h('h2', {}, 'Hi, I’m Orbit'),
                h('div', { class: 'muted' }, 'Ask about your money, files, tasks or notes. Private, on this Mac.'),
                h(
                    'div',
                    { class: 'suggest' },
                    (IDEAS[document.body.dataset.page] || IDEAS.home).map((q) =>
                        h('button', { type: 'button', onclick: () => send(q) }, q)
                    )
                )
            );
        async function load() {
            const { history } = await api('/api/history');
            msgs.replaceChildren();
            if (!history.length) msgs.append(welcome());
            else history.forEach((m) => say(m.role === 'user' ? 'user' : 'bot', m.content));
        }
        async function send(text) {
            text = (text || input.value).trim();
            if (!text || busy) return;
            busy = true;
            sendBtn.disabled = true;
            input.value = '';
            input.style.height = '';
            msgs.querySelector('.welcome')?.remove();
            say('user', text);
            const note = h('div', { class: 'faint small' }),
                typing = h(
                    'div',
                    { class: 'msg bot' },
                    avatar(),
                    h('div', { class: 'bubble bot' }, h('div', { class: 'typing' }, h('i'), h('i'), h('i')), note)
                );
            msgs.append(typing);
            scroll();
            const slow = setTimeout(() => {
                note.textContent = 'Checking your numbers…';
                scroll();
            }, 3500);
            try {
                const r = await api('/api/chat', { text });
                typing.remove();
                say(
                    'bot',
                    r.reply || '(no answer)',
                    [...(r.tools || [])]
                        .filter((t) => t !== 'checked')
                        .slice(0, 3)
                        .concat(r.tools && r.tools.includes('checked') ? ['✓ checked'] : [])
                );
            } catch (e) {
                typing.remove();
                say('bot', e.message);
            }
            clearTimeout(slow);
            busy = false;
            sendBtn.disabled = false;
            input.focus();
        }
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
                e.preventDefault();
                send();
            }
        });
        input.addEventListener('input', () => {
            input.style.height = 'auto';
            input.style.height = Math.min(input.scrollHeight, 130) + 'px';
        });
        sendBtn.addEventListener('click', () => send());
        const root = h(
            'div',
            { class: 'chatbox' + (compact ? ' compact' : '') },
            msgs,
            h('div', { class: 'composer' }, input, sendBtn)
        );
        return { root, send, load, focus: () => input.focus() };
    }
    const corner = { chat: null, open: false };
    async function resetChat() {
        await api('/api/chat/reset', {});
        if (corner.chat) await corner.chat.load();
        if (route() === 'chat') render();
    }
    /** The round button in the corner of every page, and the panel it opens. */
    function mountCornerChat() {
        corner.chat = buildChat(true);
        const close = () => setCorner(false);
        const panel = h(
            'section',
            { class: 'chat-panel', id: 'chat-panel', hidden: true, role: 'dialog', 'aria-label': 'Ask Orbit' },
            h(
                'header',
                { class: 'chat-head' },
                h('span', { class: 'orb' }),
                h(
                    'div',
                    { class: 'grow' },
                    h('b', {}, 'Orbit'),
                    h('div', { class: 'faint small' }, 'Private · on this Mac')
                ),
                h('button', { class: 'btn ghost small', title: 'Start a new chat', onclick: guard(resetChat) }, 'New'),
                h(
                    'button',
                    {
                        class: 'btn ghost small',
                        title: 'Open on its own page',
                        onclick: () => {
                            close();
                            location.hash = '#/chat';
                        },
                    },
                    'Expand'
                ),
                h('button', { class: 'btn ghost small', 'aria-label': 'Close', onclick: close }, '✕')
            ),
            corner.chat.root
        );
        const fab = h(
            'button',
            {
                class: 'fab',
                id: 'chat-fab',
                type: 'button',
                'aria-label': 'Ask Orbit',
                title: 'Ask Orbit  (Ctrl/⌘ J)',
                onclick: () => setCorner(!corner.open),
            },
            icon('chat'),
            h('span', {}, 'Ask Orbit')
        );
        document.body.append(panel, fab);
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && corner.open && !$('.overlay')) setCorner(false);
            else if ((e.key === 'j' || e.key === 'J') && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                setCorner(!corner.open);
            }
        });
    }
    async function setCorner(on, text) {
        const panel = $('#chat-panel');
        if (!panel) return;
        if (on && route() === 'chat') {
            if (text) sessionStorage.setItem('orbit.ask', text);
            return;
        } // the full page is already a chat
        corner.open = on;
        panel.hidden = !on;
        document.body.classList.toggle('chat-open', on);
        if (on) {
            await guard(corner.chat.load)();
            corner.chat.focus();
            if (text) corner.chat.send(text);
        }
    }
    /** Open the chat (from anywhere) and ask this. */
    function askOrbit(text) {
        if (route() === 'chat') {
            sessionStorage.setItem('orbit.ask', text);
            render();
        } else setCorner(true, text);
    }

    pages.chat = async () => {
        const chat = buildChat(false);
        await chat.load();
        const pending = sessionStorage.getItem('orbit.ask');
        sessionStorage.removeItem('orbit.ask');
        if (pending) setTimeout(() => chat.send(pending), 50);
        return h(
            'div',
            {},
            head('Ask Orbit', null, h('button', { class: 'btn ghost', onclick: guard(resetChat) }, 'New chat')),
            h('div', { class: 'chat' }, chat.root)
        );
    };

    async function moneyPage(title, allowed, startTab) {
        const [trend0, settings] = await Promise.all([tool('monthly_trend', { months: 12 }), api('/api/settings')]);
        cur = settings.currency;
        let month = location.hash.split('?m=')[1] || startMonth(trend0);
        let jump = null;
        try {
            jump = JSON.parse(sessionStorage.getItem('orbit.explore') || 'null');
            sessionStorage.removeItem('orbit.explore');
        } catch (_) {
            /* ignore */
        }
        let explorer = null;
        let tab = jump ? 'payments' : startTab || allowed[0];
        const openCats = new Set();
        const openEvents = new Set();
        const wrap = h('div', { class: 'stack' });
        const importBtn = h('button', { class: 'btn primary', onclick: guard(startImport) }, 'Read my files');
        const status = h('div', { class: 'card', style: { display: 'none' } });
        async function startImport() {
            await api('/api/import', {});
            poll();
        }
        async function poll() {
            const s = await api('/api/import');
            status.style.display = s.running || s.result || s.error ? '' : 'none';
            if (s.running) {
                importBtn.disabled = true;
                importBtn.textContent = 'Reading...';
                status.replaceChildren(
                    h(
                        'div',
                        { class: 'row' },
                        h('span', { class: 'chip' }, 'In progress'),
                        h('div', { class: 'grow muted' }, s.progress || 'Starting...')
                    ),
                    h('div', { class: 'progress busy' })
                );
                setTimeout(poll, 1500);
                return;
            }
            importBtn.disabled = false;
            importBtn.textContent = 'Read my files';
            if (s.error) status.replaceChildren(h('div', { class: 'bad', style: { fontWeight: 600 } }, s.error));
            else if (s.result) {
                const r = s.result;
                status.replaceChildren(
                    h(
                        'div',
                        { style: { fontWeight: 650 } },
                        `Added ${r.new_transactions} payments from ${r.files} file${r.files === 1 ? '' : 's'}.`
                    ),
                    ...r.problems.map((p) => h('div', { class: 'bad' }, p)),
                    r.files_with_no_transactions.length
                        ? h('div', { class: 'muted' }, 'Could not read: ' + r.files_with_no_transactions.join(', '))
                        : null
                );
                if (r.files) draw(true);
            }
        }
        async function draw(refreshTrend) {
            const trend = refreshTrend ? await tool('monthly_trend', { months: 12 }) : trend0;
            const [sum, recurring, slips, docs, docTotals, txs, evs, byMain, daily, checks, ver, cc, pf] =
                await Promise.all([
                    tool('spending_summary', { month }),
                    tool('recurring_payments'),
                    tool('list_payslips', { limit: 12 }),
                    tool('finance_documents', { limit: 200 }),
                    tool('finance_document_totals', { by: 'kind' }),
                    tool('list_transactions', { since: month + '-01', until: month + '-31', limit: 400 }),
                    tool('list_events'),
                    tool('spending_by_main', { month }),
                    tool('daily_spending', { month }),
                    tool('files_to_check'),
                    tool('verification_report'),
                    tool('currencies'),
                    tool('month_proof', { month }),
                ]);
            const curChips =
                cc.currencies.length > 1 || cc.currencies.some((c) => c.currency !== cc.main)
                    ? h(
                          'div',
                          { class: 'seg' },
                          [...cc.currencies, { currency: 'ALL', payments: 0, label: 'In euros' }].map((c) =>
                              h(
                                  'button',
                                  {
                                      class: c.currency === cc.viewing ? 'on' : '',
                                      title:
                                          c.currency === 'ALL' ? 'Show everything in euros' : `${c.payments} payments`,
                                      onclick: guard(async () => {
                                          await api('/api/settings', { view_currency: c.currency });
                                          location.reload();
                                      }),
                                  },
                                  c.label || c.currency
                              )
                          )
                      )
                    : null;
            const nav = h(
                'div',
                { class: 'monthnav' },
                h('button', { 'aria-label': 'Previous month', onclick: () => step(-1) }, '‹'),
                h('span', {}, monthName(month)),
                h('button', { 'aria-label': 'Next month', onclick: () => step(1) }, '›')
            );
            function step(n) {
                const d = new Date(month + '-15');
                d.setMonth(d.getMonth() + n);
                month = d.toISOString().slice(0, 7);
                openCats.clear();
                draw(false);
            }
            const dayTotal = (byMain.find((m) => m.main === 'others') || { net: 0 }).net;
            const outingTotal = byMain.filter((m) => m.main !== 'others').reduce((x, m) => x + m.net, 0);
            const proofChip = pf.proven
                ? null
                : h(
                      'button',
                      {
                          class: 'proof bad',
                          title: pf.reasons.join('\n'),
                          onclick: () => alert('Not proven:\n\n' + pf.reasons.map((r) => '• ' + r).join('\n')),
                      },
                      '⚠ Check this month · tap to see why'
                  ); // nothing is shown for a month that is fine
            const hero = h(
                'div',
                { class: 'card hero' },
                h('div', { class: 'eyebrow' }, 'Spent · ' + monthName(month), ' ', proofChip),
                h('div', { class: 'big num' }, money(dayTotal + outingTotal)),
                h(
                    'div',
                    { class: 'meta' },
                    h('div', {}, h('div', { class: 'k' }, 'Monthly'), h('div', { class: 'v num' }, money(dayTotal))),
                    h(
                        'div',
                        {},
                        h('div', { class: 'k' }, 'One-time'),
                        h('div', { class: 'v num' }, signed(outingTotal, 0))
                    ),
                    h('div', {}, h('div', { class: 'k' }, 'Money in'), h('div', { class: 'v num' }, money(sum.income)))
                )
            );
            const trendCard = h(
                'div',
                { class: 'card' },
                h(
                    'div',
                    { class: 'card-head' },
                    h('h2', {}, 'Month by month'),
                    h('span', { class: 'faint', style: { fontSize: '13px' } }, 'tap a bar')
                ),
                trend.length
                    ? barChart(trend.slice(-8), month, (m) => {
                          month = m;
                          openCats.clear();
                          draw(false);
                      })
                    : h('div', { class: 'empty' }, 'No data yet.')
            );
            const recCard = h(
                'div',
                { class: 'card' },
                h(
                    'div',
                    { class: 'card-head' },
                    h('h2', {}, 'Repeating payments'),
                    recurring.length
                        ? h('span', { class: 'chip' }, `≈ ${money(recurring.reduce((s, r) => s + r.per_month, 0))}/mo`)
                        : null
                ),
                recurring.length
                    ? h(
                          'div',
                          { class: 'list' },
                          recurring.slice(0, 8).map((r) =>
                              h(
                                  'div',
                                  { class: 'item' },
                                  h('span', {
                                      class: 'sw',
                                      style: {
                                          width: '10px',
                                          height: '10px',
                                          borderRadius: '4px',
                                          background: colour(r.merchant),
                                          flex: 'none',
                                      },
                                  }),
                                  h(
                                      'div',
                                      { class: 'grow', style: { textTransform: 'capitalize', fontWeight: 600 } },
                                      r.merchant,
                                      h(
                                          'div',
                                          {
                                              class: 'faint',
                                              style: { fontSize: '12px', textTransform: 'none', fontWeight: 400 },
                                          },
                                          `${r.times} payments · last ${r.last}`
                                      )
                                  ),
                                  h('div', { class: 'num', style: { fontWeight: 650 } }, money(r.typical_amount, 2))
                              )
                          )
                      )
                    : h('div', { class: 'empty' }, 'None found yet.')
            );
            const KIND = {
                invoice: '#6366f1',
                receipt: '#10b981',
                payslip: '#ec4899',
                tax: '#f59e0b',
                insurance: '#06b6d4',
                contract: '#8b5cf6',
                bank_statement: '#a3a3a3',
                other: '#a3a3a3',
            };
            const other = docs.filter((d) => !['bank_statement', 'payslip'].includes(d.kind));
            const docCard = docs.length
                ? h(
                      'div',
                      { class: 'card' },
                      h(
                          'div',
                          { class: 'card-head' },
                          h('h2', {}, 'Other files'),
                          h(
                              'div',
                              { class: 'row' },
                              docTotals.map((t) => h('span', { class: 'chip' }, `${t.grp} ${money(t.total)}`))
                          )
                      ),
                      other.length
                          ? h(
                                'table',
                                { class: 'table' },
                                h(
                                    'thead',
                                    {},
                                    h(
                                        'tr',
                                        {},
                                        ['', 'From', 'Date', 'Due', 'Total'].map((x, i) =>
                                            h('th', { class: i === 4 ? 'r' : '' }, x)
                                        )
                                    )
                                ),
                                h(
                                    'tbody',
                                    {},
                                    other.slice(0, 30).map((d) =>
                                        h(
                                            'tr',
                                            {},
                                            h(
                                                'td',
                                                {},
                                                h(
                                                    'span',
                                                    {
                                                        class: 'chip',
                                                        style: {
                                                            background: 'transparent',
                                                            border: '1px solid var(--line-strong)',
                                                            color: KIND[d.kind] || 'var(--muted)',
                                                        },
                                                    },
                                                    h('span', {
                                                        class: 'sw',
                                                        style: { background: KIND[d.kind] || '#999' },
                                                    }),
                                                    d.kind
                                                )
                                            ),
                                            h(
                                                'td',
                                                {},
                                                h('div', { style: { fontWeight: 600 } }, d.party || d.title || d.name),
                                                d.summary
                                                    ? h(
                                                          'div',
                                                          { class: 'faint', style: { fontSize: '12px' } },
                                                          d.summary
                                                      )
                                                    : null
                                            ),
                                            h('td', { class: 'num' }, d.date || '-'),
                                            h('td', { class: 'num' }, d.due_date || '-'),
                                            h(
                                                'td',
                                                { class: 'r num', style: { fontWeight: 650 } },
                                                d.total != null ? money(d.total, 2) : '-'
                                            )
                                        )
                                    )
                                )
                            )
                          : h('div', { class: 'empty' }, 'Nothing else yet.')
                  )
                : null;
            // ---- day to day: category tiles; tap one to see its payments
            const payRow = (t) =>
                h(
                    'div',
                    { class: 'pay' },
                    h('span', { class: 'num faint', style: { width: '48px' } }, t.day.slice(5)),
                    h(
                        'span',
                        {
                            class: 'grow',
                            style: { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
                        },
                        t.note || '-'
                    ),
                    t.event ? h('span', { class: 'chip' }, t.event) : null,
                    t.currency !== cur
                        ? h(
                              'span',
                              { class: 'faint', style: { fontSize: '12.5px' } },
                              new Intl.NumberFormat(undefined, { style: 'currency', currency: t.currency }).format(
                                  t.original
                              )
                          )
                        : null,
                    h(
                        'span',
                        { class: 'num ' + (t.kind === 'income' ? 'good' : ''), style: { fontWeight: 600 } },
                        (t.kind === 'income' ? '+' : '−') + money(t.amount, 2)
                    )
                );
            const tiles = dailyTiles(
                daily,
                (c) => openCats.has(c),
                (c) => {
                    openCats.has(c) ? openCats.delete(c) : openCats.add(c);
                    draw(false);
                }
            );
            const opened = daily
                .filter((d) => openCats.has(d.category))
                .map((d) =>
                    h(
                        'div',
                        { class: 'card' },
                        h(
                            'div',
                            { class: 'card-head' },
                            h('h2', { style: { textTransform: 'capitalize' } }, d.category),
                            h('span', { class: 'chip' }, money(d.amount))
                        ),
                        h(
                            'div',
                            { class: 'list' },
                            txs
                                .filter(
                                    (t) =>
                                        !t.event &&
                                        t.kind === 'expense' &&
                                        (t.category === 'other' ? 'unsorted' : t.category) === d.category
                                )
                                .map(payRow)
                        )
                    )
                );
            const dailyPane = [
                daily.length
                    ? h(
                          'div',
                          { class: 'card' },
                          h('div', { class: 'card-head' }, h('h2', {}, 'Where it went')),
                          spendDonut(daily)
                      )
                    : null,
                daily.length ? tiles : h('div', { class: 'card empty' }, 'Nothing spent this month.'),
                ...opened,
                trendCard,
                recCard,
                h(
                    'div',
                    { class: 'row', style: { justifyContent: 'center' } },
                    h(
                        'button',
                        {
                            class: 'btn',
                            onclick: () => {
                                tab = 'payments';
                                draw(false);
                            },
                        },
                        'Browse every payment →'
                    )
                ),
            ];

            // ---- trips & events: found by the model from your statements; tap a card for its lines
            const evCard = (ev) => {
                const open = openEvents.has(ev.id);
                return h(
                    'div',
                    { class: 'card event' + (open ? ' open' : '') },
                    h(
                        'button',
                        {
                            class: 'evhead',
                            onclick: () => {
                                open ? openEvents.delete(ev.id) : openEvents.add(ev.id);
                                draw(false);
                            },
                        },
                        h(
                            'div',
                            { class: 'grow', style: { textAlign: 'left' } },
                            h(
                                'div',
                                { style: { fontSize: '17px', fontWeight: 700, letterSpacing: '-.01em' } },
                                ev.name
                            ),
                            h(
                                'div',
                                { class: 'faint', style: { fontSize: '13px' } },
                                ev.first ? (ev.first === ev.last ? ev.first : `${ev.first} to ${ev.last}`) : ''
                            )
                        ),
                        h(
                            'div',
                            {
                                class: 'num ' + (ev.total < 0 ? 'good' : ''),
                                style: { fontSize: '22px', fontWeight: 750 },
                            },
                            signed(ev.total)
                        ),
                        h('span', { class: 'chev' }, open ? '▾' : '▸')
                    ),
                    open
                        ? h(
                              'div',
                              { class: 'evbody' },
                              h(
                                  'div',
                                  { class: 'lines' },
                                  ev.lines.map((l) =>
                                      h(
                                          'div',
                                          { class: 'line' },
                                          h('span', { style: { textTransform: 'capitalize' } }, l.sub),
                                          h('span', { class: 'num ' + (l.amount < 0 ? 'good' : '') }, signed(l.amount))
                                      )
                                  )
                              )
                          )
                        : null
                );
            };
            const sections = MAINS.filter((m) => m !== 'others').map((m) => {
                const list = evs.filter((e) => e.main === m);
                if (!list.length) return null;
                const net = list.reduce((x, e) => x + e.total, 0);
                return h(
                    'div',
                    { class: 'stack', style: { gap: '12px' } },
                    h(
                        'div',
                        { class: 'row' },
                        h('span', {
                            class: 'sw',
                            style: { width: '12px', height: '12px', borderRadius: '4px', background: MAIN_COLOUR[m] },
                        }),
                        h('h2', {}, MAIN_LABEL[m]),
                        h('span', { class: 'chip' }, signed(net, 0))
                    ),
                    ...list.map(evCard)
                );
            });
            const eventsPane = evs.length
                ? [
                      ...sections,
                      h(
                          'div',
                          { class: 'muted', style: { textAlign: 'center', fontSize: '14px' } },
                          'Not right? Tell Orbit in ',
                          h('a', { href: '#/chat' }, 'chat'),
                          '.'
                      ),
                  ]
                : [
                      h(
                          'div',
                          { class: 'card welcome-card' },
                          h('h2', {}, 'No trips or events yet'),
                          h('p', { class: 'muted' }, 'Tickets, flights and hotels are grouped here for you.')
                      ),
                  ];

            // ---- income: how much came in, from where, and the payslip
            // ---- every verifier agent, in words
            const LEVEL = { ok: ['✓', 'good'], warn: ['!', ''], fail: ['✗', 'bad'] };
            const statusCard = ver.problems.length
                ? h(
                      'div',
                      { class: 'card' },
                      h(
                          'h2',
                          { style: { marginBottom: '8px' } },
                          `${ver.problems.length} thing${ver.problems.length === 1 ? '' : 's'} to look at`
                      ),
                      h(
                          'div',
                          { class: 'list' },
                          ver.problems
                              .slice(0, 8)
                              .map((p) =>
                                  h(
                                      'div',
                                      { class: 'item' },
                                      h(
                                          'span',
                                          { class: LEVEL[p.level][1], style: { fontWeight: 700, width: '18px' } },
                                          LEVEL[p.level][0]
                                      ),
                                      h(
                                          'div',
                                          { class: 'grow' },
                                          h('div', { style: { fontWeight: 600 } }, plain(p.message)),
                                          h('div', { class: 'faint', style: { fontSize: '12.5px' } }, p.subject)
                                      )
                                  )
                              )
                      )
                  )
                : ver.passed
                  ? h(
                        'div',
                        { class: 'card' },
                        h(
                            'div',
                            { class: 'row' },
                            h('span', { class: 'tick' }, '✓'),
                            h('div', { style: { fontWeight: 650, fontSize: '18px' } }, 'Everything adds up')
                        )
                    )
                  : null;
            const detailsFold = Object.keys(ver.summary).length
                ? h(
                      'details',
                      { class: 'card fold' },
                      h('summary', {}, h('span', { style: { fontWeight: 650, fontSize: '17px' } }, 'Details')),
                      h('div', { style: { height: '12px' } }),
                      h(
                          'div',
                          { class: 'lines' },
                          Object.entries(ver.summary).map(([agent, c]) =>
                              h(
                                  'div',
                                  { class: 'line' },
                                  h('span', { style: { textTransform: 'capitalize' } }, agent),
                                  h(
                                      'span',
                                      { class: 'num' },
                                      h('span', { class: 'good' }, `✓ ${c.ok}`),
                                      c.warn
                                          ? h(
                                                'span',
                                                { style: { color: 'var(--warn)', marginLeft: '12px' } },
                                                `! ${c.warn}`
                                            )
                                          : null,
                                      c.fail
                                          ? h('span', { class: 'bad', style: { marginLeft: '12px' } }, `✗ ${c.fail}`)
                                          : null
                                  )
                              )
                          )
                      )
                  )
                : null;
            // ---- honesty about files: what could not be proven correct is said out loud and is NOT in the totals
            const bad = checks.filter((c) => c.status === 'needs_check'),
                unproven = checks.filter((c) => c.status === 'unverified');
            const checkNote = bad.length
                ? h(
                      'div',
                      {
                          class: 'note-banner',
                          style: {
                              background: 'rgba(244,63,94,.1)',
                              borderColor: 'rgba(244,63,94,.3)',
                              flexDirection: 'column',
                              alignItems: 'flex-start',
                              gap: '6px',
                          },
                      },
                      h('b', {}, `${bad.length} file${bad.length === 1 ? '' : 's'} left out`),
                      ...bad
                          .slice(0, 4)
                          .map((c) =>
                              h(
                                  'div',
                                  { class: 'muted', style: { fontSize: '14px' } },
                                  `${c.file}: ${plain(c.issues) || 'could not be read'}`
                              )
                          )
                  )
                : unproven.length
                  ? h(
                        'div',
                        { class: 'note-banner' },
                        h(
                            'div',
                            { class: 'grow' },
                            h('b', {}, `${unproven.length} file${unproven.length === 1 ? '' : 's'} not double-checked`)
                        )
                    )
                  : null;
            const empty = !trend.length && !docs.length && !slips.length;
            const tabs = [
                ['daily', 'Monthly & recurring'],
                ['events', 'One-offs'],
                ['payments', 'All payments'],
                ['documents', 'Files' + (ver.problems.length ? ` · ${ver.problems.length}` : '')],
            ];
            const tabBar =
                allowed.length < 2
                    ? null
                    : h(
                          'div',
                          { class: 'seg' },
                          tabs
                              .filter(([id]) => allowed.includes(id))
                              .map(([id, label]) =>
                                  h(
                                      'button',
                                      {
                                          class: tab === id ? 'on' : '',
                                          onclick: () => {
                                              tab = id;
                                              draw(false);
                                          },
                                      },
                                      label
                                  )
                              )
                      );
            if (tab === 'payments' && !explorer)
                explorer = paymentsExplorer(
                    trend.map((t) => t.month),
                    [...new Set([...daily.map((d) => d.category), ...txs.map((t) => t.category)])].sort(),
                    jump || {}
                );
            const content = {
                daily: dailyPane,
                payments: [explorer],
                events: eventsPane,
                documents: [
                    statusCard,
                    docCard,
                    detailsFold,
                    h(
                        'div',
                        { class: 'muted', style: { textAlign: 'center' } },
                        h('a', { href: '#/files' }, 'Search all files')
                    ),
                ],
            }[tab];
            const first = h(
                'div',
                { class: 'card welcome-card' },
                h('div', { class: 'orb big' }),
                h('h2', {}, 'Add your money'),
                h('p', { class: 'muted' }, 'Put your PDFs in your finance folder, then press the button.'),
                h('div', {}, importBtn)
            );
            wrap.replaceChildren(
                ...[
                    head(title, null, empty ? null : curChips, empty ? null : nav, empty ? null : importBtn),
                    status,
                    empty ? null : checkNote,
                    empty ? first : title === 'Documents' ? null : hero,
                    empty ? null : tabBar,
                    ...(empty ? [] : content),
                ].filter(Boolean)
            );
        }
        await draw(false);
        poll();
        return wrap;
    }
    pages.expenses = () => moneyPage('Expenses', ['daily', 'events', 'payments']);
    pages.documents = () => moneyPage('Documents', ['documents']);

    pages.plan = async () => {
        const [yo, goals, fc, tl, look, det, bud, bills, ins] = await Promise.all([
            tool('yearly_overview'),
            tool('list_goals'),
            tool('forecast', { months: 6 }),
            tool('timeline'),
            tool('suggestions'),
            tool('money_detective'),
            tool('budget_progress'),
            tool('bills_due'),
            tool('insurances'),
        ]);
        cur = yo.currency || cur;
        const wanted = route();
        let tab = wanted === 'tax' ? 'tax' : 'overview',
            taxYear = '';
        const wrap = h('div', { class: 'stack' }),
            body = h('div', { class: 'stack' });
        const row = (...cells) => h('div', { class: 'item' }, ...cells);
        const col = (w, t, cls = '') =>
            h('div', { class: 'num ' + cls, style: { width: w + 'px', textAlign: 'right' } }, t);
        const lookItems = [
            ...look.items.map((x) => ({ k: x.topic, t: x.text })),
            ...det.items.map((x) => ({ k: x.kind, t: x.text })),
        ];
        const overview = () => [
            bills.items.length
                ? section(
                      'Coming up',
                      h(
                          'div',
                          { class: 'list' },
                          bills.items
                              .slice(0, 5)
                              .map((x) =>
                                  row(
                                      h(
                                          'div',
                                          { class: 'grow' },
                                          h('div', { style: { fontWeight: 650 } }, x.what),
                                          h(
                                              'div',
                                              { class: 'faint small' },
                                              x.in_days <= 0 ? 'now' : `in ${x.in_days} days · ${x.due}`
                                          )
                                      ),
                                      h('div', { class: 'num' }, money(x.amount, 2))
                                  )
                              )
                      )
                  )
                : null,
            ins.paid.length
                ? section(
                      'Insurance',
                      h(
                          'div',
                          { class: 'list' },
                          ins.paid
                              .slice()
                              .reverse()
                              .map((x) =>
                                  row(
                                      h(
                                          'div',
                                          { class: 'grow' },
                                          h(
                                              'div',
                                              { style: { fontWeight: 650 } },
                                              x.insurer.charAt(0).toUpperCase() + x.insurer.slice(1)
                                          ),
                                          h('div', { class: 'faint small' }, x.year)
                                      ),
                                      h('div', { class: 'num strong' }, money(x.paid))
                                  )
                              ),
                          ins.total_per_year.length
                              ? row(
                                    h('div', { class: 'grow faint' }, 'Total per year'),
                                    h(
                                        'div',
                                        { class: 'num faint' },
                                        ins.total_per_year
                                            .slice()
                                            .reverse()
                                            .map((t) => `${t.year}: ${money(t.paid)}`)
                                            .join('  ·  ')
                                    )
                                )
                              : null
                      )
                  )
                : null,
            lookItems.length
                ? section(
                      'Worth a look',
                      h(
                          'div',
                          { class: 'list' },
                          lookItems
                              .slice(0, 12)
                              .map((x) => row(h('span', { class: 'chip' }, x.k), h('div', { class: 'grow' }, x.t)))
                      )
                  )
                : null,
        ];
        const goalsTab = () => {
            const budCat = h('input', { class: 'field', placeholder: 'Category (groceries…)', style: { flex: 1 } }),
                budAmt = h('input', {
                    class: 'field',
                    type: 'number',
                    placeholder: 'Per month',
                    style: { width: '130px' },
                });
            const addBudget = guard(async () => {
                if (!budCat.value.trim() || !(+budAmt.value > 0)) return;
                await tool('set_budget', { category: budCat.value.trim(), monthly_amount: +budAmt.value });
                render();
            });
            const name = h('input', { class: 'field', placeholder: 'Save for…', style: { flex: 1 } }),
                target = h('input', {
                    class: 'field',
                    type: 'number',
                    placeholder: 'Amount',
                    style: { width: '130px' },
                }),
                by = h('input', { class: 'field', type: 'date', style: { width: '160px' } });
            const addGoal = guard(async () => {
                if (!name.value.trim() || !(+target.value > 0)) return;
                await tool('add_goal', { name: name.value.trim(), target: +target.value, by: by.value || undefined });
                render();
            });
            return [
                section(
                    'Goals',
                    h(
                        'div',
                        { class: 'row form' },
                        name,
                        target,
                        by,
                        h('button', { class: 'btn primary', onclick: addGoal }, 'Add')
                    ),
                    goals.goals.length
                        ? h(
                              'div',
                              { class: 'list' },
                              goals.goals.map((g) =>
                                  h(
                                      'div',
                                      { class: 'item block' },
                                      h(
                                          'div',
                                          { class: 'row' },
                                          h('div', { class: 'grow', style: { fontWeight: 650 } }, g.name),
                                          h('span', { class: 'num' }, money(g.target)),
                                          g.on_track === undefined
                                              ? null
                                              : h(
                                                    'span',
                                                    { class: 'chip ' + (g.on_track ? '' : 'bad') },
                                                    g.on_track ? 'on track' : 'behind'
                                                ),
                                          h(
                                              'button',
                                              {
                                                  class: 'btn ghost small',
                                                  onclick: guard(async () => {
                                                      await tool('delete_goal', { id: g.id });
                                                      render();
                                                  }),
                                              },
                                              'Remove'
                                          )
                                      ),
                                      g.percent == null
                                          ? null
                                          : h(
                                                'div',
                                                { class: 'progress' },
                                                h('i', { style: { width: Math.min(100, g.percent) + '%' } })
                                            ),
                                      h(
                                          'div',
                                          { class: 'faint small' },
                                          [
                                              g.percent == null
                                                  ? 'No balance yet'
                                                  : `${g.percent}% · ${money(g.have)} now`,
                                              g.by ? `by ${g.by}` : '',
                                              g.needed_per_month ? `${money(g.needed_per_month)}/month needed` : '',
                                          ]
                                              .filter(Boolean)
                                              .join(' · ')
                                      )
                                  )
                              )
                          )
                        : h('div', { class: 'empty' }, 'No goals yet.')
                ),
                section(
                    'Budgets',
                    h(
                        'div',
                        { class: 'row form' },
                        budCat,
                        budAmt,
                        h('button', { class: 'btn primary', onclick: addBudget }, 'Set')
                    ),
                    bud.budgets.length
                        ? h(
                              'div',
                              { class: 'list' },
                              bud.budgets.map((x) =>
                                  h(
                                      'div',
                                      { class: 'item block' },
                                      h(
                                          'div',
                                          { class: 'row' },
                                          h(
                                              'div',
                                              { class: 'grow', style: { fontWeight: 650 } },
                                              x.category.charAt(0).toUpperCase() + x.category.slice(1)
                                          ),
                                          h(
                                              'span',
                                              { class: 'num ' + (x.over ? 'bad' : '') },
                                              `${money(x.spent)} of ${money(x.budget)}`
                                          )
                                      ),
                                      h(
                                          'div',
                                          { class: 'progress' },
                                          h('i', {
                                              class: x.over ? 'over' : '',
                                              style: { width: Math.min(100, x.percent || 0) + '%' },
                                          })
                                      )
                                  )
                              )
                          )
                        : h('div', { class: 'empty' }, 'No budgets yet.')
                ),
            ];
        };
        const outlook = () => [
            section(
                'Next months',
                h(
                    'div',
                    { class: 'faint small', style: { marginBottom: '8px' } },
                    fc.months.length ? 'An estimate from your last six months' : ''
                ),
                fc.months.length
                    ? h(
                          'div',
                          { class: 'list' },
                          fc.months.map((m) =>
                              row(
                                  h('div', { class: 'grow' }, monthName(m.month)),
                                  h(
                                      'div',
                                      { class: 'num faint' },
                                      (m.income - m.spent >= 0 ? '+' : '') + signed(m.income - m.spent, 0)
                                  ),
                                  col(110, m.balance == null ? '' : money(m.balance), 'strong')
                              )
                          )
                      )
                    : h('div', { class: 'empty' }, fc.note)
            ),
            section(
                'Timeline',
                tl.items.length
                    ? h(
                          'div',
                          { class: 'list' },
                          tl.items
                              .slice(0, 20)
                              .map((x) =>
                                  row(
                                      h(
                                          'div',
                                          { class: 'faint', style: { width: '104px', whiteSpace: 'nowrap' } },
                                          x.date
                                      ),
                                      h('div', { class: 'grow' }, x.what)
                                  )
                              )
                      )
                    : h('div', { class: 'empty' }, 'Nothing yet.')
            ),
        ];
        async function taxTab() {
            const years = yo.years.map((y) => y.year).reverse();
            taxYear = taxYear || years[0] || String(new Date().getFullYear());
            const t = await tool('tax_summary', { year: taxYear });
            cur = t.currency || cur;
            const rows = [],
                a = t.annual_statement;
            if (a)
                rows.push(
                    ['Annual statement · gross', money(a.gross)],
                    ['Annual statement · tax withheld', money(a.tax_withheld)],
                    ['Annual statement · net', money(a.net)]
                );
            if (t.payslips.count)
                rows.push(
                    [`Payslips (${t.payslips.count}) · gross`, money(t.payslips.gross)],
                    ['Payslips · tax withheld', money(t.payslips.tax_withheld)],
                    ['Payslips · pension', money(t.payslips.pension)]
                );
            rows.push(
                ['Interest received', money(t.interest_received, 2)],
                ['Paid into investments', money(t.paid_into_investments)],
                ['Insurance paid', money(t.insurance_paid)]
            );
            t.balances_on_1_january.forEach((x) =>
                rows.push([`Balance on 1 January · …${x.account}`, money(x.balance)])
            );
            t.tax_letters.forEach((l) =>
                rows.push([`Tax letter ${l.date} · ${l.party || l.name}`, money(l.amount, 2)])
            );
            const picker = h(
                'div',
                { class: 'seg' },
                (years.length ? years : [taxYear]).map((y) =>
                    h(
                        'button',
                        {
                            class: y === taxYear ? 'on' : '',
                            onclick: () => {
                                taxYear = y;
                                show();
                            },
                        },
                        y
                    )
                )
            );
            return [
                h(
                    'div',
                    { class: 'row between' },
                    picker,
                    h('a', { class: 'btn primary', href: '/report/' + taxYear, target: '_blank' }, 'Print year report')
                ),
                section(
                    'Facts for your return',
                    h(
                        'div',
                        { class: 'list' },
                        rows.map(([k, v]) => row(h('div', { class: 'grow' }, k), h('div', { class: 'num strong' }, v)))
                    )
                ),
                h('div', { class: 'muted small center' }, t.note),
            ];
        }
        const tabs = [
            ['overview', 'Overview'],
            ['goals', 'Goals & budgets'],
            ['outlook', 'Outlook'],
            ['tax', 'Tax'],
        ];
        async function show() {
            const content =
                tab === 'overview'
                    ? overview()
                    : tab === 'goals'
                      ? goalsTab()
                      : tab === 'outlook'
                        ? outlook()
                        : await taxTab();
            body.replaceChildren(...content.filter(Boolean));
            wrap.replaceChildren(
                head(
                    'Plan',
                    null,
                    h(
                        'div',
                        { class: 'seg' },
                        tabs.map(([id, label]) =>
                            h(
                                'button',
                                {
                                    class: tab === id ? 'on' : '',
                                    onclick: () => {
                                        tab = id;
                                        show();
                                    },
                                },
                                label
                            )
                        )
                    )
                ),
                body
            );
        }
        await show();
        return wrap;
    };

    // ------------------------------------------------------------------ the five sections: income, expenses, savings, investments, net worth
    const PARTS = [
        ['salary', 'Salary', '#10b981'],
        ['bonus', 'Bonus', '#f59e0b'],
        ['other', 'Other', '#8b5cf6'],
    ];
    pages.income = async () => {
        const [ib, slips] = await Promise.all([tool('income_breakdown'), tool('list_payslips', { limit: 6 })]);
        cur = ib.currency || cur;
        if (!ib.months.length)
            return h(
                'div',
                { class: 'stack' },
                head('Income', 'Salary, bonus and other'),
                emptyCard('Money in appears here once your statements are read.')
            );
        const y = ib.latest_year,
            recent = ib.months.slice(-12);
        const num = (n, cls = '') =>
            h('div', { class: 'num ' + cls, style: { width: '96px', textAlign: 'right' } }, n ? money(n) : '–');
        return h(
            'div',
            { class: 'stack' },
            head('Income', 'Salary, bonus and other'),
            heroOf(`Money in · ${y.year}`, money(y.total), [
                ['Salary', money(y.salary)],
                ['Bonus', money(y.bonus)],
                ['Other', money(y.other)],
            ]),
            section('Month by month', stackedBars(recent, PARTS)),
            section(
                'Table',
                h(
                    'div',
                    { class: 'list' },
                    h(
                        'div',
                        { class: 'item' },
                        h('div', { class: 'grow faint' }, 'Month'),
                        ...['Salary', 'Bonus', 'Other', 'Total'].map((t) =>
                            h('div', { class: 'faint', style: { width: '96px', textAlign: 'right' } }, t)
                        )
                    ),
                    ...recent
                        .slice()
                        .reverse()
                        .map((m) =>
                            h(
                                'div',
                                { class: 'item' },
                                h('div', { class: 'grow', style: { fontWeight: 650 } }, monthName(m.month)),
                                num(m.salary),
                                num(m.bonus),
                                num(m.other),
                                num(m.total, 'strong')
                            )
                        )
                ),
                ib.years.length > 1
                    ? h(
                          'div',
                          { class: 'faint small', style: { marginTop: '12px' } },
                          ib.years
                              .slice()
                              .reverse()
                              .map((r) => `${r.year}: ${money(r.total)}`)
                              .join('  ·  ')
                      )
                    : null
            ),
            slips.length
                ? section(
                      'Payslips',
                      h(
                          'div',
                          { class: 'list' },
                          h(
                              'div',
                              { class: 'item' },
                              h('div', { class: 'grow faint' }, 'Month'),
                              ...['Gross', 'Tax', 'Net'].map((t) =>
                                  h('div', { class: 'faint', style: { width: '96px', textAlign: 'right' } }, t)
                              )
                          ),
                          ...slips.map((p) =>
                              h(
                                  'div',
                                  { class: 'item' },
                                  h(
                                      'div',
                                      { class: 'grow', style: { fontWeight: 650 } },
                                      p.period ? monthName(p.period) : p.name
                                  ),
                                  num(p.gross),
                                  num(p.tax),
                                  num(p.net, 'strong good')
                              )
                          )
                      )
                  )
                : null
        );
    };

    pages.savings = async () => {
        const sv = await tool('savings_overview');
        cur = sv.currency || cur;
        if (!sv.months.length)
            return h(
                'div',
                { class: 'stack' },
                head('Savings', 'Amount saved and savings rate'),
                emptyCard('Savings are worked out from your money in and spending.')
            );
        const l = sv.last12,
            recent = sv.months.slice(-12);
        return h(
            'div',
            { class: 'stack' },
            head('Savings', 'Amount saved and savings rate'),
            heroOf(`Kept · last ${l.months} month${l.months === 1 ? '' : 's'}`, rate(l.rate), [
                ['Saved', signed(l.saved, 0)],
                ['Money in', money(l.income)],
                ['Spent', money(l.spent)],
            ]),
            section(
                'Saved each month',
                signedBars(recent.map((m) => ({ month: m.month, value: m.saved, rate: m.rate }))),
                h(
                    'div',
                    { class: 'faint small', style: { marginTop: '12px' } },
                    'Green: money kept. Red: more went out than came in.'
                )
            ),
            h(
                'div',
                { class: 'grid g3' },
                stat(
                    'Best month',
                    sv.best ? monthName(sv.best.month) : '–',
                    sv.best ? `${sv.best.rate}% kept` : '',
                    null,
                    'good'
                ),
                stat(
                    'Hardest month',
                    sv.worst ? monthName(sv.worst.month) : '–',
                    sv.worst ? `${sv.worst.rate}% kept` : '',
                    null,
                    sv.worst && sv.worst.rate < 0 ? 'bad' : ''
                ),
                stat(
                    'Per year',
                    sv.latest_year ? rate(sv.latest_year.savings_rate) : '–',
                    sv.latest_year ? `${signed(sv.latest_year.saved, 0)} saved in ${sv.latest_year.year}` : '',
                    '#/plan'
                )
            ),
            section(
                'Year by year',
                h(
                    'div',
                    { class: 'list' },
                    h(
                        'div',
                        { class: 'item' },
                        h('div', { class: 'grow faint' }, 'Year'),
                        ...['Money in', 'Spent', 'Saved', 'Rate'].map((t) =>
                            h('div', { class: 'faint', style: { width: '96px', textAlign: 'right' } }, t)
                        )
                    ),
                    ...sv.years
                        .slice()
                        .reverse()
                        .map((y) =>
                            h(
                                'div',
                                { class: 'item' },
                                h(
                                    'div',
                                    { class: 'grow', style: { fontWeight: 650 } },
                                    y.year + (y.months < 12 ? ` · ${y.months} mo` : '')
                                ),
                                h(
                                    'div',
                                    { class: 'num', style: { width: '96px', textAlign: 'right' } },
                                    money(y.income)
                                ),
                                h(
                                    'div',
                                    { class: 'num', style: { width: '96px', textAlign: 'right' } },
                                    money(y.spent)
                                ),
                                h(
                                    'div',
                                    {
                                        class: 'num ' + (y.saved >= 0 ? 'good' : 'bad'),
                                        style: { width: '96px', textAlign: 'right' },
                                    },
                                    signed(y.saved, 0)
                                ),
                                h(
                                    'div',
                                    { class: 'num strong', style: { width: '96px', textAlign: 'right' } },
                                    rate(y.savings_rate)
                                )
                            )
                        )
                )
            )
        );
    };

    /** The form for something you type in (an investment, an asset or a debt). `kinds` limits what can be added on this page. */
    function holdingForm(kinds, withCost) {
        const kind = h(
            'select',
            { class: 'field slim' },
            kinds.map(([v, t]) => h('option', { value: v }, t))
        );
        const name = h('input', { class: 'field slim grow', placeholder: 'Name (ETF, house, loan…)' }),
            value = h('input', {
                class: 'field slim',
                type: 'number',
                placeholder: 'Value now',
                style: { minWidth: '110px' },
            });
        const units = h('input', {
                class: 'field slim',
                type: 'number',
                placeholder: 'or Units',
                style: { minWidth: '90px' },
            }),
            price = h('input', {
                class: 'field slim',
                type: 'number',
                placeholder: 'Price',
                style: { minWidth: '90px' },
            });
        const cost = withCost
            ? h('input', {
                  class: 'field slim',
                  type: 'number',
                  placeholder: 'Paid in (total)',
                  style: { minWidth: '130px' },
              })
            : null;
        const add = guard(async () => {
            const byUnits = +units.value > 0 && +price.value > 0;
            if (!name.value.trim() || !(+value.value > 0 || byUnits)) return;
            await tool('add_holding', {
                name: name.value.trim(),
                kind: kind.value,
                ...(byUnits ? { units: +units.value, price: +price.value } : { value: +value.value }),
                ...(cost && +cost.value > 0 ? { cost: +cost.value } : {}),
            });
            render();
        });
        return h(
            'div',
            { class: 'row form' },
            kinds.length > 1 ? kind : null,
            name,
            value,
            units,
            price,
            cost,
            h('button', { class: 'btn primary', onclick: add }, 'Add')
        );
    }
    const holdingActions = (x) => [
        h(
            'button',
            {
                class: 'btn ghost small',
                onclick: guard(async () => {
                    const v = prompt(
                        'New ' + (x.units ? 'price per unit' : 'value') + ' for ' + x.name,
                        x.units ? x.price : x.value
                    );
                    if (v == null || v === '' || isNaN(+v)) return;
                    await tool('update_holding', { id: x.id, ...(x.units ? { price: +v } : { value: +v }) });
                    render();
                }),
            },
            'Update'
        ),
        h(
            'button',
            {
                class: 'btn ghost small',
                onclick: guard(async () => {
                    await tool('delete_holding', { id: x.id });
                    render();
                }),
            },
            'Remove'
        ),
    ];

    pages.investments = async () => {
        const inv = await tool('investments_overview');
        cur = inv.currency || cur;
        const gainTone = inv.gain == null ? '' : inv.gain >= 0 ? 'good' : 'bad';
        const nothing = !inv.holdings.length && !inv.contributed_by_year.length;
        return h(
            'div',
            { class: 'stack' },
            head('Investments', 'Paid in, current value, gain or loss'),
            heroOf('Current value', money(inv.value), [
                ['Paid in (payments)', money(inv.contributed_total)],
                [
                    'Gain / loss',
                    inv.gain == null
                        ? '–'
                        : `${signed(inv.gain, 0)}${inv.gain_percent == null ? '' : ' · ' + (inv.gain_percent > 0 ? '+' : '') + inv.gain_percent + '%'}`,
                ],
            ]),
            h(
                'div',
                { class: 'grid g3' },
                stat(
                    'Contributions',
                    money(inv.contributed_total),
                    inv.contributed_by_year.length
                        ? `${inv.contributed_by_year.length} year${inv.contributed_by_year.length === 1 ? '' : 's'} of payments`
                        : 'None found in your payments'
                ),
                stat(
                    'Current value',
                    money(inv.value),
                    inv.holdings.length
                        ? `${inv.holdings.length} holding${inv.holdings.length === 1 ? '' : 's'} you added`
                        : 'Add your holdings below'
                ),
                stat(
                    'Gain / loss',
                    inv.gain == null ? '–' : signed(inv.gain, 0),
                    inv.gain == null
                        ? 'Add what you paid in for a holding'
                        : inv.complete
                          ? 'on all holdings'
                          : 'only on holdings with an amount paid in',
                    null,
                    gainTone
                )
            ),
            section(
                'Your holdings',
                h(
                    'div',
                    { class: 'faint small', style: { marginBottom: '10px' } },
                    'Type in what you hold and what you paid in. Update the price when it moves.'
                ),
                holdingForm([['investment', 'Investment']], true),
                inv.holdings.length
                    ? h(
                          'div',
                          { class: 'list' },
                          inv.holdings.map((x) =>
                              h(
                                  'div',
                                  { class: 'item' },
                                  h(
                                      'div',
                                      { class: 'grow' },
                                      h('div', { style: { fontWeight: 650 } }, x.name),
                                      h(
                                          'div',
                                          { class: 'faint small' },
                                          (x.units ? `${x.units} × ${money(x.price, 2)} · ` : '') +
                                              'as of ' +
                                              x.as_of +
                                              (x.cost == null
                                                  ? ' · amount paid in not entered'
                                                  : ` · paid in ${money(x.cost)}`)
                                      )
                                  ),
                                  h('div', { class: 'num strong' }, money(x.value)),
                                  h(
                                      'div',
                                      {
                                          class: 'num ' + (x.gain == null ? 'faint' : x.gain >= 0 ? 'good' : 'bad'),
                                          style: { width: '92px', textAlign: 'right' },
                                      },
                                      x.gain == null ? '–' : signed(x.gain, 0)
                                  ),
                                  h(
                                      'button',
                                      {
                                          class: 'btn ghost small',
                                          onclick: guard(async () => {
                                              const v = prompt(
                                                  'Total paid in for ' + x.name,
                                                  x.cost == null ? '' : x.cost
                                              );
                                              if (v == null || v === '' || isNaN(+v)) return;
                                              await tool('update_holding', { id: x.id, cost: +v });
                                              render();
                                          }),
                                      },
                                      'Paid in'
                                  ),
                                  ...holdingActions(x)
                              )
                          )
                      )
                    : h('div', { class: 'empty' }, 'No holdings yet.')
            ),
            inv.contributed_by_year.length
                ? section(
                      'Paid in, by year',
                      h(
                          'div',
                          { class: 'list' },
                          inv.contributed_by_year
                              .slice()
                              .reverse()
                              .map((y) =>
                                  h(
                                      'div',
                                      { class: 'item' },
                                      h(
                                          'div',
                                          { class: 'grow' },
                                          y.year,
                                          h('span', { class: 'faint small' }, `  ${y.payments} payments`)
                                      ),
                                      h('div', { class: 'num strong' }, money(y.contributed))
                                  )
                              )
                      )
                  )
                : null,
            nothing ? null : h('div', { class: 'muted small center' }, inv.note)
        );
    };

    pages.networth = async () => {
        const [w, accounts, holdings, intr] = await Promise.all([
            tool('wealth_summary'),
            tool('accounts_overview'),
            tool('list_holdings'),
            tool('interest_earned'),
        ]);
        const row = (...cells) => h('div', { class: 'item' }, ...cells);
        const other = holdings.filter((x) => x.kind !== 'investment');
        const parts = [
            ['Cash', money(w.accounts || 0)],
            ['Investments', money(w.investments)],
            ['Other assets', money(w.assets)],
            ['Debts', signed(-w.debts, 0)],
        ];
        return h(
            'div',
            { class: 'stack' },
            head('Net worth', 'Cash, investments and debts'),
            heroOf('Net worth', w.net_worth == null ? '–' : money(w.net_worth), parts),
            w.series.length > 1
                ? section(
                      'Cash over time',
                      barChart(
                          w.series.slice(-12).map((x) => ({ month: x.month, nw: x.eur })),
                          w.series[w.series.length - 1].month,
                          () => {},
                          'nw'
                      )
                  )
                : null,
            section(
                'Cash',
                accounts.length
                    ? h(
                          'div',
                          { class: 'list' },
                          accounts.map((a) =>
                              row(
                                  h(
                                      'div',
                                      { class: 'grow' },
                                      h('div', { style: { fontWeight: 650 } }, a.label + ' · ' + a.currency),
                                      h('div', { class: 'faint small' }, 'as of ' + a.as_of)
                                  ),
                                  a.proven ? null : h('span', { class: 'chip' }, 'check'),
                                  h(
                                      'div',
                                      { class: 'num strong' },
                                      a.eur == null ? a.balance.toLocaleString() : money(a.eur)
                                  )
                              )
                          )
                      )
                    : h('div', { class: 'empty' }, 'No account balances yet. They come from your statements.'),
                intr.by_year.length
                    ? h(
                          'div',
                          { class: 'faint small', style: { marginTop: '12px' } },
                          intr.by_year
                              .slice()
                              .reverse()
                              .map(
                                  (y) =>
                                      `${y.year} interest ${money(y.interest, 2)}${y.rate_percent == null ? '' : ` (about ${y.rate_percent}% a year)`}`
                              )
                              .join('  ·  ')
                      )
                    : null
            ),
            section(
                'Investments',
                h(
                    'div',
                    { class: 'row between' },
                    h('div', { class: 'num strong' }, money(w.investments)),
                    h('a', { class: 'btn small', href: '#/investments' }, 'Open Investments →')
                )
            ),
            section(
                'Assets and debts you added',
                h(
                    'div',
                    { class: 'faint small', style: { marginBottom: '10px' } },
                    'A house, a car, a loan, a mortgage: values you type in. Update them when they change.'
                ),
                holdingForm(
                    [
                        ['asset', 'Asset'],
                        ['debt', 'Debt'],
                    ],
                    false
                ),
                other.length
                    ? h(
                          'div',
                          { class: 'list' },
                          other.map((x) =>
                              row(
                                  h('span', { class: 'chip' }, x.kind),
                                  h(
                                      'div',
                                      { class: 'grow' },
                                      h('div', { style: { fontWeight: 650 } }, x.name),
                                      h('div', { class: 'faint small' }, 'as of ' + x.as_of)
                                  ),
                                  h('div', { class: 'num strong' }, (x.kind === 'debt' ? '−' : '') + money(x.value)),
                                  ...holdingActions(x)
                              )
                          )
                      )
                    : h('div', { class: 'empty' }, 'Nothing added yet.')
            ),
            h('div', { class: 'muted small center' }, w.note)
        );
    };

    pages.tasks = async () => {
        const tasks = await tool('list_tasks', { status: 'open', limit: 200 }),
            today = new Date().toISOString().slice(0, 10);
        const title = h('input', { class: 'field', placeholder: 'Add a task or reminder...', style: { flex: 1 } }),
            due = h('input', { class: 'field', type: 'date', style: { width: '170px' } });
        const rec = h(
            'select',
            { class: 'field', style: { width: '140px' } },
            ['none', 'daily', 'weekly', 'monthly', 'yearly'].map((r) =>
                h('option', { value: r }, r === 'none' ? 'No repeat' : r)
            )
        );
        const add = guard(async () => {
            if (!title.value.trim()) return;
            await tool('add_task', { title: title.value.trim(), due: due.value || undefined, recurrence: rec.value });
            render();
        });
        title.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') add();
        });
        const groups = [
            ['Overdue', (t) => t.due && t.due.slice(0, 10) < today],
            ['Today', (t) => t.due && t.due.slice(0, 10) === today],
            ['Upcoming', (t) => t.due && t.due.slice(0, 10) > today],
            ['Someday', (t) => !t.due],
        ];
        return h(
            'div',
            { class: 'stack' },
            head('Tasks', `${tasks.length} open`),
            h(
                'div',
                { class: 'card row' },
                title,
                due,
                rec,
                h('button', { class: 'btn primary', onclick: add }, 'Add')
            ),
            ...groups.map(([name, f]) => {
                const items = tasks.filter(f);
                return items.length
                    ? h(
                          'div',
                          { class: 'card' },
                          h(
                              'div',
                              { class: 'card-head' },
                              h('h2', { class: name === 'Overdue' ? 'bad' : '' }, name),
                              h('span', { class: 'chip' }, String(items.length))
                          ),
                          h(
                              'div',
                              { class: 'list' },
                              items.map((t) =>
                                  h(
                                      'div',
                                      { class: 'item' },
                                      h(
                                          'button',
                                          {
                                              class: 'check',
                                              'aria-label': 'Mark done',
                                              onclick: guard(async (e) => {
                                                  await tool('complete_task', { id: t.id });
                                                  e.currentTarget.classList.add('done');
                                                  setTimeout(render, 300);
                                              }),
                                          },
                                          h('span', {
                                              html: '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
                                              style: { display: 'contents' },
                                          })
                                      ),
                                      h(
                                          'div',
                                          { class: 'grow' },
                                          h('div', { style: { fontWeight: 600 } }, t.title),
                                          h(
                                              'div',
                                              { class: 'faint', style: { fontSize: '13px' } },
                                              [t.due || 'no date', t.recurrence !== 'none' ? '↻ ' + t.recurrence : '']
                                                  .filter(Boolean)
                                                  .join(' · ')
                                          )
                                      ),
                                      h(
                                          'button',
                                          {
                                              class: 'btn ghost small',
                                              onclick: guard(async () => {
                                                  await tool('delete_task', { id: t.id });
                                                  render();
                                              }),
                                          },
                                          'Delete'
                                      )
                                  )
                              )
                          )
                      )
                    : null;
            }),
            tasks.length ? null : h('div', { class: 'empty' }, 'Nothing to do.')
        );
    };

    pages.notes = async () => {
        let query = '';
        const grid = h('div', { class: 'masonry' }),
            search = h('input', { class: 'field', placeholder: 'Search notes', style: { maxWidth: '300px' } });
        const load = guard(async () => {
            const notes = await tool('search_notes', { query, limit: 200 });
            grid.replaceChildren(
                ...notes.map((n) =>
                    h(
                        'div',
                        { class: 'card note' },
                        n.title ? h('h3', {}, n.title) : null,
                        h('p', {}, n.body),
                        h(
                            'div',
                            { class: 'row', style: { marginTop: '14px' } },
                            h(
                                'div',
                                { class: 'grow row', style: { flexWrap: 'wrap', gap: '6px' } },
                                (n.tags || '')
                                    .split(',')
                                    .filter(Boolean)
                                    .map((t) => h('span', { class: 'chip' }, t))
                            ),
                            h(
                                'button',
                                {
                                    class: 'btn ghost small',
                                    onclick: guard(async () => {
                                        await tool('delete_note', { id: n.id });
                                        load();
                                    }),
                                },
                                'Delete'
                            )
                        )
                    )
                )
            );
            if (!notes.length) grid.append(h('div', { class: 'empty' }, 'No notes yet.'));
        });
        search.addEventListener('input', () => {
            query = search.value;
            load();
        });
        const t = h('input', { class: 'field', placeholder: 'Title (optional)' }),
            body = h('textarea', { class: 'field', placeholder: 'Write a note...' }),
            tags = h('input', { class: 'field', placeholder: 'Tags, comma separated' });
        await load();
        return h(
            'div',
            { class: 'stack' },
            head(
                'Notes',
                null,
                search,
                h(
                    'button',
                    {
                        class: 'btn',
                        onclick: guard(async () => {
                            const r = await api('/api/notes/tag', {});
                            toast(`Tagged ${r.tagged} note(s)`);
                            load();
                        }),
                    },
                    'Auto-tag'
                ),
                h(
                    'button',
                    {
                        class: 'btn',
                        onclick: guard(async () => {
                            const r = await api('/api/notes/import', {});
                            toast(`Imported: ${r.new ?? 0} new`);
                            load();
                        }),
                    },
                    'Import Apple Notes'
                )
            ),
            h(
                'div',
                { class: 'card stack', style: { gap: '12px' } },
                t,
                body,
                h(
                    'div',
                    { class: 'row' },
                    tags,
                    h(
                        'button',
                        {
                            class: 'btn primary',
                            onclick: guard(async () => {
                                if (!body.value.trim()) return;
                                await tool('add_note', { title: t.value, body: body.value, tags: tags.value });
                                t.value = body.value = tags.value = '';
                                load();
                            }),
                        },
                        'Save'
                    )
                )
            ),
            grid
        );
    };

    pages.people = async () => {
        const [people, dates, fam] = await Promise.all([
            tool('list_people'),
            tool('upcoming_dates', { days: 60 }),
            tool('family_money'),
        ]);
        const famBy = Object.fromEntries(fam.people.map((x) => [x.id, x]));
        const name = h('input', { class: 'field', placeholder: 'Name' }),
            rel = h('input', { class: 'field', placeholder: 'Relation (mother, friend...)' }),
            about = h('input', { class: 'field', placeholder: 'About (health notes, likes...)' }),
            bday = h('input', { class: 'field', type: 'date', title: 'Birthday' });
        return h(
            'div',
            { class: 'stack' },
            head('People', `${people.length} people`),
            h(
                'div',
                { class: 'card row', style: { flexWrap: 'wrap' } },
                name,
                rel,
                about,
                bday,
                h(
                    'button',
                    {
                        class: 'btn primary',
                        onclick: guard(async () => {
                            if (!name.value.trim()) return;
                            const p = await tool('add_person', {
                                name: name.value,
                                relation: rel.value,
                                about: about.value,
                            });
                            if (bday.value)
                                await tool('add_important_date', {
                                    person_id: p.id,
                                    label: 'Birthday',
                                    date: bday.value,
                                });
                            render();
                        }),
                    },
                    'Add'
                )
            ),
            h(
                'div',
                { class: 'grid g-main' },
                h(
                    'div',
                    { class: 'grid g2' },
                    people.map((p) =>
                        h(
                            'div',
                            { class: 'card person' },
                            h(
                                'div',
                                {
                                    class: 'avatar',
                                    style: {
                                        background: colour(p.name),
                                        width: '48px',
                                        height: '48px',
                                        fontSize: '17px',
                                    },
                                },
                                initials(p.name)
                            ),
                            h(
                                'div',
                                { class: 'grow' },
                                h('div', { style: { fontWeight: 650 } }, p.name),
                                h(
                                    'div',
                                    { class: 'muted', style: { fontSize: '13px' } },
                                    [p.relation, p.about].filter(Boolean).join(' · ')
                                ),
                                famBy[p.id] && famBy[p.id].payments
                                    ? h(
                                          'div',
                                          { class: 'faint small' },
                                          `Sent ${money(famBy[p.id].sent)} · received ${money(famBy[p.id].received)} · ${famBy[p.id].payments} payments`
                                      )
                                    : null
                            ),
                            h(
                                'button',
                                {
                                    class: 'btn ghost small',
                                    onclick: guard(async () => {
                                        await tool('delete_person', { id: p.id });
                                        render();
                                    }),
                                },
                                'Remove'
                            )
                        )
                    )
                ),
                h(
                    'div',
                    { class: 'card' },
                    h('div', { class: 'card-head' }, h('h2', {}, 'Next 60 days')),
                    dates.length
                        ? h(
                              'div',
                              { class: 'list' },
                              dates.map((d) =>
                                  h(
                                      'div',
                                      { class: 'item' },
                                      h(
                                          'div',
                                          { class: 'grow' },
                                          h('div', { style: { fontWeight: 600 } }, `${d.name} · ${d.label}`),
                                          h(
                                              'div',
                                              { class: 'faint', style: { fontSize: '13px' } },
                                              d.in_days === 0 ? 'today' : `in ${d.in_days} days`
                                          )
                                      ),
                                      d.turning ? h('span', { class: 'chip' }, `turning ${d.turning}`) : null
                                  )
                              )
                          )
                        : h('div', { class: 'empty' }, 'Nothing coming up.')
                )
            )
        );
    };

    pages.files = async () => {
        let mode = 'finance',
            q = '';
        const out = h('div', { class: 'card' }),
            search = h('input', {
                class: 'field',
                placeholder: 'Search by name, supplier or words',
                style: { maxWidth: '340px' },
            });
        const seg = h('div', { class: 'seg' });
        const load = guard(async () => {
            seg.replaceChildren(
                ...[
                    ['finance', 'Finance files'],
                    ['all', 'All documents'],
                ].map(([id, label]) =>
                    h(
                        'button',
                        {
                            class: mode === id ? 'on' : '',
                            onclick: () => {
                                mode = id;
                                load();
                            },
                        },
                        label
                    )
                )
            );
            if (mode === 'finance') {
                const docs = await tool('finance_documents', { party: q, limit: 200 });
                out.replaceChildren(
                    docs.length
                        ? h(
                              'table',
                              { class: 'table' },
                              h(
                                  'thead',
                                  {},
                                  h(
                                      'tr',
                                      {},
                                      ['Type', 'From / title', 'Date', 'Reference', 'Total'].map((x, i) =>
                                          h('th', { class: i === 4 ? 'r' : '' }, x)
                                      )
                                  )
                              ),
                              h(
                                  'tbody',
                                  {},
                                  docs.map((d) =>
                                      h(
                                          'tr',
                                          {},
                                          h('td', {}, h('span', { class: 'chip' }, d.kind)),
                                          h(
                                              'td',
                                              {},
                                              h('div', { style: { fontWeight: 600 } }, d.party || d.title || d.name),
                                              d.summary
                                                  ? h('div', { class: 'faint', style: { fontSize: '12px' } }, d.summary)
                                                  : null
                                          ),
                                          h('td', { class: 'num' }, d.date || '-'),
                                          h('td', { class: 'num faint' }, d.reference || '-'),
                                          h(
                                              'td',
                                              { class: 'r num', style: { fontWeight: 650 } },
                                              d.total != null ? money(d.total, 2) : '-'
                                          )
                                      )
                                  )
                              )
                          )
                        : h('div', { class: 'empty' }, 'No files yet.')
                );
            } else {
                const docs = await tool('search_documents', { query: q, limit: 25 });
                out.replaceChildren(
                    docs.length
                        ? h(
                              'div',
                              { class: 'list' },
                              docs.map((d) =>
                                  h(
                                      'div',
                                      { class: 'item' },
                                      h(
                                          'div',
                                          { class: 'grow' },
                                          h('div', { style: { fontWeight: 600 } }, d.name),
                                          h('div', { class: 'muted', style: { fontSize: '13px' } }, d.snippet)
                                      ),
                                      h('span', { class: 'chip' }, d.kind)
                                  )
                              )
                          )
                        : h('div', { class: 'empty' }, 'No documents found.')
                );
            }
        });
        search.addEventListener('input', () => {
            q = search.value;
            load();
        });
        await load();
        const s = await api('/api/settings');
        cur = s.currency;
        return h('div', { class: 'stack' }, head('Files', 'Everything the offline parser has read.', seg, search), out);
    };

    pages.settings = async () => {
        const s = await api('/api/settings'),
            cu = h('input', { class: 'field', value: s.currency, maxlength: 5 }),
            mo = h('input', { class: 'field', value: s.model }),
            ho = h('input', { class: 'field', value: s.ollama_host });
        const lab = (t, el) =>
            h(
                'label',
                { style: { display: 'block' } },
                h('div', { class: 'eyebrow', style: { marginBottom: '6px' } }, t),
                el
            );
        return h(
            'div',
            { class: 'stack', style: { maxWidth: '640px' } },
            head('Settings'),
            h(
                'div',
                { class: 'card stack', style: { gap: '16px' } },
                lab('Currency code', cu),
                lab('Local model (Ollama)', mo),
                lab('Ollama address', ho),
                h(
                    'div',
                    {},
                    h(
                        'button',
                        {
                            class: 'btn primary',
                            onclick: guard(async () => {
                                await api('/api/settings', {
                                    currency: cu.value,
                                    model: mo.value,
                                    ollama_host: ho.value,
                                });
                                cur = cu.value.toUpperCase();
                                toast('Saved');
                                refreshStatus();
                            }),
                        },
                        'Save'
                    )
                )
            ),
            h(
                'div',
                { class: 'card muted' },
                `Your data lives in ${s.data} (encrypted when the key is set). The model runs on this Mac and Orbit makes no internet requests.`
            )
        );
    };

    // ------------------------------------------------------------------ start
    buildNav();
    refreshStatus();
    setInterval(refreshStatus, 20000);
    setupTheme();
    $('#search-btn').addEventListener('click', openPalette);
    mountCornerChat();
    api('/api/settings')
        .then((s) => {
            cur = s.currency;
        })
        .finally(() => {
            window.addEventListener('hashchange', render);
            render();
        });
})();
