import Foundation

/// The one navigation model (UI/UX specification section 3): Home, Ask Atlas, Library, life areas, Activity and Settings. A destination is shown only when its surface is available.
public enum Destination: Hashable {
    case home, ask, library, lifeArea(String), activity, settings

    public var title: String {
        switch self {
        case .home: return "Home"
        case .ask: return "Ask Atlas"
        case .library: return "Library"
        case .lifeArea(let name): return name
        case .activity: return "Activity"
        case .settings: return "Settings"
        }
    }

    /// SF Symbols names; every sidebar row also carries its text label, so an icon never stands alone.
    public var symbol: String {
        switch self {
        case .home: return "house"
        case .ask: return "bubble.left.and.text.bubble.right"
        case .library: return "books.vertical"
        case .lifeArea: return "square.grid.2x2"
        case .activity: return "clock.arrow.circlepath"
        case .settings: return "gearshape"
        }
    }

    /// A stable string for restoring the selection after a relaunch.
    public var restorationKey: String {
        switch self {
        case .home: return "home"
        case .ask: return "ask"
        case .library: return "library"
        case .lifeArea(let name): return "life:" + name
        case .activity: return "activity"
        case .settings: return "settings"
        }
    }

    public init?(restorationKey key: String) {
        switch key {
        case "home": self = .home
        case "ask": self = .ask
        case "library": self = .library
        case "activity": self = .activity
        case "settings": self = .settings
        default:
            guard key.hasPrefix("life:"), key.count > 5 else { return nil }
            self = .lifeArea(String(key.dropFirst(5)))
        }
    }
}

public enum NavigationLayout: Equatable {
    case compact, medium, wide

    public static func forWidth(_ width: Double) -> NavigationLayout {
        if width < Tokens.Size.compactBreakpoint { return .compact }
        return width < Tokens.Size.mediumBreakpoint ? .medium : .wide
    }

    /// At wide sizes the evidence inspector may take a trailing column; at medium and compact sizes it folds away into a sheet before body text is compressed.
    public var inspectorIsTrailingColumn: Bool { self == .wide }
    public var sidebarIsCompact: Bool { self == .compact }
}

/// What the app can really show today. A domain appears only when its product surface is available (progressive disclosure); nothing is listed as if it worked when it does not.
public struct Availability: Equatable {
    public var library = false
    public var lifeAreas: [String] = []
    public init(library: Bool = false, lifeAreas: [String] = []) { self.library = library; self.lifeAreas = lifeAreas }
}

public enum Sidebar {
    public static func destinations(_ availability: Availability) -> [Destination] {
        var list: [Destination] = [.home, .ask]
        if availability.library { list.append(.library) }
        list += availability.lifeAreas.sorted().map { Destination.lifeArea($0) }
        list += [.activity, .settings]
        return list
    }

    /// The destination to show after a restart: the remembered one if it is still available, otherwise Home.
    public static func restored(_ key: String?, in availability: Availability) -> Destination {
        guard let key, let remembered = Destination(restorationKey: key), destinations(availability).contains(remembered) else { return .home }
        return remembered
    }

    /// Command-1 ... Command-6 select the first six destinations in order, so the shortcuts stay predictable as areas come and go.
    public static func destination(forShortcut number: Int, in availability: Availability) -> Destination? {
        let list = destinations(availability)
        return (1...list.count).contains(number) ? list[number - 1] : nil
    }
}
