/* Lumo front end. Plain JavaScript, no libraries. All dynamic text is added with textContent (never innerHTML). */
(() => {
    'use strict';
    const token = document.querySelector('meta[name="lumo-token"]').content;
    const $ = (s) => document.querySelector(s);
    const el = (tag, cls, text) => {
        const e = document.createElement(tag);
        if (cls) e.className = cls;
        if (text != null) e.textContent = text;
        return e;
    };
    const SHOW_TRACE = new URLSearchParams(location.search).has('trace'); // the step-by-step panel is for debugging: off unless asked for
    const EMBEDDED = window.self !== window.top;
    const photoUrl = (id, kind) => `/api/photo/${id}/${kind}?t=${encodeURIComponent(token)}`;
    const api = (path, opts = {}) =>
        fetch(path, { ...opts, headers: { 'X-Lumo-Token': token, ...(opts.headers || {}) } });
    const uid = () =>
        crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2);

    const thread = $('#thread'),
        welcome = $('#welcome'),
        input = $('#input'),
        send = $('#send'),
        form = $('#composer');
    let conv = uid(),
        history = [],
        controller = null,
        busy = false,
        stick = true;

    // ---------------------------------------------------------------- small helpers
    const sparkle = () => {
        const a = el('div', 'avatar');
        a.innerHTML =
            '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2l2.2 6.3L21 10l-6.8 1.7L12 18l-2.2-6.3L3 10l6.8-1.7z"/></svg>';
        return a;
    };
    const scroller = $('#chatscroll');
    const scrollDown = (force) => {
        if (force || stick) scroller.scrollTo({ top: scroller.scrollHeight, behavior: 'smooth' });
    };
    scroller.addEventListener(
        'scroll',
        () => {
            stick = scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 160;
        },
        { passive: true }
    );

    // markdown-lite, built with DOM nodes: **bold**, `code`, - lists, paragraphs
    function inline(parent, text) {
        const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
        let last = 0,
            m;
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
                    if (!list) {
                        list = el('ul');
                        node.append(list);
                        p = null;
                    }
                    const item = el('li');
                    inline(item, li[1]);
                    list.append(item);
                } else {
                    list = null;
                    if (!p) {
                        p = el('p');
                        node.append(p);
                    } else p.append(el('br'));
                    inline(p, line);
                }
            }
        }
    }

    // ---------------------------------------------------------------- photos
    function makeGallery(host) {
        const root = el('div', 'gallery'),
            head = el('div', 'gal-head'),
            readings = el('div', 'readings'),
            grid = el('div', 'grid');
        root.append(head, readings, grid);
        host.append(root);
        return { root, head, readings, grid, ids: [], total: 0, more: null, group: -1 };
    }
    function addTiles(g, ids) {
        for (const id of ids) {
            const t = el('button', 'tile');
            t.type = 'button';
            t.setAttribute('aria-label', 'Open photo');
            const img = new Image();
            img.alt = '';
            img.decoding = 'async';
            img.loading = 'lazy';
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
        const g = msg.gallery;
        g.ids = [];
        g.grid.replaceChildren();
        g.head.replaceChildren(
            el('span', 'count', `${total.toLocaleString()} quick matches`),
            el('span', 'refining', 'checking with the AI')
        );
        addTiles(g, ids);
    }
    function showResults(msg, d) {
        msg.gallery = msg.gallery || makeGallery(msg.body);
        const g = msg.gallery;
        g.ids = [];
        g.grid.replaceChildren();
        g.total = d.total;
        g.rid = d.rid || '';
        g.head.replaceChildren(
            el(
                'span',
                'count',
                d.kind === 'count'
                    ? `${d.total.toLocaleString()} photos`
                    : `${d.total.toLocaleString()} photo${d.total === 1 ? '' : 's'}`
            )
        );
        addTiles(g, d.ids);
        showReadings(g, d.groups || []);
        showMore(g);
    }
    // Every way the query could be read, with how many photos each finds: pick one to see its photos.
    function showReadings(g, groups) {
        g.readings.replaceChildren();
        if (groups.length < 2) return;
        groups.forEach((r, i) => {
            const b = el(
                'button',
                'reading' + (i === 0 ? ' active' : ''),
                `${r.label} \u00b7 ${r.count.toLocaleString()}`
            );
            b.type = 'button';
            b.addEventListener('click', async () => {
                g.readings.querySelectorAll('.reading').forEach((x) => x.classList.remove('active'));
                b.classList.add('active');
                g.group = i;
                g.ids = [];
                g.grid.replaceChildren();
                try {
                    const data = await (
                        await api(
                            `/api/results?conv=${encodeURIComponent(conv)}&rid=${encodeURIComponent(g.rid || '')}&offset=0&group=${i}`
                        )
                    ).json();
                    g.total = data.total;
                    g.head.replaceChildren(
                        el('span', 'count', `${data.total.toLocaleString()} photo${data.total === 1 ? '' : 's'}`)
                    );
                    addTiles(g, data.ids);
                } catch (_) {
                    /* keep what is shown */
                }
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
                    const r = await api(
                        `/api/results?conv=${encodeURIComponent(conv)}&rid=${encodeURIComponent(g.rid || '')}&offset=${g.ids.length}&group=${g.group}`
                    );
                    const data = await r.json();
                    addTiles(g, data.ids);
                } catch (_) {
                    /* keep what is shown */
                }
                if (g.ids.length >= g.total) g.more.remove();
                else g.more.disabled = false;
            });
            g.root.append(g.more);
        }
    }

    // ---------------------------------------------------------------- lightbox
    const lb = $('#lightbox'),
        lbImg = $('#lb-img'),
        lbCap = $('#lb-cap');
    let lbIds = [],
        lbAt = 0;
    async function openLightbox(ids, at) {
        lbIds = ids;
        lbAt = at;
        lb.hidden = false;
        document.body.style.overflow = 'hidden';
        await showLightbox();
    }
    async function showLightbox() {
        const id = lbIds[lbAt];
        lbImg.onerror = () => {
            lbImg.onerror = null;
            lbImg.src = photoUrl(id, 'thumb');
        };
        lbImg.src = photoUrl(id, 'preview');
        lbCap.textContent = '';
        try {
            const r = await api(`/api/item/${id}`);
            if (!r.ok || lbIds[lbAt] !== id) return;
            const d = await r.json();
            const parts = [d.taken && String(d.taken).slice(0, 10), d.place, d.camera].filter(Boolean);
            lbCap.replaceChildren(el('b', '', d.name || ''), parts.length ? '  ·  ' + parts.join('  ·  ') : '');
        } catch (_) {
            /* caption is optional */
        }
    }
    const lbStep = (n) => {
        lbAt = (lbAt + n + lbIds.length) % lbIds.length;
        showLightbox();
    };
    const lbClose = () => {
        lb.hidden = true;
        document.body.style.overflow = '';
        lbImg.removeAttribute('src');
    };
    $('#lb-close').addEventListener('click', lbClose);
    $('#lb-prev').addEventListener('click', () => lbStep(-1));
    $('#lb-next').addEventListener('click', () => lbStep(1));
    lb.addEventListener('click', (e) => {
        if (e.target === lb) lbClose();
    });

    // ---------------------------------------------------------------- conversation
    function addUser(text) {
        const m = el('div', 'msg user');
        m.append(el('div', 'bubble', text));
        thread.append(m);
        return m;
    }
    function addBot() {
        const m = el('div', 'msg bot'),
            body = el('div', 'body'),
            text = el('div', 'text');
        const typing = el('span', 'typing');
        typing.append(el('i'), el('i'), el('i'));
        text.append(typing);
        body.append(text);
        m.append(sparkle(), body);
        thread.append(m);
        return { root: m, body, text, typing, gallery: null, raw: '' };
    }
    function showStatus(msg, text) {
        // what it is doing right now, under the dots, until the answer starts
        if (!msg.typing.isConnected) return;
        let line = msg.text.querySelector('.stage');
        if (!line) {
            line = el('div', 'stage');
            msg.text.append(line);
        }
        line.textContent = text + '\u2026';
    }
    function handle(msg, event, d) {
        if (event !== 'status') {
            const s = msg.text.querySelector('.stage');
            if (s) s.remove();
        } // the answer has started: no more progress line
        if (event === 'status') showStatus(msg, d.text);
        else if (event === 'preview') showPreview(msg, d.ids, d.total);
        else if (event === 'delta') {
            msg.raw += d.text;
            msg.text.classList.add('streaming');
            renderText(msg.text, msg.raw);
        } else if (event === 'reply') {
            msg.raw = d.text;
            renderText(msg.text, d.text);
        } else if (event === 'results') showResults(msg, d);
        else if (event === 'notes') addNotes(msg, d);
        else if (event === 'error') {
            msg.text.classList.remove('streaming');
            msg.text.replaceChildren();
            msg.body.append(el('div', 'error', d.message));
        } else if (event === 'done') {
            msg.text.classList.remove('streaming');
            if (msg.gallery && !msg.gallery.total) {
                msg.gallery.root.remove();
                msg.gallery = null;
            } // a preview that was not confirmed
            if (d.kind !== 'error' && d.text) history.push({ role: 'assistant', text: d.record || d.text });
            if (SHOW_TRACE) addTrace(msg, d);
            const who =
                d.timings && d.timings.understood === 'cloud'
                    ? '  \u00b7  \u2601 cloud understood the request'
                    : d.timings && d.timings.understood === 'local'
                      ? '  \u00b7  understood locally'
                      : '';
            if (d.took >= 0.01) {
                msg.body.append(
                    el(
                        'div',
                        'meta',
                        d.took < 0.2 ? 'instant' : `answered in ${d.took.toFixed(1)}s${breakdown(d)}${who}`
                    )
                );
            }
        }
        if (event === 'results') addNotes(msg, d);
        scrollDown();
    }
    const STEP_NAMES = {
        route: 'deciding',
        decide: 'deciding',
        context: 'library lookup',
        plan: 'AI plan',
        dates: 'date check',
        tools: 'tools',
        search: 'search',
        first_words: 'first words',
    };
    function breakdown(d) {
        // when an answer is slow, show where the time went
        if (d.took < 3 || !d.timings) return '';
        const parts = Object.entries(d.timings)
            .filter(([, v]) => v >= 0.1)
            .map(([k, v]) => `${STEP_NAMES[k] || k} ${v.toFixed(1)}s`);
        return parts.length ? `  \u00b7  ${parts.join('  \u00b7  ')}` : '';
    }
    function addTrace(msg, d) {
        // "How I answered": exactly what each step was given and what it returned
        if (!d.trace || !d.trace.length) return;
        const box = el('details', 'trace'),
            head = el('summary', '', `How I answered (${d.trace.length} step${d.trace.length === 1 ? '' : 's'})`);
        box.append(head);
        d.trace.forEach((c, i) => {
            box.append(
                el(
                    'h4',
                    '',
                    `Step ${i + 1}${c.tools && c.tools.length ? '  \u00b7  tools: ' + c.tools.join(', ') : ''}`
                )
            );
            box.append(el('div', 'lbl', 'Instructions it was given'), el('pre', '', c.system || '(none)'));
            box.append(
                el('div', 'lbl', 'Conversation'),
                el('pre', '', (c.messages || []).map((m) => `${m.role}: ${m.text}`).join('\n'))
            );
            const out = [
                c.output,
                ...(c.tool_calls || []).map((t) => `tool call: ${t.name}(${JSON.stringify(t.arguments)})`),
            ]
                .filter(Boolean)
                .join('\n');
            box.append(el('div', 'lbl', 'What it answered'), el('pre', '', out || '(nothing)'));
        });
        msg.body.append(box);
    }
    function addNotes(msg, d) {
        for (const t of d.notes || []) msg.body.append(el('div', 'note', t));
        for (const t of d.warnings || []) msg.body.append(el('div', 'note warn', t));
    }
    function parseBlock(block) {
        let event = 'message',
            data = '';
        for (const line of block.split('\n')) {
            if (line.startsWith('event:')) event = line.slice(6).trim();
            else if (line.startsWith('data:')) data += line.slice(5).trim();
        }
        return [event, data ? JSON.parse(data) : {}];
    }
    let notReady = false; // the library is still loading: a question would only time out, so the box waits
    function setBusy(on) {
        busy = on;
        document.body.classList.toggle('busy', on);
        send.disabled = notReady || (!on && !input.value.trim());
    }

    async function ask(text) {
        text = text.trim();
        if (!text || busy || notReady) return;
        welcome.hidden = true;
        addUser(text);
        const bot = addBot();
        history.push({ role: 'user', text });
        input.value = '';
        autosize();
        setBusy(true);
        stick = true;
        scrollDown(true);
        controller = new AbortController();
        try {
            const res = await fetch('/api/chat', {
                method: 'POST',
                signal: controller.signal,
                headers: { 'Content-Type': 'application/json', 'X-Lumo-Token': token },
                body: JSON.stringify({
                    message: text,
                    conv,
                    history: history
                        .slice(0, -1)
                        .slice(-8)
                        .map((h) => [h.role, h.text]),
                }),
            });
            if (!res.ok || !res.body) throw new Error(`The server answered ${res.status}`);
            const reader = res.body.getReader(),
                dec = new TextDecoder();
            let buf = '';
            for (;;) {
                const { done, value } = await reader.read();
                if (done) break;
                buf += dec.decode(value, { stream: true });
                let i;
                while ((i = buf.indexOf('\n\n')) >= 0) {
                    const [event, data] = parseBlock(buf.slice(0, i));
                    buf = buf.slice(i + 2);
                    handle(bot, event, data);
                }
            }
        } catch (err) {
            if (err.name !== 'AbortError') handle(bot, 'error', { message: `Lumo could not answer: ${err.message}` });
        } finally {
            bot.text.classList.remove('streaming');
            if (bot.typing.isConnected) bot.typing.remove();
            setBusy(false);
            controller = null;
            input.focus();
        }
    }

    function newChat() {
        // instant: nothing is asked of the server
        if (controller) controller.abort();
        conv = uid();
        history = [];
        thread.replaceChildren();
        welcome.hidden = false;
        setBusy(false);
        input.value = '';
        autosize();
        scroller.scrollTo({ top: 0 });
        input.focus();
    }

    // ---------------------------------------------------------------- composer
    function autosize() {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 150) + 'px';
        send.disabled = notReady || (!busy && !input.value.trim());
    }
    input.addEventListener('input', autosize);
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
            e.preventDefault();
            ask(input.value);
        }
    });
    form.addEventListener('submit', (e) => {
        e.preventDefault();
        if (busy && controller) controller.abort();
        else ask(input.value);
    });
    $('#newchat').addEventListener('click', newChat);
    $('#topsearch').addEventListener('submit', (e) => {
        e.preventDefault();
        const t = $('#topq').value.trim();
        if (!t) return;
        $('#topq').value = '';
        askLumo(t);
    });
    document.addEventListener('keydown', (e) => {
        if (!lb.hidden) {
            e.stopImmediatePropagation();
            if (e.key === 'Escape') lbClose();
            else if (e.key === 'ArrowLeft') lbStep(-1);
            else if (e.key === 'ArrowRight') lbStep(1);
            return;
        }
        const typing = /^(INPUT|TEXTAREA)$/.test(document.activeElement ? document.activeElement.tagName : '');
        if (((e.key === 'k' || e.key === 'K') && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !typing)) {
            e.preventDefault();
            if (EMBEDDED) toParent({ type: 'palette' });
            else openPalette();
        }
    });
    $('#topq').addEventListener('focus', () => {
        $('#topq').blur();
        openPalette();
    }); // the top bar opens the same search-everything box as Ctrl/Cmd+K and "/"

    // ---------------------------------------------------------------- one search box for everything: pages, places, people, trips, years. Opens with Ctrl/Cmd+K or "/".
    let finder = null;
    const loadFinder = async () => {
        if (finder) return finder;
        const [places, people, trips, tl] = await Promise.all(
            ['places', 'people', 'trips', 'timeline'].map((n) => getJson('/api/' + n))
        );
        finder = { places, people: people.filter((p) => p.name), trips, years: tl.years || [] };
        return finder;
    };
    function openPalette() {
        if ($('.palette')) return;
        const box = el('input', 'palette-input');
        box.placeholder = 'Search places, people, trips, years… or jump to a page';
        box.autocomplete = 'off';
        box.spellcheck = false;
        box.setAttribute('aria-label', 'Search everything');
        const list = el('div', 'palette-list');
        let items = [],
            active = 0,
            seq = 0;
        const close = () => {
            overlay.remove();
            document.removeEventListener('keydown', onKey, true);
        };
        const run = (it) => {
            close();
            it.run();
        };
        const mark = () =>
            list.querySelectorAll('.palette-item').forEach((b) => b.classList.toggle('on', +b.dataset.i === active));
        const paint = () => {
            list.replaceChildren(
                ...(items.length
                    ? items.map((it, i) => {
                          if (it.head) return el('div', 'palette-head', it.head);
                          const b = el('button', 'palette-item' + (i === active ? ' on' : ''));
                          b.type = 'button';
                          b.dataset.i = i;
                          const text = el('span', 'grow');
                          text.append(el('div', 'strong', it.label));
                          if (it.sub) text.append(el('div', 'faint small', it.sub));
                          b.append(icon(it.icon), text);
                          if (it.right) b.append(el('span', 'faint', it.right));
                          b.addEventListener('click', () => run(it));
                          b.addEventListener('mouseenter', () => {
                              active = i;
                              mark();
                          });
                          return b;
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
        const pages = (q) =>
            NAV.filter(([, n]) => !q || n.toLowerCase().includes(q)).map(([id, n, d]) => ({
                label: n,
                sub: 'Go to',
                icon: d,
                run: () => go(id),
            }));
        const has = (text, q) => (text || '').toLowerCase().includes(q);
        const build = async () => {
            const raw = box.value.trim(),
                q = raw.toLowerCase(),
                mine = ++seq;
            if (q.length < 2) {
                items = [{ head: 'Jump to' }, ...pages(q)];
                firstReal();
                paint();
                return;
            }
            let f;
            try {
                f = await loadFinder();
            } catch (_) {
                f = { places: [], people: [], trips: [], years: [] };
            }
            if (mine !== seq) return;
            const pg = pages(q);
            const askItem = { label: `Ask Lumo: “${raw}”`, sub: 'Chat', icon: NAV[0][2], run: () => askLumo(raw) };
            const pl = f.places.filter((x) => has(x.place, q)).slice(0, 6),
                pe = f.people.filter((x) => has(x.name, q)).slice(0, 6),
                tr = f.trips.filter((x) => has(x.title, q) || has(x.place, q)).slice(0, 6);
            const yr = /^\d{4}$/.test(q) ? f.years.filter((y) => y.year === q) : [];
            items = [
                ...(pg.length ? [{ head: 'Pages' }, ...pg.slice(0, 4)] : []),
                ...(yr.length
                    ? [
                          { head: 'Years' },
                          ...yr.map((y) => ({
                              label: y.year,
                              sub: 'Photos from this year',
                              right: y.total.toLocaleString(),
                              icon: NAV[1][2],
                              run: () => go('library', { year: y.year }),
                          })),
                      ]
                    : []),
                ...(pl.length
                    ? [
                          { head: 'Places' },
                          ...pl.map((x) => ({
                              label: x.place,
                              right: x.n.toLocaleString(),
                              icon: NAV[3][2],
                              run: () => go('library', { place: x.place }),
                          })),
                      ]
                    : []),
                ...(pe.length
                    ? [
                          { head: 'People' },
                          ...pe.map((x) => ({
                              label: x.name,
                              right: x.n.toLocaleString(),
                              icon: NAV[4][2],
                              run: () => go('library', { person: String(x.id) }),
                          })),
                      ]
                    : []),
                ...(tr.length
                    ? [
                          { head: 'Trips' },
                          ...tr.map((x) => ({
                              label: x.title,
                              sub: dateRange(x.start, x.stop),
                              right: x.n.toLocaleString(),
                              icon: NAV[2][2],
                              run: () => go('library', { from: x.start, to: x.stop }),
                          })),
                      ]
                    : []),
                { head: 'Or ask' },
                askItem,
            ];
            firstReal();
            paint();
        };
        let timer;
        box.addEventListener('input', () => {
            clearTimeout(timer);
            timer = setTimeout(build, 120);
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
                e.stopImmediatePropagation();
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
        const bar = el('div', 'palette-bar');
        bar.append(icon('M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14ZM21 21l-4.3-4.3'), box, el('kbd', '', 'esc'));
        const overlay = el('div', 'overlay top');
        const pal = el('div', 'palette');
        pal.append(bar, list);
        overlay.append(pal);
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) close();
        });
        document.body.append(overlay);
        document.addEventListener('keydown', onKey, true);
        items = [{ head: 'Jump to' }, ...pages('')];
        firstReal();
        paint();
        box.focus();
    }

    // ---------------------------------------------------------------- the corner chat: the same conversation, one tap away from every page
    const corner = { open: false };
    function setCorner(on) {
        if (on && where().page === 'search') return; // the full page is already the chat
        corner.open = on;
        if (EMBEDDED) toParent({ type: 'chat', open: on });
        document.body.classList.toggle('chat-open', on);
        if (on) {
            stick = true;
            scrollDown(true);
            input.focus();
        }
    }
    function askLumo(text) {
        go('search');
        ask(text);
    }
    $('#chat-fab').addEventListener('click', () => setCorner(true));
    $('#chat-close').addEventListener('click', () => setCorner(false));
    $('#chat-expand').addEventListener('click', () => {
        setCorner(false);
        go('search');
    });
    document.addEventListener('keydown', (e) => {
        if (lb && !lb.hidden) return;
        if (e.key === 'Escape' && corner.open) setCorner(false);
        else if ((e.key === 'j' || e.key === 'J') && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            if (where().page === 'search') input.focus();
            else setCorner(!corner.open);
        }
    });

    // ---------------------------------------------------------------- navigation, theme and the browsing pages
    const SVG = 'http://www.w3.org/2000/svg';
    const icon = (d) => {
        const svg = document.createElementNS(SVG, 'svg'),
            path = document.createElementNS(SVG, 'path');
        svg.setAttribute('viewBox', '0 0 24 24');
        path.setAttribute('d', d);
        svg.append(path);
        return svg;
    };
    const NAV = [
        ['search', 'Chat', 'M20 12a8 8 0 0 1-11.6 7.1L4 20l1-4.2A8 8 0 1 1 20 12Z'],
        ['library', 'Library', 'M4 5h16v14H4V5Zm0 10 4-4 4 4 3-3 5 5M9 9h.01'],
        ['trips', 'Trips', 'M2 14l20-8-8 20-3-9-9-3Z'],
        [
            'places',
            'Places',
            'M12 21s-7-5.3-7-11a7 7 0 0 1 14 0c0 5.7-7 11-7 11ZM12 12a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z',
        ],
        [
            'people',
            'People',
            'M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm-6 9a6 6 0 0 1 12 0M16 4.3a3.5 3.5 0 0 1 0 6.4M18 14.2A6 6 0 0 1 21 20',
        ],
    ];
    const PAGES = NAV.map((n) => n[0]);
    const THEME_ICONS = {
        dark: 'M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z',
        light: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4',
        auto: 'M12 3a9 9 0 1 0 0 18V3Z',
    };
    function setupTheme() {
        let mode = 'dark';
        try {
            mode = localStorage.getItem('lumo.theme') || 'dark';
        } catch (_) {
            /* private window */
        }
        const apply = () => {
            document.documentElement.dataset.theme = mode;
            $('#theme').replaceChildren(icon(THEME_ICONS[mode]));
            $('#theme').title = 'Theme: ' + mode;
        };
        $('#theme').addEventListener('click', () => {
            mode = mode === 'auto' ? 'dark' : mode === 'dark' ? 'light' : 'auto';
            try {
                localStorage.setItem('lumo.theme', mode);
            } catch (_) {
                /* ignore */
            }
            apply();
        });
        apply();
    }
    $('#nav').replaceChildren(
        ...NAV.map(([id, label, d]) => {
            const a = el('a', 'nav-item');
            a.href = '#/' + id;
            a.dataset.id = id;
            a.append(icon(d), el('span', '', label));
            return a;
        })
    );
    function where() {
        const [page, query] = location.hash.replace(/^#\/?/, '').split('?');
        return {
            page: PAGES.includes(page) ? page : 'search',
            params: Object.fromEntries(new URLSearchParams(query || '')),
        };
    }
    function go(page, params) {
        const clean = Object.fromEntries(Object.entries(params || {}).filter(([, v]) => v));
        const qs = new URLSearchParams(clean).toString(),
            target = '#/' + page + (qs ? '?' + qs : '');
        if (location.hash === target) render();
        else location.hash = target;
    }
    const getJson = async (path) => (await api(path)).json();
    const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const monthLabel = (ym) => MONTHS[+ym.slice(5, 7) - 1] || ym;
    const pageHead = (title, sub, ...right) => {
        const head = el('div', 'page-head'),
            left = el('div');
        left.append(el('h1', '', title));
        if (sub) left.append(el('div', 'sub', sub));
        head.append(left, ...right);
        return head;
    };
    const seg = (options, current, pick) => {
        const box = el('div', 'seg');
        for (const [value, label] of options) {
            const b = el('button', value === current ? 'on' : '', label);
            b.type = 'button';
            b.addEventListener('click', () => pick(value));
            box.append(b);
        }
        return box;
    };
    const tag = (label, clear) => {
        const b = el('button', 'tag', label + ' \u00d7');
        b.type = 'button';
        b.title = 'Remove this filter';
        b.addEventListener('click', clear);
        return b;
    };
    const dateRange = (a, b) => (a === b ? a : `${a} \u2192 ${b}`);
    function coverCard(id, title, subtitle, count, onClick) {
        const card = el('button', 'cover');
        card.type = 'button';
        const img = new Image();
        img.alt = '';
        img.decoding = 'async';
        img.loading = 'lazy';
        img.onload = () => card.classList.add('loaded');
        img.src = photoUrl(id, 'thumb');
        const label = el('div', 'label');
        label.append(el('b', '', title), el('span', '', subtitle));
        card.append(img, label);
        if (count != null) card.append(el('span', 'badge', count.toLocaleString()));
        card.addEventListener('click', onClick);
        return card;
    }
    let libSeq = 0;
    async function showLibrary(params) {
        const host = $('#page-library'),
            mine = ++libSeq;
        host.replaceChildren(el('div', 'empty', 'Loading\u2026'));
        const [tl, people] = await Promise.all([
            getJson('/api/timeline'),
            params.person ? getJson('/api/people') : Promise.resolve([]),
        ]);
        if (mine !== libSeq) return;
        const filters = ['year', 'month', 'place', 'person', 'from', 'to'].reduce(
            (o, k) => (params[k] ? { ...o, [k]: params[k] } : o),
            {}
        );
        const change = (c) => go('library', { ...params, ...c });
        const sub = el('div', 'sub', ''),
            grid = el('div', 'pgrid'),
            sentinel = el('div', 'sentinel'),
            moreBtn = el('button', 'pill more', 'Show more');
        moreBtn.type = 'button';
        const head = el('div', 'page-head'),
            left = el('div');
        left.append(el('h1', '', 'Library'), sub);
        head.append(left);
        const facets = el('div', 'facets');
        facets.append(
            seg(
                [
                    ['', `All \u00b7 ${tl.total.toLocaleString()}`],
                    ...tl.years.map((y) => [y.year, `${y.year} \u00b7 ${y.total.toLocaleString()}`]),
                ],
                params.year || '',
                (v) => change({ year: v, month: '', from: '', to: '', trip: '' })
            )
        );
        const yr = tl.years.find((y) => y.year === params.year);
        if (yr) {
            facets.append(
                seg(
                    [
                        ['', 'All months'],
                        ...yr.months
                            .slice()
                            .reverse()
                            .map((m) => [m.month, `${monthLabel(m.month)} \u00b7 ${m.n}`]),
                    ],
                    params.month || '',
                    (v) => change({ month: v })
                )
            );
        }
        const tags = el('div', 'tagrow');
        if (params.place) tags.append(tag(params.place, () => change({ place: '' })));
        if (params.person) {
            tags.append(
                tag((people.find((p) => String(p.id) === params.person) || {}).name || 'Person', () =>
                    change({ person: '', name: '' })
                )
            );
        }
        if (params.from || params.to) {
            tags.append(
                tag(
                    params.trip
                        ? `${params.trip} \u00b7 ${dateRange(params.from, params.to)}`
                        : dateRange(params.from, params.to),
                    () => change({ from: '', to: '', trip: '' })
                )
            );
        }
        host.replaceChildren(head, facets, tags, grid, sentinel, moreBtn);
        const g = { ids: [], grid };
        let total = 0,
            loading = false;
        async function more() {
            if (loading || mine !== libSeq || (total && g.ids.length >= total)) return;
            loading = true;
            try {
                const d = await getJson(
                    '/api/library?' + new URLSearchParams({ ...filters, offset: String(g.ids.length) })
                );
                if (mine !== libSeq) return;
                total = d.total;
                addTiles(g, d.ids);
                sub.textContent = total ? `${total.toLocaleString()} photo${total === 1 ? '' : 's'}` : '';
                if (!total) grid.replaceWith(el('div', 'empty', 'No photos match.'));
            } catch (_) {
                /* keep what is shown */
            }
            loading = false;
            moreBtn.hidden = g.ids.length >= total;
        }
        moreBtn.addEventListener('click', more);
        new IntersectionObserver(
            (entries) => {
                if (entries.some((x) => x.isIntersecting)) more();
            },
            { rootMargin: '600px' }
        ).observe(sentinel);
        await more();
    }
    async function showTrips() {
        const host = $('#page-trips');
        host.replaceChildren(el('div', 'empty', 'Loading\u2026'));
        const trips = await getJson('/api/trips');
        const body = [pageHead('Trips', trips.length ? `${trips.length} trips and occasions, newest first` : '')];
        if (!trips.length) {
            body.push(el('div', 'empty', 'No trips yet. They appear once photos have dates and places.'));
        }
        let year = '';
        const cards = el('div', 'cards');
        body.push(cards);
        for (const t of trips) {
            if (t.start.slice(0, 4) !== year) {
                year = t.start.slice(0, 4);
                cards.append(el('div', 'band wide', year));
            }
            cards.append(
                coverCard(t.cover, t.title, dateRange(t.start, t.stop), t.n, () =>
                    go('library', { from: t.start, to: t.stop, trip: t.title })
                )
            );
        }
        host.replaceChildren(...body);
    }
    async function showPlaces() {
        const host = $('#page-places');
        host.replaceChildren(el('div', 'empty', 'Loading\u2026'));
        const places = await getJson('/api/places');
        const cards = el('div', 'cards'),
            filter = el('input', 'field');
        filter.type = 'search';
        filter.placeholder = 'Find a place\u2026';
        const fill = () => {
            const f = filter.value.trim().toLowerCase();
            cards.replaceChildren(
                ...places
                    .filter((p) => !f || p.place.toLowerCase().includes(f))
                    .map((p) =>
                        coverCard(p.cover, p.place.split(',')[0], p.country || p.place, p.n, () =>
                            go('library', { place: p.place })
                        )
                    )
            );
        };
        filter.addEventListener('input', fill);
        fill();
        host.replaceChildren(
            pageHead('Places', places.length ? `${places.length} places` : ''),
            ...(places.length
                ? [filter, el('div', 'band', ''), cards]
                : [el('div', 'empty', 'No places yet. Photos with a location appear here.')])
        );
    }
    function faceStyle(node, id, box) {
        // the clearest face of a person, zoomed into the photo it comes from
        node.style.backgroundImage = `url("${photoUrl(id, 'thumb')}")`;
        const [x1, y1, x2, y2] = box,
            w = Math.max(x2 - x1, y2 - y1) * 1.7;
        if (!(w < 0.98)) {
            node.style.backgroundSize = 'cover';
            node.style.backgroundPosition = 'center';
            return;
        }
        const pos = (c) => Math.min(100, Math.max(0, ((c - w / 2) / (1 - w)) * 100));
        node.style.backgroundSize = `${100 / w}% ${100 / w}%`;
        node.style.backgroundPosition = `${pos((x1 + x2) / 2)}% ${pos((y1 + y2) / 2)}%`;
    }
    async function showPeople() {
        const host = $('#page-people');
        host.replaceChildren(el('div', 'empty', 'Loading\u2026'));
        const people = await getJson('/api/people'),
            grid = el('div', 'people');
        people.forEach((p, i) => {
            const b = el('button', 'person'),
                face = el('div', 'face');
            b.type = 'button';
            faceStyle(face, p.cover, p.box);
            b.append(
                face,
                el('b', '', p.name || `Person ${i + 1}`),
                el('span', '', `${p.n.toLocaleString()} photo${p.n === 1 ? '' : 's'}`)
            );
            b.addEventListener('click', () => go('library', { person: String(p.id) }));
            grid.append(b);
        });
        host.replaceChildren(
            pageHead('People', people.length ? `${people.length} people found in your photos` : ''),
            people.length ? grid : el('div', 'empty', 'No people yet. Faces are grouped while your library is indexed.')
        );
    }
    async function render() {
        const { page, params } = where();
        document.body.dataset.page = page;
        document.querySelectorAll('.nav-item').forEach((a) => a.classList.toggle('active', a.dataset.id === page));
        for (const id of PAGES) {
            const section = $('#page-' + id);
            if (section) section.hidden = id !== page;
        }
        if (page === 'search' && corner.open) setCorner(false);
        try {
            if (page === 'library') await showLibrary(params);
            else if (page === 'trips') await showTrips();
            else if (page === 'places') await showPlaces();
            else if (page === 'people') await showPeople();
        } catch (e) {
            const host = $('#page-' + page);
            host.replaceChildren(el('div', 'empty', `Could not load this page: ${e.message}`));
        }
        if (page !== 'search') window.scrollTo({ top: 0 });
        else input.focus();
    }

    // ---------------------------------------------------------------- status chips + first screen
    function chip(label, state, action) {
        const c = el('span', `chip ${state}`);
        c.append(el('span', 'dot'), label);
        if (action) {
            const b = el('button', '', action.text);
            b.type = 'button';
            b.addEventListener('click', action.run);
            c.append(b);
        }
        return c;
    }
    async function setCloud(on) {
        try {
            const r = await (
                await api('/api/cloud', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ on }),
                })
            ).json();
            if (!r.ok) alert(r.error);
        } catch (e) {
            /* the next status refresh shows the truth */
        }
        refreshStatus();
    }
    const searchChip = (s) => {
        if (s.search_ready) return chip('Search ready', 'ok');
        return s.warm_problem ? chip('Search unavailable', 'bad') : chip('Search warming up', 'warn');
    };
    function cloudChips(s) {
        const state = s.cloud && s.cloud.state;
        if (state === 'connected') {
            const spent = Number(s.cloud.spent || 0).toFixed(2);
            const cap = Number(s.cloud.cap || 0).toFixed(0);
            return [chip(`Cloud on · $${spent} of $${cap}`, 'ok', { text: 'Turn off', run: () => setCloud(false) })];
        }
        if (state === 'down') {
            return [chip('Cloud not connected: local only', 'warn', { text: 'Turn off', run: () => setCloud(false) })];
        }
        if (state === 'local') return [chip('Local only', 'ok', { text: 'Use cloud', run: () => setCloud(true) })];
        return [];
    }
    function indexingChips(s) {
        const chips = [];
        if (s.photos) chips.push(chip(`${s.photos.toLocaleString()} photos`, 'ok'));
        if (s.indexing) {
            chips.push(chip('Indexing', 'warn'));
        } else if (s.paused_for_chat) {
            const resume = async () => {
                await api('/api/scan/resume', { method: 'POST' });
                refreshStatus();
            };
            chips.push(chip('Indexing paused', 'warn', { text: 'Resume', run: resume }));
        }
        return chips;
    }
    function warmMessage(s) {
        if (s.warm_problem) return `Image search could not start: ${s.warm_problem}`;
        if (!s.ai) return 'The AI model is not reachable. Is Ollama running?';
        if (notReady) {
            return 'Getting ready: loading your library into memory. You can ask as soon as this message goes away.';
        }
        return 'Warming up: the first answer can take a little longer.';
    }
    async function refreshStatus() {
        try {
            const s = await (await api('/api/status')).json();
            $('#build').textContent = s.build ? `build ${s.build}` : '';
            $('#chips').replaceChildren(
                searchChip(s),
                chip(s.ai ? s.model : 'AI offline', s.ai ? 'ok' : 'bad'),
                ...cloudChips(s),
                ...indexingChips(s)
            );
            notReady = !s.search_ready && !s.warm_problem;
            input.placeholder = notReady ? 'Getting ready…' : 'Ask for photos, or ask anything…';
            send.disabled = notReady || (!busy && !input.value.trim());
            $('#warm').textContent = warmMessage(s);
            document.body.classList.toggle('warming', !s.search_ready || !s.ai);
        } catch (_) {
            $('#chips').replaceChildren(chip('Lumo is not responding', 'bad'));
        }
    }
    async function loadIdeas() {
        let ideas = [];
        try {
            ideas = (await (await api('/api/suggestions')).json()).ideas || [];
        } catch (_) {
            /* none */
        }
        $('#ideas').replaceChildren(
            ...ideas.slice(0, 6).map((t) => {
                const b = el('button', 'idea', t);
                b.type = 'button';
                b.addEventListener('click', () => ask(t));
                return b;
            })
        );
    }
    // shown inside Atlas (the shared page): its menu, search and chat button replace ours
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
            else if (m.type === 'theme' && ['dark', 'light', 'auto'].includes(m.mode))
                document.documentElement.dataset.theme = m.mode;
            else if (m.type === 'toggle-chat') setCorner(!corner.open);
            else if (m.type === 'ask' && typeof m.text === 'string') askLumo(m.text);
        });
        window.addEventListener('hashchange', () => toParent({ type: 'route', hash: location.hash }));
        toParent({ type: 'ready' });
    }
    setupEmbedding();
    const h = new Date().getHours();
    $('#greeting').textContent = h < 5 ? 'Hello' : h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
    setupTheme();
    window.addEventListener('hashchange', render);
    render();
    autosize();
    refreshStatus();
    loadIdeas();
    setInterval(refreshStatus, 4000);
    if (where().page === 'search') input.focus();
})();
