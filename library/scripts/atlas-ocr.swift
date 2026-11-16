// Apple's text recognition (Vision) for scanned pages. It runs on your Mac's own chip, in a macOS sandbox that has no network and may write only into its own scratch folder (a RAM disk:
// the pictures of your pages never touch the disk). It reads page pictures that appear in that folder and answers with the same word table Tesseract gives (TSV).
import Foundation
import ImageIO
import Vision

let dir = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "/Volumes/AtlasOCR"
let folder = URL(fileURLWithPath: dir)
let fm = FileManager.default

func table(for url: URL) -> String {
    var rows = ["level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"]
    guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
          let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else { return rows.joined(separator: "\n") + "\n" }
    let width = Double(image.width), height = Double(image.height)
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    request.recognitionLanguages = ["en-US", "nl-NL"]
    do { try VNImageRequestHandler(cgImage: image, options: [:]).perform([request]) } catch { return rows.joined(separator: "\n") + "\n" }
    var line = 0
    for observation in request.results ?? [] {
        guard let candidate = observation.topCandidates(1).first else { continue }
        line += 1
        var word = 0
        let text = candidate.string
        text.enumerateSubstrings(in: text.startIndex..<text.endIndex, options: .byWords) { piece, range, _, _ in
            guard let piece = piece, let found = try? candidate.boundingBox(for: range) else { return }
            word += 1
            let box = found.boundingBox // 0...1, origin at the bottom left
            let left = Int(box.minX * width), top = Int((1 - box.maxY) * height)
            let w = Int(box.width * width), h = Int(box.height * height)
            rows.append("5\t1\t1\t\(line)\t\(line)\t\(word)\t\(left)\t\(top)\t\(w)\t\(h)\t\(Int(candidate.confidence * 100))\t\(piece)")
        }
    }
    return rows.joined(separator: "\n") + "\n"
}

while true {
    try? "alive".write(to: folder.appendingPathComponent("alive"), atomically: false, encoding: .utf8)
    for name in (try? fm.contentsOfDirectory(atPath: dir)) ?? [] where name.hasSuffix(".png") {
        let picture = folder.appendingPathComponent(name)
        let stem = String(name.dropLast(4))
        let part = folder.appendingPathComponent(stem + ".part")
        let answer = folder.appendingPathComponent(stem + ".tsv")
        try? table(for: picture).write(to: part, atomically: false, encoding: .utf8)
        try? fm.moveItem(at: part, to: answer)
        try? fm.removeItem(at: picture)
    }
    Thread.sleep(forTimeInterval: 0.05)
}
