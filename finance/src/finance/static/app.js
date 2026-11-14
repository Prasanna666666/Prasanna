/* Finance front end. No libraries, no network: it talks only to this server. */
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
        for (const kid of kids.flat(9)) {
            if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(kid));
        }
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
    const signed = (n, d = 2) => (n < 0 ? '−' : '') + money(Math.abs(n), d);
    const money = (n, d = 0) =>
        new Intl.NumberFormat(undefined, {
            style: 'currency',
            currency: cur,
            minimumFractionDigits: d,
            maximumFractionDigits: d,
        }).format(n || 0);
    const monthName = (ym) => new Date(ym + '-15').toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
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
                      headers: { 'Content-Type': 'application/json', 'X-Finance': '1' },
                      body: JSON.stringify(body),
                  };
        const r = await fetch(path, opt);
        const d = await r.json().catch(() => ({ ok: false, error: 'The server sent something unexpected.' }));
        if (!d.ok) throw new Error(d.error || 'Something went wrong.');
        return d;
    }
    const EMBEDDED = window.self !== window.top;
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
    const PAGES = ['home', 'documents', 'settings'];
    const TABS = [
        ['home', 'Dashboard'],
        ['documents', 'Documents'],
    ];
    function buildTabs() {
        $('#tabbar').replaceChildren(
            ...TABS.map(([id, label]) =>
                h(
                    'button',
                    { type: 'button', class: 'apptab', 'data-id': id, onclick: () => (location.hash = '#/' + id) },
                    label
                )
            ),
            h(
                'a',
                {
                    class: 'apptab gear',
                    href: '#/settings',
                    'data-id': 'settings',
                    title: 'Settings',
                    'aria-label': 'Settings',
                },
                icon('settings')
            )
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
            mode = localStorage.getItem('finance.theme') || 'dark';
        } catch (_) {
            /* private window */
        }
        applyTheme(mode);
        const b = $('#theme');
        if (!b) return;
        b.addEventListener('click', () => {
            mode = mode === 'auto' ? 'dark' : mode === 'dark' ? 'light' : 'auto';
            try {
                localStorage.setItem('finance.theme', mode);
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
        const id = PAGES.includes(route()) ? route() : 'home';
        document.body.dataset.page = id;
        document.querySelectorAll('.apptab').forEach((a) => a.classList.toggle('active', a.dataset.id === id));
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
    const ASK_INSTEAD = {
        '#/networth': 'Break down my net worth',
        '#/savings': 'How much did I save this year, month by month?',
        '#/investments': 'Show my investments, what I paid in and the gain or loss',
        '#/plan': 'Which payments are due in the next three weeks?',
        '#/income': 'Where does my income come from?',
        '#/expenses': 'Where did my money go this month?',
    }; // the dashboard has no detail pages: a card asks the chat
    const stat = (label, value, sub, href, tone) => {
        const question = ASK_INSTEAD[href];
        const body = [
            h('div', { class: 'eyebrow' }, label),
            h('div', { class: 'stat-v num ' + (tone || '') }, value),
            sub ? h('div', { class: 'stat-sub' }, sub) : null,
        ];
        if (!question) return h(href ? 'a' : 'div', { class: 'stat', href }, ...body);
        const card = h('a', { class: 'stat', href: '#/home', title: 'Ask the chat' }, ...body);
        card.addEventListener('click', (e) => {
            e.preventDefault();
            askAssistant(question);
        });
        return card;
    };
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
    /** The month to open on: the latest with data, unless it is the current month and only a few days old. */
    function startMonth(trend) {
        // statements arrive after the month ends, so the newest month with data is the one to show
        return trend.length ? trend[trend.length - 1].month : new Date().toISOString().slice(0, 7);
    }

    // ------------------------------------------------------------------ finding things
    const PAGE_LINKS = [
        ['Dashboard', 'home', () => (location.hash = '#/home')],
        ['Documents', 'documents', () => (location.hash = '#/documents')],
        ['Ask', 'chat', () => toParent({ type: 'toggle-chat' })],
        ['Settings', 'settings', () => (location.hash = '#/settings')],
    ];

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
                label: `Ask Finance: “${input.value.trim()}”`,
                sub: 'Chat',
                icon: 'chat',
                run: () => askAssistant(input.value.trim()),
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
                              run: () => askAssistant(`Show my payments to ${m.merchant}`),
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
                              run: () => askAssistant(`Tell me about the payment ${p.note} on ${p.day}`),
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
                              run: () => askAssistant(p.name),
                          })),
                      ]
                    : []),
                ...(r.notes.length
                    ? [
                          { head: 'Notes' },
                          ...r.notes.map((n) => ({
                              label: n.title,
                              icon: 'notes',
                              run: () => askAssistant(n.title),
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
                              run: () => askAssistant(t.title),
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
            if (EMBEDDED) toParent({ type: 'palette' });
            else openPalette();
        }
    });

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
                askAssistant(ask.value.trim());
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
                nw.net_worth == null ? 'no data yet' : `Cash ${money(nw.accounts || 0)}`,
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
                    t: `${x.what} · ${money(x.amount, 0)} · ${x.in_days <= 0 ? 'now' : `${x.in_days}d`}`,
                })),
            ...(checks.length
                ? [{ k: 'check', t: `${checks.length} file${checks.length === 1 ? '' : 's'} to check` }]
                : []),
            ...(det.items.length
                ? [{ k: 'review', t: `${det.items.length} payment${det.items.length === 1 ? '' : 's'} to review` }]
                : []),
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
        const welcome = h(
            'div',
            { class: 'card welcome-card' },
            h('div', { class: 'orb big' }),
            h('h2', {}, 'Welcome to Finance'),
            h('p', { class: 'muted' }, 'Your money, private on this Mac. Add your statements to begin.'),
            h('a', { class: 'btn primary', href: '#/documents' }, 'Add my files')
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
                      h(
                          'div',
                          { class: 'grid g2' },
                          section('Money in and out', areaChart(d.trend)),
                          daily.length
                              ? section(
                                    'Where it went',
                                    spendDonut(daily),
                                    h(
                                        'a',
                                        {
                                            class: 'more',
                                            href: '#/home',
                                            onclick: (e) => {
                                                e.preventDefault();
                                                askAssistant('Where did my money go this month?');
                                            },
                                        },
                                        'Ask about spending →'
                                    )
                                )
                              : null
                      ),
                  ]
                : [welcome]),
            h('div', { class: 'grid g2' }, ...[attentionCard, today].filter(Boolean))
        );
    };

    /** Hand a question to the one chat that Atlas shows for everything. */
    function askAssistant(text) {
        toParent({ type: 'ask', text });
    }

    async function documentsPage() {
        cur = (await api('/api/settings')).currency;
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
                if (r.files) draw();
            }
        }
        async function draw() {
            const [slips, docs, docTotals, checks, ver, cc] = await Promise.all([
                tool('list_payslips', { limit: 12 }),
                tool('finance_documents', { limit: 200 }),
                tool('finance_document_totals', { by: 'kind' }),
                tool('files_to_check'),
                tool('verification_report'),
                tool('currencies'),
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

            // ---- trips & events: found by the model from your statements; tap a card for its lines

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
            const empty = !docs.length && !slips.length;
            const content = [statusCard, docCard, detailsFold];
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
                    head('Documents', null, empty ? null : curChips, empty ? null : importBtn),
                    status,
                    empty ? null : checkNote,
                    empty ? first : null,
                    ...(empty ? [] : content),
                ].filter(Boolean)
            );
        }
        await draw();
        poll();
        return wrap;
    }
    pages.documents = documentsPage;

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
                `Your data lives in ${s.data} (encrypted when the key is set). The model runs on this Mac and Finance makes no internet requests.`
            )
        );
    };

    // ------------------------------------------------------------------ shown inside Atlas (the shared page): its menu, search and chat button replace ours
    const toParent = (message) => {
        window.parent.postMessage(
            { atlas: 1, ...message },
            (location.ancestorOrigins && location.ancestorOrigins[0]) || '*'
        );
    };
    function setupEmbedding() {
        if (!EMBEDDED) return;
        document.documentElement.classList.add('embedded');
        window.addEventListener('message', (event) => {
            const m = event.data;
            if (event.source !== window.parent || !m || m.atlas !== 1) return;
            if (m.type === 'navigate' && typeof m.hash === 'string') location.hash = m.hash;
            else if (m.type === 'theme' && ['dark', 'light', 'auto'].includes(m.mode)) applyTheme(m.mode);
        });
        window.addEventListener('hashchange', () => toParent({ type: 'route', hash: location.hash }));
        toParent({ type: 'ready' });
    }

    // ------------------------------------------------------------------ start
    setupEmbedding();
    buildTabs();
    refreshStatus();
    setInterval(refreshStatus, 20000);
    setupTheme();
    $('#search-btn').addEventListener('click', openPalette);
    api('/api/settings')
        .then((s) => {
            cur = s.currency;
        })
        .finally(() => {
            window.addEventListener('hashchange', render);
            render();
        });
})();
