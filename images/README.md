# Images: the picture engine every app shares

Everything that understands a picture lives here, once: reading a file (EXIF, date, GPS and place names, text in the picture with Apple Vision or Tesseract, faces and who they are, CLIP embeddings, labels, quality), the index in one SQLite file, and every kind of search over it (words, places, dates, people, colours, "something that looks like this").

- `images.engine.Engine`: settings, the database, the models, the scan. Nothing about chat or screens.
- `images.indexing`, `images.ml`, `images.search`, `images.people`, `images.quality`, `images.library`: moved here unchanged from the Photos app.
- The index keeps its old name and place (`<drive>/Aperture/data/aperture.db`), so a library that is already indexed is found where it was.
- Heavy extras: `pip install "images[ml]"` (torch, CLIP, onnxruntime, OpenCV) and, on a Mac, `images[mac]` (Apple Vision).

## Who uses it
- **Documents** (`../library`) runs the engine: a sealed indexer container (no network, photos read-only) reads the photo folder and writes the index; the service answers pictures questions (`/api/pictures`, thumbnails, the text found in pictures joins the documents in one search) and relays Update.
- **Photos** (`../photos`) imports this package to show and search the index (it opens the same volume, `library-pictures`) and, with `APERTURE_LIBRARY_URL` set (the Docker setup), passes Update on to Documents instead of indexing itself. A native install without that setting still indexes by itself as before.

## Still open
- Photos still opens the index file directly to read and to write its own things (people's names, moves, captions). Moving every one of those reads and writes behind Documents' API (about 50 places) would make Documents the only program that touches the file; it is not done.
- Pictures that arrive inside mail or the inbox (not in the photo folder) are read by Documents' own reader (text only); they are not yet fed through this engine.
- Not run on a real Mac: the Docker images (the indexer carries PyTorch and the models come from the drive) have not been built.
- Move the existing index once: `photos/scripts/aperture-docker-migrate.sh` copies the index from the drive (or, with `FROM_VOLUME=aperture-data`, from the old volume) into `library-pictures`.
