'use strict';
/* The shell of the Documents service's pages. Atlas shows them inside its own frame: Health, Travel and Photos each draw their own page (healthtravel.js, pictures.js,
   changes.js); this file routes between them, shows one document, and gives them their tab bar. Opened on its own it only points to Atlas. */
(() => {
    const $ = (s) => document.querySelector(s);
    const EMBEDDED = window.parent !== window;

    const api = (path) => fetch(path, { headers: { Accept: 'application/json' } }).then((r) => r.json());
    const el = (tag, props, ...kids) => {
        const n = Object.assign(document.createElement(tag), props || {});
        n.append(...kids);
        return n;
    };
    // the tab bar at the top of an app's page: [[page, label], ...]; the Atlas menu lists the apps, the tabs are inside each one
    window.AppTabs = (items, current) => {
        const nav = el('nav', { className: 'apptabs' });
        for (const [id, label] of items) {
            const b = el('button', { type: 'button' }, label);
            b.setAttribute('aria-pressed', String(id === current));
            b.addEventListener('click', () => (location.hash = `#/${id}`));
            nav.append(b);
        }
        return nav;
    };
    const toParent = (m) =>
        window.parent.postMessage({ atlas: 1, ...m }, (location.ancestorOrigins && location.ancestorOrigins[0]) || '*');

    // one document: what it says, named by what it says
    async function openDoc(id) {
        const d = await api(`/api/document?id=${encodeURIComponent(id)}`);
        $('#doc').replaceChildren(
            el('h2', {}, d.title || d.facts?.title || d.name || 'Document'),
            el('p', { className: 'muted' }, d.name ? `${d.name} · ${d.kind}` : ''),
            el('pre', {}, (d.text || '').slice(0, 20000))
        );
    }

    const PICTURE_PAGES = ['photos', 'folders', 'library', 'changes'];
    let withPictures = false;

    function show(which) {
        for (const id of ['doc', 'page-pictures', 'page-changes', 'page-apps', 'standalone']) {
            $(`#${id}`).hidden = id !== which;
        }
    }

    function route() {
        const [path, query] = location.hash.replace(/^#\//, '').split('?');
        const params = Object.fromEntries(new URLSearchParams(query || ''));
        if (window.HealthTravelUI?.pages.includes(path)) {
            show('page-apps');
            return window.HealthTravelUI.show(path, params);
        }
        const doc = location.hash.match(/^#\/doc\/(\d+)$/);
        if (doc) {
            show('doc');
            return openDoc(doc[1]);
        }
        if (PICTURE_PAGES.includes(path)) {
            if (!withPictures) {
                show('page-pictures');
                return $('#page-pictures').replaceChildren(
                    el(
                        'div',
                        { className: 'empty' },
                        'Photos are not connected. The photo drive was not found when Atlas started. Connect it and start Atlas again.'
                    )
                );
            }
            if (path === 'changes') {
                show('page-changes');
                return window.ChangesUI.show(params);
            }
            show('page-pictures');
            return window.PicturesUI.show(path, params);
        }
        show('standalone'); // opened on its own: these pages belong inside Atlas
    }

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
        .finally(route);
})();
