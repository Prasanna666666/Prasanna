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
    const ring = (good, bad, label) => {
        const total = Math.max(1, good + bad),
            r = 38,
            c = 2 * Math.PI * r;
        const svg = svgEl('svg', { viewBox: '0 0 100 100', class: 'ring', 'aria-hidden': 'true' });
        svg.append(svgEl('circle', { cx: 50, cy: 50, r, class: bad ? 'ring-bad' : 'ring-track' }));
        svg.append(
            svgEl('circle', {
                cx: 50,
                cy: 50,
                r,
                class: 'ring-good',
                'stroke-dasharray': `${(good / total) * c} ${c}`,
                transform: 'rotate(-90 50 50)',
            })
        );
        if (label) {
            const t = svgEl('text', { x: 50, y: 56, 'text-anchor': 'middle', class: 'ring-text' });
            t.textContent = label;
            svg.append(t);
        }
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

    // the place that holds an app's documents: one tile per document, named by what it says, filtered by kind
    const DOC_ICON = 'M6 3h9l4 4v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Zm8 0v5h5M8.5 13h7M8.5 17h5';
    const docTile = (title, lines, tag, onClick) => {
        const c = el('button', 'doctile');
        c.type = 'button';
        const icon = svgEl('svg', { viewBox: '0 0 24 24', class: 'docicon', 'aria-hidden': 'true' });
        icon.append(svgEl('path', { d: DOC_ICON }));
        const text = el('span', 'doctext');
        text.append(el('b', '', title), el('span', '', lines.filter(Boolean).join(' · ')));
        c.append(icon, text);
        if (tag) c.append(el('em', 'doctag', tag));
        c.addEventListener('click', onClick);
        return c;
    };
    const documentsPlace = (tabsBar, heading, tiles, empty) => {
        const page = [tabsBar, sectionHead(heading, tiles.length)];
        if (!tiles.length) return [...page, el('div', 'empty', empty)];
        const kinds = [...new Set(tiles.map((t) => t.kind))].filter(Boolean);
        const grid = el('div', 'docgrid');
        const draw = (kind) =>
            grid.replaceChildren(...tiles.filter((t) => !kind || t.kind === kind).map((t) => t.node));
        if (kinds.length > 1) {
            const chips = el('div', 'chiprow');
            for (const k of ['', ...kinds]) {
                const b = el('button', 'chip', k ? k.replace('_', ' ') : 'All');
                b.type = 'button';
                b.addEventListener('click', () => {
                    chips.querySelectorAll('.chip').forEach((x) => x.classList.toggle('on', x === b));
                    draw(k);
                });
                if (!k) b.classList.add('on');
                chips.append(b);
            }
            page.push(chips);
        }
        draw('');
        page.push(grid);
        return page;
    };

    // ---------------------------------------------------------------- Travel
    async function travelDocs() {
        host().replaceChildren(el('div', 'empty', 'Loading…'));
        const [folder, booked] = await Promise.all([
            getJson('/api/documents?area=travel&source=documents&limit=200'),
            getJson('/api/documents?kind=ticket,booking&source=documents&limit=200'),
        ]);
        const seen = new Set();
        const documents = [...folder.documents, ...booked.documents].filter((d) => !seen.has(d.id) && seen.add(d.id)); // the travel folder, plus tickets and bookings found anywhere
        const tiles = documents.map((d) => ({
            kind: d.kind,
            node: docTile(d.title, [d.facts.start_date || d.facts.date, d.facts.place], d.kind.replace('_', ' '), () =>
                openDoc(d.id)
            ),
        }));
        const page = documentsPlace(
            appTabs('travel', 'travel-docs'),
            'Travel documents',
            tiles,
            'No travel documents yet. Press Read new files.'
        );
        host().replaceChildren(...page);
    }

    // every place gets its own colours, the same each time
    const hue = (text) => [...text].reduce((a, c) => (a * 31 + c.charCodeAt(0)) % 360, 7);
    const banner = (place) =>
        `linear-gradient(135deg, hsl(${hue(place)} 68% 46%), hsl(${(hue(place) + 50) % 360} 70% 32%))`;
    const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

    // twelve months at a glance: each trip a coloured bar where it falls
    const yearStrip = (trips, open) => {
        const now = new Date();
        const first = new Date(now.getFullYear(), now.getMonth() - 2, 1);
        const last = new Date(first.getFullYear(), first.getMonth() + 12, 1);
        const span = last - first;
        const at = (iso) => Math.min(1, Math.max(0, (new Date(iso + 'T00:00:00') - first) / span)) * 100;
        const box = el('div', 'yearstrip');
        const grid = el('div', 'ys-months');
        for (let i = 0; i < 12; i++) {
            const m = new Date(first.getFullYear(), first.getMonth() + i, 1);
            const cell = el(
                'span',
                m.getMonth() === now.getMonth() && m.getFullYear() === now.getFullYear() ? 'now' : '',
                MONTHS[m.getMonth()]
            );
            grid.append(cell);
        }
        box.append(grid);
        const lane = el('div', 'ys-lane');
        for (const t of trips) {
            const left = at(t.start),
                right = at(t.end);
            if (right <= left && at(t.start) >= 100) continue;
            const bar = el('button', 'ys-bar', t.place);
            bar.type = 'button';
            bar.style.left = `${left}%`;
            bar.style.width = `${Math.max(4, right - left)}%`;
            bar.style.background = banner(t.place);
            bar.addEventListener('click', () => open(t));
            lane.append(bar);
        }
        box.append(lane);
        return box;
    };

    const coverUrl = (id, size = 'thumb') => `/api/pictures/${size}/${id}`;

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
        const star = coming[0] || past[0];
        if (star) {
            const n = days(star.start);
            const hero = el('button', 'hero travelhero withcover');
            hero.type = 'button';
            // a picture from the trip when there is one, otherwise the place's own colours; both with text on top
            hero.style.setProperty(
                'background',
                star.cover
                    ? `linear-gradient(180deg, rgba(0,0,0,0.05), rgba(0,0,0,0.7)), url("${coverUrl(star.cover, 'preview')}") center / cover`
                    : banner(star.place),
                'important'
            );
            hero.addEventListener('click', () => open(star));
            const nights = Math.max(1, days(star.end) - days(star.start));
            const text = el('div', 'hero-text');
            text.append(
                el('span', 'stat-label', star.status === 'now' ? 'On now' : coming[0] ? 'Next trip' : 'Last trip'),
                el('b', 'hero-place', star.place),
                el('span', 'stat-sub', `${shortDate(star.start)} – ${shortDate(star.end)} · ${nights} nights`)
            );
            const count = el('div', 'hero-count');
            if (!coming[0]) count.append(el('b', '', String(nights)), el('span', '', 'nights'));
            else if (star.status === 'now' || n < 0) count.append(el('b', '', 'Now'));
            else if (n < 366)
                count.append(el('b', '', String(n)), el('span', '', n === 1 ? 'day to go' : 'days to go'));
            else count.append(el('b', '', when(n).replace('in ', '')));
            const top = el('div', 'hero-top');
            top.append(text, count);
            hero.append(top);
            const detail = await getJson(
                '/api/travel/trip?' + new URLSearchParams({ place: star.place, start: star.start, end: star.end })
            );
            const facts = el('div', 'hero-facts');
            const flights = (detail.tickets || []).filter((x) => x.kind === 'ticket').length;
            const stays = (detail.tickets || []).filter((x) => x.kind === 'booking').length;
            if (flights) facts.append(el('span', '', `✈ ${flights} ticket${flights === 1 ? '' : 's'}`));
            if (stays) facts.append(el('span', '', `⌂ ${stays} booking${stays === 1 ? '' : 's'}`));
            for (const [cur, amount] of Object.entries(detail.booked_totals || {}))
                facts.append(
                    el('span', '', `${cur} ${amount.toLocaleString(undefined, { minimumFractionDigits: 2 })} booked`)
                );
            if (detail.photos && detail.photos.total) facts.append(el('span', '', `▣ ${detail.photos.total} photos`));
            if (facts.children.length) hero.append(facts);
            page.push(hero);
        }
        // the year in three numbers
        const thisYear = String(new Date().getFullYear());
        const mine = trips.filter((t) => t.start.startsWith(thisYear));
        const away = mine.reduce((x, t) => x + Math.max(1, days(t.end) - days(t.start)), 0);
        const figures = el('div', 'figures');
        for (const [label, value] of [
            [`Trips in ${thisYear}`, mine.length],
            ['Nights away', away],
            ['Places', new Set(trips.map((t) => t.place)).size],
        ]) {
            const f = el('div', 'figure');
            f.append(el('b', '', String(value)), el('span', '', label));
            figures.append(f);
        }
        page.push(figures, yearStrip(trips, open));
        const grid = el('div', 'tripgrid photos');
        for (const t of [...coming.filter((x) => x !== star), ...past.filter((x) => x !== star)]) {
            const c = el('button', 'tripcard' + (t.status === 'past' ? ' past' : ''));
            c.type = 'button';
            c.addEventListener('click', () => open(t));
            const top = el('div', 'tc-banner');
            if (t.cover) {
                top.style.backgroundImage = `url("${coverUrl(t.cover)}")`;
                top.classList.add('has-photo');
            } else top.style.background = banner(t.place);
            const nights = Math.max(1, days(t.end) - days(t.start));
            const label = el('span', 'tc-label');
            label.append(
                el('b', '', t.place),
                el('small', '', `${shortDate(t.start)} · ${nights} night${nights === 1 ? '' : 's'}`)
            );
            top.append(label);
            c.append(top);
            const chips = [t.documents ? `✈ ${t.documents}` : '', t.photos ? `▣ ${t.photos}` : '']
                .filter(Boolean)
                .join('   ');
            if (chips) c.append(el('span', 'chips', chips));
            grid.append(c);
        }
        if (grid.children.length) page.push(sectionHead('Trips', grid.children.length), grid);
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
        svg.setAttribute('preserveAspectRatio', 'none');
        svg.setAttribute('class', 'spark');
        svg.setAttribute('aria-hidden', 'true');
        const line = document.createElementNS(NS, 'polyline');
        line.setAttribute('points', numbers.map((v, i) => `${x(i)},${y(v)}`).join(' '));
        line.setAttribute('fill', 'none');
        line.setAttribute('stroke', 'currentColor');
        line.setAttribute('stroke-width', '2');
        const area = svgEl('polygon', {
            points: `${x(0)},${h} ${numbers.map((v, i) => `${x(i)},${y(v)}`).join(' ')} ${x(numbers.length - 1)},${h}`,
            class: 'spark-area',
        });
        svg.append(area, line);
        return svg;
    }

    const FLAG = { above_range: 'high', below_range: 'low', in_range: 'ok' };
    // one small card per test: the latest value, a flag dot, and the trend
    // one test over time as a real chart: the line, its points, and the range printed on the reports as a green band
    const focusChart = (g) => {
        const box = el('div', 'focus');
        const head = el('div', 'focus-head');
        const value = el('b', 'focus-value', g.latest.value);
        if (g.unit) value.append(el('small', '', ' ' + g.unit));
        const title = el('div', 'focus-title');
        title.append(el('span', 'stat-label', 'Over time'), el('b', '', g.test));
        head.append(title, value);
        box.append(head);
        const pts = g.readings.filter((r) => r.number != null);
        if (!pts.length) return box;
        const W = 640,
            H = 210,
            L = 40,
            R = 14,
            T = 14,
            B = 28;
        const bounds = parseRange(g.latest.range) || [null, null];
        const nums = pts.map((r) => r.number);
        let lo = Math.min(...nums, bounds[0] ?? Infinity),
            hi = Math.max(...nums, bounds[1] ?? -Infinity);
        const pad = (hi - lo || Math.abs(hi) || 1) * 0.2;
        lo -= pad;
        hi += pad;
        const x = (i) => L + (pts.length === 1 ? (W - L - R) / 2 : (i / (pts.length - 1)) * (W - L - R));
        const y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
        const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, class: 'focus-svg', 'aria-hidden': 'true' });
        if (bounds[0] != null || bounds[1] != null) {
            const top = y(bounds[1] ?? hi),
                bottom = y(bounds[0] ?? lo);
            svg.append(
                svgEl('rect', {
                    x: L,
                    y: top,
                    width: W - L - R,
                    height: Math.max(2, bottom - top),
                    class: 'focus-band',
                })
            );
        }
        for (let i = 0; i <= 3; i++) {
            const v = lo + ((hi - lo) * i) / 3;
            const line = svgEl('line', { x1: L, x2: W - R, y1: y(v), y2: y(v), class: 'focus-grid' });
            const label = svgEl('text', { x: L - 6, y: y(v) + 4, 'text-anchor': 'end', class: 'focus-axis' });
            label.textContent = (Math.round(v * 10) / 10).toString();
            svg.append(line, label);
        }
        const path = pts.map((r, i) => `${i ? 'L' : 'M'}${x(i)} ${y(r.number)}`).join(' ');
        svg.append(
            svgEl('path', { d: `${path} L${x(pts.length - 1)} ${H - B} L${x(0)} ${H - B} Z`, class: 'focus-area' })
        );
        svg.append(svgEl('path', { d: path, class: 'focus-line' }));
        pts.forEach((r, i) => {
            svg.append(svgEl('circle', { cx: x(i), cy: y(r.number), r: 4.5, class: 'focus-dot' }));
            const d = svgEl('text', {
                x: x(i),
                y: H - 8,
                'text-anchor':
                    pts.length === 1 ? 'middle' : i === 0 ? 'start' : i === pts.length - 1 ? 'end' : 'middle',
                class: 'focus-axis',
            });
            d.textContent = r.date ? shortDate(r.date) : '';
            svg.append(d);
        });
        box.append(svg);
        const open = el('button', 'pill', 'Open the latest report');
        open.type = 'button';
        open.addEventListener('click', () => openDoc(g.latest.id || g.readings[g.readings.length - 1].id));
        box.append(open);
        return box;
    };
    const labGrid = (groups, onPick) => {
        const grid = el('div', 'labgrid');
        for (const g of groups) {
            const c = el('button', `labtile ${FLAG[g.flag] || ''}`);
            c.type = 'button';
            c.addEventListener('click', () => onPick(g));
            const top = el('span', 'lab-name', g.test);
            top.prepend(el('i', 'dot'));
            const value = el('b', 'lab-value', g.latest.value);
            if (g.unit) value.append(el('small', '', ' ' + g.unit));
            c.append(top, value);
            const bar = rangeBar(g);
            if (bar) c.append(bar);
            if (g.latest.range) c.append(el('span', 'stat-sub', `range ${g.latest.range}`));
            const nums = g.readings.map((r) => r.number).filter((n) => n != null);
            if (nums.length > 1) c.append(sparkline(nums));
            if (g.change && g.change.direction !== 'same') {
                const pct = g.change.percent != null ? Math.abs(g.change.percent) + '%' : Math.abs(g.change.absolute);
                c.append(
                    el(
                        'span',
                        'lab-change',
                        `${g.change.direction === 'up' ? '▲' : '▼'} ${pct} since ${shortDate(g.change.since)}`
                    )
                );
            }
            grid.append(c);
        }
        return grid;
    };
    const PILL = 'M10.5 20.5a5 5 0 0 1-7-7l7-7a5 5 0 0 1 7 7l-7 7ZM8.5 8.5l7 7';
    const sectionHead = (title, count, tone) => {
        const h = el('h3', `band ${tone || ''}`, title);
        if (count != null) h.append(el('span', 'count', String(count)));
        return h;
    };
    const medCard = (m) => {
        const c = el('button', 'medcard');
        c.type = 'button';
        const icon = svgEl('svg', { viewBox: '0 0 24 24', class: 'medicon', 'aria-hidden': 'true' });
        icon.append(svgEl('path', { d: PILL }));
        const text = el('span', 'medtext');
        text.append(el('b', '', m.name), el('span', '', [m.dose, m.duration].filter(Boolean).join(' · ')));
        c.append(icon, text);
        if (m.date) c.append(el('span', 'stat-sub', shortDate(m.date)));
        c.addEventListener('click', () => openDoc(m.id));
        return c;
    };

    async function health(sub) {
        host().replaceChildren(el('div', 'empty', 'Loading…'));
        if (sub === 'documents') {
            const data = await getJson('/api/medical/documents');
            const tiles = data.documents.map((d) => ({
                kind: 'medical',
                node: docTile(
                    d.title,
                    [d.date, d.values && `${d.values} values`, d.medicines && `${d.medicines} medicines`],
                    d.follow_up ? 'follow-up' : '',
                    () => openDoc(d.id)
                ),
            }));
            const page = documentsPlace(
                appTabs('health', 'health-docs'),
                'Health documents',
                tiles,
                'No health documents yet. Press Read new files.'
            );
            return host().replaceChildren(...page);
        }
        // the dashboard: one summary card, then what needs a look, the tests, the medicines
        const [values, meds, coming, docs] = await Promise.all([
            getJson('/api/medical/values'),
            getJson('/api/medical/medicines'),
            getJson('/api/medical/followups'),
            getJson('/api/medical/documents'),
        ]);
        const nextUp = (coming.follow_ups || [])[0];
        const out = values.attention.length;
        const total = values.tests.length;
        const latest = values.tests
            .map((g) => g.latest.date)
            .sort()
            .pop();
        const hero = el('div', `hero healthhero ${out ? 'warn' : 'good'}`);
        const summary = el('div', 'hero-text');
        summary.append(
            el('span', 'stat-label', 'Health summary'),
            el('b', 'hero-place', !total ? 'No values yet' : out ? `${out} to look at` : 'All within range'),
            el(
                'span',
                'stat-sub',
                [
                    `${total} tests`,
                    `${meds.medicines.length} medicines`,
                    `${docs.documents.length} reports`,
                    latest && `latest ${shortDate(latest)}`,
                ]
                    .filter(Boolean)
                    .join(' · ')
            )
        );
        hero.append(ring(total - out, out, total ? `${total - out}/${total}` : ''), summary);
        if (nextUp) {
            const next = el('button', 'hero-next');
            next.type = 'button';
            next.addEventListener('click', () => openDoc(nextUp.id));
            next.append(
                el('span', 'stat-label', 'Next check'),
                el('b', '', shortDate(nextUp.date)),
                el('span', 'stat-sub', `${nextUp.title} · ${when(days(nextUp.date))}`)
            );
            hero.append(next);
        }
        const page = [appTabs('health', 'health'), hero];
        const ordered = [
            ...values.attention,
            ...values.common.filter((g) => !values.attention.includes(g)),
            ...values.other,
        ];
        const chart = el('div', 'focus-slot');
        const pick = (g) => {
            chart.replaceChildren(focusChart(g));
            chart.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        };
        if (ordered.length) {
            chart.append(focusChart(ordered[0]));
            page.push(chart);
        }
        if (!total)
            page.push(el('div', 'empty', 'Lab values appear here once a report is read. Press Read new files.'));
        const rest = (list) => list.filter((g) => !values.attention.some((a) => a.test === g.test));
        if (out) page.push(sectionHead('Needs a look', out, 'warn'), labGrid(values.attention, pick));
        const others = [...rest(values.common), ...rest(values.other)];
        if (others.length)
            page.push(sectionHead(out ? 'In range or without a range' : 'Tests', others.length), labGrid(others, pick));
        if (meds.medicines.length) {
            const grid = el('div', 'medgrid');
            grid.append(...meds.medicines.map(medCard));
            page.push(sectionHead('Medicines', meds.medicines.length), grid);
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
