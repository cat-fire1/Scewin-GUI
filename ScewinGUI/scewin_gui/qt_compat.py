"""Qt5/Qt6 compatibility imports used throughout the GUI."""

from __future__ import annotations

import warnings

warnings.filterwarnings(
    "ignore",
    message=".*Point size.*",
    category=UserWarning,
)

try:
    import qfluentwidgets.components.widgets.label as _fluent_label_module
    from qfluentwidgets import (
        Action,
        BodyLabel,
        CardWidget,
        ComboBox,
        FluentWindow,
        InfoBar,
        LineEdit,
        NavigationItemPosition,
        PrimaryPushButton,
        PushButton,
        RoundMenu,
        SearchLineEdit,
        SmoothScrollArea,
        SubtitleLabel,
        TableWidget,
        TextEdit,
        Theme,
        TitleLabel,
        TransparentToolButton,
        setTheme,
    )
    from qfluentwidgets import (
        FluentIcon as FIF,
    )

    QT_BINDING = _fluent_label_module.QWidget.__module__.split(".")[0]
    if QT_BINDING == "PyQt5":
        from PyQt5.QtCore import (
            QEvent,
            QObject,
            QPoint,
            QRegularExpression,
            QSettings,
            QSize,
            Qt,
            QThread,
            QTimer,
            QUrl,
            pyqtSignal,
        )
        from PyQt5.QtGui import (
            QBrush,
            QColor,
            QCursor,
            QDesktopServices,
            QIcon,
            QKeySequence,
            QRegularExpressionValidator,
            QTextCursor,
        )
        from PyQt5.QtWidgets import (
            QAbstractItemView,
            QAction,
            QApplication,
            QDialog,
            QFileDialog,
            QFrame,
            QHBoxLayout,
            QHeaderView,
            QLabel,
            QMessageBox,
            QShortcut,
            QTableWidgetItem,
            QToolTip,
            QVBoxLayout,
            QWidget,
        )
    elif QT_BINDING == "PyQt6":
        from PyQt6.QtCore import (
            QEvent,
            QObject,
            QPoint,
            QRegularExpression,
            QSettings,
            QSize,
            Qt,
            QThread,
            QTimer,
            QUrl,
            pyqtSignal,
        )
        from PyQt6.QtGui import (
            QAction,
            QBrush,
            QColor,
            QCursor,
            QDesktopServices,
            QIcon,
            QKeySequence,
            QRegularExpressionValidator,
            QShortcut,
            QTextCursor,
        )
        from PyQt6.QtWidgets import (
            QAbstractItemView,
            QApplication,
            QDialog,
            QFileDialog,
            QFrame,
            QHBoxLayout,
            QHeaderView,
            QLabel,
            QMessageBox,
            QTableWidgetItem,
            QToolTip,
            QVBoxLayout,
            QWidget,
        )
    elif QT_BINDING == "PySide6":
        from PySide6.QtCore import (
            QEvent,
            QObject,
            QPoint,
            QRegularExpression,
            QSettings,
            QSize,
            Qt,
            QThread,
            QTimer,
            QUrl,
            Signal as pyqtSignal,
        )
        from PySide6.QtGui import (
            QAction,
            QBrush,
            QColor,
            QCursor,
            QDesktopServices,
            QIcon,
            QKeySequence,
            QRegularExpressionValidator,
            QShortcut,
            QTextCursor,
        )
        from PySide6.QtWidgets import (
            QAbstractItemView,
            QApplication,
            QDialog,
            QFileDialog,
            QFrame,
            QHBoxLayout,
            QHeaderView,
            QLabel,
            QMessageBox,
            QTableWidgetItem,
            QToolTip,
            QVBoxLayout,
            QWidget,
        )
    else:
        raise RuntimeError(f"Unsupported Qt binding: {QT_BINDING}")
except ImportError as error:
    raise RuntimeError(
        "Missing GUI dependencies for the Qt binding used by qfluentwidgets."
    ) from error

if QT_BINDING == "PyQt5":
    QEvent.Type = QEvent
    Qt.AlignmentFlag = Qt
    Qt.ContextMenuPolicy = Qt
    Qt.FocusPolicy = Qt
    Qt.ItemDataRole = Qt
    Qt.ItemFlag = Qt
    Qt.SortOrder = Qt
    Qt.TextInteractionFlag = Qt
    QAbstractItemView.ScrollHint = QAbstractItemView
    QAbstractItemView.ScrollMode = QAbstractItemView
    QAbstractItemView.SelectionBehavior = QAbstractItemView
    QAbstractItemView.SelectionMode = QAbstractItemView
    QFrame.Shape = QFrame
    QFrame.Shadow = QFrame
    QHeaderView.ResizeMode = QHeaderView
    QSettings.Format = QSettings
    QMessageBox.Icon = QMessageBox
    QMessageBox.StandardButton = QMessageBox

TEXT_CURSOR_END = (
    QTextCursor.MoveOperation.End if hasattr(QTextCursor, "MoveOperation") else QTextCursor.End
)

__all__ = [name for name in globals() if not name.startswith("_")]
