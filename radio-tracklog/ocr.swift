// Text recognition for radio_tracklog.py's watch mode, using macOS's
// built-in Vision framework — fully on-device and offline.
// Compiled automatically by the script (swiftc -O -o .ocr ocr.swift).
//
// Prints one line per recognized text:  "<x> <y>\t<text>"
// where x/y are the text's position as fractions of the frame measured
// from the BOTTOM-LEFT corner (Vision's coordinate system).
import Foundation
import Vision
import AppKit

guard CommandLine.arguments.count > 1,
      let img = NSImage(contentsOfFile: CommandLine.arguments[1]),
      let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("usage: ocr <image>\n".data(using: .utf8)!)
    exit(1)
}
let req = VNRecognizeTextRequest { request, _ in
    for obs in (request.results as? [VNRecognizedTextObservation]) ?? [] {
        if let top = obs.topCandidates(1).first {
            let b = obs.boundingBox
            print("\(String(format: "%.3f %.3f", b.origin.x, b.origin.y))\t\(top.string)")
        }
    }
}
req.recognitionLevel = .accurate
try VNImageRequestHandler(cgImage: cg).perform([req])
