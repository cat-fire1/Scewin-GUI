"""Backup management page."""

from __future__ import annotations

import datetime
import os
from functools import partial

from .config import APP_CONFIG
from .core import NvramValidationError
from .i18n import LanguageManager
from .qt_compat import (
    FIF,
    BodyLabel,
    CardWidget,
    InfoBar,
    PrimaryPushButton,
    PushButton,
    QColor,
    QDesktopServices,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSize,
    Qt,
    QUrl,
    QVBoxLayout,
    QWidget,
    SmoothScrollArea,
    SubtitleLabel,
    TextEdit,
    TitleLabel,
    TransparentToolButton,
)
from .ui_common import BiosCommandInterface
from .workers import BiosOperationCoordinator

NVRAM_FILE = APP_CONFIG.nvram_file
BACKUP_DIR = APP_CONFIG.backup_directory
WIDGET_HEIGHT = APP_CONFIG.widget_height
LOG_CARD_HEIGHT = APP_CONFIG.log_card_height
LAYOUT_MARGIN = APP_CONFIG.layout_margin
LAYOUT_SPACING = APP_CONFIG.layout_spacing


class BackupInterface(BiosCommandInterface):
    """List, create, restore, and safely delete NVRAM backups."""

    def __init__(
        self,
        parent: QWidget | None = None,
        lang_manager: LanguageManager | None = None,
        coordinator: BiosOperationCoordinator | None = None,
    ) -> None:
        super().__init__(
            parent=parent,
            lang_manager=lang_manager,
            coordinator=coordinator,
        )
        self.setObjectName("BackupInterface")
        self.init_ui()
        self.apply_language()
        self.refresh_backups()

    # Собирает UI: кнопки, список и сводку.
    def init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(LAYOUT_MARGIN, LAYOUT_MARGIN, LAYOUT_MARGIN, LAYOUT_MARGIN)
        layout.setSpacing(LAYOUT_SPACING)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        self.lbl_title = TitleLabel("", self)
        titles.addWidget(self.lbl_title)
        self.lbl_subtitle = BodyLabel("", self)
        self.lbl_subtitle.setTextColor(QColor(220, 220, 220), QColor(240, 240, 240))
        titles.addWidget(self.lbl_subtitle)
        header.addLayout(titles)
        header.addStretch(1)

        self.btn_create_backup = PrimaryPushButton(FIF.SAVE, "", self)
        self.btn_create_backup.clicked.connect(self.action_create_backup)
        self.btn_open_folder = PushButton(FIF.FOLDER, "", self)
        self.btn_open_folder.clicked.connect(self.action_open_backup_dir)
        self.btn_refresh = TransparentToolButton(FIF.SYNC, self)
        self.btn_refresh.clicked.connect(self.refresh_backups)

        header.addWidget(self.btn_create_backup)
        header.addWidget(self.btn_open_folder)
        header.addWidget(self.btn_refresh)
        layout.addLayout(header)

        self.summary_card = CardWidget(self)
        self.summary_card.setFixedHeight(90)
        summary_layout = QHBoxLayout(self.summary_card)
        summary_layout.setContentsMargins(16, 12, 16, 12)
        summary_layout.setSpacing(12)

        self.summary_total = self._create_summary_item()
        self.summary_last = self._create_summary_item()
        self.summary_size = self._create_summary_item()

        summary_layout.addWidget(self.summary_total["card"])
        summary_layout.addWidget(self.summary_last["card"])
        summary_layout.addWidget(self.summary_size["card"])
        layout.addWidget(self.summary_card)

        self.backup_card = CardWidget(self)
        card_layout = QVBoxLayout(self.backup_card)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(8)
        self.lbl_empty = BodyLabel("", self)
        self.lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty.setStyleSheet("color: rgba(255,255,255,160);")

        self.backup_scroll = SmoothScrollArea(self)
        self.backup_scroll.setWidgetResizable(True)
        self.backup_scroll.setStyleSheet(
            "SmoothScrollArea { border: none; background: transparent; }"
        )

        self.backup_list_container = QWidget()
        self.backup_list_layout = QVBoxLayout(self.backup_list_container)
        self.backup_list_layout.setContentsMargins(6, 6, 6, 6)
        self.backup_list_layout.setSpacing(10)
        self.backup_list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.backup_scroll.setWidget(self.backup_list_container)

        card_layout.addWidget(self.lbl_empty)
        card_layout.addWidget(self.backup_scroll)
        layout.addWidget(self.backup_card, 1)

        self.log_card = CardWidget(self)
        self.log_card.setFixedHeight(LOG_CARD_HEIGHT)
        log_layout = QVBoxLayout(self.log_card)
        log_layout.setContentsMargins(12, 12, 12, 12)
        log_layout.setSpacing(8)

        self.txt_log = TextEdit(self)
        self.txt_log.setReadOnly(True)
        log_layout.addWidget(self.txt_log)
        layout.addWidget(self.log_card)

    # Обновляет тексты и подсказки по текущему языку.
    def apply_language(self) -> None:
        self.lbl_title.setText(self.t("backup.title"))
        self.lbl_subtitle.setText(self.t("backup.subtitle"))
        self.btn_create_backup.setText(self.t("button.create_backup"))
        self.btn_open_folder.setText(self.t("button.open_folder"))
        self.btn_refresh.setToolTip(self.t("tooltip.refresh"))
        self.lbl_empty.setText(self.t("backup.empty"))
        self.summary_total["title"].setText(self.t("backup.summary_total"))
        self.summary_last["title"].setText(self.t("backup.summary_last"))
        self.summary_size["title"].setText(self.t("backup.summary_size"))
        self.refresh_backups()

    # Создает карточку для элемента сводки.
    def _create_summary_item(self) -> dict[str, QWidget]:
        card = CardWidget(self)
        card.setFixedHeight(60)
        card.setStyleSheet(
            "CardWidget {"
            " background-color: rgba(255, 255, 255, 0.04);"
            " border: 1px solid rgba(255, 255, 255, 0.08);"
            " border-radius: 8px;"
            " }"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)
        title = BodyLabel("", card)
        title.setStyleSheet("color: rgba(255,255,255,160); font-size: 12px;")
        value = SubtitleLabel("", card)
        value.setTextColor(QColor(255, 255, 255), QColor(255, 255, 255))
        layout.addWidget(title)
        layout.addWidget(value)
        return {"card": card, "title": title, "value": value}

    # Форматирует размер файла в читаемый вид.
    def _format_size(self, size_bytes: int) -> str:
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(size_bytes)
        for unit in units:
            if size < 1024 or unit == units[-1]:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    # Обновляет блок сводки по списку бэкапов.
    def _update_summary(self, items: list[tuple[str, float, int]]) -> None:
        total = len(items)
        last = self.t("backup.summary_none")
        if items:
            last_ts = items[0][1]
            last = datetime.datetime.fromtimestamp(last_ts).strftime("%Y-%m-%d %H:%M")
        size_total = sum(s for _, _, s in items)
        self.summary_total["value"].setText(str(total))
        self.summary_last["value"].setText(last)
        self.summary_size["value"].setText(self._format_size(size_total))

    # Перестраивает список бэкапов и сводку.
    def refresh_backups(self) -> None:
        while self.backup_list_layout.count():
            item = self.backup_list_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget:
                widget.deleteLater()
        items = self.service.list_backups()
        self._update_summary(items)
        self.lbl_empty.setVisible(len(items) == 0)
        self.backup_scroll.setVisible(len(items) > 0)

        for path, mtime, _size in items:
            filename = os.path.basename(path)
            date_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")

            card = CardWidget(self)
            card.setFixedHeight(72)
            card.setStyleSheet(
                "CardWidget {"
                " background-color: rgba(255, 255, 255, 0.03);"
                " border: 1px solid rgba(255, 255, 255, 0.06);"
                " border-radius: 10px;"
                " }"
            )
            row_layout = QHBoxLayout(card)
            row_layout.setContentsMargins(12, 10, 12, 10)
            row_layout.setSpacing(12)

            icon_label = QLabel(card)
            icon = FIF.DOCUMENT.icon()
            icon_label.setPixmap(icon.pixmap(QSize(20, 20)))
            icon_label.setFixedSize(24, 24)
            row_layout.addWidget(icon_label)

            text_layout = QVBoxLayout()
            text_layout.setSpacing(2)
            lbl_name = SubtitleLabel(filename, card)
            lbl_date = BodyLabel(date_str, card)
            lbl_date.setStyleSheet("color: rgba(255,255,255,160); font-size: 12px;")
            text_layout.addWidget(lbl_name)
            text_layout.addWidget(lbl_date)
            row_layout.addLayout(text_layout, 1)

            btn_restore = PushButton(FIF.DOWNLOAD, self.t("button.restore"), card)
            btn_restore.setFixedHeight(WIDGET_HEIGHT)
            btn_restore.setToolTip(self.t("tooltip.restore"))
            btn_restore.clicked.connect(partial(self.action_restore_backup, path))

            btn_delete = PushButton(FIF.DELETE, self.t("button.delete"), card)
            btn_delete.setFixedHeight(WIDGET_HEIGHT)
            btn_delete.setToolTip(self.t("tooltip.delete_backup"))
            btn_delete.clicked.connect(partial(self.action_delete_backup_by_path, path))

            row_layout.addWidget(btn_restore)
            row_layout.addWidget(btn_delete)

            self.backup_list_layout.addWidget(card)

    # Создает новый бэкап текущего nvram.txt.
    def action_create_backup(self) -> None:
        if not os.path.exists(self.service.resolve_path(NVRAM_FILE)):
            InfoBar.warning(
                self.t("infobar.warning"), self.t("infobar.no_file", file=NVRAM_FILE), parent=self
            )
            return
        try:
            path = self.service.create_backup(NVRAM_FILE, BACKUP_DIR)
            InfoBar.success(self.t("title.backup"), self.t("backup.saved", path=path), parent=self)
            self.log(self.t("backup.created", path=path))
            self.refresh_backups()
        except OSError as error:
            self.log(self.t("backup.error", error=error))
            InfoBar.error(self.t("infobar.error"), str(error), parent=self)

    # Открывает папку бэкапов в проводнике.
    def action_open_backup_dir(self) -> None:
        backup_path = self.service.resolve_path(BACKUP_DIR)
        if not os.path.exists(backup_path):
            os.makedirs(backup_path, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(backup_path))

    # Удаляет выбранный бэкап после подтверждения.
    def action_delete_backup_by_path(self, path: str) -> None:
        if not path or not os.path.exists(path):
            InfoBar.warning(self.t("infobar.warning"), self.t("backup.file_missing"), parent=self)
            return
        reply = QMessageBox.question(
            self,
            self.t("backup.delete_title"),
            self.t("backup.delete_text", name=os.path.basename(path)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,  # type: ignore[arg-type]
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self.service.delete_backup(path)
            InfoBar.success(
                self.t("backup.deleted_title"), self.t("backup.deleted_short"), parent=self
            )
            self.log(self.t("backup.deleted", path=path))
            self.refresh_backups()
        except (OSError, ValueError) as error:
            self.log(self.t("log.error", detail=error))
            InfoBar.error(self.t("infobar.error"), str(error), parent=self)

    # Восстанавливает выбранный бэкап через SCEWIN.
    def action_restore_backup(self, path: str) -> None:
        if not path or not os.path.exists(path):
            InfoBar.warning(self.t("infobar.warning"), self.t("backup.file_missing"), parent=self)
            return
        try:
            operation = self.service.create_import_operation(
                path,
                self.t(
                    "backup.restore_desc",
                    name=os.path.basename(path),
                ),
                action="restore",
            )
        except (OSError, NvramValidationError) as error:
            InfoBar.error(
                self.t("infobar.error"),
                self.t("bios.invalid_file", error=error),
                parent=self,
            )
            return
        self.run_operation(operation)
