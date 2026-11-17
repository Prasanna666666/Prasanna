-- Written by the code of commit 5f7fa48 (invented rows only): `sqlite3.Connection.iterdump()` of a database it created and filled.
BEGIN TRANSACTION;
CREATE TABLE _migrations (module TEXT PRIMARY KEY, version INTEGER NOT NULL);
INSERT INTO "_migrations" VALUES('people',1);
INSERT INTO "_migrations" VALUES('tasks',1);
INSERT INTO "_migrations" VALUES('notes',2);
INSERT INTO "_migrations" VALUES('money',15);
INSERT INTO "_migrations" VALUES('events',2);
INSERT INTO "_migrations" VALUES('documents',3);
CREATE TABLE audit_log (                                                      -- every import and correction, each entry sealed with the one before
        id INTEGER PRIMARY KEY, at TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL, prev TEXT NOT NULL, hash TEXT NOT NULL
    );
CREATE TABLE budgets (category TEXT PRIMARY KEY, monthly_minor INTEGER NOT NULL);
CREATE TABLE documents (
        id INTEGER PRIMARY KEY,
        sha256 TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        kind TEXT NOT NULL,
        text TEXT NOT NULL,
        tags TEXT NOT NULL DEFAULT '',
        parsed_at TEXT,
        created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    , area TEXT NOT NULL DEFAULT '', data TEXT NOT NULL DEFAULT '', facts TEXT NOT NULL DEFAULT '');
