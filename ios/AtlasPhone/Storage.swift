import AtlasKit
import Foundation
import Security

/// The phone's pairing, kept in the Keychain: the device key never leaves this phone and is only usable while it is unlocked.
final class KeychainVault: DeviceVault {
    private let service = "invalid.atlas.phone.pairing"

    private struct Stored: Codable { let id: String; let key: Data; let fingerprint: String; let address: String }

    private var query: [String: Any] { [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service] }

    func load() -> PairedDevice? {
        var request = query
        request[kSecReturnData as String] = true
        request[kSecMatchLimit as String] = kSecMatchLimitOne
        var found: CFTypeRef?
        guard SecItemCopyMatching(request as CFDictionary, &found) == errSecSuccess, let data = found as? Data, let stored = try? JSONDecoder().decode(Stored.self, from: data) else { return nil }
        return PairedDevice(id: stored.id, keyBytes: stored.key, fingerprint: stored.fingerprint, address: stored.address)
    }

    func save(_ device: PairedDevice) throws {
        erase()
        let data = try JSONEncoder().encode(Stored(id: device.id, key: device.keyBytes, fingerprint: device.fingerprint, address: device.address))
        var add = query
        add[kSecValueData as String] = data
        add[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly  // never backed up, never moved to another phone
        guard SecItemAdd(add as CFDictionary, nil) == errSecSuccess else { throw AtlasError.local("keychain") }
    }

    func erase() { SecItemDelete(query as CFDictionary) }
}

/// A small file for the offline queue and the read cache, protected while the phone is locked and excluded from backups.
final class FileBlob: BlobStore {
    private let url: URL

    init(name: String) {
        let folder = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("Atlas", isDirectory: true)
        try? FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        url = folder.appendingPathComponent(name + ".json")
    }

    func load() -> Data? { try? Data(contentsOf: url) }

    func save(_ data: Data) {
        try? data.write(to: url, options: [.atomic, .completeFileProtection])
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        var excluded = url
        try? excluded.setResourceValues(values)
    }

    func erase() { try? FileManager.default.removeItem(at: url) }
}
