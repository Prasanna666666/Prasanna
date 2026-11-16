/* Atlas front end. Plain JavaScript. All text from the apps is added with textContent, never as markup. */
(() => {
    'use strict';
    const $ = (selector) => document.querySelector(selector);
    const SVG = 'http://www.w3.org/2000/svg';
    const el = (tag, cls, text) => {
        const node = document.createElement(tag);
        if (cls) node.className = cls;
        if (text != null) node.textContent = text;
        return node;
    };
    const icon = (path) => {
        const svg = document.createElementNS(SVG, 'svg');
        const shape = document.createElementNS(SVG, 'path');
        svg.setAttribute('viewBox', '0 0 24 24');
        shape.setAttribute('d', path || 'M4 12h16M12 4v16');
        svg.append(shape);
        return svg;
    };
    const tint = (node, module) => {
        node.style.setProperty('--c1', module.accent[0]);
        node.style.setProperty('--c2', module.accent[1]);
    };
    const ICON = {
        home: 'M4 11l8-7 8 7v8a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1v-8Z',
        search: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14ZM21 21l-4.3-4.3',
        chat: 'M20 12a8 8 0 0 1-11.6 7.1L4 20l1-4.2A8 8 0 1 1 20 12Z',
        dark: 'M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z',
        light: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4',
        auto: 'M12 3a9 9 0 1 0 0 18V3Z',
        plus: 'M12 5v14M5 12h14',
        refresh: 'M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5',
    };

    const state = { modules: [], health: {}, ai: null, frames: new Map(), mode: 'light' };
    const byId = (id) => state.modules.find((m) => m.id === id);
    const origin = (module) => `${location.protocol}//${module.id}.${location.host}`;

    // ---------------------------------------------------------------- the address: #/  or  #/<module>  or  #/<module>/<page>?<query>
    const parse = () => {
        const [first, ...rest] = location.hash.replace(/^#\/?/, '').split('/');
        const module = byId(first);
        return module ? { module, route: rest.join('/') } : { module: null, route: '' };
    };
    const defaultRoute = (module) =>
        (module.home || (module.pages[0] ? '#/' + module.pages[0].id : '#/')).replace(/^#\/?/, '');
    const address = (module, route) => '#/' + module.id + (route ? '/' + route : '');
    const go = (module, route) => {
        location.hash = module ? address(module, route == null ? '' : route) : '#/';
    };

    // ---------------------------------------------------------------- talking to an app's page
    const tell = (module, message) => {
        const frame = state.frames.get(module.id);
        if (frame && frame.contentWindow) frame.contentWindow.postMessage({ atlas: 1, ...message }, origin(module));
    };
    const broadcastTheme = () => state.modules.forEach((m) => tell(m, { type: 'theme', mode: state.mode }));
    window.addEventListener('message', (event) => {
        const module = state.modules.find((m) => event.origin === origin(m));
        const data = event.data;
        if (!module || !data || data.atlas !== 1) return;
        if (data.type === 'ready') tell(module, { type: 'theme', mode: state.mode });
        else if (data.type === 'palette') openPalette();
        else if (data.type === 'ask' && typeof data.text === 'string') askAtlas(data.text);
        else if (data.type === 'toggle-chat') toggleChat();
        else if (data.type === 'route' && typeof data.hash === 'string') followApp(module, data.hash);
    });
    const followApp = (module, hash) => {
        const now = parse();
        if (now.module !== module) return;
        const route = hash.replace(/^#\/?/, '');
        history.replaceState(null, '', address(module, route));
        markActive();
    };

    // ---------------------------------------------------------------- the frame for each app (kept alive so switching is instant)
    const frameFor = (module, route) => {
        let frame = state.frames.get(module.id);
        const wanted = '#/' + (route || defaultRoute(module));
        if (!frame) {
            frame = el('iframe');
            frame.title = module.name;
            frame.src = origin(module) + '/' + wanted;
            frame.addEventListener('load', () => tell(module, { type: 'theme', mode: state.mode }));
            state.frames.set(module.id, frame);
            $('#stage').append(frame);
        } else {
            tell(module, { type: 'navigate', hash: wanted });
        }
        return frame;
    };

    // ---------------------------------------------------------------- the menu
    const statusClass = (module) => (state.health[module.id] ? (state.health[module.id].up ? 'up' : 'down') : '');
    const renderNav = () => {
        const nav = $('#nav');
        const home = el('a', 'item');
        home.href = '#/';
        home.dataset.key = '';
        home.append(icon(ICON.home), el('span', '', 'Overview'));
        nav.replaceChildren(home);
        for (const module of state.modules.filter((m) => !m.hidden)) {
            const group = el('div', 'group');
            group.dataset.module = module.id;
            tint(group, module);
            const head = el('a', 'item');
            head.href = address(module, '');
            head.dataset.key = module.id;
            head.append(icon(module.icon), el('span', '', module.name), el('i', 'dot ' + statusClass(module)));
            const pages = el('div', 'pages');
            for (const page of module.pages) {
                const link = el('a', 'item');
                link.href = address(module, page.id);
                link.dataset.key = module.id + '/' + page.id;
                link.append(icon(page.icon), el('span', '', page.label));
                pages.append(link);
            }
            group.append(head, pages);
            nav.append(group);
        }
        markActive();
    };
    const markActive = () => {
        const { module, route } = parse();
        const page = route.split('?')[0] || (module ? defaultRoute(module).split('?')[0] : '');
        document.querySelectorAll('#nav .item').forEach((a) => {
            const key = a.dataset.key;
            a.classList.toggle(
                'active',
                module ? key === module.id + '/' + page || (key === module.id && !module.pages.length) : key === ''
            );
        });
        document
            .querySelectorAll('#nav .group')
            .forEach((g) => g.classList.toggle('open', Boolean(module) && g.dataset.module === module.id));
        document.title = module ? `${module.name} · Atlas` : 'Atlas';
        document.documentElement.style.setProperty('--a1', module ? module.accent[0] : '#6366f1');
        document.documentElement.style.setProperty('--a2', module ? module.accent[1] : '#ec4899');
    };

    // ---------------------------------------------------------------- the stage: the overview, or one app
    // ---------------------------------------------------------------- the calendar: Atlas draws it itself, from what every app knows, joined
    const EVENT_LABEL = { trip: 'Trip', due: 'Due', followup: 'Check-up', ends: 'Ends' };
    const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const isoDay = (d) =>
        `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    const whenDays = (n) =>
        n === 0 ? 'today' : n > 0 ? `in ${n} day${n === 1 ? '' : 's'}` : `${-n} day${n === -1 ? '' : 's'} ago`;

    // one event: where it opens (the document it came from), and what state it is in
    const openEvent = (e) => {
        const documents = state.modules.find((m) => m.id === 'documents');
        if (e.doc && documents) location.href = address(documents, `doc/${e.doc}`);
    };

    const agendaRow = (e) => {
        const row = el('button', `agenda-row ${e.type}`);
        row.type = 'button';
        const date = el('span', 'agenda-date');
        date.append(el('b', '', String(+e.date.slice(8, 10))), el('small', '', MONTH_NAMES[+e.date.slice(5, 7) - 1]));
        const text = el('span', 'agenda-text');
        const sub = [EVENT_LABEL[e.type], e.subtitle, e.sources > 1 ? `${e.sources} sources` : '']
            .filter(Boolean)
            .join(' · ');
        text.append(el('b', '', e.title), el('span', '', sub));
        row.append(date, text, el('em', `agenda-when ${e.state === 'overdue' ? 'late' : ''}`, whenDays(e.days)));
        row.addEventListener('click', () => openEvent(e));
        return row;
    };

    const monthGrid = (year, month, events) => {
        const grid = el('div', 'monthgrid');
        for (const name of ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']) grid.append(el('span', 'mg-head', name));
        for (let i = 0; i < (new Date(year, month, 1).getDay() + 6) % 7; i++) grid.append(el('span', 'mg-empty'));
        const today = isoDay(new Date());
        for (let day = 1; day <= new Date(year, month + 1, 0).getDate(); day++) {
            const key = isoDay(new Date(year, month, day));
            const cell = el('div', 'mg-day' + (key === today ? ' today' : ''));
            cell.append(el('b', '', String(day)));
            for (const e of events.filter((x) => x.date <= key && key <= x.end).slice(0, 3)) {
                const chip = el('button', `mg-chip ${e.type}`, e.title);
                chip.type = 'button';
                chip.title = `${EVENT_LABEL[e.type]}: ${e.title}`;
                chip.addEventListener('click', () => openEvent(e));
                cell.append(chip);
            }
            grid.append(cell);
        }
        return grid;
    };

    const renderCalendar = () => {
        const wrap = el('div', 'dash calendar');
        const body = el('div');
        wrap.append(el('h1', '', 'Calendar'), body);
        const draw = (joined, shown) => {
            const [year, month] = [shown.getFullYear(), shown.getMonth()];
            const bar = el('div', 'monthbar');
            const step = (n) => draw(joined, new Date(year, month + n, 1));
            const prev = el('button', 'pill', '‹'),
                next = el('button', 'pill', '›');
            prev.addEventListener('click', () => step(-1));
            next.addEventListener('click', () => step(1));
            bar.append(
                prev,
                el('b', '', shown.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })),
                next
            );
            const soon = joined.events.filter((e) => e.days <= 60);
            const list = el('div', 'agenda');
            list.append(...soon.map(agendaRow));
            const out = joined.left_out || {};
            const notes = [
                out.incomplete
                    ? `${out.incomplete} dated documents are not shown: who they are from or what they are for is not clear yet.`
                    : '',
                out.settled || out.done || out.renewed
                    ? `Left out because already dealt with: ${out.settled || 0} settled bills, ${out.done || 0} follow-ups done, ${out.renewed || 0} renewed.`
                    : '',
            ].filter(Boolean);
            body.replaceChildren(
                bar,
                monthGrid(year, month, joined.events),
                el('h3', 'band', 'Coming up'),
                soon.length
                    ? list
                    : el('div', 'empty', 'Nothing dated yet. Dates appear here once your documents are read.'),
                ...notes.map((n) => el('p', 'note', n))
            );
        };
        fetch('/_atlas/api/agenda')
            .then((r) => r.json())
            .then((joined) => draw(joined, new Date()))
            .catch(() => body.append(el('div', 'empty', 'The calendar could not be loaded.')));
        return wrap;
    };

    // ---------------------------------------------------------------- the home page: the few things that matter in each part of your life
    const HOME_ORDER = ['calendar', 'documents', 'finance', 'health', 'travel', 'photos'];
    const mediaUrl = (id) => `/_atlas/api/media/documents/api/pictures/thumb/${id}`;

    // the rows of a card: a small label and its value, coloured by what kind of thing it is
    const cardRows = (items) => {
        const list = el('div', 'hc-rows');
        for (const item of items) {
            const row = el('div', 'hc-row ' + (item.kind || ''));
            row.append(el('i'), el('span', '', item.label), el('b', '', item.value));
            list.append(row);
        }
        return list;
    };

    // one card of the home page: the app, its main figure, a few rows, and pictures when it has them
    const homeCard = (module, card) => {
        const node = el('a', `hc hc-${module.id} ${card.tone || ''}`);
        node.href = card.link ? address(module, card.link.replace(/^#\/?/, '')) : address(module, '');
        tint(node, module);
        const top = el('div', 'hc-top');
        top.append(icon(module.icon), el('span', '', module.name));
        node.append(top);
        if (card.images.length && module.id === 'travel') {
            node.style.setProperty('--cover', `url("${mediaUrl(card.images[0])}")`);
            node.classList.add('has-cover');
        }
        const headline = el('b', 'hc-head', card.headline);
        if (card.figure != null && module.id === 'travel') headline.dataset.figure = String(card.figure);
        node.append(headline);
        if (card.sub) node.append(el('span', 'hc-sub', card.sub));
        if (card.note) node.append(el('span', 'hc-note', card.note));
        if (card.items.length) node.append(cardRows(card.items));
        if (card.images.length && module.id !== 'travel') {
            const strip = el('div', 'hc-strip');
            for (const id of card.images) {
                const img = new Image();
                img.alt = '';
                img.loading = 'lazy';
                img.src = mediaUrl(id);
                strip.append(img);
            }
            node.append(strip);
        }
        return node;
    };

    // which version of the code each part is running: a part that was not updated shows up here
    const versionLine = (builds) => {
        const values = Object.values(builds);
        const line = el('p', 'versions' + (new Set(values).size > 1 ? ' differ' : ''));
        line.textContent =
            'Version ' +
            Object.entries(builds)
                .map(([name, build]) => `${name} ${build}`)
                .join(' · ');
        return line;
    };

    const renderDashboard = () => {
        const wrap = el('div', 'dash');
        const hour = new Date().getHours();
        wrap.append(
            el('h1', '', hour < 12 ? 'Good morning.' : hour < 18 ? 'Good afternoon.' : 'Good evening.'),
            el(
                'div',
                'sub',
                new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })
            ),
            scan.panel // the reading of the files is part of this page, under its heading
        );
        // things to ask: Atlas prepares, you confirm; nothing is changed by asking
        const asks = el('div', 'asks');
        for (const text of [
            'What is due this month?',
            'Which results are out of range?',
            'File my invoices',
            'What did I spend most on?',
        ]) {
            const chip = el('button', 'ask-chip', text);
            chip.type = 'button';
            chip.addEventListener('click', () => askAtlas(text));
            asks.append(chip);
        }
        const board = el('div', 'board');
        wrap.append(asks, board);
        fetch('/_atlas/api/home')
            .then((r) => r.text())
            .then((raw) => {
                state.homeSig = raw;
                const { cards, builds } = JSON.parse(raw);
                const shown = HOME_ORDER.filter((id) => cards[id]).map((id) => state.modules.find((m) => m.id === id));
                board.replaceChildren(...shown.filter(Boolean).map((m) => homeCard(m, cards[m.id])));
                if (!shown.length) board.append(el('div', 'empty', 'Nothing to show yet. Press Read new files.'));
                wrap.append(versionLine(builds || {}));
            })
            .catch(() => board.append(el('div', 'empty', 'The home page could not be loaded.')));
        return wrap;
    };
    const render = () => {
        const stage = $('#stage');
        const { module, route } = parse();
        scan.park.append(scan.panel); // out of the page being replaced: it goes back into the new overview below
        stage.querySelector('.dash')?.remove();
        state.frames.forEach((frame, id) => {
            frame.hidden = !module || module.id !== id || module.native;
        });
        if (module && module.native) stage.prepend(renderCalendar());
        else if (module) frameFor(module, route);
        else stage.prepend(renderDashboard());
        markActive();
        if (scan.last) {
            scan.sig = ''; // the card appears on the overview and is gone on every other page
            showScan(scan.last);
        }
    };

    // ---------------------------------------------------------------- chips and health
    const aiChip = () => {
        if (!state.ai || !state.ai.configured) return null;
        const model = state.ai.models.find((m) => m.startsWith('ministral')) || state.ai.models[0] || '';
        const chip = el(
            'span',
            'chip ' + (state.ai.up ? 'up' : 'down'),
            state.ai.up ? `AI · ${model}` : 'AI model not running'
        );
        chip.prepend(el('i'));
        chip.title = state.ai.up
            ? 'One local model, shared by every app'
            : 'Start Ollama: every app that reads or explains needs it';
        return chip;
    };
    const renderChips = () => {
        const chips = [
            aiChip(),
            ...state.modules
                .filter((m) => !m.hidden)
                .map((module) => {
                    const chip = el('span', 'chip ' + statusClass(module), module.name);
                    chip.prepend(el('i'));
                    return chip;
                }),
        ].filter(Boolean);
        const box = $('#chips');
        const html = chips.map((c) => c.outerHTML).join('');
        if (box.dataset.html === html) return; // nothing changed: nothing is redrawn
        box.dataset.html = html;
        box.replaceChildren(...chips);
    };
    const refreshHealth = async () => {
        try {
            state.health = await (await fetch('/_atlas/api/health')).json();
            state.ai = await (await fetch('/_atlas/api/ai')).json();
        } catch (_) {
            state.health = {};
        }
        renderChips();
        document.querySelectorAll('#nav .group .dot').forEach((dot) => {
            const module = byId(dot.closest('.group').dataset.module);
            const next = 'dot ' + statusClass(module);
            if (dot.className !== next) dot.className = next;
        });
        if (!parse().module) refreshHome();
    };
    // the overview is redrawn only when what it shows has changed (redrawing it every 15 seconds made it flash)
    const refreshHome = async () => {
        try {
            const raw = await (await fetch('/_atlas/api/home')).text();
            if (raw !== state.homeSig) render();
        } catch (_) {
            /* the page stays as it is; the next look tries again */
        }
    };

    // ---------------------------------------------------------------- one search box for everything
    let palette = null;
    /** The pages of every app, narrowed by what was typed. */
    const pageItems = (q) =>
        state.modules.flatMap((m) =>
            [{ id: '', label: m.name }, ...m.pages]
                .filter((p) => !q || `${m.name} ${p.label}`.toLowerCase().includes(q))
                .map((p) => ({
                    module: m,
                    label: p.id ? `${m.name} · ${p.label}` : m.name,
                    sub: 'Go to',
                    run: () => go(m, p.id),
                }))
        );

    /** What the search list can do, when what is typed asks for it. */
    const actions = (q) =>
        !q || 'update scan read new files photos'.includes(q) || q.includes('update') || q.includes('scan')
            ? [{ head: 'Do' }, { label: 'Read new files', sub: 'Read all new files, mail and photos', run: startScan }]
            : [];

    /** The rows of the search list: actions first, then pages, what was found, and the question put to the chat. */
    function searchRows(acts, pages, found, asks) {
        return [
            ...acts,
            ...(pages.length ? [{ head: 'Pages' }, ...pages.slice(0, 5)] : []),
            ...(found.length
                ? [
                      { head: 'Found' },
                      ...found.map((r) => ({
                          module: byId(r.module),
                          label: r.title,
                          sub: [byId(r.module)?.name, r.subtitle].filter(Boolean).join(' · '),
                          run: () => go(byId(r.module), r.link.replace(/^#\/?/, '')),
                      })),
                  ]
                : []),
            { head: 'Ask' },
            ...asks,
        ];
    }

    function openPalette() {
        if (palette) return;
        const box = el('input');
        box.placeholder = 'Search every app, jump to a page, or ask…';
        box.autocomplete = 'off';
        box.spellcheck = false;
        box.setAttribute('aria-label', 'Search everything');
        const list = el('div', 'plist');
        let items = [];
        let active = 0;
        let seq = 0;
        const close = () => {
            overlay.remove();
            document.removeEventListener('keydown', onKey, true);
            palette = null;
        };
        const run = (item) => {
            close();
            item.run();
        };
        const mark = () =>
            list.querySelectorAll('.pitem').forEach((b) => b.classList.toggle('on', Number(b.dataset.i) === active));
        const paint = () => {
            list.replaceChildren(
                ...(items.length
                    ? items.map((item, i) => {
                          if (item.head) return el('div', 'phead', item.head);
                          const row = el('button', 'pitem' + (i === active ? ' on' : ''));
                          row.type = 'button';
                          row.dataset.i = i;
                          const dot = el('span', 'dotc');
                          tint(row, item.module || { accent: ['#6366f1', '#ec4899'] });
                          const text = el('span', 'grow');
                          text.append(el('div', 'strong', item.label));
                          if (item.sub) text.append(el('div', 'small', item.sub));
                          row.append(dot, text);
                          row.addEventListener('click', () => run(item));
                          row.addEventListener('mouseenter', () => {
                              active = i;
                              mark();
                          });
                          return row;
                      })
                    : [el('div', 'empty', 'No results')])
            );
            list.querySelector('.on')?.scrollIntoView({ block: 'nearest' });
        };
        const firstReal = () => {
            active = Math.max(
                0,
                items.findIndex((x) => !x.head)
            );
        };
        const build = async () => {
            const raw = box.value.trim();
            const q = raw.toLowerCase();
            const mine = ++seq;
            const pages = pageItems(q);
            if (q.length < 2) {
                items = [...actions(q), { head: 'Jump to' }, ...pages.slice(0, 12)];
                firstReal();
                paint();
                return;
            }
            let found = [];
            try {
                found = (await (await fetch('/_atlas/api/search?q=' + encodeURIComponent(raw))).json()).results || [];
            } catch (_) {
                found = [];
            }
            if (mine !== seq) return;
            const asks = [{ label: `Ask Atlas: “${raw}”`, sub: 'Chat', run: () => askAtlas(raw) }];
            items = searchRows(actions(q), pages, found, asks);
            firstReal();
            paint();
        };
        let timer;
        box.addEventListener('input', () => {
            clearTimeout(timer);
            timer = setTimeout(build, 140);
        });
        const move = (d) => {
            const real = items.map((x, i) => (x.head ? -1 : i)).filter((i) => i >= 0);
            if (!real.length) return;
            active = real[(real.indexOf(active) + d + real.length) % real.length];
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
        const bar = el('div', 'pbar');
        bar.append(icon(ICON.search), box, el('kbd', '', 'esc'));
        const overlay = el('div', 'overlay');
        const card = el('div', 'palette');
        card.append(bar, list);
        overlay.append(card);
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) close();
        });
        document.body.append(overlay);
        document.addEventListener('keydown', onKey, true);
        palette = overlay;
        items = [...actions(''), { head: 'Jump to' }, ...pageItems('').slice(0, 12)];
        firstReal();
        paint();
        box.focus();
    }

    // ---------------------------------------------------------------- one Update button: read everything new, in every app that can
    const scan = {
        timer: null,
        hide: null,
        panel: document.getElementById('scan'),
        park: document.getElementById('scan').parentNode,
    };
    // ---- the reading card: one overall bar, one row per file (done, being read, waiting), and the totals; part of the page, redrawn only where something changed
    // never "100%" before it is all done (99.8 reads 99%), and never "0%" shown as a guess
    const pctText = (p, estimated) => {
        if (p == null) return '';
        if (p === 0) return '0%';
        const shown = p >= 100 ? '100' : p < 10 ? p.toFixed(1) : String(Math.min(99, Math.floor(p)));
        return (estimated ? '~' : '') + shown + '%';
    };
    const meter = (percent) => {
        const track = el('div', 'rd-meter' + (percent == null ? ' unknown' : ''));
        const fill = el('div', 'rd-fill');
        if (percent != null) fill.style.width = percent + '%';
        track.append(fill);
        return track;
    };
    // the one file being worked on, with how long it has been on it
    const nowBlock = (info) => {
        if (!info.file) return null;
        const row = el('div', 'rd-nowrow');
        const text = el('div', 'rd-nowtext');
        text.append(
            el('b', 'rd-name', info.file.name),
            el('span', 'rd-detail', `${info.file.step} · ${info.file.seconds} s`)
        );
        row.append(el('i', 'rd-dot'), text);
        if (info.file.percent != null) {
            const side = el('div', 'rd-nowside');
            side.append(
                meter(info.file.percent),
                el('span', 'rd-pct', pctText(info.file.percent, info.file.estimated))
            );
            row.append(side);
        }
        return row;
    };
    // files the model could not make sense of: named, with the reason
    const failedBlock = (info) => {
        const failed = (info.recent || []).filter((f) => f.state === 'failed').slice(0, 3);
        if (!failed.length) return null;
        const box = el('div', 'rd-failed');
        for (const f of failed) {
            const row = el('div', 'rd-nowrow');
            const text = el('div', 'rd-nowtext');
            text.append(el('b', 'rd-name', f.name), el('span', 'rd-detail', f.detail));
            row.append(el('i', 'rd-dot'), text);
            box.append(row);
        }
        return box;
    };
    // the steps of a read: which one is running, and how far each has got
    const currentStep = (steps) =>
        steps.find((s) => s.state === 'running' && s.n > 1) ||
        steps.find((s) => s.state === 'running') ||
        steps.find((s) => s.state === 'waiting');
    const countText = (c) =>
        !c.known ? 'counting…' : c.total ? `${c.done.toLocaleString()} of ${c.total.toLocaleString()}` : 'none found';
    // a step: its name, what it does, how far it is, and its three counts (documents, mails, documents in mails), all alike
    const stepCard = (s, now) => {
        const card = el('div', 'rd-step ' + s.state + (now && now.n === s.n ? ' current' : ''));
        card.title = s.about || '';
        const head = el('div', 'rd-stepname');
        head.append(
            el('i', 'rd-stepmark', s.state === 'done' ? '' : String(s.n)),
            el('b', '', s.name),
            el('span', 'rd-pct', pctText(s.percent))
        );
        card.append(head, meter(s.percent));
        const counts = el('div', 'rd-counts');
        for (const c of s.counts || []) {
            const line = el('div', 'rd-count');
            line.append(el('span', '', c.label), el('b', '', countText(c)));
            counts.append(line);
            if (c.note) counts.append(el('div', 'rd-countnote', c.note));
        }
        if (counts.children.length) card.append(counts);
        return card;
    };
    const stepsBlock = (steps) => {
        if (!steps || !steps.length) return null;
        const now = currentStep(steps);
        const grid = el('div', 'rd-stepgrid');
        grid.append(...steps.map((s) => stepCard(s, now)));
        return grid;
    };
    const noteBlock = (text, bad = false) => el('div', 'rd-note' + (bad ? ' bad' : ''), text);
    // Pause, Resume and Stop: the button only says which action it stands for (as data), so a button that stays in place when its label changes from Pause to Resume
    // does what its label says; one handler on the card does the work
    const controlButton = (label, action) => {
        const b = el('button', 'rd-btn' + (action === 'stop' ? ' stop' : ''), label);
        b.type = 'button';
        b.dataset.action = action;
        return b;
    };
    const pressControl = async (e) => {
        const b = e.target.closest('.rd-btn');
        if (!b || b.disabled) return;
        b.disabled = true;
        try {
            const reply = await fetch(`/_atlas/api/scan/${b.dataset.action}`, {
                method: 'POST',
                headers: { 'X-Atlas': '1' },
            });
            if (reply.ok) {
                showScan(await reply.json());
                followScan(); // keeps showing where it stands until it has really stopped, paused or finished
            }
        } catch (_) {
            /* the next refresh shows where it stands */
        } finally {
            b.disabled = false; // pressable again: the same button is now Resume, or still Pause if nothing changed
        }
    };
    const topRow = (title, running, paused, panel) => {
        const top = el('div', 'rd-top');
        const words = el('div', 'rd-words');
        words.append(el('b', 'rd-title', title));
        const buttons = el('div', 'rd-actions');
        if (running) {
            buttons.append(
                controlButton(paused ? 'Resume' : 'Pause', paused ? 'resume' : 'pause'),
                controlButton('Stop', 'stop')
            );
        }
        const close = el('button', 'rd-x', '×');
        close.type = 'button';
        close.setAttribute('aria-label', 'Close');
        close.addEventListener('click', () => {
            panel.hidden = true;
        });
        buttons.append(close);
        top.append(words, buttons);
        return top;
    };
    const scanTitle = (report, readerOff, running) => {
        if (readerOff) return 'Reading is switched off';
        if (!running) return 'Finished reading';
        const some = (key) => Object.values(report.modules).some((m) => m[key]);
        return some('paused') ? 'Paused' : some('stopping') ? 'Stopping…' : 'Reading your files, mail and photos';
    };
    // only the rows whose content changed are replaced: the buttons stay under the cursor and the scroll position stays (a full rebuild each second broke both)
    const syncAttributes = (old, node) => {
        // the style goes through the style object: the page's security policy refuses a style written as an attribute, so the bar would keep the width it was first drawn with
        if (old.style.cssText !== node.style.cssText) old.style.cssText = node.style.cssText;
        for (const { name, value } of [...node.attributes]) {
            if (name !== 'style' && old.getAttribute(name) !== value) old.setAttribute(name, value); // a button's action follows its label
        }
        for (const { name } of [...old.attributes]) {
            if (!node.hasAttribute(name) && name !== 'disabled' && name !== 'style') old.removeAttribute(name);
        }
    };
    const patchNode = (old, node) => {
        const same =
            old.nodeName === node.nodeName &&
            old.className === node.className &&
            old.children.length === node.children.length;
        if (!same) return old.replaceWith(node);
        syncAttributes(old, node);
        if (!node.children.length) {
            if (old.textContent !== node.textContent) old.textContent = node.textContent;
            return undefined;
        }
        [...node.children].forEach((child, i) => patchNode(old.children[i], child));
        return undefined;
    };
    const patchChildren = (parent, nodes) => {
        nodes.forEach((node, i) => {
            const old = parent.children[i];
            if (!old) parent.append(node);
            else patchNode(old, node);
        });
        while (parent.children.length > nodes.length) parent.lastElementChild.remove();
    };
    // the card is rebuilt only when what it says has changed
    const scanUnchanged = (report, panel) => {
        const sig = JSON.stringify(report);
        const missing = Object.values(report.modules || {}).some((r) => r && r.up === false);
        const same = !missing && sig === scan.sig && !panel.hidden;
        scan.sig = sig;
        return same;
    };
    // what the person wants to know while it reads: which step, how far, how long, and what is being worked on right now
    const headlineBlock = (info, running) => {
        const box = el('div', 'rd-headline');
        if (!running) {
            if (info.summary) box.append(el('span', 'rd-summary', info.summary));
            return box.children.length ? box : null;
        }
        const steps = info.steps || [];
        const now = currentStep(steps);
        if (!now) return null;
        const where = `Step ${now.n} of ${steps.length} · ${now.doing || now.name}`;
        box.append(el('b', 'rd-doing', where));
        const bar = el('div', 'rd-big');
        bar.append(meter(now.percent), el('span', 'rd-bigpct', pctText(now.percent)));
        box.append(bar);
        return box;
    };
    const problemBlocks = (report) =>
        state.modules.flatMap((m) => (report.modules[m.id] || {}).problems || []).map((p) => noteBlock(p, true));
    const showScan = (report) => {
        const panel = scan.panel;
        scan.last = report;
        if (scanUnchanged(report, panel)) return;
        // the part of Atlas that reads the files (hidden from the menu) decides what the card says: when it is switched off there is nothing to pause or stop
        const reader = state.modules.filter((m) => m.hidden && report.modules[m.id]).map((m) => report.modules[m.id]);
        // one missed answer is not "switched off": it must stay missing for two looks in a row (a few seconds)
        scan.misses = reader.some((r) => r.up === false) ? (scan.misses || 0) + 1 : 0;
        const readerOff = scan.misses >= 2;
        const running = !readerOff && report.running;
        const info = reader.find((r) => r.up) || reader[0] || {};
        const paused = Object.values(report.modules).some((m) => m.paused);
        const blocks = [topRow(scanTitle(report, readerOff, running), running, paused, panel)];
        if (readerOff) {
            blocks.push(
                noteBlock(
                    'The part of Atlas that reads your files is not answering. It may still be starting (up to 30 seconds after ./up.sh) or it has stopped: run ./up.sh again, or open the Atlas app. Nothing is lost.',
                    true
                )
            );
        } else {
            blocks.push(headlineBlock(info, running));
            if (running) blocks.push(stepsBlock(info.steps), nowBlock(info), failedBlock(info));
            blocks.push(...problemBlocks(report));
        }
        patchChildren(panel, blocks.filter(Boolean));
        panel.hidden = !!parse().module; // the reading card belongs to the overview: every other page is its app's own, with nothing of the read above it
        $('#update').classList.toggle('busy', running);
        $('#update span').textContent = running ? 'Reading…' : 'Read new files';
    };
    const followScan = async () => {
        clearTimeout(scan.timer);
        let report;
        try {
            report = await (await fetch('/_atlas/api/scan')).json();
        } catch (_) {
            return;
        }
        showScan(report);
        if (report.running) scan.timer = setTimeout(followScan, 1000);
        else refreshHealth().then(() => parse().module && render()); // the read is finished: a page of an app is drawn again; the overview redraws itself only if its data changed
    };
    const startScan = async () => {
        try {
            const reply = await fetch('/_atlas/api/scan', { method: 'POST', headers: { 'X-Atlas': '1' } });
            if (!reply.ok) return;
            showScan(await reply.json());
            scan.timer = setTimeout(followScan, 1000);
        } catch (_) {
            /* the page keeps working; the button can be pressed again */
        }
    };

    // ---------------------------------------------------------------- the one chat: ask anything; Atlas decides which app answers
    const chat = { conv: crypto.randomUUID ? crypto.randomUUID() : String(Date.now()), history: [], busy: false };
    const IDEAS = [
        'Give me my weekly summary',
        'How much did I spend last month?',
        'Show my photos from the last trip',
        'What is my net worth?',
    ];
    const bold = (parent, text) => {
        text.split(/(\*\*[^*]+\*\*)/).forEach((piece) => {
            if (piece.startsWith('**') && piece.endsWith('**') && piece.length > 4) {
                parent.append(el('strong', '', piece.slice(2, -2)));
            } else if (piece) parent.append(piece);
        });
    };
    // pictures and documents are shown when the user asked to see them; otherwise they stay folded behind one button
    const photoGrid = (module, items) => {
        const grid = el('div', 'part-grid');
        items.forEach((item) => {
            const link = el('a', 'part-tile');
            link.href = address(module, item.link.replace(/^#\/?/, ''));
            const img = new Image();
            img.alt = '';
            img.loading = 'lazy';
            img.src = item.thumb;
            link.append(img);
            grid.append(link);
        });
        return grid;
    };
    const documentList = (module, items) => {
        const list = el('div', 'part-docs');
        items.forEach((item) => {
            const row = el('a', 'part-doc');
            row.href = address(module, item.link.replace(/^#\/?/, ''));
            row.append(el('b', '', item.title), el('span', '', item.subtitle));
            if (item.text) row.append(el('em', '', item.text));
            list.append(row);
        });
        return list;
    };
    const foldable = (label, open, build) => {
        const wrap = el('div', 'part-fold');
        const show = () => wrap.replaceChildren(build());
        if (open) {
            show();
        } else {
            const button = el('button', 'part-show', label);
            button.type = 'button';
            button.addEventListener('click', show);
            wrap.append(button);
        }
        return wrap;
    };
    // a change waiting for you: one card that opens that part's confirmation window (nothing is changed until you press Confirm there)
    const confirmCard = (module, item) => {
        const card = el('div', 'part-confirm');
        const text = el('div');
        text.append(el('b', '', item.title), el('span', '', item.subtitle));
        const open = el('a', 'part-review', 'Review and confirm');
        open.href = address(module, item.link.replace(/^#\/?/, ''));
        card.append(text, open);
        return card;
    };
    // the pictures and files an answer brought, each shown through the part it came from
    const appendAnswerItems = (box, part) => {
        const modules = [...new Set((part.items || []).map((i) => i.module))];
        modules.forEach((id) => {
            const module = byId(id);
            if (!module) return;
            const own = (part.items || []).filter((i) => i.module === id);
            own.filter((i) => i.kind === 'confirm').forEach((i) => box.append(confirmCard(module, i)));
            appendItems(box, { ...part, items: own.filter((i) => i.kind !== 'confirm'), total: 0 }, module);
        });
    };
    const appendItems = (box, part, module) => {
        const items = part.items || [];
        const photos = items.filter((i) => i.kind === 'photo');
        const documents = items.filter((i) => i.kind === 'document');
        const wanted = part.show || {};
        if (photos.length) {
            const of = part.total > photos.length ? ` of ${part.total.toLocaleString()}` : '';
            box.append(foldable(`Show ${photos.length}${of} photos`, wanted.photos, () => photoGrid(module, photos)));
            if (wanted.photos && part.total > photos.length) {
                box.append(
                    el('div', 'part-note', `${part.total.toLocaleString()} in all: open ${module.name} to see them all`)
                );
            }
        }
        if (documents.length) {
            box.append(
                foldable(
                    `Show ${documents.length} document${documents.length === 1 ? '' : 's'}`,
                    wanted.documents,
                    () => documentList(module, documents)
                )
            );
        }
    };
    const partNode = (part) => {
        const module = byId(part.module);
        const box = el('div', 'part');
        tint(box, module || { accent: ['#6366f1', '#ec4899'] });
        const tag = el('span', 'part-tag', part.name);
        tag.prepend(el('i'));
        box.append(tag);
        if (!part.ok) {
            box.append(el('p', 'part-error', part.error));
            return box;
        }
        const body = el('div', 'part-text');
        part.text.split(/\n{2,}/).forEach((paragraph) => {
            const p = el('p');
            bold(p, paragraph);
            body.append(p);
        });
        box.append(body);
        appendAnswerItems(box, part);
        (part.notes || []).forEach((note) => box.append(el('div', 'part-note', note)));
        return box;
    };
    const chatWelcome = () => {
        const wrap = el('div', 'achat-welcome');
        wrap.append(
            el('h2', '', 'Ask me anything'),
            el('p', '', 'Ask about your money, files, mail and pictures, together or one at a time.')
        );
        IDEAS.forEach((idea) => {
            const chip = el('button', 'achat-idea', idea);
            chip.type = 'button';
            chip.addEventListener('click', () => askAtlas(idea));
            wrap.append(chip);
        });
        return wrap;
    };
    const resetChat = () => {
        chat.conv = crypto.randomUUID ? crypto.randomUUID() : String(Date.now());
        chat.history = [];
        $('#achat-thread').replaceChildren(chatWelcome());
    };
    const setChatOpen = (on) => {
        $('#achat').hidden = !on;
        document.body.classList.toggle('chatting', on);
        if (on) {
            if (!$('#achat-thread').children.length) resetChat();
            $('#achat-input').focus();
        }
    };
    const toggleChat = () => setChatOpen($('#achat').hidden);
    const addBubble = (cls, ...kids) => {
        const bubble = el('div', cls);
        bubble.append(...kids);
        const thread = $('#achat-thread');
        thread.append(bubble);
        const scroller = $('#achat-scroll');
        scroller.scrollTop = scroller.scrollHeight;
        return bubble;
    };
    async function askAtlas(text) {
        text = String(text || '').trim();
        if (!text || chat.busy) return;
        setChatOpen(true);
        $('#achat-thread').querySelector('.achat-welcome')?.remove();
        addBubble('am-user', text);
        const waiting = addBubble('am-bot', el('span', 'am-wait', 'Thinking…'));
        chat.busy = true;
        $('#achat-send').disabled = true;
        let parts;
        try {
            const reply = await fetch('/_atlas/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Atlas': '1' },
                body: JSON.stringify({ text, conv: chat.conv, history: chat.history }),
            });
            parts = (await reply.json()).parts || [
                { module: 'atlas', name: 'Atlas', ok: false, error: 'No answer came back.' },
            ];
        } catch (_) {
            parts = [{ module: 'atlas', name: 'Atlas', ok: false, error: 'Atlas could not be reached.' }];
        }
        waiting.replaceChildren(...parts.map(partNode));
        const said = parts
            .filter((p) => p.ok)
            .map((p) => `${p.name}: ${p.text}`)
            .join('\n');
        chat.history = [...chat.history, ['user', text], ['assistant', said || 'No answer.']].slice(-8);
        chat.busy = false;
        $('#achat-send').disabled = false;
        $('#achat-scroll').scrollTop = $('#achat-scroll').scrollHeight;
        $('#achat-input').focus();
    }
    const setupChat = () => {
        const input = $('#achat-input');
        $('#achat-form').addEventListener('submit', (e) => {
            e.preventDefault();
            const text = input.value;
            input.value = '';
            input.style.height = 'auto';
            askAtlas(text);
        });
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
                e.preventDefault();
                $('#achat-form').requestSubmit();
            }
        });
        input.addEventListener('input', () => {
            input.style.height = 'auto';
            input.style.height = Math.min(input.scrollHeight, 140) + 'px';
        });
        $('#achat-new').addEventListener('click', resetChat);
        $('#achat-close').addEventListener('click', () => setChatOpen(false));
    };

    // ---------------------------------------------------------------- theme, keys, the one chat button
    const applyTheme = () => {
        document.documentElement.dataset.theme = state.mode;
        $('#theme').replaceChildren(icon(ICON[state.mode]));
        $('#theme').title = 'Theme: ' + state.mode;
        broadcastTheme();
    };
    const setupTheme = () => {
        try {
            state.mode = localStorage.getItem('atlas.theme') || 'light';
        } catch (_) {
            state.mode = 'light';
        }
        $('#theme').addEventListener('click', () => {
            state.mode = state.mode === 'auto' ? 'dark' : state.mode === 'dark' ? 'light' : 'auto';
            try {
                localStorage.setItem('atlas.theme', state.mode);
            } catch (_) {
                /* private window: the choice just is not remembered */
            }
            applyTheme();
        });
        applyTheme();
    };
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !palette && !$('#achat').hidden) setChatOpen(false);
        const typing = /^(INPUT|TEXTAREA)$/.test(document.activeElement ? document.activeElement.tagName : '');
        if (((e.key === 'k' || e.key === 'K') && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !typing)) {
            e.preventDefault();
            openPalette();
        } else if ((e.key === 'j' || e.key === 'J') && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            toggleChat();
        }
    });
    $('#search-btn').addEventListener('click', openPalette);
    $('#update').addEventListener('click', startScan);
    $('#fab').addEventListener('click', toggleChat);
    setupChat();
    window.addEventListener('hashchange', render);

    // ---------------------------------------------------------------- start
    (async () => {
        setupTheme();
        try {
            state.modules = (await (await fetch('/_atlas/api/modules')).json()).modules;
        } catch (_) {
            state.modules = [];
        }
        renderNav();
        renderChips();
        $('#scan').addEventListener('click', pressControl);
        render();
        refreshHealth();
        setInterval(refreshHealth, 15000);
        // a read that is already running (the page was reloaded, or opened later): bring its panel and its Pause and Stop buttons back
        try {
            const report = await (await fetch('/_atlas/api/scan')).json();
            if (report.running) followScan();
        } catch (_) {
            /* nothing is running, or the apps are down: no panel */
        }
    })();
})();
