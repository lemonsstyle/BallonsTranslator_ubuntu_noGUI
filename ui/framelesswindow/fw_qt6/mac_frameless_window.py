# coding:utf-8
from qtpy.QtCore import Qt
from qtpy.QtWidgets import QWidget


class MacFramelessWindowBase:
    """Qt-only frameless window for macOS.

    The old PyObjC/NSWindow path crashes with the current macOS + PyQt6 stack
    during widget construction, so keep the implementation on the Qt side.
    """

    def __init__(self, *args, **kwargs):
        self._isSystemButtonVisible = False
        self._isResizeEnabled = True

    def _initFrameless(self):
        self.updateFrameless()

    def updateFrameless(self):
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)

    def setStayOnTop(self, isTop: bool):
        if isTop:
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint)

        self.updateFrameless()
        self.show()

    def toggleStayOnTop(self):
        if self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint:
            self.setStayOnTop(False)
        else:
            self.setStayOnTop(True)

    def setResizeEnabled(self, isEnabled: bool):
        self._isResizeEnabled = isEnabled

    def hideSystemTitleBar(self):
        # No-op in the Qt-only path: there is no native title bar to modify.
        return

    def isSystemButtonVisible(self):
        return self._isSystemButtonVisible

    def setSystemTitleBarButtonVisible(self, isVisible):
        self._isSystemButtonVisible = isVisible


class MacFramelessWindow(QWidget, MacFramelessWindowBase):
    """Frameless window for macOS using Qt only."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        MacFramelessWindowBase.__init__(self)
        self._initFrameless()
