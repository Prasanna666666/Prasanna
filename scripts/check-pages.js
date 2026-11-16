// Opens every page of the three apps in a real browser and fails on a script error or a WCAG 2.1 AA violation (axe-core).
// Needs the apps running (Finance :8501, Documents :8502, Atlas :8000) and: npm i axe-core playwright. Run: node scripts/check-pages.js
const { chromium } = require("playwright");
const fs = require("fs");
const axe = fs.readFileSync(
    process.env.AXE_JS || require.resolve("axe-core/axe.min.js"),
    "utf8",
);
const targets = [
    [
        "finance",
        "http://127.0.0.1:8501/",
        ["#/home", "#/expenses", "#/plan", "#/documents", "#/savings", "#/tax"],
    ],
    [
        "library",
        "http://127.0.0.1:8502/",
        ["#/", "#/pictures", "#/changes", "#/travel", "#/health"],
    ],
    [
        "atlas",
        "http://127.0.0.1:8000/",
        ["#/", "#/home", "#/documents", "#/finance"],
    ],
];
(async () => {
    const browser = await chromium.launch();
    let bad = 0;
    for (const [name, base, routes] of targets) {
        const ctx = await browser.newContext({
            viewport: { width: 1280, height: 900 },
        });
        for (const r of routes) {
            const page = await ctx.newPage();
            const errors = [];
            page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
            page.on(
                "console",
                (m) =>
                    m.type() === "error" && errors.push("console: " + m.text()),
            );
            await page
                .goto(base + r, { waitUntil: "networkidle", timeout: 20000 })
                .catch((e) => errors.push("goto: " + e.message));
            await page.waitForTimeout(700);
            const hasUI = await page.evaluate(
                () =>
                    typeof window.UI === "object" &&
                    typeof window.UI.h === "function",
            );
            await page.evaluate(axe);
            const res = await page.evaluate(() =>
                axe.run({ runOnly: ["wcag2a", "wcag2aa", "wcag21aa"] }),
            );
            const filtered = errors.filter(
                (e) =>
                    !/favicon|Failed to load resource: the server responded with a status of (4|5)0/.test(
                        e,
                    ),
            );
            console.log(
                `${name} ${r}: UI=${hasUI} errors=${filtered.length} a11y=${res.violations.length}`,
            );
            for (const e of filtered) console.log("   ", e.slice(0, 160));
            for (const v of res.violations)
                console.log("    a11y", v.id, v.nodes[0].target.join(" "));
            bad += filtered.length + res.violations.length + (hasUI ? 0 : 1);
            await page.close();
        }
        await ctx.close();
    }
    await browser.close();
    console.log("PROBLEMS", bad);
})();
