'use strict';
/* The pictures side of the page: the library by date, trips, places and people. All text is added with textContent. */
(() => {
    const $ = (s) => document.querySelector(s);
    const el = (tag, cls, text) => {
        const e = document.createElement(tag);
        if (cls) e.className = cls;
        if (text != null) e.textContent = text;
        return e;
    };
    const getJson = async (path) => (await fetch(path, { headers: { Accept: 'application/json' } })).json();
    const browse = async (page, params = {}) =>
        (await getJson('/api/pictures/browse?' + new URLSearchParams({ page, ...params }))).page;
    const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const monthLabel = (ym) => MONTHS[+ym.slice(5, 7) - 1] || ym;
    const dateRange = (a, b) => (a === b ? a : `${a} → ${b}`);
    const host = () => $('#page-pictures');
    const go = (section, params) => {
        const qs = new URLSearchParams(
            Object.fromEntries(Object.entries(params || {}).filter(([, v]) => v))
        ).toString();
        location.hash = `#/${section}${qs ? '?' + qs : ''}`;
    };

    // ---------------------------------------------------------------- one picture, large
    const lb = $('#lightbox'),
        lbImg = $('#lb-img'),
        lbCap = $('#lb-cap');
    let lbIds = [],
        lbAt = 0;
    async function showLightbox() {
        const id = lbIds[lbAt];
        lbImg.onerror = () => {
            lbImg.onerror = null;
            lbImg.src = `/api/pictures/thumb/${id}`;
        };
        lbImg.src = `/api/pictures/preview/${id}`;
        lbCap.textContent = '';
        try {
            const d = await getJson(`/api/pictures/item?id=${id}`);
            if (lbIds[lbAt] !== id) return;
            const parts = [d.taken && String(d.taken).slice(0, 10), d.place, d.camera].filter(Boolean);
            lbCap.replaceChildren(el('b', '', d.name || ''), parts.length ? '  ·  ' + parts.join('  ·  ') : '');
        } catch (_) {
            /* the caption is optional */
        }
    }
    function openLightbox(ids, at) {
        lbIds = ids;
        lbAt = at;
        lb.hidden = false;
        document.body.style.overflow = 'hidden';
        showLightbox();
    }
    const lbClose = () => {
        lb.hidden = true;
        document.body.style.overflow = '';
        lbImg.removeAttribute('src');
    };
    const lbStep = (n) => {
        lbAt = (lbAt + n + lbIds.length) % lbIds.length;
        showLightbox();
    };
    $('#lb-close').addEventListener('click', lbClose);
    $('#lb-prev').addEventListener('click', () => lbStep(-1));
    $('#lb-next').addEventListener('click', () => lbStep(1));
    lb.addEventListener('click', (e) => {
        if (e.target === lb) lbClose();
    });
    document.addEventListener('keydown', (e) => {
        if (lb.hidden) return;
        if (e.key === 'Escape') lbClose();
        else if (e.key === 'ArrowLeft') lbStep(-1);
        else if (e.key === 'ArrowRight') lbStep(1);
    });

    // ---------------------------------------------------------------- pieces
    const head = (title, sub) => {
        const box = el('div', 'page-head');
        box.append(el('h2', '', title));
        if (sub) box.append(el('p', 'muted', sub));
        return box;
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
        const b = el('button', 'tag', label + ' ×');
        b.type = 'button';
        b.addEventListener('click', clear);
        return b;
    };
    function cover(id, title, subtitle, count, onClick) {
        const card = el('button', 'cover');
        card.type = 'button';
        const img = new Image();
        img.alt = '';
        img.loading = 'lazy';
        img.src = `/api/pictures/thumb/${id}`;
        const label = el('div', 'label');
        label.append(el('b', '', title), el('span', '', subtitle));
        card.append(img, label);
        if (count != null) {
            card.append(el('span', 'badge', count.toLocaleString()));
        }
        card.addEventListener('click', onClick);
        return card;
    }
    function addTiles(g, ids) {
        for (const id of ids) {
            const t = el('button', 'tile');
            t.type = 'button';
            t.setAttribute('aria-label', 'Open picture');
            const img = new Image();
            img.alt = '';
            img.loading = 'lazy';
            img.src = `/api/pictures/thumb/${id}`;
            t.append(img);
            g.ids.push(id);
            const at = g.ids.length - 1;
            t.addEventListener('click', () => openLightbox(g.ids, at));
            g.grid.append(t);
        }
    }

    // ---------------------------------------------------------------- the pages
    let seq = 0;
    async function showLibrary(params) {
        const mine = ++seq;
        host().replaceChildren(el('div', 'empty', 'Loading…'));
        const [tl, people] = await Promise.all([
            browse('timeline'),
            params.person ? browse('people') : Promise.resolve([]),
        ]);
        if (mine !== seq) return;
        const filters = ['year', 'month', 'place', 'person', 'from', 'to'].reduce(
            (o, k) => (params[k] ? { ...o, [k]: params[k] } : o),
            {}
        );
        const change = (c) => go('library', { ...params, ...c });
        const sub = el('p', 'muted', ''),
            grid = el('div', 'pgrid'),
            sentinel = el('div', 'sentinel'),
            moreBtn = el('button', 'pill', 'Show more');
        moreBtn.type = 'button';
        const facets = el('div', 'facets');
        facets.append(
            seg(
                [
                    ['', `All · ${tl.total.toLocaleString()}`],
                    ...tl.years.map((y) => [y.year, `${y.year} · ${y.total.toLocaleString()}`]),
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
                            .map((m) => [m.month, `${monthLabel(m.month)} · ${m.n}`]),
                    ],
                    params.month || '',
                    (v) => change({ month: v })
                )
            );
        }
        const tags = el('div', 'tagrow');
        if (params.place) {
            tags.append(tag(params.place, () => change({ place: '' })));
        }
        if (params.person) {
            tags.append(
                tag((people.find((p) => String(p.id) === params.person) || {}).name || 'Person', () =>
                    change({ person: '' })
                )
            );
        }
        if (params.from || params.to) {
            tags.append(
                tag(
                    params.trip
                        ? `${params.trip} · ${dateRange(params.from, params.to)}`
                        : dateRange(params.from, params.to),
                    () => change({ from: '', to: '', trip: '' })
                )
            );
        }
        const best = el('div', 'best');
        host().replaceChildren(tabs('library'), head('Photos'), best, sub, facets, tags, grid, sentinel, moreBtn);
        if (!Object.keys(filters).length) {
            // the best few on display, only on the Photos home (not when narrowed to a year, place or person)
            browse('highlights').then((h) => {
                if (mine !== seq || !h.ids.length) return;
                const strip = el('div', 'pgrid');
                const g2 = { ids: [], grid: strip };
                addTiles(g2, h.ids);
                best.replaceChildren(el('div', 'band', 'Highlights'), strip);
            });
        }
        const g = { ids: [], grid };
        let total = 0,
            loading = false;
        async function more() {
            if (loading || mine !== seq || (total && g.ids.length >= total)) {
                return;
            }
            loading = true;
            try {
                const d = await browse('library', {
                    ...filters,
                    offset: String(g.ids.length),
                });
                if (mine !== seq) return;
                total = d.total;
                addTiles(g, d.ids);
                sub.textContent = total ? `${total.toLocaleString()} picture${total === 1 ? '' : 's'}` : '';
                if (!total) {
                    grid.replaceWith(el('div', 'empty', 'No pictures match.'));
                }
            } catch (_) {
                /* keep what is shown */
            }
            loading = false;
            moreBtn.hidden = g.ids.length >= total;
        }
        moreBtn.addEventListener('click', more);
        new IntersectionObserver((entries) => entries.some((x) => x.isIntersecting) && more(), {
            rootMargin: '600px',
        }).observe(sentinel);
        await more();
    }
    function faceStyle(node, id, box) {
        node.style.backgroundImage = `url("/api/pictures/thumb/${id}")`;
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
    // ---------------------------------------------------------------- the picture folders: trips, places and people, each a row of covers
    const stat = (label, value, onClick) => {
        const t = el(onClick ? 'button' : 'div', 'stat');
        if (onClick) {
            t.type = 'button';
            t.addEventListener('click', onClick);
        }
        t.append(el('span', 'stat-label', label), el('b', 'stat-value', value.toLocaleString()));
        return t;
    };
    const tripCovers = (trips, limit) => {
        const cards = el('div', 'cards');
        for (const t of trips.slice(0, limit)) {
            cards.append(
                cover(t.cover, t.title, dateRange(t.start, t.stop), t.n, () =>
                    go('library', { from: t.start, to: t.stop, trip: t.title })
                )
            );
        }
        return cards;
    };
    const placeCovers = (places, limit) => {
        const cards = el('div', 'cards');
        for (const p of places.slice(0, limit)) {
            cards.append(
                cover(p.cover, p.place.split(',')[0], p.country || p.place, p.n, () =>
                    go('library', { place: p.place })
                )
            );
        }
        return cards;
    };
    const personFaces = (people, limit) => {
        const grid = el('div', 'people');
        people.slice(0, limit).forEach((p, i) => {
            const b = el('button', 'person'),
                face = el('div', 'face');
            b.type = 'button';
            faceStyle(face, p.cover, p.box);
            b.append(face, el('b', '', p.name || `Person ${i + 1}`), el('span', '', p.n.toLocaleString()));
            b.addEventListener('click', () => go('library', { person: String(p.id) }));
            grid.append(b);
        });
        return grid;
    };
    const tabs = (current) =>
        window.AppTabs(
            [
                ['photos', 'Dashboard'],
                ['folders', 'Folders'],
            ],
            current
        );
    const loadAll = () =>
        Promise.all([
            browse('trips'),
            browse('places'),
            browse('people'),
            browse('highlights'),
            getJson('/api/pictures/status'),
        ]);

    async function showPhotosHome() {
        host().replaceChildren(tabs('photos'), el('div', 'empty', 'Loading…'));
        const [trips, places, people, best, status] = await loadAll();
        const page = [tabs('photos'), el('div', 'tiles')];
        page[1].append(
            stat('Photos', status.pictures || 0, () => go('library')),
            stat('Trips', trips.length, () => go('folders')),
            stat('Places', places.length, () => go('folders')),
            stat('People', people.length, () => go('folders'))
        );
        if (best.ids && best.ids.length) {
            const mosaic = el('div', 'mosaic');
            addTiles({ ids: [], grid: mosaic }, best.ids.slice(0, 8));
            page.push(el('div', 'band', 'Highlights'), mosaic);
        }
        if (trips.length) page.push(el('div', 'band', 'Recent trips'), tripCovers(trips, 4));
        if (places.length) page.push(el('div', 'band', 'Places'), placeCovers(places, 4));
        if (people.length) page.push(el('div', 'band', 'People'), personFaces(people, 8));
        if (!status.pictures)
            page.push(el('div', 'empty', 'No pictures yet. They appear while your pictures are read.'));
        page.push(changesButton());
        host().replaceChildren(...page);
    }

    // the one change a person can ask for here: it is only prepared, the confirmation window does the rest
    const albumsButton = () => {
        const b = el('button', 'btn', 'Sort into trip albums…');
        b.type = 'button';
        b.addEventListener('click', async () => {
            b.disabled = true;
            const r = await (
                await fetch('/api/change/albums', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-Library': '1' },
                    body: '{}',
                })
            ).json();
            if (r.change_id) location.hash = `#/changes?id=${r.change_id}`;
            else {
                b.disabled = false;
                b.textContent = r.error || 'Nothing to sort';
            }
        });
        return b;
    };
    const changesButton = () => {
        const b = el('button', 'btn', 'Changes');
        b.type = 'button';
        b.addEventListener('click', () => go('changes'));
        return b;
    };

    async function showFolders() {
        host().replaceChildren(tabs('folders'), el('div', 'empty', 'Loading…'));
        const [trips, places, people] = await loadAll();
        const page = [tabs('folders')];
        if (trips.length)
            page.push(el('div', 'band', `Trips · ${trips.length}`), albumsButton(), tripCovers(trips, trips.length));
        if (places.length)
            page.push(el('div', 'band', `Places · ${places.length}`), placeCovers(places, places.length));
        if (people.length)
            page.push(el('div', 'band', `People · ${people.length}`), personFaces(people, people.length));
        if (page.length === 1)
            page.push(
                el('div', 'empty', 'No folders yet. Trips, places and people appear while your pictures are read.')
            );
        host().replaceChildren(...page);
    }

    window.PicturesUI = {
        pages: {
            photos: showPhotosHome,
            folders: showFolders,
            library: showLibrary,
        },
        async show(page, params) {
            try {
                await this.pages[page](params);
            } catch (e) {
                host().replaceChildren(el('div', 'empty', `Could not load this page: ${e.message}`));
            }
        },
    };
})();
