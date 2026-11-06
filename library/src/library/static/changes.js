'use strict';
/* The Changes page and the confirmation window. Nothing that writes to your files happens without you pressing Confirm here. All text is added with textContent. */
(() => {
    const $ = (s) => document.querySelector(s);
    const el = (tag, cls, text) => {
        const e = document.createElement(tag);
        if (cls) e.className = cls;
        if (text != null) e.textContent = text;
        return e;
    };
    const getJson = async (path) => (await fetch(path, { headers: { Accept: 'application/json' } })).json();
    const post = async (path, body) =>
        (
            await fetch(path, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Library': '1' },
                body: JSON.stringify(body),
            })
        ).json();
    const box = () => $('#window');
    const closeWindow = () => {
        box().hidden = true;
        box().replaceChildren();
        document.body.style.overflow = '';
    };

    function openWindow(...parts) {
        const dialog = el('div', 'dialog');
        dialog.append(...parts);
        box().replaceChildren(dialog);
        box().hidden = false;
        document.body.style.overflow = 'hidden';
        return dialog;
    }
    const buttons = (...items) => {
        const row = el('div', 'dialog-actions');
        row.append(...items);
        return row;
    };
    const button = (label, cls, onClick) => {
        const b = el('button', cls, label);
        b.type = 'button';
        b.addEventListener('click', onClick);
        return b;
    };

    /** The window for one prepared change: everything it would do, what is wrong with it now, and Confirm / Cancel. */
    async function review(id) {
        const d = await getJson(`/api/change?id=${encodeURIComponent(id)}`);
        if (d.ok === false)
            return openWindow(
                el('h2', '', 'Not available'),
                el('p', 'muted', d.error),
                buttons(button('Close', 'btn', closeWindow))
            );
        const title = el(
            'h2',
            '',
            d.kind === 'delete'
                ? 'Delete these pictures?'
                : d.kind === 'export'
                  ? 'Copy these pictures?'
                  : 'Move these pictures?'
        );
        title.id = 'window-title';
        const summary = el(
            'p',
            '',
            `${d.label}. ${d.files.toLocaleString()} file${d.files === 1 ? '' : 's'}, ${d.megabytes} MB, into ${d.into}.`
        );
        const note = el(
            'p',
            'muted',
            d.kind === 'export' || d.kind === 'file_copy'
                ? 'The originals stay where they are. Nothing is changed until you press Confirm.'
                : d.kind === 'delete'
                  ? 'They are moved to a trash folder inside your photo folder, not erased, and you can put them back with Undo.'
                  : 'The files are moved, the library follows them, and you can put them back with Undo.'
        );
        const list = el('div', 'dialog-list');
        for (const f of d.list) {
            const row = el('div', 'dialog-row');
            row.append(el('b', '', f.name), el('span', 'muted', `${f.from}  →  ${f.to}`));
            list.append(row);
        }
        if (d.files > d.list.length)
            list.append(el('div', 'muted', `and ${(d.files - d.list.length).toLocaleString()} more`));
        const problems = el('div', 'dialog-problems');
        (d.problems || []).forEach((p) => problems.append(el('p', '', p)));
        const result = el('p', 'dialog-result');
        const confirm = button(
            d.kind === 'delete' ? 'Delete' : d.kind === 'export' || d.kind === 'file_copy' ? 'Copy' : 'Move',
            d.kind === 'delete' ? 'btn danger' : 'btn primary',
            async () => {
                confirm.disabled = true;
                const r = await post('/api/change/confirm', { id, nonce: d.nonce });
                result.textContent = r.ok ? `Done: ${r.text}` : r.error || 'It was not done.';
                result.className = 'dialog-result ' + (r.ok ? 'good' : 'bad');
                confirm.hidden = true;
                cancel.textContent = 'Close';
                cancel.onclick = () => {
                    closeWindow();
                    location.hash = '#/changes';
                    show({});
                };
            }
        );
        const cancel = button('Cancel', 'btn', async () => {
            await post('/api/change/cancel', { id });
            closeWindow();
            show({});
        });
        confirm.disabled = !d.nonce || (d.problems || []).length > 0;
        if (d.status !== 'pending') {
            result.textContent =
                d.status === 'expired'
                    ? 'This was prepared more than an hour ago. Ask for it again.'
                    : `This change is ${d.status}.`;
        }
        openWindow(title, summary, note, problems, list, result, buttons(cancel, ...(d.nonce ? [confirm] : [])));
    }

    /** Putting a move or a delete back: one more question, because it moves files too. */
    function undoWindow(change) {
        const title = el('h2', '', 'Put these back?');
        title.id = 'window-title';
        const result = el('p', 'dialog-result');
        const yes = button('Put back', 'btn primary', async () => {
            yes.disabled = true;
            const r = await post('/api/change/undo', { batch: change.undo_number });
            result.textContent = r.ok ? `Done: ${r.text}` : r.error || 'It was not done.';
            result.className = 'dialog-result ' + (r.ok ? 'good' : 'bad');
            yes.hidden = true;
            close.textContent = 'Close';
        });
        const close = button('Cancel', 'btn', () => {
            closeWindow();
            show({});
        });
        openWindow(
            title,
            el('p', '', `${change.label}. Every file goes back where it was; nothing is overwritten.`),
            result,
            buttons(close, yes)
        );
    }

    async function show(params) {
        const host = $('#page-changes');
        const o = await getJson('/api/changes');
        const section = (title, rows, empty, action) => {
            const wrap = el('div', 'changes');
            wrap.append(el('h2', '', title));
            if (!rows.length) wrap.append(el('p', 'muted', empty));
            for (const c of rows) {
                const row = el('div', 'change');
                const text = el('div');
                text.append(el('b', '', c.label), el('span', 'muted', c.result || `${c.files.toLocaleString()} files`));
                row.append(text);
                const a = action(c);
                if (a) row.append(a);
                wrap.append(row);
            }
            return wrap;
        };
        host.replaceChildren(
            section(
                'Waiting for you',
                o.waiting,
                'Nothing is waiting. Changes to your pictures appear here for you to review and confirm.',
                (c) => button('Review', 'btn primary', () => review(c.id))
            ),
            section('Done lately', o.history, 'Nothing yet.', (c) =>
                c.undo_number ? button('Undo', 'btn', () => undoWindow(c)) : el('span', 'muted', c.status)
            )
        );
        if (params && params.id) await review(params.id);
    }

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !box().hidden) closeWindow();
    });
    window.ChangesUI = { show };
})();
