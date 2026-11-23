import AtlasKit
import SwiftUI

@main
struct AtlasPhoneApp: App {
    @StateObject private var model = PhoneModel()

    var body: some Scene {
        WindowGroup { PhoneRoot(model: model) }
    }
}
