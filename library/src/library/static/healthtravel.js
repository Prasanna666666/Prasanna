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
    const post = (path) =>
        fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Library': '1' }, body: '{}' });
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

    // ---------------------------------------------------------------- Travel
    async function travel() {
        host().replaceChildren(el('div', 'empty', 'Loading…'));
        const { trips } = await getJson('/api/travel/trips');
        const page = [head('Travel', trips.length ? `${trips.length} trips` : '')];
        if (trips.length) {
            const cal = el('a', 'pill', 'Add trips to Calendar');
            cal.href = '/api/travel/calendar.ics';
            cal.setAttribute('download', 'trips.ics');
            page.push(cal);
        }
        const tripCard = (t) =>
            card(
                t.place,
                `${range(t.start, t.end)} · ${t.documents ? `${t.documents} documents` : `${t.photos} photos`}${
                    t.source === 'photos' ? ' (from photos)' : ''
                }`,
                () => go('trip', { place: t.place, start: t.start, end: t.end })
            );
        const coming = trips.filter((t) => t.status !== 'past');
        const past = trips.filter((t) => t.status === 'past');
        if (coming.length) page.push(section('Upcoming'), ...coming.map(tripCard));
        if (past.length) page.push(section('Past'), ...past.map(tripCard));
        if (!trips.length)
            page.push(
                el('div', 'empty', 'No trips yet. Tickets and bookings are found when you press Read new files.')
            );
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
        const page = [head(t.place, range(t.start, t.end))];
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
    const lockedView = (r, again) => {
        const unlock = button('Unlock Health', async () => {
            await post('/api/medical/unlock');
            again();
        });
        return [
            head('Health is locked', ''),
            el(
                'p',
                'muted',
                `${r.held_back ? `${r.held_back} documents are held back. ` : ''}They stay out of search and chat until you unlock them, and lock again after 15 minutes unused or whenever Atlas starts.`
            ),
            unlock,
        ];
    };
    const lockButton = (again) =>
        button('Lock Health again', async () => {
            await post('/api/medical/lock');
            again();
        });

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

    async function health(sub) {
        host().replaceChildren(el('div', 'empty', 'Loading…'));
        const again = () => health(sub);
        const state = await getJson('/api/medical');
        if (state.locked) return host().replaceChildren(...lockedView(state, again));
        const data = await getJson(`/api/medical/${sub}`);
        if (data.locked) return host().replaceChildren(...lockedView(data, again));
        const note = el(
            'p',
            'muted',
            'Everything here is copied from your documents exactly as printed. Atlas does not interpret it or give medical advice.'
        );
        if (sub === 'values') {
            const FLAG = {
                above_range: ['Above printed range', 'flag-high'],
                below_range: ['Below printed range', 'flag-low'],
            };
            const page = [head('Lab values', `${data.tests.length} measurements`), lockButton(again)];
            // the summary: anything outside the range printed on the report, or a plain "nothing"
            const summary = el('div', 'healthsummary' + (data.attention.length ? ' attention' : ''));
            summary.append(
                el(
                    'b',
                    '',
                    data.attention.length
                        ? `${data.attention.length} ${data.attention.length === 1 ? 'result is' : 'results are'} outside the printed range`
                        : data.tests.length
                          ? 'Nothing is outside the printed ranges'
                          : 'No values found yet. Press Read new files.'
                )
            );
            data.attention.forEach((g) => {
                const line = el(
                    'span',
                    '',
                    `${g.test}: ${g.latest.value}${g.unit ? ' ' + g.unit : ''} (range ${g.latest.range}) on ${g.latest.date}`
                );
                summary.append(line);
            });
            page.push(summary, el('p', 'muted', data.note));
            const row = (g) => {
                const d = el('details', 'testrow');
                const top = el('summary');
                top.append(el('b', '', g.test), el('span', 'latest', `${g.latest.value}${g.unit ? ' ' + g.unit : ''}`));
                if (FLAG[g.flag]) top.append(el('span', `flagchip ${FLAG[g.flag][1]}`, FLAG[g.flag][0]));
                else if (g.flag === 'in_range') top.append(el('span', 'flagchip flag-ok', 'In printed range'));
                if (g.change && g.change.direction !== 'same') {
                    const sign = g.change.absolute > 0 ? '+' : '';
                    top.append(
                        el(
                            'span',
                            'muted',
                            `${g.change.direction === 'up' ? '▲' : '▼'} ${sign}${g.change.absolute}${
                                g.change.percent != null ? ` (${sign}${g.change.percent}%)` : ''
                            } since ${g.change.since}`
                        )
                    );
                }
                d.append(top);
                const nums = g.readings.map((r) => r.number).filter((n) => n != null);
                if (nums.length > 1) d.append(sparkline(nums));
                const table = el('table', 'tbl');
                for (const r of g.readings) {
                    const tr = el('tr');
                    const doc = el('a', '', r.date || r.document);
                    doc.href = `#/doc/${r.id}`;
                    const first = el('td');
                    first.append(doc);
                    tr.append(first, el('td', '', r.value), el('td', 'muted', r.range ? `range ${r.range}` : ''));
                    table.append(tr);
                }
                d.append(table);
                return d;
            };
            if (data.attention.length) page.push(section('Outside the printed range'), ...data.attention.map(row));
            const rest = (list) =>
                list.filter((g) => !data.attention.includes(g) && !data.attention.some((a) => a.test === g.test));
            if (rest(data.common).length) page.push(section('Common tests'), ...rest(data.common).map(row));
            if (rest(data.other).length) page.push(section('Other measurements'), ...rest(data.other).map(row));
            return host().replaceChildren(...page);
        }
        if (sub === 'medicines') {
            const page = [head('Medicines', `${data.medicines.length} found`), lockButton(again), note];
            if (!data.medicines.length) page.push(el('p', 'muted', 'No medicines found yet.'));
            for (const m of data.medicines)
                page.push(card(m.name, [m.dose, m.duration, m.date].filter(Boolean).join(' · '), () => openDoc(m.id)));
            return host().replaceChildren(...page);
        }
        const coming = await getJson('/api/medical/followups');
        const page = [head('Health', `${data.documents.length} documents`), lockButton(again), note];
        if (coming.follow_ups && coming.follow_ups.length) {
            page.push(section('Coming up (stated in your documents)'));
            coming.follow_ups.forEach((f) => page.push(card(f.date, f.title, () => openDoc(f.id))));
        }
        page.push(section('Timeline'));
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
        host().replaceChildren(...page);
    }

    const PAGES = {
        travel: () => travel(),
        trip: (p) => trip(p),
        health: () => health('timeline'),
        'health-values': () => health('values'),
        'health-medicines': () => health('medicines'),
    };
    window.HealthTravelUI = { show: (path, params) => PAGES[path](params || {}), pages: Object.keys(PAGES) };
    if (PAGES[location.hash.replace(/^#\//, '').split('?')[0]]) window.dispatchEvent(new Event('hashchange'));
})();
