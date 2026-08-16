"""NVRAM editor page and its table/detail components."""

from __future__ import annotations

import os
from contextlib import suppress

from .config import APP_CONFIG
from .core import BiosParser, BiosSetting, CommandResult, NvramDocument, NvramValidationError
from .i18n import LanguageManager
from .nvram_table import NvramTableController
from .qt_compat import (
    FIF,
    Action,
    BodyLabel,
    CardWidget,
    InfoBar,
    PrimaryPushButton,
    PushButton,
    QAbstractItemView,
    QColor,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QKeySequence,
    QPoint,
    QShortcut,
    Qt,
    QTimer,
    QVBoxLayout,
    QWidget,
    RoundMenu,
    SearchLineEdit,
    SubtitleLabel,
    TableWidget,
    TextEdit,
    TitleLabel,
    TransparentToolButton,
)
from .ui_common import BiosCommandInterface, DelayedToolTipEventFilter
from .workers import BiosOperationCoordinator, NvramLoadResult, NVRAMLoadWorker

NVRAM_FILE = APP_CONFIG.nvram_file
NVRAM_NEW_FILE = APP_CONFIG.nvram_new_file
BACKUP_DIR = APP_CONFIG.backup_directory
SEARCH_DEBOUNCE_MS = APP_CONFIG.search_debounce_ms
SORT_DEBOUNCE_MS = APP_CONFIG.sort_debounce_ms
AUTO_LOAD_DELAY_MS = APP_CONFIG.auto_load_delay_ms
COLUMN_WIDTH_PARAM = APP_CONFIG.column_width_parameter
COLUMN_WIDTH_VALUE = APP_CONFIG.column_width_value
COLUMN_WIDTH_DEFAULT = APP_CONFIG.column_width_default
COLUMN_WIDTH_STATUS = APP_CONFIG.column_width_status
ROW_HEIGHT = APP_CONFIG.row_height
SEARCH_BAR_WIDTH = APP_CONFIG.search_bar_width
LOG_CARD_HEIGHT = APP_CONFIG.log_card_height
LOG_TEXT_WIDTH = APP_CONFIG.log_text_width
LAYOUT_MARGIN = APP_CONFIG.layout_margin
LAYOUT_SPACING = APP_CONFIG.layout_spacing
BORDER_RADIUS = APP_CONFIG.border_radius


class NvramTableWidget(TableWidget):
    """Preconfigured table used to display editable BIOS settings."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setBorderVisible(True)
        self.setBorderRadius(BORDER_RADIUS)
        self.setColumnCount(5)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setShowGrid(False)
        if hasattr(self, "setCheckedColor"):
            transparent = QColor(0, 0, 0, 0)
            self.setCheckedColor(transparent, transparent)
        self.setSortingEnabled(False)
        self.horizontalHeader().setSortIndicatorShown(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().hide()
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.scrollDelagate.useAni = True
        self.setAutoScroll(False)
        self.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(0, COLUMN_WIDTH_PARAM)
        self.setColumnWidth(1, COLUMN_WIDTH_VALUE)
        self.setColumnWidth(2, COLUMN_WIDTH_DEFAULT)
        self.setColumnWidth(3, COLUMN_WIDTH_STATUS)
        self.setColumnHidden(4, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)


class DetailsLogPanel(CardWidget):
    """Parameter details and operation log displayed below the table."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(LOG_CARD_HEIGHT)
        root_layout = QHBoxLayout(self)
        details_layout = QVBoxLayout()

        self.name_label = SubtitleLabel("", self)
        self.name_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        separator = QFrame(self)
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setFixedHeight(1)
        separator.setStyleSheet("background-color: rgba(255, 255, 255, 30);")
        self.description_label = BodyLabel("", self)
        self.description_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.description_label.setWordWrap(True)
        self.description_label.setTextColor(
            QColor(220, 220, 220),
            QColor(240, 240, 240),
        )
        details_layout.addWidget(self.name_label)
        details_layout.addWidget(separator)
        details_layout.addWidget(self.description_label)
        details_layout.addStretch()

        self.log = TextEdit(self)
        self.log.setReadOnly(True)
        self.log.setFixedWidth(LOG_TEXT_WIDTH)
        root_layout.addLayout(details_layout, 1)
        root_layout.addWidget(self.log)


