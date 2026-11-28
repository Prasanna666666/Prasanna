import AtlasKit
import SwiftUI

/// Maps the canonical tokens (`AtlasKit/Tokens.swift`) to SwiftUI. Views take every colour, spacing and size from here; no view carries a literal value.
extension Color {
    init(_ rgb: RGB) { self.init(red: rgb.red / 255, green: rgb.green / 255, blue: rgb.blue / 255) }
}

struct Theme {
    let colors: SemanticColors

    init(_ scheme: ColorScheme) { colors = Tokens.colors(scheme == .dark ? .dark : .light) }

    var background: Color { Color(colors.background) }
    var surface: Color { Color(colors.surface) }
    var separator: Color { Color(colors.separator) }
    var textPrimary: Color { Color(colors.textPrimary) }
    var textSecondary: Color { Color(colors.textSecondary) }
    var textMuted: Color { Color(colors.textMuted) }
    var accent: Color { Color(colors.accent) }
    var onAccent: Color { Color(colors.onAccent) }
    var success: Color { Color(colors.success) }
    var warning: Color { Color(colors.warning) }
    var destructive: Color { Color(colors.destructive) }
}

enum Space {
    static let xs = CGFloat(Tokens.Space.xs), sm = CGFloat(Tokens.Space.sm), md = CGFloat(Tokens.Space.md), lg = CGFloat(Tokens.Space.lg), xl = CGFloat(Tokens.Space.xl), xxl = CGFloat(Tokens.Space.xxl)
}

enum Radius {
    static let small = CGFloat(Tokens.Radius.small), medium = CGFloat(Tokens.Radius.medium)
}

enum Metrics {
    static let readingWidth = CGFloat(Tokens.Size.readingWidth)
    static let sidebarWidth = CGFloat(Tokens.Size.sidebarWidth)
    static let inspectorWidth = CGFloat(Tokens.Size.inspectorWidth)
    static let minimumHit = CGFloat(Tokens.Size.minimumHit)
}

/// Text styles: system fonts that scale with the user's text size (never fixed heights).
enum TextStyle {
    static let title = Font.title2.weight(.semibold)
    static let headline = Font.headline
    static let body = Font.body
    static let secondary = Font.callout
    static let caption = Font.footnote
}

/// The short, purposeful transition: none when the system asks for Reduce Motion.
struct MotionModifier: ViewModifier {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let value: AnyHashable

    func body(content: Content) -> some View {
        content.animation(.easeInOut(duration: Tokens.Motion.duration(Tokens.Motion.standard, reduceMotion: reduceMotion)), value: value)
    }
}

extension View {
    func atlasMotion<V: Hashable>(_ value: V) -> some View { modifier(MotionModifier(value: AnyHashable(value))) }

    /// One reading column: a comfortable maximum line length, centred.
    func readingColumn() -> some View { frame(maxWidth: Metrics.readingWidth, alignment: .leading).frame(maxWidth: .infinity) }
}
