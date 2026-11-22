import Darwin
import Foundation

/// A minimal HTTP/1.1 client over the Core's owner-only Unix socket (Foundation's HTTP loader cannot speak to a Unix socket). One request per connection.
public struct UnixHTTP {
    public let path: String
    public init(path: String) { self.path = path }

    public struct Response { public let status: Int; public let headers: [String: String]; public let body: Data }

    public func send(method: String, target: String, headers: [String: String], body: Data) throws -> Response {
        let fd = socket(AF_UNIX, SOCK_STREAM, 0)
        guard fd >= 0 else { throw AtlasError.local("socket") }
        defer { close(fd) }
        var address = sockaddr_un()
        address.sun_family = sa_family_t(AF_UNIX)
        let capacity = MemoryLayout.size(ofValue: address.sun_path)
        guard path.utf8.count < capacity else { throw AtlasError.local("path too long") }
        withUnsafeMutablePointer(to: &address.sun_path) { $0.withMemoryRebound(to: CChar.self, capacity: capacity) { _ = path.withCString { src in strncpy($0, src, capacity - 1) } } }
        let connected = withUnsafePointer(to: &address) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { connect(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size)) } }
        guard connected == 0 else { throw AtlasError.local("connect") }
        var head = "\(method) \(target) HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\nContent-Length: \(body.count)\r\n"
        for (key, value) in headers { head += "\(key): \(value)\r\n" }
        var request = Data((head + "\r\n").utf8)
        request.append(body)
        try request.withUnsafeBytes { raw in
            var sent = 0
            while sent < raw.count {
                let n = write(fd, raw.baseAddress!.advanced(by: sent), raw.count - sent)
                guard n > 0 else { throw AtlasError.local("write") }
                sent += n
            }
        }
        var received = Data()
        var buffer = [UInt8](repeating: 0, count: 65536)
        while true {
            let n = read(fd, &buffer, buffer.count)
            if n < 0 { throw AtlasError.local("read") }
            if n == 0 { break }
            received.append(buffer, count: n)
        }
        return try Self.parse(received)
    }

    static func parse(_ data: Data) throws -> Response {
        guard let split = data.range(of: Data("\r\n\r\n".utf8)), let head = String(data: data[..<split.lowerBound], encoding: .utf8) else { throw AtlasError.local("response") }
        let lines = head.components(separatedBy: "\r\n")
        let parts = lines[0].split(separator: " ")
        guard parts.count >= 2, let status = Int(parts[1]) else { throw AtlasError.local("status") }
        var headers: [String: String] = [:]
        for line in lines.dropFirst() {
            if let colon = line.firstIndex(of: ":") { headers[line[..<colon].lowercased()] = line[line.index(after: colon)...].trimmingCharacters(in: .whitespaces) }
        }
        return Response(status: status, headers: headers, body: data[split.upperBound...])
    }
}
