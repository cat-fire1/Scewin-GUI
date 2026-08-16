"""Main FluentWindow and navigation assembly."""

from __future__ import annotations

from .config import APP_CONFIG
from .i18n import LANG_OPTIONS, LanguageManager, load_language_setting, save_language_setting
from .qt_compat import (
    FIF,
    Action,
    FluentWindow,
    NavigationItemPosition,
    QApplication,
    QCursor,
    QIcon,
    RoundMenu,
    Theme,
    setTheme,
)
from .ui_about import AboutInterface
from .ui_backup import BackupInterface
from .ui_editor import NVRAMInterface
from .workers import BiosOperationCoordinator

APP_NAME = APP_CONFIG.app_name
WINDOW_WIDTH = APP_CONFIG.window_width
WINDOW_HEIGHT = APP_CONFIG.window_height


class MainWindow(FluentWindow):
    """Top-level application window and shared operation coordinator."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.lang_manager = LanguageManager(load_language_setting())
        self.operation_coordinator = BiosOperationCoordinator()
        self._setup_icon()
        setTheme(Theme.DARK)
        self._setup_interfaces()
        self._setup_language_selector()
        self.lang_manager.language_changed.connect(self.apply_language)
        self.lang_manager.language_changed.connect(save_language_setting)
        self.apply_language()

    # Устанавливает иконку приложения.
    def _setup_icon(self) -> None:
        icon_path = APP_CONFIG.icon_path
        if icon_path.exists():
            icon = QIcon(str(icon_path))
            self.setWindowIcon(icon)
            QApplication.setWindowIcon(icon)

    # Создает основные вкладки и элементы навигации.
    def _setup_interfaces(self) -> None:
        self.interface = NVRAMInterface(
            self,
            self.lang_manager,
            self.operation_coordinator,
        )
        self.nav_item_editor = self.addSubInterface(
            self.interface, FIF.EDIT, self.lang_manager.tr("nav.editor")
        )
        self.backup_interface = BackupInterface(
            self,
            self.lang_manager,
            self.operation_coordinator,
        )
        self.nav_item_backup = self.addSubInterface(
            self.backup_interface, FIF.SAVE, self.lang_manager.tr("nav.backup")
        )
        self.about_interface = AboutInterface(self, self.lang_manager)
        self.nav_item_about = self.addSubInterface(
            self.about_interface, FIF.INFO, self.lang_manager.tr("nav.about")
        )
        self.navigationInterface.setCurrentItem(self.interface.objectName())

    # Добавляет выбор языка в навигацию.
    def _setup_language_selector(self) -> None:
        self.navigationInterface.addSeparator(NavigationItemPosition.BOTTOM)
        self.nav_item_language = self.navigationInterface.addItem(
            routeKey="language_selector",
            icon=FIF.LANGUAGE,
            text=self.lang_manager.tr("nav.language"),
            onClick=self.show_language_menu,
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
            tooltip=self.lang_manager.tr("nav.language_tooltip"),
        )

    # Показывает меню выбора языка.
    def show_language_menu(self) -> None:
        menu = RoundMenu(parent=self)
        menu.setTitle(self.lang_manager.tr("language.menu_title"))
        current = self.lang_manager.language()
        for code, name in LANG_OPTIONS:
            action = Action(name, self)
            action.setCheckable(True)
            action.setChecked(code == current)
            action.triggered.connect(lambda _, c=code: self.lang_manager.set_language(c))
            menu.addAction(action)
        menu.exec(QCursor.pos())

    # Применяет локализацию к навигации и вкладкам.
    def apply_language(self) -> None:
        self.nav_item_editor.setText(self.lang_manager.tr("nav.editor"))
        self.nav_item_editor.setToolTip(self.lang_manager.tr("nav.editor"))
        self.nav_item_backup.setText(self.lang_manager.tr("nav.backup"))
        self.nav_item_backup.setToolTip(self.lang_manager.tr("nav.backup"))
        self.nav_item_about.setText(self.lang_manager.tr("nav.about"))
        self.nav_item_about.setToolTip(self.lang_manager.tr("nav.about"))
        self.nav_item_language.setText(self.lang_manager.tr("nav.language"))
        self.nav_item_language.setToolTip(self.lang_manager.tr("nav.language_tooltip"))
        self.interface.apply_language()
        self.backup_interface.apply_language()
        self.about_interface.apply_language()
