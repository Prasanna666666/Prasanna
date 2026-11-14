'use strict';
/* The Health and Travel apps. Everything shown is copied from the person's own documents; all text is added with textContent. */
(() => {
    const $ = (s) => document.querySelector(s);
    const el = (tag, cls, text) => {
        const e = document.createElement(tag);
        if (cls) e.className = cls;
        if (text != null) e.textContent = text;
        return e;
    };
    const getJson = async (path) => (await fetch(path, { headers: { Accept: 'application/json' } })).json();
    const host = () => $('#page-apps');
    const go = (path, params) => {
        const qs = new URLSearchParams(
            Object.fromEntries(Object.entries(params || {}).filter(([, v]) => v))
        ).toString();
        location.hash = `#/${path}${qs ? '?' + qs : ''}`;
    };
    const askAtlas = (text) =>
        window.parent.postMessage(
            { atlas: 1, type: 'ask', text },
            (location.ancestorOrigins && location.ancestorOrigins[0]) || '*'
        );
    const range = (a, b) => (a === b || !b ? a : `${a} → ${b}`);
    const head = (title, sub) => {
        const h = el('div', 'apphead');
        h.append(el('h2', '', title));
        if (sub) h.append(el('p', 'muted', sub));
        return h;
    };
    const card = (title, sub, onClick) => {
        const c = el('button', 'card');
        c.type = 'button';
        c.append(el('b', '', title), el('span', '', sub || ''));
        c.addEventListener('click', onClick);
        return c;
    };
    const button = (label, onClick) => {
        const b = el('button', 'pill', label);
        b.type = 'button';
        b.addEventListener('click', onClick);
        return b;
    };
    const openDoc = (id) => (location.hash = `#/doc/${id}`);
    const section = (title) => el('h3', 'band', title);
    // a headline number with a label under it: the building block of every dashboard
    const tile = (label, value, tone, sub, onClick) => {
        const t = el(onClick ? 'button' : 'div', `stat ${tone || ''}`);
        if (onClick) {
            t.type = 'button';
            t.addEventListener('click', onClick);
        }
        t.append(el('span', 'stat-label', label), el('b', 'stat-value', value));
        if (sub) t.append(el('span', 'stat-sub', sub));
        return t;
    };
    const tiles = (...list) => {
        const row = el('div', 'tiles');
        row.append(...list.filter(Boolean));
        return row;
    };
    const days = (iso) => Math.round((new Date(iso + 'T00:00:00') - new Date(new Date().toDateString())) / 86400000);
    const when = (n) =>
        n === 0
            ? 'today'
            : n === 1
              ? 'tomorrow'
              : n < 0
                ? `${-n} days ago`
                : n < 60
                  ? `in ${n} days`
                  : n < 730
                    ? `in ${Math.round(n / 30)} months`
                    : `in ${Math.round(n / 365)} years`;
    const shortDate = (iso) =>
        new Date(iso + 'T00:00:00').toLocaleDateString(undefined, { day: 'numeric', month: 'short' });

    const appTabs = (app, current) =>
        window.AppTabs(
            [
                [app, 'Dashboard'],
                [`${app}-docs`, 'Documents'],
            ],
            current
        );
    const NS = 'http://www.w3.org/2000/svg';
    const svgEl = (tag, attrs) => {
        const n = document.createElementNS(NS, tag);
        for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
        return n;
    };
    // a ring: the share of `good` out of good + `bad`, with the count of `bad` in the middle
    const ring = (good, bad) => {
        const total = Math.max(1, good + bad),
            r = 34,
            c = 2 * Math.PI * r;
        const svg = svgEl('svg', { viewBox: '0 0 84 84', class: 'ring', 'aria-hidden': 'true' });
        svg.append(svgEl('circle', { cx: 42, cy: 42, r, class: 'ring-bad' }));
        svg.append(
            svgEl('circle', {
                cx: 42,
                cy: 42,
                r,
                class: 'ring-good',
                'stroke-dasharray': `${(good / total) * c} ${c}`,
                transform: 'rotate(-90 42 42)',
            })
        );
        return svg;
    };
    // where the latest value sits against the range printed on the report
    const parseRange = (text) => {
        const num = (x) => parseFloat(x.replace(',', '.'));
        let m = (text || '').match(/(-?\d[\d.,]*)\s*[-–]\s*(-?\d[\d.,]*)/);
        if (m) return [num(m[1]), num(m[2])];
        m = (text || '').match(/[<≤]\s*(-?\d[\d.,]*)/);
        if (m) return [null, num(m[1])];
        m = (text || '').match(/[>≥]\s*(-?\d[\d.,]*)/);
        return m ? [num(m[1]), null] : null;
    };
    const rangeBar = (g) => {
        const bounds = parseRange(g.latest.range),
            value = parseFloat(String(g.latest.value).replace(',', '.'));
        if (!bounds || !Number.isFinite(value)) return null;
        const [lo, hi] = bounds;
        const span = lo != null && hi != null ? hi - lo : Math.abs(hi ?? lo) * 0.6;
        const min = lo != null ? lo - span * 0.6 : Math.min(0, value),
            max = hi != null ? hi + span * 0.6 : lo + span * 1.6;
        const at = (v) => Math.min(100, Math.max(0, ((v - min) / (max - min || 1)) * 100));
        const svg = svgEl('svg', {
            viewBox: '0 0 100 10',
            class: 'rangebar',
            preserveAspectRatio: 'none',
            'aria-hidden': 'true',
        });
        svg.append(svgEl('rect', { x: 0, y: 3, width: 100, height: 4, rx: 2, class: 'rb-track' }));
        const from = lo != null ? at(lo) : 0,
            to = hi != null ? at(hi) : 100;
        svg.append(svgEl('rect', { x: from, y: 3, width: Math.max(1, to - from), height: 4, rx: 2, class: 'rb-ok' }));
        svg.append(svgEl('circle', { cx: at(value), cy: 5, r: 3.4, class: 'rb-dot' }));
        return svg;
    };

    // ---------------------------------------------------------------- Travel
    async function travelDocs() {
        host().replaceChildren(el('div', 'empty', 'Loading…'));
        const [folder, booked] = await Promise.all([
            getJson('/api/documents?area=travel&limit=200'),
            getJson('/api/documents?kind=ticket,booking&limit=200'),
        ]);
        const seen = new Set();
        const documents = [...folder.documents, ...booked.documents].filter((d) => !seen.has(d.id) && seen.add(d.id)); // the travel folder, plus tickets and bookings found anywhere
        const page = [appTabs('travel', 'travel-docs')];
        if (!documents.length) page.push(el('p', 'muted', 'No travel documents yet. Press Read new files.'));
        for (const d of documents)
            page.push(
                card(
                    d.facts && d.facts.title ? d.facts.title : d.name,
                    [d.kind, d.parsed_at && d.parsed_at.slice(0, 10)].filter(Boolean).join(' · '),
                    () => openDoc(d.id)
                )
            );
        host().replaceChildren(...page);
    }

    async function travel() {
        host().replaceChildren(el('div', 'empty', 'Loading…'));
        const { trips } = await getJson('/api/travel/trips');
        if (!trips.length)
            return host().replaceChildren(
                appTabs('travel', 'travel'),
                el('div', 'empty', 'No trips yet. Tickets and bookings are found when you press Read new files.')
            );
        const coming = trips.filter((t) => t.status !== 'past').sort((x, y) => x.start.localeCompare(y.start));
        const past = trips.filter((t) => t.status === 'past');
        const open = (t) => go('trip', { place: t.place, start: t.start, end: t.end });
        const page = [appTabs('travel', 'travel')];
        const next = coming[0];
        if (next) {
            const n = days(next.start);
            const hero = el('button', 'hero');
            hero.type = 'button';
            hero.addEventListener('click', () => open(next));
            const nights = Math.max(1, days(next.end) - days(next.start));
            const text = el('div', 'hero-text');
            text.append(
                el('span', 'stat-label', next.status === 'now' ? 'On now' : 'Next trip'),
                el('b', 'hero-place', next.place),
                el('span', 'stat-sub', `${shortDate(next.start)} – ${shortDate(next.end)} · ${nights} nights`)
            );
            const count = el('div', 'hero-count');
            if (next.status === 'now' || n < 0) count.append(el('b', '', 'Now'));
            else if (n < 366)
                count.append(el('b', '', String(n)), el('span', '', n === 1 ? 'day to go' : 'days to go'));
            else count.append(el('b', '', when(n).replace('in ', '')));
            const top = el('div', 'hero-top');
            top.append(text, count);
            hero.append(top);
            const detail = await getJson(
                '/api/travel/trip?' + new URLSearchParams({ place: next.place, start: next.start, end: next.end })
            );
            if (detail.photos && detail.photos.ids.length) {
                const strip = el('div', 'hero-photos');
                for (const id of detail.photos.ids.slice(0, 4)) {
                    const img = new Image();
                    img.alt = '';
                    img.loading = 'lazy';
                    img.src = `/api/pictures/thumb/${id}`;
                    strip.append(img);
                }
                hero.append(strip);
            }
            page.push(hero);
        }
        page.push(
            tiles(
                tile('Upcoming', coming.length, 'accent'),
                tile('Past', past.length),
                tile('Places', new Set(trips.map((t) => t.place)).size),
                tile(
                    'Documents',
                    trips.reduce((x, t) => x + (t.documents || 0), 0)
                )
            )
        );
        const grid = el('div', 'tripgrid');
        for (const t of [...coming.slice(1), ...past]) {
            const c = el('button', 'tripcard' + (t.status === 'past' ? ' past' : ''));
            c.type = 'button';
            c.addEventListener('click', () => open(t));
            c.append(
                el('b', '', t.place),
                el('span', 'stat-sub', `${shortDate(t.start)}${t.end !== t.start ? ' – ' + shortDate(t.end) : ''}`),
                el(
                    'span',
                    'chips',
                    `${t.documents ? '✈ ' + t.documents : ''}${t.documents && t.photos ? '   ' : ''}${t.photos ? '▣ ' + t.photos : ''}`
                )
            );
            grid.append(c);
        }
        page.push(grid);
        const cal = el('a', 'pill', 'Add trips to Calendar');
        cal.href = '/api/travel/calendar.ics';
        cal.setAttribute('download', 'trips.ics');
        page.push(cal);
        host().replaceChildren(...page);
    }

    // the packing list: the person's own checklist for one trip
    async function packingBlock(t) {
        const box = el('div', 'packing');
        const body = { place: t.place, start: t.start, end: t.end };
        const act = async (action, extra) => {
            const r = await (
                await fetch('/api/travel/packing', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-Library': '1' },
                    body: JSON.stringify({ ...body, action, ...extra }),
                })
            ).json();
            if (r.ok === false) box.prepend(el('p', 'muted', r.error || 'That did not work.'));
            else draw(r);
        };
        const draw = (p) => {
            const parts = [section(`Packing list${p.total ? ` (${p.packed} of ${p.total} packed)` : ''}`)];
            if (!p.total) parts.push(button('Start with a standard list', () => act('seed')));
            let current = '';
            for (const item of p.items) {
                if (item.section !== current) {
                    current = item.section;
                    parts.push(el('h4', 'packsection', current));
                }
                const row = el('label', 'packitem');
                const box1 = el('input');
                box1.type = 'checkbox';
                box1.checked = !!item.done;
                box1.addEventListener('change', () => act('toggle', { id: item.id }));
                const text = el('span', item.done ? 'packed' : '', item.text);
                const del = el('button', 'packdel', '×');
                del.type = 'button';
                del.setAttribute('aria-label', `Remove ${item.text}`);
                del.addEventListener('click', (e) => {
                    e.preventDefault();
                    act('delete', { id: item.id });
                });
                row.append(box1, text, del);
                parts.push(row);
            }
            const form = el('form', 'packadd');
            const input = el('input', 'field');
            input.placeholder = 'Add something to pack';
            input.maxLength = 120;
            const add = el('button', 'pill', 'Add');
            add.type = 'submit';
            form.append(input, add);
            form.addEventListener('submit', (e) => {
                e.preventDefault();
                if (input.value.trim()) act('add', { text: input.value.trim() });
            });
            parts.push(form);
            box.replaceChildren(...parts);
        };
        draw(await getJson(`/api/travel/packing?${new URLSearchParams({ place: t.place, start: t.start })}`));
        return box;
    }

    async function trip(params) {
        host().replaceChildren(el('div', 'empty', 'Loading…'));
        const q = new URLSearchParams({ place: params.place || '', start: params.start || '', end: params.end || '' });
        const t = await getJson('/api/travel/trip?' + q);
        if (t.ok === false) return host().replaceChildren(el('div', 'empty', t.error || 'That trip was not found.'));
        const page = [appTabs('travel', ''), head(t.place, range(t.start, t.end))];
        page.push(button('← All trips', () => go('travel')));
        page.push(
            button('How much did this trip cost?', () =>
                askAtlas(
                    `How much did my ${t.place} trip cost? Add up everything I paid from ${t.start} to ${t.end}, and say what is included.`
                )
            )
        );
        const totals = Object.entries(t.booked_totals);
        if (totals.length) {
            page.push(section('Booked (as the tickets and bookings print it)'));
            totals.forEach(([cur, v]) => page.push(el('p', 'bigfigure', `${cur} ${v.toFixed(2)}`)));
        }
        page.push(section('Tickets and bookings'));
        if (!t.tickets.length) page.push(el('p', 'muted', 'None found for these days.'));
        for (const x of t.tickets)
            page.push(
                card(
                    x.title,
                    [
                        x.party,
                        range(x.start_date, x.end_date),
                        x.reference && `ref ${x.reference}`,
                        x.total != null && `${x.currency} ${x.total.toFixed(2)}`,
                    ]
                        .filter(Boolean)
                        .join(' · '),
                    () => openDoc(x.id)
                )
            );
        if (t.other_documents.length) {
            page.push(section('Other documents from these days'));
            t.other_documents.forEach((d) => page.push(card(d.title, `${d.kind} · ${d.date}`, () => openDoc(d.id))));
        }
        page.push(await packingBlock(t));
        if (t.photos.total) {
            page.push(section(`Photos (${t.photos.total.toLocaleString()} from these days)`));
            const strip = el('div', 'photostrip');
            for (const id of t.photos.ids) {
                const img = new Image();
                img.alt = '';
                img.loading = 'lazy';
                img.src = `/api/pictures/thumb/${id}`;
                strip.append(img);
            }
            page.push(strip);
        }
        host().replaceChildren(...page);
    }

    // ---------------------------------------------------------------- Health
    function sparkline(numbers) {
        const w = 160,
            h = 36;
        const lo = Math.min(...numbers),
            hi = Math.max(...numbers);
        const x = (i) => (numbers.length === 1 ? w / 2 : (i / (numbers.length - 1)) * (w - 8) + 4);
        const y = (v) => (hi === lo ? h / 2 : h - 4 - ((v - lo) / (hi - lo)) * (h - 8));
        const NS = 'http://www.w3.org/2000/svg';
        const svg = document.createElementNS(NS, 'svg');
        svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
        svg.setAttribute('width', w);
        svg.setAttribute('height', h);
        svg.setAttribute('aria-hidden', 'true');
        const line = document.createElementNS(NS, 'polyline');
        line.setAttribute('points', numbers.map((v, i) => `${x(i)},${y(v)}`).join(' '));
        line.setAttribute('fill', 'none');
        line.setAttribute('stroke', 'currentColor');
        line.setAttribute('stroke-width', '2');
        svg.append(line);
        return svg;
    }

    const FLAG = { above_range: 'high', below_range: 'low', in_range: 'ok' };
    // one small card per test: the latest value, a flag dot, and the trend
    const labGrid = (groups) => {
        const grid = el('div', 'labgrid');
        for (const g of groups) {
            const c = el('button', `labtile ${FLAG[g.flag] || ''}`);
            c.type = 'button';
            c.title = g.latest.range ? `printed range ${g.latest.range}` : g.test;
            c.addEventListener('click', () => openDoc(g.latest.id || g.readings[g.readings.length - 1].id));
            const top = el('span', 'stat-label', g.test);
            top.prepend(el('i', 'dot'));
            c.append(top, el('b', 'stat-value', `${g.latest.value}${g.unit ? ' ' + g.unit : ''}`));
            const bar = rangeBar(g);
            if (bar) c.append(bar);
            const nums = g.readings.map((r) => r.number).filter((n) => n != null);
            if (nums.length > 1) c.append(sparkline(nums));
            if (g.change && g.change.direction !== 'same')
                c.append(
                    el(
                        'span',
                        'stat-sub',
                        `${g.change.direction === 'up' ? '▲' : '▼'} ${g.change.percent != null ? Math.abs(g.change.percent) + '%' : Math.abs(g.change.absolute)}`
                    )
                );
            grid.append(c);
        }
        return grid;
    };

    async function health(sub) {
        host().replaceChildren(el('div', 'empty', 'Loading…'));
        if (sub === 'documents') {
            const data = await getJson('/api/medical/documents');
            const page = [appTabs('health', 'health-docs')];
            if (!data.documents.length) page.push(el('p', 'muted', 'No health documents yet. Press Read new files.'));
            for (const d of data.documents)
                page.push(
                    card(
                        d.title,
                        [d.date, d.party, d.values && `${d.values} values`, d.medicines && `${d.medicines} medicines`]
                            .filter(Boolean)
                            .join(' · '),
                        () => openDoc(d.id)
                    )
                );
            return host().replaceChildren(...page);
        }
        // the dashboard: four headline tiles, the tests as small cards, the medicines as chips
        const [values, meds, coming] = await Promise.all([
            getJson('/api/medical/values'),
            getJson('/api/medical/medicines'),
            getJson('/api/medical/followups'),
        ]);
        const nextUp = (coming.follow_ups || [])[0];
        const out = values.attention.length;
        const inside = values.tests.length - out;
        const status = el('div', 'stat statusring');
        const label = el('div', 'ring-label');
        label.append(el('b', 'stat-value', String(out)), el('span', 'stat-label', 'outside range'));
        status.append(ring(inside, out), label);
        const page = [
            appTabs('health', 'health'),
            tiles(
                status,
                nextUp
                    ? tile(
                          'Next check',
                          shortDate(nextUp.date),
                          'accent',
                          `${nextUp.title} · ${when(days(nextUp.date))}`,
                          () => openDoc(nextUp.id)
                      )
                    : null,
                tile('Tests', values.tests.length),
                tile('Medicines', meds.medicines.length)
            ),
        ];
        if (!values.tests.length) page.push(el('div', 'empty', 'No values yet. Press Read new files.'));
        const rest = (list) => list.filter((g) => !values.attention.some((a) => a.test === g.test));
        const ordered = [...values.attention, ...rest(values.common), ...rest(values.other)];
        if (ordered.length) page.push(labGrid(ordered));
        if (meds.medicines.length) {
            const row = el('div', 'chiprow');
            for (const m of meds.medicines) {
                const c = el('button', 'chip');
                c.type = 'button';
                c.append(el('b', '', m.name), el('span', '', m.dose || ''));
                c.addEventListener('click', () => openDoc(m.id));
                row.append(c);
            }
            page.push(row);
        }
        page.push(
            el(
                'p',
                'foot',
                'Copied exactly as printed in your documents. A flag only compares with the range printed on the report.'
            )
        );
        host().replaceChildren(...page);
    }

    const PAGES = {
        travel: () => travel(),
        trip: (p) => trip(p),
        health: () => health('dashboard'),
        'health-docs': () => health('documents'),
        'travel-docs': () => travelDocs(),
    };
    window.HealthTravelUI = { show: (path, params) => PAGES[path](params || {}), pages: Object.keys(PAGES) };
    if (PAGES[location.hash.replace(/^#\//, '').split('?')[0]]) window.dispatchEvent(new Event('hashchange'));
})();
