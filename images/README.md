# Images: the picture engine every app shares

Everything that understands a picture lives here, once: reading a file (EXIF, date, GPS and place names, text in the picture with Apple Vision or Tesseract, faces and who they are, CLIP embeddings, labels, quality), the index in one SQLite file, and every kind of search over it (words, places, dates, people, colours, "something that looks like this").

- `images.engine.Engine`: settings, the database, the models, the scan. Nothing about chat or screens.
- `images.indexing`, `images.ml`, `images.search`, `images.people`, `images.quality`, `images.library`: moved here unchanged from the old Photos app, together with `images.search.plan`/`executor` (the structured search) and `images.browse` (the pages).
- The index keeps its old name and place (`<drive>/Aperture/data/aperture.db`), so a library that is already indexed is found where it was.
- Heavy extras: `pip install "images[ml]"` (torch, CLIP, onnxruntime, OpenCV) and, on a Mac, `images[mac]` (Apple Vision).

## Who uses it
**Documents** (`../library`) is the only program that runs it. A sealed indexer container (no network, photos read-only) reads the photo folder, the inbox and the pictures that came in mail, and writes the index. The Documents service answers from the index: the library by date, trips, places and people as pages, the tools the one assistant uses (`find_pictures`), and thumbnails. Pictures in mail are kept as plain files in a private volume (named by their content) so they are read like every other picture.

There is no separate Photos app any more. The chat-style search screen is the one assistant now. Moving, deleting and exporting pictures (`images.organize`, `images.export`) are kept and used by Documents through the assistant: a change is prepared and only described, shown in a confirmation window, and carried out only when the person presses Confirm there after every check is run again; a move is journaled and can be undone, and a delete moves the picture to a trash folder. What is not carried over is the macOS launcher and the command line (in git history).

## Encrypted
With `ORBIT_DB_KEY` set (the Docker setup) the index is an encrypted SQLCipher file, full-text index included; an existing plain index is converted once on first open and the plain file is kept beside it as `aperture.db.unencrypted` until you delete it. A native install with no key keeps a plain index as before.

## Still open
- Not run on a real Mac: the Docker images (the indexer carries PyTorch and the models come from the drive) have not been built.
- Move the existing index once: `library/scripts/adopt-picture-index.sh` copies the index from the drive (or, with `FROM_VOLUME=aperture-data`, from the old volume) into `library-pictures`.
- The vision-model steps that named venues and judged pictures with the local model are in the engine but nothing runs them yet.
