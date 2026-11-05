# Images: the picture engine every app shares

Everything that understands a picture lives here, once: reading a file (EXIF, date, GPS and place names, text in the picture with Apple Vision or Tesseract, faces and who they are, CLIP embeddings, labels, quality), the index in one SQLite file, and every kind of search over it (words, places, dates, people, colours, "something that looks like this").

- `images.engine.Engine`: settings, the database, the models, the scan. Nothing about chat or screens.
- `images.indexing`, `images.ml`, `images.search`, `images.people`, `images.quality`, `images.library`: moved here unchanged from the Photos app.
- The index keeps its old name and place (`<drive>/Aperture/data/aperture.db`), so a library that is already indexed is found where it was.
- Heavy extras: `pip install "images[ml]"` (torch, CLIP, onnxruntime, OpenCV) and, on a Mac, `images[mac]` (Apple Vision).

## Who uses it
- **Photos** (`../photos`) still runs the engine in its own process and shows the results and the chat. It imports this package; it no longer contains the engine.
- **Documents** (`../library`) will run the same engine for every picture it receives, so a picture is read the same way wherever it arrives. **Not done yet**; see below.

## What is left to do (in this order, together, so nothing is indexed twice)
1. Documents runs `Engine` over the photo folder and the pictures it receives, and serves the pictures API (search, thumbnails, people).
2. Photos stops opening the index file itself (about 50 places pass a database connection straight into the search and screens) and asks Documents instead.
3. Switch over: only one program indexes.