CREATE TABLE events (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL COLLATE NOCASE UNIQUE,
        main TEXT NOT NULL CHECK (main IN ('sports','events','trips','cancellations','others')),
        starts TEXT, ends TEXT,
        confirmed INTEGER NOT NULL DEFAULT 1,   -- 0 = proposed by the model, waiting for you
        created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
CREATE TABLE finance_docs (
        sha256 TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT '',
        party TEXT NOT NULL DEFAULT '', doc_date TEXT, due_date TEXT, reference TEXT NOT NULL DEFAULT '',
        total_minor INTEGER, vat_minor INTEGER, currency TEXT NOT NULL DEFAULT ''
    , gross_minor INTEGER, tax_minor INTEGER, net_minor INTEGER, period TEXT NOT NULL DEFAULT '', start_date TEXT, end_date TEXT, place TEXT NOT NULL DEFAULT '', concept TEXT NOT NULL DEFAULT '');
CREATE TABLE findings (                                                        -- what each verifier agent concluded
        id INTEGER PRIMARY KEY, agent TEXT NOT NULL, level TEXT NOT NULL CHECK (level IN ('ok','warn','fail')),
        subject TEXT NOT NULL, message TEXT NOT NULL, cross INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
CREATE TABLE goals (                                           -- something you are saving for
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, target_minor INTEGER NOT NULL, by_date TEXT, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
CREATE TABLE holdings (                                        -- what you typed in: investments, assets (house, car), debts (loan, mortgage)
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL CHECK (kind IN ('investment','asset','debt')),
        value_minor INTEGER NOT NULL, units REAL, price_minor INTEGER, currency TEXT NOT NULL DEFAULT 'EUR', as_of TEXT NOT NULL
    , cost_minor INTEGER);
INSERT INTO "holdings" VALUES(1,'Index fund','investment',500000,NULL,NULL,'EUR','2026-09-30',NULL);
CREATE TABLE important_dates (
        id INTEGER PRIMARY KEY,
        person_id INTEGER NOT NULL REFERENCES people(id) ON DELETE CASCADE,
        label TEXT NOT NULL,
        month INTEGER NOT NULL, day INTEGER NOT NULL,
        year INTEGER                          -- original year, if known (for ages / anniversaries)
    );
CREATE TABLE kind_concepts (kind TEXT PRIMARY KEY, concept TEXT NOT NULL);
CREATE TABLE mail_skipped (sha256 TEXT PRIMARY KEY);
CREATE TABLE merchant_alias (alias TEXT PRIMARY KEY, canonical TEXT NOT NULL);
CREATE TABLE merchant_categories (merchant TEXT PRIMARY KEY, category TEXT NOT NULL);
CREATE TABLE merchant_rules (merchant TEXT PRIMARY KEY, category TEXT NOT NULL);
INSERT INTO "merchant_rules" VALUES('albert heijn','groceries');
CREATE TABLE notes (
        id INTEGER PRIMARY KEY,
        title TEXT NOT NULL DEFAULT '',
        body TEXT NOT NULL,
        tags TEXT NOT NULL DEFAULT '',     -- comma separated, lowercase
        person_id INTEGER,
        created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    , source_id TEXT);
INSERT INTO "notes" VALUES(1,'','A note','',NULL,'2026-11-17 09:41:59','2026-11-17 09:41:59',NULL);
CREATE TABLE payslips (
        sha256 TEXT PRIMARY KEY, name TEXT NOT NULL, period TEXT NOT NULL, gross_minor INTEGER NOT NULL, net_minor INTEGER NOT NULL,
        tax_minor INTEGER, pension_minor INTEGER, holiday_minor INTEGER
    );
INSERT INTO "payslips" VALUES('p1','slip.pdf','2026-09',350000,251260,81240,17500,28000);
CREATE TABLE people (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        relation TEXT NOT NULL DEFAULT '',   -- mother, father, spouse, friend...
        about TEXT NOT NULL DEFAULT ''       -- health notes, preferences, anything useful
    );
INSERT INTO "people" VALUES(1,'Alex Example','','');
CREATE TABLE rates (day TEXT NOT NULL, currency TEXT NOT NULL, per_eur TEXT NOT NULL, PRIMARY KEY (day, currency));
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO "settings" VALUES('currency','EUR');
CREATE TABLE statement_files (
        sha256 TEXT PRIMARY KEY, name TEXT NOT NULL, found INTEGER NOT NULL, added INTEGER NOT NULL,
        at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    , status TEXT NOT NULL DEFAULT 'ok', issues TEXT NOT NULL DEFAULT '', account TEXT NOT NULL DEFAULT '', period_start TEXT, period_end TEXT, opening_minor INTEGER, closing_minor INTEGER, proofs TEXT NOT NULL DEFAULT '', currency TEXT NOT NULL DEFAULT '');
INSERT INTO "statement_files" VALUES('s1','a.pdf',4,4,'2026-11-17 09:41:59','verified','','NL00TEST0000000001','2026-09-01','2026-09-30',0,85656,'totals','EUR');
CREATE TABLE tasks (
        id INTEGER PRIMARY KEY,
        title TEXT NOT NULL,
        due TEXT,                         -- 'YYYY-MM-DD' or 'YYYY-MM-DDTHH:MM'
        recurrence TEXT NOT NULL DEFAULT 'none',
        done INTEGER NOT NULL DEFAULT 0,
        person_id INTEGER,                -- optional link to people.id
        created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
INSERT INTO "tasks" VALUES(1,'Renew insurance',NULL,'none',0,NULL,'2026-11-17 09:41:59');
CREATE TABLE transactions (
        id INTEGER PRIMARY KEY,
        day TEXT NOT NULL,
        amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
        kind TEXT NOT NULL CHECK (kind IN ('expense','income')),
        category TEXT NOT NULL DEFAULT 'other',
        note TEXT NOT NULL DEFAULT '',
        created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    , ref TEXT, source TEXT NOT NULL DEFAULT '', balance_minor INTEGER, auto INTEGER NOT NULL DEFAULT 0, currency TEXT NOT NULL DEFAULT '', account TEXT NOT NULL DEFAULT '', transfer_id INTEGER, eur_minor INTEGER, rate TEXT NOT NULL DEFAULT '', rate_source TEXT NOT NULL DEFAULT '', refund_of INTEGER, event_id INTEGER REFERENCES events(id) ON DELETE SET NULL, sub TEXT NOT NULL DEFAULT '', event_checked INTEGER NOT NULL DEFAULT 0);
INSERT INTO "transactions" VALUES(1,'2026-09-01',200000,'income','salary','Acme BV Salaris','2026-11-17 09:41:59','r1','a.pdf',NULL,0,'EUR','NL00TEST0000000001',NULL,NULL,'','',NULL,NULL,'',0);
INSERT INTO "transactions" VALUES(2,'2026-09-03',2345,'expense','groceries','Albert Heijn Utrecht','2026-11-17 09:41:59','r2','a.pdf',197655,1,'EUR','NL00TEST0000000001',NULL,NULL,'','',NULL,NULL,'',0);
INSERT INTO "transactions" VALUES(3,'2026-09-05',110000,'expense','housing','Huur september','2026-11-17 09:41:59','r3','a.pdf',87655,1,'EUR','NL00TEST0000000001',NULL,NULL,'','',NULL,NULL,'',0);
INSERT INTO "transactions" VALUES(4,'2026-09-09',1999,'expense','subscriptions','Streaming','2026-11-17 09:41:59','r4','a.pdf',85656,1,'EUR','NL00TEST0000000001',NULL,NULL,'','',NULL,NULL,'',0);
CREATE INDEX tasks_due ON tasks(done, due);
CREATE UNIQUE INDEX notes_source ON notes(source_id) WHERE source_id IS NOT NULL;
CREATE INDEX tx_day ON transactions(day);
CREATE UNIQUE INDEX tx_ref ON transactions(ref) WHERE ref IS NOT NULL;
CREATE INDEX finance_docs_kind ON finance_docs(kind, doc_date);
CREATE INDEX tx_account ON transactions(account, day);
CREATE INDEX tx_acc_amount ON transactions(account, amount_minor, day);
CREATE INDEX tx_refund ON transactions(refund_of) WHERE refund_of IS NOT NULL;
CREATE INDEX finance_docs_concept ON finance_docs(concept, doc_date);
CREATE INDEX tx_event ON transactions(event_id);
COMMIT;
