import Foundation

/// How a signed request reaches a Core. The contract, the signing and every rule are the same whichever way it travels.
public protocol HTTPTransport {
    func send(method: String, target: String, headers: [String: String], body: Data) throws -> UnixHTTP.Response
}

extension UnixHTTP: HTTPTransport {}

/// The remote channel for a phone: HTTPS to the address in the pairing invite (a private network such as a VPN, or a relay the owner runs in front of the Mac; the channel itself is the owner's choice, G-O14).
/// Plain http is allowed only for a loopback, private or `.local` address. Redirects are never followed, replies are bounded, and the request carries only what the contract defines.
public struct RemoteHTTP: HTTPTransport {
    public let base: URL
    public var timeout: TimeInterval = 20
    private static let maxReply = 4_000_000

    public init?(address: String) {
        guard let url = URL(string: address), let scheme = url.scheme?.lowercased(), let host = url.host, scheme == "https" || (scheme == "http" && ConnectDraft.isHomeNetwork(host)) else { return nil }
        base = url
    }

    private final class NoRedirect: NSObject, URLSessionTaskDelegate {
        func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) { completionHandler(nil) }
    }

    public func send(method: String, target: String, headers: [String: String], body: Data) throws -> UnixHTTP.Response {
        guard let url = URL(string: target, relativeTo: base)?.absoluteURL else { throw AtlasError.local("address") }
        var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: timeout)
        request.httpMethod = method
        request.httpShouldHandleCookies = false
        for (key, value) in headers { request.setValue(value, forHTTPHeaderField: key) }
        if !body.isEmpty { request.httpBody = body }
        let session = URLSession(configuration: .ephemeral, delegate: NoRedirect(), delegateQueue: nil)
        defer { session.finishTasksAndInvalidate() }
        let semaphore = DispatchSemaphore(value: 0)
        var result: (Data?, URLResponse?, Error?) = (nil, nil, nil)
        session.dataTask(with: request) { result = ($0, $1, $2); semaphore.signal() }.resume()
        semaphore.wait()
        guard result.2 == nil, let http = result.1 as? HTTPURLResponse, let data = result.0, data.count <= Self.maxReply else { throw AtlasError.local("unreachable") }
        var headers: [String: String] = [:]
        for (key, value) in http.allHeaderFields { if let k = key as? String, let v = value as? String { headers[k.lowercased()] = v } }
        return UnixHTTP.Response(status: http.statusCode, headers: headers, body: data)
    }
}
