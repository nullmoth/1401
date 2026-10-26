import AppKit
// The window is dragged by its title bar only if a click there lands on the drag strip. 10-26: the strip was sized from a
// zero frame and no click ever reached it. Checked at the opening size and after the window grows.
var failed = 0
func check(_ ok: Bool, _ what: String) { if ok { print("ok   " + what) } else { failed += 1; print("FAIL " + what) } }
let page = NSView()
let box = TitleBar.container(web: page, size: NSSize(width: 1100, height: 760))
func hit(_ x: CGFloat, _ yFromTop: CGFloat) -> NSView? { box.hitTest(NSPoint(x: x, y: box.bounds.height - yFromTop)) }
check(hit(500, 15) is TitleDragView, "a click in the middle of the title bar drags the window")
check(hit(1060, 15) === page, "the light/dark switch on the right of the bar still gets its click")
check(hit(40, 15) === page, "the window buttons' corner is left alone")
check(hit(500, 200) === page, "a click below the bar goes to the page")
box.setFrameSize(NSSize(width: 1400, height: 900))
check(hit(1200, 15) is TitleDragView, "after the window grows, the bar still drags it")
check(hit(1360, 15) === page, "after the window grows, the switch still gets its click")
check(hit(700, 60) === page, "after the window grows, the page under the bar gets its clicks")
print("\(failed) failed"); exit(failed == 0 ? 0 : 1)
