import Foundation

/// One canonical design-token layer (UI/UX specification section 10): colour, type, spacing, sizing, radii and motion live here and nowhere else. The values are plain numbers and
/// RGB triples so they can be tested (contrast, ordering, completeness) without a screen; `AtlasApp/DesignSystem.swift` maps them to SwiftUI.
public struct RGB: Equatable {
    public let red: Double, green: Double, blue: Double  // 0...255

    public init(_ red: Double, _ green: Double, _ blue: Double) { self.red = red; self.green = green; self.blue = blue }
    public init(hex: UInt32) {
        self.init(Double((hex >> 16) & 0xFF), Double((hex >> 8) & 0xFF), Double(hex & 0xFF))
    }

    /// Relative luminance as WCAG defines it.
    public var luminance: Double {
        func channel(_ value: Double) -> Double {
            let v = value / 255
            return v <= 0.03928 ? v / 12.92 : pow((v + 0.055) / 1.055, 2.4)
        }
        return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)
    }

    /// WCAG contrast ratio between two colours (1...21).
    public static func contrast(_ a: RGB, _ b: RGB) -> Double {
        let high = max(a.luminance, b.luminance), low = min(a.luminance, b.luminance)
        return (high + 0.05) / (low + 0.05)
    }
}

public enum Appearance: CaseIterable { case light, dark }

public struct SemanticColors: Equatable {
    public let background: RGB, surface: RGB, separator: RGB
    public let textPrimary: RGB, textSecondary: RGB, textMuted: RGB
    public let accent: RGB, onAccent: RGB
    public let success: RGB, warning: RGB, destructive: RGB

    /// The text colours, which must each reach contrast 4.5 on the background and the surface.
    public var textColours: [RGB] { [textPrimary, textSecondary, textMuted] }
    /// The status and accent colours, which must each reach 4.5 on the background (they carry text or sit beside a symbol and a label, never alone).
    public var signalColours: [RGB] { [accent, success, warning, destructive] }
}

public enum Tokens {
    public static func colors(_ appearance: Appearance) -> SemanticColors {
        switch appearance {
        case .light:
            return SemanticColors(
                background: RGB(hex: 0xFFFFFF), surface: RGB(hex: 0xF4F4F6), separator: RGB(hex: 0xC8C8CE),
                textPrimary: RGB(hex: 0x1C1C1E), textSecondary: RGB(hex: 0x48484D), textMuted: RGB(hex: 0x5C5C63),
                accent: RGB(hex: 0x2F5BD9), onAccent: RGB(hex: 0xFFFFFF),
                success: RGB(hex: 0x1E7B3C), warning: RGB(hex: 0x8A5A00), destructive: RGB(hex: 0xC0262D))
        case .dark:
            return SemanticColors(
                background: RGB(hex: 0x1B1B1E), surface: RGB(hex: 0x26262A), separator: RGB(hex: 0x4A4A52),
                textPrimary: RGB(hex: 0xF2F2F5), textSecondary: RGB(hex: 0xC6C6CC), textMuted: RGB(hex: 0xA8A8B0),
                accent: RGB(hex: 0x7B9CFF), onAccent: RGB(hex: 0x10101A),
                success: RGB(hex: 0x58C27A), warning: RGB(hex: 0xE6B34A), destructive: RGB(hex: 0xFF7A80))
        }
    }

    /// Spacing on a 4-point grid.
    public enum Space {
        public static let xxs = 2.0, xs = 4.0, sm = 8.0, md = 12.0, lg = 16.0, xl = 24.0, xxl = 32.0
        public static let all = [xxs, xs, sm, md, lg, xl, xxl]
    }

    public enum Radius { public static let small = 6.0, medium = 10.0, large = 14.0 }

    public enum Size {
        public static let minimumHit = 28.0  // the smallest interactive control
        public static let controlHeight = 32.0
        public static let readingWidth = 680.0  // the comfortable maximum line length of a conversation
        public static let sidebarWidth = 220.0
        public static let inspectorWidth = 320.0
        public static let compactBreakpoint = 760.0  // below this the sidebar becomes a compact navigation and inspectors fold away
        public static let mediumBreakpoint = 1040.0  // below this the inspector is a sheet, not a trailing column
    }

    /// Type sizes in points, scaled by the system text size in the views (never fixed heights). Body is the sustained-reading size.
    public enum TypeScale {
        public static let caption = 12.0, footnote = 13.0, body = 15.0, headline = 17.0, title = 22.0, largeTitle = 28.0
        public static let ordered = [caption, footnote, body, headline, title, largeTitle]
    }

    /// Motion: short and purposeful; zero when the system asks for Reduce Motion.
    public enum Motion {
        public static let quick = 0.12, standard = 0.2
        public static func duration(_ base: Double, reduceMotion: Bool) -> Double { reduceMotion ? 0 : base }
    }
}
