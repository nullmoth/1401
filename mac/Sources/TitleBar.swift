// Copyright (c) 2026 NullMoth Systems.
import AppKit

enum TitleBar {
    /// The window's content: the page filling it, and above the page's title bar a strip that drags the window. The strip
    /// was first sized from the web view's frame at creation, which is zero, so it had no width and the window could
    /// not be moved (10-26). It is sized from the container here and follows the window's width from then on: 84 pt
    /// left for the window buttons, 80 pt right for the light/dark switch, 38 pt tall like the page's bar.
    static func container(web: NSView, size: NSSize) -> NSView {
        let box = NSView(frame: NSRect(origin: .zero, size: size))
        web.frame = box.bounds; web.autoresizingMask = [.width, .height]
        box.addSubview(web)
        let drag = TitleDragView(frame: NSRect(x: 84, y: size.height - 38, width: max(0, size.width - 84 - 80), height: 38))
        drag.autoresizingMask = [.width, .minYMargin]
        box.addSubview(drag)   // added after the page, so it is on top and takes the clicks in the bar
        return box
    }
}

/// The draggable part of the page's title bar (between the window buttons and the light/dark switch).
final class TitleDragView: NSView {
    override func mouseDown(with event: NSEvent) { window?.performDrag(with: event) }
    override func mouseUp(with event: NSEvent) { if event.clickCount == 2 { window?.performZoom(nil) } }
}
