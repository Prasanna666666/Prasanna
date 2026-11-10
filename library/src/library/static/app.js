'use strict';
(() => {
    const $ = (s) => document.querySelector(s);
    const EMBEDDED = window.parent !== window;
    const state = { kind: '', q: '', source: 'files' };

    const api = (path) => fetch(path, { headers: { Accept: 'application/json' } }).then((r) => r.json());
    const el = (tag, props, ...kids) => {
        const n = Object.assign(document.createElement(tag), props || {});
        n.append(...kids);
        return n;
    };
    const toParent = (m) =>
        window.parent.postMessage({ atlas: 1, ...m }, (location.ancestorOrigins && location.ancestorOrigins[0]) || '*');

    const subtitle = (d) =>
        [d.kind.replace('_', ' '), d.facts.party, d.facts.date || d.facts.start_date, d.facts.place]
            .filter(Boolean)
            .join(' · ');

    function showList(docs) {
        const list = $('#list');
        list.replaceChildren();
        $('#doc').hidden = true;
        if (!docs.length) {
            list.append(el('p', { className: 'muted' }, 'Nothing here yet. Press Update.'));
        }
        for (const d of docs) {
            const card = el(
                'button',
                { className: 'card', type: 'button' },
                el('b', {}, d.facts.title || d.name),
                el('span', {}, subtitle(d) || d.name)
            );
            card.addEventListener('click', () => (location.hash = `#/doc/${d.id}`));
            list.append(card);
        }
    }

    async function loadList() {
        if (state.q) {
            const r = await api(`/api/search?q=${encodeURIComponent(state.q)}`);
            const list = $('#list');
            list.replaceChildren();
            if (!r.results.length) {
                list.append(el('p', { className: 'muted' }, 'Nothing found.'));
            }
            for (const h of r.results) {
                const card = el(
                    'button',
                    { className: 'card', type: 'button' },
                    el('b', {}, h.title),
                    el('span', {}, h.subtitle)
                );
                card.addEventListener('click', () => (location.hash = h.link));
                list.append(card);
            }
            return;
        }
        const r = await api(
            `/api/documents?limit=200&source=${state.source}${state.kind ? `&kind=${encodeURIComponent(state.kind)}` : ''}`
        );
        showList(r.documents.reverse());
    }

    async function loadKinds() {
        const s = await api('/api/status');
        $('#count').textContent = `${s.documents} files and mails`;
        const box = $('#kinds');
        box.replaceChildren();
        for (const k of [{ kind: '', count: s.read }, ...s.kinds.filter((x) => x.kind !== 'other')]) {
            const label = k.kind ? k.kind.replace('_', ' ') : 'All';
            const b = el('button', { type: 'button' }, `${label}`);
            b.setAttribute('aria-pressed', String(state.kind === k.kind));
            b.addEventListener('click', () => {
                state.kind = k.kind;
                state.q = '';
                $('#q').value = '';
                loadKinds();
                loadList();
            });
            box.append(b);
        }
    }

    async function openDoc(id) {
        const d = await api(`/api/document?id=${encodeURIComponent(id)}`);
        const box = $('#doc');
        box.replaceChildren(
            el('h2', {}, d.facts?.title || d.name || 'Document'),
            el('p', { className: 'muted' }, d.name ? `${d.name} · ${d.kind}` : ''),
            el('pre', {}, (d.text || '').slice(0, 20000))
        );
        box.hidden = false;
        $('#list').replaceChildren();
    }

    // ---------------------------------------------------------------- sections: documents, and (when pictures are set up) the picture library
    const SECTIONS = [
        ['documents', 'Documents'],
        ['mail', 'Emails'],
        ['library', 'Photos'],
        ['trips', 'Trips'],
        ['places', 'Places'],
        ['people', 'People'],
        ['changes', 'Changes'],
    ];
    let withPictures = false;

    function tabs(current) {
        const box = $('#tabs');
        box.replaceChildren();
        for (const [id, label] of SECTIONS) {
            if (!withPictures && !['documents', 'mail'].includes(id)) continue;
            const b = el('button', { type: 'button' }, label);
            b.setAttribute('aria-pressed', String(id === current));
            b.addEventListener('click', () => (location.hash = id === 'documents' ? '#/home' : `#/${id}`));
            box.append(b);
        }
    }

    function route() {
        const [path, query] = location.hash.replace(/^#\//, '').split('?');
        if (window.HealthTravelUI?.pages.includes(path)) {
            // the Travel and Health apps have their own page; the Atlas menu does the navigation
            ['#page-documents', '#page-pictures', '#page-changes'].forEach((id) => ($(id).hidden = true));
            $('#page-apps').hidden = false;
            return window.HealthTravelUI.show(path, Object.fromEntries(new URLSearchParams(query || '')));
        }
        $('#page-apps').hidden = true;
        const known = SECTIONS.some(([id]) => id === path) && path !== 'documents';
        const tab = known && (withPictures || path === 'mail') ? path : 'documents';
        const section = tab === 'mail' ? 'documents' : tab; // emails are the document list, filtered to mail
        const source = tab === 'mail' ? 'mail' : 'files';
        state.source = source;
        tabs(tab);
        if (known && path !== 'mail' && !withPictures) {
            $('#page-documents').hidden = false;
            $('#page-pictures').hidden = true;
            $('#page-changes').hidden = true;
            $('#doc').hidden = true;
            $('#list').replaceChildren(
                el(
                    'p',
                    { className: 'muted' },
                    'Photos are not connected. The photo drive was not found when Documents started. Connect it, then start Documents again.'
                )
            );
            return;
        }
        $('#page-documents').hidden = section !== 'documents';
        $('#page-pictures').hidden = section === 'documents' || section === 'changes';
        $('#page-changes').hidden = section !== 'changes';
        const params = Object.fromEntries(new URLSearchParams(query || ''));
        if (section === 'changes') return window.ChangesUI.show(params);
        if (section !== 'documents') {
            return window.PicturesUI.show(section, params);
        }
        const m = location.hash.match(/^#\/doc\/(\d+)$/);
        if (m) openDoc(m[1]);
        else loadList();
    }

    $('#find').addEventListener('submit', (e) => {
        e.preventDefault();
        state.q = $('#q').value.trim();
        location.hash = '#/home';
        loadList();
    });
    window.addEventListener('hashchange', () => {
        route();
        if (EMBEDDED) toParent({ type: 'route', hash: location.hash });
    });
    if (EMBEDDED) {
        document.documentElement.classList.add('embedded');
        window.addEventListener('message', (event) => {
            const m = event.data;
            if (event.source !== window.parent || !m || m.atlas !== 1) return;
            if (m.type === 'navigate' && typeof m.hash === 'string') {
                location.hash = m.hash;
            } else if (m.type === 'theme' && ['dark', 'light'].includes(m.mode)) {
                document.documentElement.dataset.theme = m.mode;
            }
        });
        toParent({ type: 'ready' });
    }
    api('/api/pictures/status')
        .then((r) => {
            withPictures = r.ok !== false && r.pictures !== undefined;
        })
        .catch(() => {})
        .finally(() => {
            loadKinds();
            route();
        });
})();