class NVRAMInterface(BiosCommandInterface):
    """Main editor page for viewing and modifying NVRAM settings."""

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
        self.setObjectName("NVRAMInterface")
        self.parser = BiosParser()
        self.document: NvramDocument | None = None
        self.settings: list[BiosSetting] = []
        self.loaded_filepath: str | None = None
        self.load_worker: NVRAMLoadWorker | None = None
        self.sort_state: dict = {}
        self._pending_sort_index: int | None = None

        self._sort_timer = QTimer(self)
        self._sort_timer.setSingleShot(True)
        self._sort_timer.setInterval(SORT_DEBOUNCE_MS)
        self._sort_timer.timeout.connect(self._execute_sort)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(SEARCH_DEBOUNCE_MS)
        self._search_timer.timeout.connect(self._execute_filter)

        self.tooltip_filter = DelayedToolTipEventFilter()
        self.init_ui()
        self.apply_language()
        QTimer.singleShot(100, self.check_dependencies)

        if os.path.exists(self.service.resolve_path(NVRAM_FILE)):
            QTimer.singleShot(AUTO_LOAD_DELAY_MS, lambda: self.load_data(NVRAM_FILE))
        else:
            QTimer.singleShot(AUTO_LOAD_DELAY_MS, self.action_export_bios)

    # Собирает UI редактора (шапка, таблица, лог).
    def init_ui(self) -> None:
        self.v_layout = QVBoxLayout(self)
        self.v_layout.setContentsMargins(LAYOUT_MARGIN, LAYOUT_MARGIN, LAYOUT_MARGIN, LAYOUT_MARGIN)
        self.v_layout.setSpacing(LAYOUT_SPACING)

        # Header: title/subtitle and primary actions.
        header = QHBoxLayout()
        titles = QVBoxLayout()
        self.lbl_title = TitleLabel("", self)
        titles.addWidget(self.lbl_title)
        self.lbl_subtitle = BodyLabel("", self)
        self.lbl_subtitle.setTextColor(QColor(220, 220, 220), QColor(240, 240, 240))
        titles.addWidget(self.lbl_subtitle)

        self.search_bar = SearchLineEdit(self)
        self.search_bar.setFixedWidth(SEARCH_BAR_WIDTH)
        self.search_bar.textChanged.connect(self._on_search_changed)
        titles.addStretch(1)
        titles.addWidget(self.search_bar)

        self.shortcut_search = QShortcut(QKeySequence("Ctrl+F"), self)
        self.shortcut_search.activated.connect(self.search_bar.setFocus)
        self.shortcut_esc = QShortcut(QKeySequence("Escape"), self.search_bar)
        self.shortcut_esc.activated.connect(self.search_bar.clear)

        self.btn_import = PushButton(FIF.DOWNLOAD, "", self)
        self.btn_import.clicked.connect(self.action_import_bios)
        self.btn_export = PushButton(FIF.SHARE, "", self)
        self.btn_export.clicked.connect(self.action_export_bios)
        self.btn_import_loaded = PushButton(FIF.DOCUMENT, "", self)
        self.btn_import_loaded.clicked.connect(self.action_import_loaded)
        self.btn_open = TransparentToolButton(FIF.FOLDER, self)
        self.btn_open.clicked.connect(self.open_file_dialog)
        self.btn_save = PrimaryPushButton(FIF.SAVE, "", self)
        self.btn_save.clicked.connect(self.action_apply_changes)
        self.btn_save.setDefault(False)
        self.btn_save.setAutoDefault(False)

        self.lbl_export_category = BodyLabel("", self)
        self.lbl_export_hint = BodyLabel("", self)
        self.lbl_import_category = BodyLabel("", self)
        self.lbl_import_loaded_hint = BodyLabel("", self)
        self.lbl_import_hint = BodyLabel("", self)
        self.lbl_apply_category = BodyLabel("", self)
        self.lbl_apply_hint = BodyLabel("", self)

        category_style = "font-size: 11px; font-weight: 600; color: #b0b0b0;"
        hint_style = "font-size: 10px; color: #888888;"
        for label in (
            self.lbl_export_category,
            self.lbl_import_category,
            self.lbl_apply_category,
        ):
            label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            label.setFixedHeight(14)
            label.setStyleSheet(category_style)
        for label in (
            self.lbl_export_hint,
            self.lbl_import_loaded_hint,
            self.lbl_import_hint,
            self.lbl_apply_hint,
        ):
            label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            label.setFixedHeight(14)
            label.setStyleSheet(hint_style)

        export_group = QVBoxLayout()
        export_group.setSpacing(2)
        export_group.addWidget(self.lbl_export_category)
        export_group.addWidget(self.btn_export)
        export_group.addWidget(self.lbl_export_hint)

        import_loaded_group = QVBoxLayout()
        import_loaded_group.setSpacing(2)
        import_loaded_group.addWidget(self.btn_import_loaded)
        import_loaded_group.addWidget(self.lbl_import_loaded_hint)
        import_group = QVBoxLayout()
        import_group.setSpacing(2)
        import_group.addWidget(self.btn_import)
        import_group.addWidget(self.lbl_import_hint)
        import_buttons = QHBoxLayout()
        import_buttons.setSpacing(12)
        import_buttons.addLayout(import_loaded_group)
        import_buttons.addLayout(import_group)
        bios_write_group = QVBoxLayout()
        bios_write_group.setSpacing(2)
        bios_write_group.addWidget(self.lbl_import_category)
        bios_write_group.addLayout(import_buttons)

        open_file_group = QVBoxLayout()
        open_file_group.setSpacing(2)
        open_file_group.addSpacing(16)
        open_file_group.addWidget(self.btn_open)
        open_file_group.addSpacing(16)
        write_section = QHBoxLayout()
        write_section.setSpacing(4)
        write_section.addLayout(open_file_group)
        write_section.addLayout(bios_write_group)

        apply_group = QVBoxLayout()
        apply_group.setSpacing(2)
        apply_group.addWidget(self.lbl_apply_category)
        apply_group.addWidget(self.btn_save)
        apply_group.addWidget(self.lbl_apply_hint)

        actions = QHBoxLayout()
        actions.setAlignment(Qt.AlignmentFlag.AlignBottom)
        actions.addLayout(export_group)
        actions.addSpacing(8)
        actions.addLayout(write_section)
        actions.addSpacing(8)
        actions.addLayout(apply_group)
        self.btn_export.installEventFilter(self.tooltip_filter)
        self.btn_import.installEventFilter(self.tooltip_filter)
        self.btn_import_loaded.installEventFilter(self.tooltip_filter)
        self.btn_save.installEventFilter(self.tooltip_filter)
        header.addLayout(titles, 1)
        header.addSpacing(8)
        header.addLayout(actions)
        self.v_layout.addLayout(header)

        # Settings table: list, selection, and sorting controls.
        self.table_card = CardWidget(self)
        self.table = NvramTableWidget(self)
        self.table_controller = NvramTableController(self.table, self.t, self.log, self)

        self.table.cellClicked.connect(self.on_table_click)
        self.table.currentCellChanged.connect(self.on_cell_changed)

        self.table.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.horizontalHeader().customContextMenuRequested.connect(self.show_header_menu)
        self.table.horizontalHeader().sectionClicked.connect(self.handle_header_click)

        table_layout = QVBoxLayout(self.table_card)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.addWidget(self.table)
        self.v_layout.addWidget(self.table_card, 1)

        self.log_card = DetailsLogPanel(self)
        self.lbl_p_name = self.log_card.name_label
        self.lbl_p_desc = self.log_card.description_label
        self.txt_log = self.log_card.log
        self.v_layout.addWidget(self.log_card)

    # Применяет локализацию ко всем виджетам интерфейса.
    def apply_language(self) -> None:
        self.lbl_title.setText(self.t("editor.title"))
        self.lbl_subtitle.setText(self.t("editor.subtitle"))
        self.btn_import.setText(self.t("button.import"))
        self.btn_import.setToolTip(self.t("tooltip.import"))
        self.btn_export.setText(self.t("button.export"))
        self.btn_export.setToolTip(self.t("tooltip.export"))
        self.btn_import_loaded.setText(self.t("button.import_loaded"))
        self.btn_import_loaded.setToolTip(self.t("tooltip.import_loaded"))
        import_button_width = max(
            self.btn_import.sizeHint().width(),
            self.btn_import_loaded.sizeHint().width(),
        )
        self.btn_import.setFixedWidth(import_button_width)
        self.btn_import_loaded.setFixedWidth(import_button_width)
        self.btn_save.setText(self.t("button.apply"))
        self.btn_save.setToolTip(self.t("tooltip.apply"))
        self.lbl_export_category.setText(self.t("category.export"))
        self.lbl_export_hint.setText(self.t("hint.export"))
        self.lbl_import_category.setText(self.t("category.import"))
        self.lbl_import_loaded_hint.setText(self.t("hint.import_loaded"))
        self.lbl_import_hint.setText(self.t("hint.import"))
        self.lbl_apply_category.setText(self.t("category.apply"))
        self.lbl_apply_hint.setText(self.t("hint.apply"))
        self.search_bar.setPlaceholderText(self.t("search.placeholder"))
        self.search_bar.setToolTip(self.t("search.tooltip"))
        self.btn_open.setToolTip(self.t("tooltip.open_file"))
        self.table.setHorizontalHeaderLabels(
            [
                self.t("table.param"),
                self.t("table.value"),
                self.t("table.default"),
                self.t("table.status"),
                self.t("table.id"),
            ]
        )
        if self.table.currentRow() >= 0:
            self._update_details(self.table.currentRow())
        else:
            self.lbl_p_name.setText(self.t("details.none"))
            self.lbl_p_desc.setText(self.t("details.select_row"))
        for row, setting in enumerate(self.settings):
            self.table_controller.update_status(row, setting)

    # Проверяет наличие зависимостей SCEWIN и сообщает пользователю.
    def check_dependencies(self) -> None:
        ok, missing, unreadable = self.service.check_dependencies()
        if not ok:
            msg = self.t("deps.missing", files=", ".join(missing + unreadable))
            self.log(self.t("log.warning", message=msg))
            InfoBar.error(self.t("infobar.startup_error"), msg, duration=5000, parent=self)
        else:
            self.log(self.t("deps.ready"))
            if not os.path.exists(self.service.resolve_path(NVRAM_FILE)):
                self.log(self.t("file.not_found_auto", file=NVRAM_FILE))

    # Загружает и парсит NVRAM-файл, затем обновляет таблицу.
    def load_data(self, filepath: str) -> None:
        if self.load_worker is not None and self.load_worker.isRunning():
            InfoBar.warning(
                self.t("infobar.warning"),
                self.t("infobar.loading_content", desc=filepath),
                parent=self,
            )
            return
        self.log(self.t("log.reading", file=filepath))
        self.load_worker = NVRAMLoadWorker(filepath, self.service)
        self.load_worker.result_ready.connect(self.on_load_finished)
        self.load_worker.start()

    def on_load_finished(self, result: NvramLoadResult) -> None:
        if self.load_worker is not None:
            with suppress(TypeError):
                self.load_worker.result_ready.disconnect(self.on_load_finished)
            self.load_worker.deleteLater()
            self.load_worker = None

        if not result.success:
            self.log(self.t("log.error", detail=result.error))
            InfoBar.error(
                self.t("infobar.error"),
                self.t("bios.invalid_file", error=result.error),
                parent=self,
            )
            return

        self.document = result.document
        self.settings = self.document.settings if self.document else []
        self.table_controller.populate(self.settings)
        self.table_controller.filter(self.search_bar.text())
        self.loaded_filepath = result.filepath
        self.log(self.t("log.loaded", count=len(self.settings)))
        InfoBar.success(
            self.t("infobar.loaded_title"),
            self.t("infobar.loaded_content", count=len(self.settings)),
            parent=self,
        )

    # Запускает таймер дебаунса поиска.
    def _on_search_changed(self, text: str) -> None:
        self._search_timer.start()

    # Выполняет фильтрацию после задержки.
    def _execute_filter(self) -> None:
        self.table_controller.filter(self.search_bar.text())

    # Обновляет детали при клике по строке таблицы.
    def on_table_click(self, row: int, _column: int) -> None:
        self._update_details(row)

    # Следит за сменой активной строки и прокруткой.
    def on_cell_changed(
        self,
        row: int,
        _column: int,
        _previous_row: int,
        _previous_column: int,
    ) -> None:
        if row >= 0:
            self._update_details(row)
            item = self.table.item(row, 0)
            if item:
                self.table.scrollToItem(item, QAbstractItemView.ScrollHint.EnsureVisible)

    # Выводит подробности выбранной настройки.
    def _update_details(self, row: int) -> None:
        item = self.table.item(row, 0)
        if item:
            s = item.data(Qt.ItemDataRole.UserRole)
            self.lbl_p_name.setText(s.name)
            desc = s.help_string or self.t("details.no_description")
            extras = []
            if s.token:
                extras.append(f"Token: {s.token}")
            if s.offset:
                extras.append(f"Offset: {s.offset}")
            if extras:
                desc += "\n\n" + " | ".join(extras)
            self.lbl_p_desc.setText(desc)

    # Управляет состоянием сортировки при клике по заголовку.
    def handle_header_click(self, index: int) -> None:
        header = self.table.horizontalHeader()

        if index == 1:
            header.setSortIndicatorShown(False)
            self.sort_state = {}
            self._pending_sort_index = -1
            self._sort_timer.start()
            return

        for col in list(self.sort_state.keys()):
            if col != index:
                self.sort_state[col] = 0

        current = self.sort_state.get(index, 0)
        if current == 0:
            next_state = 2
        elif current == 2:
            next_state = 1
        else:
            next_state = 0

        self.sort_state[index] = next_state

        if next_state == 2:
            header.setSortIndicatorShown(True)
            header.setSortIndicator(index, Qt.SortOrder.DescendingOrder)
        elif next_state == 1:
            header.setSortIndicatorShown(True)
            header.setSortIndicator(index, Qt.SortOrder.AscendingOrder)
        else:
            header.setSortIndicatorShown(False)

        self._pending_sort_index = index
        self._sort_timer.start()

    # Применяет сортировку, отложенную таймером.
    def _execute_sort(self) -> None:
        index = self._pending_sort_index
        if index is None:
            return

        self.table.setUpdatesEnabled(False)
        try:
            if index == -1:
                self.table.sortItems(4, Qt.SortOrder.AscendingOrder)
                return

            next_state = self.sort_state.get(index, 0)

            if next_state == 2:
                self.table.sortItems(index, Qt.SortOrder.DescendingOrder)
            elif next_state == 1:
                self.table.sortItems(index, Qt.SortOrder.AscendingOrder)
            else:
                self.table.sortItems(4, Qt.SortOrder.AscendingOrder)
        finally:
            self.table.setUpdatesEnabled(True)
            self._pending_sort_index = None

    # Контекстное меню заголовка таблицы (сброс фильтра).
    def show_header_menu(self, position: QPoint) -> None:
        menu = RoundMenu(parent=self)
        if self.search_bar.text():
            action_clear_filter = Action(FIF.CANCEL, "Сбросить фильтр", self)
            action_clear_filter.triggered.connect(self.search_bar.clear)
            menu.addAction(action_clear_filter)
        if not menu.actions():
            return
        menu.exec(self.table.horizontalHeader().mapToGlobal(position))

    # Диалог выбора NVRAM файла для загрузки.
    def open_file_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.t("dialog.open_nvram"), "", self.t("dialog.file_filter")
        )
        if path:
            self.load_data(path)

    # Применяет изменения и сохраняет nvram_new.txt.
    def action_apply_changes(self) -> None:
        modified = [s for s in self.settings if s.is_modified]
        if not modified:
            InfoBar.info(
                self.t("infobar.no_changes_title"),
                self.t("infobar.no_changes_content"),
                parent=self,
            )
            return
        try:
            if self.document is None:
                raise ValueError("NVRAM document is not loaded")
            content = self.parser.generate_changes(self.document)
            self.service.atomic_write(NVRAM_NEW_FILE, content)
            self.log(self.t("apply.saved", count=len(modified), file=NVRAM_NEW_FILE))
            InfoBar.success(
                self.t("infobar.ready_import_title"),
                self.t("infobar.ready_import_content", file=NVRAM_NEW_FILE),
                parent=self,
            )
        except OSError as error:
            self.log(self.t("log.read_error", error=error))
            InfoBar.error(self.t("infobar.error"), str(error), parent=self)

    # Импортирует загруженный файл в BIOS через SCEWIN.
    def action_import_loaded(self) -> None:
        if not self.settings or not self.loaded_filepath:
            InfoBar.warning(
                self.t("infobar.warning"), self.t("infobar.no_loaded_file"), parent=self
            )
            return
        try:
            operation = self.service.create_import_operation(
                self.loaded_filepath,
                self.t("action.import_loaded"),
                action="import_loaded",
            )
        except (OSError, NvramValidationError) as error:
            InfoBar.error(
                self.t("infobar.error"),
                self.t("bios.invalid_file", error=error),
                parent=self,
            )
            return
        self.run_operation(operation)

    # Экспортирует текущие настройки BIOS в nvram.txt.
    def action_export_bios(self) -> None:
        operation = self.service.create_export_operation(self.t("action.export"))
        self.run_operation(operation)

    # Импортирует nvram_new.txt в BIOS.
    def action_import_bios(self) -> None:
        if not os.path.exists(self.service.resolve_path(NVRAM_NEW_FILE)):
            InfoBar.error(
                self.t("infobar.error"),
                self.t("infobar.no_new_file", file=NVRAM_NEW_FILE),
                parent=self,
            )
            return
        try:
            operation = self.service.create_import_operation(
                NVRAM_NEW_FILE,
                self.t("action.import"),
            )
        except (OSError, NvramValidationError) as error:
            InfoBar.error(
                self.t("infobar.error"),
                self.t("bios.invalid_file", error=error),
                parent=self,
            )
            return
        self.run_operation(operation)

    def _after_worker_success(self, result: CommandResult) -> None:
        if result.action != "export":
            return

        self.load_data(NVRAM_FILE)
        try:
            backup_path = self.service.create_backup(NVRAM_FILE, BACKUP_DIR)
            self.log(self.t("backup.auto_created", path=backup_path))
            InfoBar.success(
                self.t("title.backup"),
                self.t("backup.saved", path=backup_path),
                parent=self,
            )
        except OSError as error:
            self.log(self.t("log.error", detail=error))
