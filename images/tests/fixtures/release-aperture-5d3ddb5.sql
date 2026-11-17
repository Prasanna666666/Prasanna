-- Written by the released aperture code (commit 5d3ddb5 of branch aperture, the real older release; invented rows only): iterdump() of the index it created and filled. The full-text tables are left out; the current code creates them. iterdump() does not write `PRAGMA user_version`; the released database held 16 (read from it), so the line is added by hand at the end.
BEGIN TRANSACTION;
CREATE TABLE captions(
    item_id INTEGER PRIMARY KEY,
    caption TEXT NOT NULL,
    model   TEXT NOT NULL,
    created REAL NOT NULL
);
CREATE TABLE embeddings(
    item_id INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
    vec     BLOB NOT NULL                  -- float16, L2-normalised
);
CREATE TABLE events(                -- a trip or occasion: photos close in time (and place)
    id      INTEGER PRIMARY KEY,
    start   TEXT NOT NULL,
    stop    TEXT NOT NULL,
    n       INTEGER NOT NULL,
    place   TEXT NOT NULL DEFAULT '',
    country TEXT NOT NULL DEFAULT ''
);
CREATE TABLE face_ages(             -- the age model's estimate for each face, in years
    face_id INTEGER PRIMARY KEY REFERENCES faces(id) ON DELETE CASCADE,
    years   REAL NOT NULL
);
CREATE TABLE face_attributes(       -- expression and age group of each face, read from its saved crop
    face_id      INTEGER PRIMARY KEY REFERENCES faces(id) ON DELETE CASCADE,
    expression   TEXT NOT NULL,
    expression_p REAL NOT NULL,
    age          TEXT NOT NULL,
    age_p        REAL NOT NULL
);
CREATE TABLE faces(
    id        INTEGER PRIMARY KEY,
    item_id   INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    x1 REAL, y1 REAL, x2 REAL, y2 REAL,    -- normalised 0..1
    score     REAL NOT NULL DEFAULT 0,
    px        INTEGER NOT NULL DEFAULT 0,  -- shorter side of the face box in pixels
    emb       BLOB NOT NULL,               -- float32, L2-normalised
    person_id INTEGER REFERENCES people(id) ON DELETE SET NULL,
    locked    INTEGER NOT NULL DEFAULT 0,  -- 1 = decided by the user, never regrouped
    crop      TEXT
);
CREATE TABLE file_metadata(
    item_id        INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
    reader_version INTEGER NOT NULL,
    sha256         TEXT,
    data           TEXT NOT NULL,   -- JSON
    read_at        REAL NOT NULL
);
CREATE TABLE flags(
    item_id INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
    status  TEXT NOT NULL,
    reason  TEXT NOT NULL DEFAULT '',
    created REAL NOT NULL
);
PRAGMA writable_schema=ON;
CREATE TABLE items(
    id          INTEGER PRIMARY KEY,
    path        TEXT UNIQUE NOT NULL,      -- absolute path of the ORIGINAL (read-only)
    rel_path    TEXT NOT NULL DEFAULT '',
    meta_text   TEXT NOT NULL DEFAULT '',  -- lower-cased rel_path + camera + lens (path engine)
    kind        TEXT NOT NULL,             -- image | pdf | text
    size        INTEGER NOT NULL DEFAULT 0,
    mtime       REAL NOT NULL DEFAULT 0,
    width       INTEGER, height INTEGER,
    taken_at    TEXT,                      -- 'YYYY-MM-DD HH:MM:SS' (EXIF, else file date)
    camera      TEXT, lens TEXT,
    gps_lat     REAL, gps_lon REAL,
    place       TEXT,                      -- display: 'Bengaluru, India'
    place_text  TEXT NOT NULL DEFAULT '',  -- lower-cased names + alternates (place engine)
    exif_json   TEXT,
    thumb       TEXT, preview TEXT,        -- relative to the data folder
    meta_done   INTEGER NOT NULL DEFAULT 0,
    clip_done   INTEGER NOT NULL DEFAULT 0,
    faces_done  INTEGER NOT NULL DEFAULT 0,
    ocr_done    INTEGER NOT NULL DEFAULT 0,
    ocr_chars   INTEGER NOT NULL DEFAULT 0,
    error       TEXT,                      -- set when the item could not be indexed at all
    notes       TEXT,                      -- non-fatal per-stage warnings
    missing     INTEGER NOT NULL DEFAULT 0,
    indexed_at  REAL
, sha256 TEXT, sharp REAL, bright REAL, contrast REAL, taken_exif INTEGER NOT NULL DEFAULT 0, hue REAL, sat REAL, val REAL, gps_est_lat REAL, gps_est_lon REAL, gps_est_conf REAL, gps_est_place TEXT, gps_est_place_text TEXT NOT NULL DEFAULT '');
INSERT INTO "items" VALUES(1,'/Photos/2026/lisbon-1.jpg','','','photo',0,0.0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,'',NULL,NULL,NULL,0,0,0,0,0,NULL,NULL,0,NULL,NULL,NULL,NULL,NULL,0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,'');
INSERT INTO "items" VALUES(2,'/Photos/2026/lisbon-2.jpg','','','photo',0,0.0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,'',NULL,NULL,NULL,0,0,0,0,0,NULL,NULL,0,NULL,NULL,NULL,NULL,NULL,0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,'');
INSERT INTO "items" VALUES(3,'/Photos/2026/receipt.jpg','','','photo',0,0.0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,'',NULL,NULL,NULL,0,0,0,0,0,NULL,NULL,0,NULL,NULL,NULL,NULL,NULL,0,NULL,NULL,NULL,NULL,NULL,NULL,NULL,'');
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE move_batches(
    id TEXT PRIMARY KEY, label TEXT NOT NULL, created REAL NOT NULL, undone INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE moves(
    id      INTEGER PRIMARY KEY,
    batch   TEXT NOT NULL REFERENCES move_batches(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL,
    src     TEXT NOT NULL,
    dst     TEXT NOT NULL,
    status  TEXT NOT NULL,                          -- pending | done | undone | failed
    detail  TEXT
);
CREATE TABLE people(
    id INTEGER PRIMARY KEY, name TEXT, hidden INTEGER NOT NULL DEFAULT 0, created_at REAL
);
INSERT INTO "people" VALUES(1,'Alex Example',0,NULL);
CREATE TABLE photo_details(
    item_id INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    read_at REAL NOT NULL,
    notes   TEXT NOT NULL DEFAULT ''
, phash INTEGER);
CREATE TABLE photo_events(
    item_id  INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE
);
CREATE TABLE photo_labels(          -- scene / object / landmark labels, from Apple Vision and from the image embedding
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    label   TEXT NOT NULL,
    score   REAL NOT NULL,
    source  TEXT NOT NULL
);
CREATE TABLE photo_objects(         -- things with a place in the frame (animals, people, salient regions, barcodes); boxes are 0..1
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    kind    TEXT NOT NULL,
    label   TEXT NOT NULL,
    score   REAL NOT NULL,
    x1 REAL, y1 REAL, x2 REAL, y2 REAL
);
CREATE TABLE photo_text(            -- every piece of text with where it sits in the frame
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    text    TEXT NOT NULL,
    score   REAL NOT NULL,
    x1 REAL, y1 REAL, x2 REAL, y2 REAL
);
CREATE TABLE photo_venues(          -- what the vision model made of photos that look like a sports venue (one analysis per photo, kept for good)
    item_id INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
    data    TEXT NOT NULL,
    read_at REAL NOT NULL
);
CREATE TABLE photo_vision(          -- everything the vision-language model read from a picture, kept for good (one analysis per photo)
    item_id INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
    model   TEXT NOT NULL,
    data    TEXT NOT NULL,       -- JSON
    read_at REAL NOT NULL
);
CREATE INDEX items_taken ON items(taken_at);
CREATE INDEX items_live  ON items(missing, kind);
CREATE INDEX faces_person ON faces(person_id);
CREATE INDEX faces_item   ON faces(item_id);
CREATE INDEX items_size ON items(size);
CREATE INDEX moves_batch ON moves(batch);
CREATE INDEX flags_status ON flags(status);
CREATE INDEX file_metadata_sha ON file_metadata(sha256);
CREATE INDEX photo_labels_label ON photo_labels(label);
CREATE INDEX photo_labels_item  ON photo_labels(item_id);
CREATE INDEX photo_objects_item ON photo_objects(item_id);
CREATE INDEX photo_text_item ON photo_text(item_id);
CREATE INDEX photo_details_phash ON photo_details(phash);
CREATE INDEX photo_events_event ON photo_events(event_id);
CREATE INDEX faces_count ON faces(item_id, score, px);
PRAGMA writable_schema=OFF;
COMMIT;
PRAGMA user_version=16;
