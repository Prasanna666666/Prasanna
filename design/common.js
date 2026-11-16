/* The page helpers every app shares, written once (copied next to each app by scripts/sync-design.sh; a test fails when a copy differs).
   All text goes in with textContent or createTextNode, never as markup, unless a caller passes `html` on purpose. */
'use strict';
window.UI = (() => {
    // el('div', 'card', 'text'): an element with a class and plain text.
    const el = (tag, cls, text) => {
        const node = document.createElement(tag);
        if (cls) node.className = cls;
        if (text != null) node.textContent = text;
        return node;
    };
    // h('button', {class: 'pill', onclick: fn, type: 'button'}, 'children', node, [more]): an element with attributes, listeners and children.
    function h(tag, props, ...kids) {
        const node = document.createElement(tag);
        for (const [k, v] of Object.entries(props || {})) {
            if (v === false || v == null) continue;
            if (k === 'class') node.className = v;
            else if (k === 'html') node.innerHTML = v;
            else if (k === 'style' && typeof v === 'object') Object.assign(node.style, v);
            else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
            else node.setAttribute(k, v === true ? '' : v);
        }
        for (const kid of kids.flat(9)) {
            if (kid != null && kid !== false) node.append(kid.nodeType ? kid : document.createTextNode(kid));
        }
        return node;
    }
    const $ = (selector, root = document) => root.querySelector(selector);
    const getJson = async (path) => (await fetch(path, { headers: { Accept: 'application/json' } })).json();
    return { el, h, $, getJson };
})();
