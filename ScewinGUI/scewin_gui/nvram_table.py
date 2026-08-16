"""Editing behavior for the NVRAM settings table."""

from __future__ import annotations

from functools import partial
from typing import Callable

from .config import APP_CONFIG
from .core import BiosSetting
from .qt_compat import (
    FIF,
    BodyLabel,
    ComboBox,
    LineEdit,
    QBrush,
    QColor,
    QHBoxLayout,
    QRegularExpression,
    QRegularExpressionValidator,
    Qt,
    QTableWidgetItem,
    QWidget,
    TransparentToolButton,
)


class NvramTableController:
    """Render settings and keep table editors synchronized with their model."""

    def __init__(
        self,
        table,
        translate: Callable[..., str],
        log: Callable[[str], None],
        parent: QWidget,
    ) -> None:
        self.table = table
        self.translate = translate
        self.log = log
        self.parent = parent

    def populate(self, settings: list[BiosSetting]) -> None:
        self.table.setUpdatesEnabled(False)
        self.table.setSortingEnabled(False)
        try:
            self.table.setRowCount(0)
            self.table.setRowCount(len(settings))
            for row, setting in enumerate(settings):
                self._populate_row(row, setting)
        finally:
            self.table.setUpdatesEnabled(True)

    def _populate_row(self, row: int, setting: BiosSetting) -> None:
        name = QTableWidgetItem(setting.name)
        name.setData(Qt.ItemDataRole.UserRole, setting)
        name.setFlags(name.flags() ^ Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, 0, name)

        if setting.options:
            editor = ComboBox()
            editor.setFixedHeight(APP_CONFIG.widget_height)
            editor.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            for option_id, label in setting.options:
                editor.addItem(label, userData=option_id)
            index = editor.findData(setting.current_option_id)
            if index >= 0:
                editor.setCurrentIndex(index)
            editor.currentIndexChanged.connect(
                partial(self._on_option_changed, setting, editor)
            )
            self.table.setCellWidget(row, 1, editor)
        elif setting.is_numeric:
            editor = LineEdit()
            editor.setFixedHeight(APP_CONFIG.widget_height)
            if hasattr(editor, "setCustomFocusedBorderColor"):
                transparent = QColor(0, 0, 0, 0)
                editor.setCustomFocusedBorderColor(transparent, transparent)
            editor.setText(setting.raw_value.strip("<>"))
            editor.setValidator(
                QRegularExpressionValidator(QRegularExpression(r"^(0x)?[0-9A-Fa-f]+$"))
            )
            editor.editingFinished.connect(partial(self._on_number_changed, setting, editor))
            self.table.setCellWidget(row, 1, editor)
        else:
            self.table.setItem(row, 1, QTableWidgetItem(setting.current_value))

        default = QTableWidgetItem(setting.bios_default or "-")
        default.setForeground(QBrush(QColor(220, 220, 220)))
        default.setFlags(default.flags() ^ Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, 2, default)
        self.update_status(row, setting)

        original_index = QTableWidgetItem()
        original_index.setData(Qt.ItemDataRole.DisplayRole, row)
        self.table.setItem(row, 4, original_index)

    def _on_option_changed(self, setting: BiosSetting, editor: ComboBox, _index: int) -> None:
        row = self.table.indexAt(editor.pos()).row()
        option_id = editor.currentData()
        if row < 0 or option_id is None or option_id == setting.current_option_id:
            return
        setting.set_option(str(option_id))
        self.update_status(row, setting)
        self.log(
            self.translate("log.changed", name=setting.name, value=setting.current_value)
        )

    def _on_number_changed(self, setting: BiosSetting, editor: LineEdit) -> None:
        row = self.table.indexAt(editor.pos()).row()
        if row < 0:
            return
        value = editor.text()
        value = f"<{value}>" if setting.raw_value.startswith("<") else value
        if value == setting.current_value:
            return
        setting.set_value(value)
        self.update_status(row, setting)
        self.log(self.translate("log.changed", name=setting.name, value=value))

    def update_status(self, row: int, setting: BiosSetting) -> None:
        name = self.table.item(row, 0)
        if name:
            font = name.font()
            font.setBold(setting.is_modified)
            name.setFont(font)

        status = QTableWidgetItem(
            self.translate("status.modified") if setting.is_modified else ""
        )
        status.setFlags(status.flags() ^ Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, 3, status)
        if not (setting.is_modified or setting.differs_from_default):
            self.table.removeCellWidget(row, 3)
            return

        status.setForeground(QBrush(QColor(0, 0, 0, 0)))
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(5, 0, 20, 0)
        layout.setSpacing(4)
        if setting.is_modified:
            label = BodyLabel(self.translate("status.modified"))
            label.setTextColor(QColor("#00c853"), QColor("#00c853"))
            layout.addWidget(label)
        layout.addStretch(1)
        if setting.differs_from_default:
            reset = TransparentToolButton(FIF.SYNC, self.parent)
            reset.setToolTip(self.translate("status.reset_default"))
            reset.setFixedSize(26, 26)
            reset.clicked.connect(partial(self.reset, setting))
            layout.addWidget(reset)
        if setting.is_modified:
            revert = TransparentToolButton(FIF.HISTORY, self.parent)
            revert.setToolTip(self.translate("status.revert"))
            revert.setFixedSize(26, 26)
            revert.clicked.connect(partial(self.revert, setting))
            layout.addWidget(revert)
        self.table.setCellWidget(row, 3, container)

    def reset(self, setting: BiosSetting) -> None:
        row = self._find_row(setting)
        if row < 0 or not (
            setting.default_option_id or (not setting.options and setting.bios_default)
        ):
            return
        setting.reset_to_default()
        self._sync_editor(row, setting)
        self.log(self.translate("log.reset", name=setting.name))

    def revert(self, setting: BiosSetting) -> None:
        row = self._find_row(setting)
        if row < 0:
            return
        setting.reset_to_initial()
        self._sync_editor(row, setting)

    def _sync_editor(self, row: int, setting: BiosSetting) -> None:
        editor = self.table.cellWidget(row, 1)
        if isinstance(editor, ComboBox):
            index = editor.findData(setting.current_option_id)
            if index < 0:
                return
            editor.blockSignals(True)
            editor.setCurrentIndex(index)
            editor.blockSignals(False)
        elif isinstance(editor, LineEdit):
            editor.setText(setting.current_value.strip("<>"))
        self.update_status(row, setting)

    def _find_row(self, setting: BiosSetting) -> int:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) is setting:
                return row
        return -1

    def filter(self, text: str) -> None:
        query = text.lower().strip()
        self.table.setUpdatesEnabled(False)
        try:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                setting = item.data(Qt.ItemDataRole.UserRole) if item else None
                matches = bool(
                    setting
                    and any(
                        query in value.lower()
                        for value in (
                            setting.name,
                            setting.help_string,
                            setting.token,
                            setting.offset,
                        )
                    )
                )
                self.table.setRowHidden(row, not matches)
        finally:
            self.table.setUpdatesEnabled(True)
