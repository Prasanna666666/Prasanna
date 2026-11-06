"use strict";
(() => {
    const $ = (s) => document.querySelector(s);
    const EMBEDDED = window.parent !== window;
    const state = { kind: "", q: "" };

    const api = (path) =>
        fetch(path, { headers: { Accept: "application/json" } }).then((r) =>
            r.json(),
        );
    const el = (tag, props, ...kids) => {
        const n = Object.assign(document.createElement(tag), props || {});
        n.append(...kids);
        return n;
    };
    const toParent = (m) =>
        window.parent.postMessage(
            { atlas: 1, ...m },
            (location.ancestorOrigins && location.ancestorOrigins[0]) || "*",
        );

    const subtitle = (d) =>
        [
            d.kind.replace("_", " "),
            d.facts.party,
            d.facts.date || d.facts.start_date,
            d.facts.place,
        ]
            .filter(Boolean)
            .join(" · ");

    function showList(docs) {
        const list = $("#list");
        list.replaceChildren();
        $("#doc").hidden = true;
        if (!docs.length) {
            list.append(
                el(
                    "p",
                    { className: "muted" },
                    "Nothing here yet. Press Update.",
                ),
            );
        }
        for (const d of docs) {
            const card = el(
                "button",
                { className: "card", type: "button" },
                el("b", {}, d.facts.title || d.name),
                el("span", {}, subtitle(d) || d.name),
            );
            card.addEventListener(
                "click",
                () => (location.hash = `#/doc/${d.id}`),
            );
            list.append(card);
        }
    }

    async function loadList() {
        if (state.q) {
            const r = await api(`/api/search?q=${encodeURIComponent(state.q)}`);
            const list = $("#list");
            list.replaceChildren();
            if (!r.results.length) {
                list.append(el("p", { className: "muted" }, "Nothing found."));
            }
            for (const h of r.results) {
                const card = el(
                    "button",
                    { className: "card", type: "button" },
                    el("b", {}, h.title),
                    el("span", {}, h.subtitle),
                );
                card.addEventListener("click", () => (location.hash = h.link));
                list.append(card);
            }
            return;
        }
        const r = await api(
            `/api/documents?limit=200${state.kind ? `&kind=${encodeURIComponent(state.kind)}` : ""}`,
        );
        showList(r.documents.reverse());
    }

    async function loadKinds() {
        const s = await api("/api/status");
        $("#count").textContent = `${s.documents} files and mails`;
        const box = $("#kinds");
        box.replaceChildren();
        for (const k of [
            { kind: "", count: s.read },
            ...s.kinds.filter((x) => x.kind !== "other"),
        ]) {
            const label = k.kind ? k.kind.replace("_", " ") : "All";
            const b = el("button", { type: "button" }, `${label}`);
            b.setAttribute("aria-pressed", String(state.kind === k.kind));
            b.addEventListener("click", () => {
                state.kind = k.kind;
                state.q = "";
                $("#q").value = "";
                loadKinds();
                loadList();
            });
            box.append(b);
        }
    }

    async function openDoc(id) {
        const d = await api(`/api/document?id=${encodeURIComponent(id)}`);
        const box = $("#doc");
        box.replaceChildren(
            el("h2", {}, d.facts?.title || d.name || "Document"),
            el(
                "p",
                { className: "muted" },
                d.name ? `${d.name} · ${d.kind}` : "",
            ),
            el("pre", {}, (d.text || "").slice(0, 20000)),
        );
        box.hidden = false;
        $("#list").replaceChildren();
    }

    // ---------------------------------------------------------------- sections: documents, and (when pictures are set up) the picture library
    const SECTIONS = [
        ["documents", "Documents"],
        ["library", "Library"],
        ["trips", "Trips"],
        ["places", "Places"],
        ["people", "People"],
    ];
    let withPictures = false;

    function tabs(current) {
        const box = $("#tabs");
        box.replaceChildren();
        if (!withPictures) return;
        for (const [id, label] of SECTIONS) {
            const b = el("button", { type: "button" }, label);
            b.setAttribute("aria-pressed", String(id === current));
            b.addEventListener(
                "click",
                () =>
                    (location.hash = id === "documents" ? "#/home" : `#/${id}`),
            );
            box.append(b);
        }
    }

    function route() {
        const [path, query] = location.hash.replace(/^#\//, "").split("?");
        const section =
            SECTIONS.some(([id]) => id === path) &&
            path !== "documents" &&
            withPictures
                ? path
                : "documents";
        tabs(section);
        $("#page-documents").hidden = section !== "documents";
        $("#page-pictures").hidden = section === "documents";
        if (section !== "documents") {
            return window.PicturesUI.show(
                section,
                Object.fromEntries(new URLSearchParams(query || "")),
            );
        }
        const m = location.hash.match(/^#\/doc\/(\d+)$/);
        if (m) openDoc(m[1]);
        else loadList();
    }

    $("#find").addEventListener("submit", (e) => {
        e.preventDefault();
        state.q = $("#q").value.trim();
        location.hash = "#/home";
        loadList();
    });
    window.addEventListener("hashchange", () => {
        route();
        if (EMBEDDED) toParent({ type: "route", hash: location.hash });
    });
    if (EMBEDDED) {
        document.documentElement.classList.add("embedded");
        window.addEventListener("message", (event) => {
            const m = event.data;
            if (event.source !== window.parent || !m || m.atlas !== 1) return;
            if (m.type === "navigate" && typeof m.hash === "string") {
                location.hash = m.hash;
            } else if (
                m.type === "theme" &&
                ["dark", "light"].includes(m.mode)
            ) {
                document.documentElement.dataset.theme = m.mode;
            }
        });
        toParent({ type: "ready" });
    }
    api("/api/pictures/status")
        .then((r) => {
            withPictures = r.ok !== false && r.pictures !== undefined;
        })
        .catch(() => {})
        .finally(() => {
            loadKinds();
            route();
        });
})();
