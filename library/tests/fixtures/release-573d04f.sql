-- Written by the code of commit 573d04f (invented rows only): iterdump() of a database it created and filled.
BEGIN TRANSACTION;
CREATE TABLE _migrations (module TEXT PRIMARY KEY, version INTEGER NOT NULL);
INSERT INTO "_migrations" VALUES('library',14);
CREATE TABLE cases (
        id INTEGER PRIMARY KEY,
        input_hash TEXT NOT NULL UNIQUE,         -- which pieces, as they were when it was read: a changed matter is read again
        members TEXT NOT NULL,                   -- the ids of its pieces
        summary TEXT NOT NULL DEFAULT '',        -- what was understood of it as a whole, every claim with a quote ('' = not yet)
        tries INTEGER NOT NULL DEFAULT 0
    , rank INTEGER NOT NULL DEFAULT 99);
CREATE TABLE documents (
        id INTEGER PRIMARY KEY,
        sha256 TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        kind TEXT NOT NULL,                      -- how it was read: pdf, image, email, sheet ...
        text TEXT NOT NULL,
        area TEXT NOT NULL DEFAULT '',           -- where it came from: a collection folder you named (finance, health ...), 'mail', or '' (the inbox)
        data TEXT NOT NULL DEFAULT '',           -- structured rows or lines, as JSON
        parsed_at TEXT,
        facts TEXT NOT NULL DEFAULT '',          -- what the model said it is (kind, who, when, how much), every amount and date verified, as JSON
        judged INTEGER NOT NULL DEFAULT 0,       -- 0 not yet, 1 read by the model, 2 not worth it
        ready INTEGER,                           -- the order in which documents became ready
        created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    , fact_kind TEXT, source TEXT NOT NULL DEFAULT '', case_id INTEGER, tries INTEGER NOT NULL DEFAULT 0, fact_apps TEXT, promised INTEGER NOT NULL DEFAULT 0, sig TEXT);
INSERT INTO "documents" VALUES(1,'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','invoice-ziggo.pdf','pdf','FACTUUR Ziggo total 60,50 EUR','','',NULL,'',0,NULL,'2026-11-17 09:44:46',NULL,'',NULL,0,NULL,0,NULL);
INSERT INTO "documents" VALUES(2,'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','blood-test.pdf','pdf','Glucose 5,2 mmol/L range 4 - 6','','',NULL,'',0,NULL,'2026-11-17 09:44:46',NULL,'',NULL,0,NULL,0,NULL);
CREATE TABLE file_moves (
        id INTEGER PRIMARY KEY,
        batch TEXT NOT NULL,                     -- the journal number a filing can be undone with
        src TEXT NOT NULL,
        dst TEXT NOT NULL,
        op TEXT NOT NULL,                        -- file_move | file_copy
        status TEXT NOT NULL,                    -- pending (written before the file is touched) | done | failed | undone
        at REAL NOT NULL
    );
CREATE TABLE links (
        sha_a TEXT NOT NULL,                     -- two pieces (by content) and whether reading them showed they are one matter
        sha_b TEXT NOT NULL,
        same INTEGER NOT NULL,
        PRIMARY KEY (sha_a, sha_b)
    );
CREATE TABLE pending_changes (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,                      -- move | albums | delete | export | file_move | file_copy
        label TEXT NOT NULL,
        dest TEXT NOT NULL,
        entries TEXT NOT NULL,                   -- [[item id, from, to, size, modified]], what would happen and what each file looked like when it was prepared
        nonce TEXT NOT NULL,                     -- given only to the confirmation window when it is opened
        created REAL NOT NULL,
        viewed REAL,                             -- when the window was opened: nothing is confirmed without having been looked at
        status TEXT NOT NULL DEFAULT 'pending',  -- pending | done | cancelled | failed
        decided REAL,
        batch TEXT,                              -- the journal number a done move can be undone with
        result TEXT NOT NULL DEFAULT ''
    );
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE sigs (doc_id INTEGER NOT NULL, band INTEGER NOT NULL, h INTEGER NOT NULL);
CREATE TABLE trace (
        id INTEGER PRIMARY KEY,
        run TEXT NOT NULL,                       -- which read (when it started)
        at TEXT NOT NULL,
        name TEXT NOT NULL,                      -- the file
        step TEXT NOT NULL,                      -- what was done to it
        detail TEXT NOT NULL DEFAULT '',         -- what came of it (never what the file says)
        seconds REAL NOT NULL DEFAULT 0
    );
CREATE TABLE trip_items (
        id INTEGER PRIMARY KEY,
        trip TEXT NOT NULL,                      -- which trip (a short key from its place and first day)
        section TEXT NOT NULL DEFAULT '',        -- Documents, Money, Clothes ...
        text TEXT NOT NULL,
        done INTEGER NOT NULL DEFAULT 0,         -- 1 = packed
        pos INTEGER NOT NULL DEFAULT 0
    );
CREATE TABLE write_audit (
        id INTEGER PRIMARY KEY,
        at REAL NOT NULL,
        change_id TEXT NOT NULL,
        action TEXT NOT NULL,                    -- prepared | opened | confirmed | refused | cancelled | undone
        detail TEXT NOT NULL DEFAULT ''
    );
CREATE INDEX documents_ready ON documents (ready);
CREATE INDEX file_moves_batch ON file_moves (batch);
CREATE INDEX documents_fact_kind ON documents (judged, fact_kind);
CREATE INDEX documents_area ON documents (area);
CREATE TRIGGER documents_kind_new AFTER INSERT ON documents WHEN NEW.facts<>'' BEGIN
        UPDATE documents SET fact_kind=json_extract(NEW.facts,'$.kind') WHERE id=NEW.id;
    END;
CREATE TRIGGER documents_kind_changed AFTER UPDATE OF facts ON documents BEGIN
        UPDATE documents SET fact_kind=CASE WHEN NEW.facts<>'' THEN json_extract(NEW.facts,'$.kind') END WHERE id=NEW.id;
    END;
CREATE INDEX trip_items_trip ON trip_items (trip);
CREATE INDEX documents_source ON documents (source) WHERE source <> '';
CREATE INDEX documents_case ON documents (case_id);
CREATE INDEX trace_run ON trace (run, id);
CREATE INDEX cases_rank ON cases (rank, id);
CREATE INDEX documents_fact_apps ON documents (judged, fact_apps);
CREATE TRIGGER documents_apps_new AFTER INSERT ON documents WHEN NEW.facts<>'' AND json_valid(NEW.facts) BEGIN
        UPDATE documents SET fact_apps = '|' || COALESCE((SELECT group_concat(value, '|') FROM json_each(json_extract(NEW.facts, '$.apps'))), '') || '|' WHERE id=NEW.id;
    END;
CREATE TRIGGER documents_apps_changed AFTER UPDATE OF facts ON documents BEGIN
        UPDATE documents SET fact_apps = CASE WHEN NEW.facts<>'' AND json_valid(NEW.facts)
            THEN '|' || COALESCE((SELECT group_concat(value, '|') FROM json_each(json_extract(NEW.facts, '$.apps'))), '') || '|' END WHERE id=NEW.id;
    END;
CREATE INDEX sigs_lookup ON sigs (band, h);
COMMIT;
