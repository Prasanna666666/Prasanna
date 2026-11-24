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

    /// Collects the reply as it arrives and ends the transfer the moment it passes the cap, so an oversized or endless reply is never buffered whole. Redirects are never followed.
    private final class Collector: NSObject, URLSessionDataDelegate {
        let limit: Int
        let finished = DispatchSemaphore(value: 0)
        var body = Data()
        var response: HTTPURLResponse?
        var failure: Error?
        var tooLarge = false
        init(limit: Int) { self.limit = limit }

        func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) { completionHandler(nil) }

        func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive response: URLResponse, completionHandler: @escaping (URLSession.ResponseDisposition) -> Void) {
            self.response = response as? HTTPURLResponse
            if response.expectedContentLength > Int64(limit) {
                tooLarge = true
                completionHandler(.cancel)
            } else {
                completionHandler(.allow)
            }
        }

        func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
            body.append(data)
            if body.count > limit {
                tooLarge = true
                dataTask.cancel()
            }
        }

        func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
            failure = error
            finished.signal()
        }
    }

    public func send(method: String, target: String, headers: [String: String], body: Data) throws -> UnixHTTP.Response {
        guard let url = URL(string: target, relativeTo: base)?.absoluteURL else { throw AtlasError.local("address") }
        var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: timeout)
        request.httpMethod = method
        request.httpShouldHandleCookies = false
        for (key, value) in headers { request.setValue(value, forHTTPHeaderField: key) }
        if !body.isEmpty { request.httpBody = body }
        let collector = Collector(limit: Self.maxReply)
        let session = URLSession(configuration: .ephemeral, delegate: collector, delegateQueue: nil)
        defer { session.finishTasksAndInvalidate() }
        session.dataTask(with: request).resume()
        collector.finished.wait()
        guard collector.failure == nil, !collector.tooLarge, let http = collector.response else { throw AtlasError.local("unreachable") }
        let data = collector.body
        var headers: [String: String] = [:]
        for (key, value) in http.allHeaderFields { if let k = key as? String, let v = value as? String { headers[k.lowercased()] = v } }
        return UnixHTTP.Response(status: http.statusCode, headers: headers, body: data)
    }
}
