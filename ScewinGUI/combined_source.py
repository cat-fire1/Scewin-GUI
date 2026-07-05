import os
import sys
import warnings

# Базовая настройка окружения и поведения UI.
os.environ['QFLUENTWIDGETS_DISABLE_BANNER'] = '1'

# Скрываем неважные предупреждения Qt о размере шрифта.
warnings.filterwarnings("ignore", message=".*Point size.*", category=UserWarning)

# Импортируем GUI-зависимости, чтобы сразу сообщить о проблемах установки.
try:
    from qfluentwidgets import (
        FluentWindow, NavigationItemPosition, FluentIcon as FIF,
        TableWidget, PrimaryPushButton, PushButton, SearchLineEdit,
        TextEdit, InfoBar, InfoBarPosition, Theme, setTheme,
        ComboBox, LineEdit, CardWidget, TitleLabel, SubtitleLabel,
        TransparentToolButton, RoundMenu, Action, BodyLabel, SmoothScrollArea
    )
    import qfluentwidgets.components.widgets.label as _fluent_label_module

    QT_BINDING = _fluent_label_module.QWidget.__module__.split(".")[0]
    if QT_BINDING == "PyQt5":
        from PyQt5.QtCore import Qt, QUrl, QSize, QTimer, QThread, pyqtSignal, QRegularExpression, QPoint, QEvent, QObject, QSettings
        from PyQt5.QtGui import QColor, QIcon, QDesktopServices, QRegularExpressionValidator, QBrush, QKeySequence, QPixmap, QCursor, QTextCursor
        from PyQt5.QtWidgets import (
            QApplication, QWidget, QHBoxLayout, QVBoxLayout,
            QHeaderView, QFileDialog, QTableWidgetItem, QFrame, QMenu,
            QAbstractItemView, QLabel, QToolTip, QMessageBox, QDialog,
            QAction, QShortcut
        )
    else:
        from PyQt6.QtCore import Qt, QUrl, QSize, QTimer, QThread, pyqtSignal, QRegularExpression, QPoint, QEvent, QObject, QSettings
        from PyQt6.QtGui import QColor, QIcon, QDesktopServices, QAction, QRegularExpressionValidator, QBrush, QKeySequence, QShortcut, QPixmap, QCursor, QTextCursor
        from PyQt6.QtWidgets import (
            QApplication, QWidget, QHBoxLayout, QVBoxLayout,
            QHeaderView, QFileDialog, QTableWidgetItem, QFrame, QMenu,
            QAbstractItemView, QLabel, QToolTip, QMessageBox, QDialog
        )
except ImportError as e:
    print(f"CRITICAL ERROR: Missing dependencies.\nPlease install PyQt5-Fluent-Widgets or PyQt6-Fluent-Widgets with its matching Qt binding.\n\nDetails: {e}")
    sys.exit(1)

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

TEXT_CURSOR_END = QTextCursor.MoveOperation.End if hasattr(QTextCursor, "MoveOperation") else QTextCursor.End

import re
import shutil
import tempfile
import datetime
import subprocess
from dataclasses import dataclass, field
from functools import partial
from typing import List, Tuple, Optional, Dict, Pattern


def get_app_dir() -> str:
    # Resolve the directory where the script/executable lives, not the shell cwd.
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


APP_DIR = get_app_dir()

# Пробуем подключить pywin32 для защиты от повторного запуска.
try:
    import win32event
    import win32api
    import winerror
    MUTEX_AVAILABLE = True
except ImportError:
    MUTEX_AVAILABLE = False
    print("WARNING: pywin32 not installed. Single instance protection disabled.")

class SingleInstanceGuard:
    # Prevents running more than one instance using a named OS mutex.
    
    # Инициализирует имя мьютекса и флаги состояния.
    def __init__(self, app_name: str = "ScewinGUI_SingleInstance"):
        self.mutex_name = f"Local\\{app_name}"
        self.mutex_handle = None
        self._is_running = False
    
    # Проверяет, запущен ли уже другой экземпляр приложения.
    def is_already_running(self) -> bool:
        if not MUTEX_AVAILABLE:
            return False
        
        try:
            self.mutex_handle = win32event.CreateMutex(None, False, self.mutex_name)
            last_error = win32api.GetLastError()
            
            if last_error == winerror.ERROR_ALREADY_EXISTS:
                self._is_running = True
                return True
            
            self._is_running = False
            return False
            
        except Exception as e:
            print(f"Ошибка проверки единственного экземпляра: {e}")
            return False
    
    # Освобождает мьютекс при корректном завершении.
    def release(self) -> None:
        if self.mutex_handle and not self._is_running:
            try:
                win32api.CloseHandle(self.mutex_handle)
                self.mutex_handle = None
            except Exception as e:
                print(f"Ошибка освобождения мьютекса: {e}")
    
    # Подстраховка освобождения ресурса при удалении объекта.
    def __del__(self):
        self.release()

class DelayedToolTipEventFilter(QObject):
    # Delays tooltip display to reduce UI noise on hover.
    
    # Настраивает таймер задержки для всплывающих подсказок.
    def __init__(self, delay_ms: int = 500):
        super().__init__()
        self.delay_ms = delay_ms
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._show_tooltip)
        self.current_widget = None
        self.original_tooltip = ""
    
    # Отслеживает вход/выход курсора и откладывает показ tooltip.
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if isinstance(obj, QWidget):
            tooltip = obj.toolTip()
            
            if event.type() == QEvent.Type.Enter and tooltip:
                # Сохраняем оригинальный tooltip и временно скрываем его
                self.current_widget = obj
                self.original_tooltip = tooltip
                obj.setToolTip("")  # Временно убираем tooltip
                
                # Запускаем таймер на 3 секунды
                self.timer.start(self.delay_ms)
                
            elif event.type() == QEvent.Type.Leave:
                # При уходе курсора останавливаем таймер и восстанавливаем tooltip
                self.timer.stop()
                if self.current_widget and self.original_tooltip:
                    self.current_widget.setToolTip(self.original_tooltip)
                    self.current_widget = None
                    self.original_tooltip = ""
        
        return super().eventFilter(obj, event)
    
    # Показывает tooltip после истечения задержки.
    def _show_tooltip(self):
        # Show tooltip after the configured delay.
        if self.current_widget and self.original_tooltip:
            self.current_widget.setToolTip(self.original_tooltip)
            # Принудительно показываем tooltip
            QToolTip.showText(
                self.current_widget.mapToGlobal(QPoint(0, self.current_widget.height())),
                self.original_tooltip,
                self.current_widget
            )

@dataclass
class BiosSetting:
    # Represents one BIOS setup entry and its editable state.
    name: str = ""
    help_string: str = ""
    token: str = ""
    offset: str = ""
    width: str = ""
    bios_default: str = ""
    current_value: str = ""
    options: List[Tuple[str, str]] = field(default_factory=list)
    raw_value: str = ""
    is_numeric: bool = False
    options_map: Dict[str, str] = field(default_factory=dict)
    line_start: int = 0
    line_end: int = 0
    original_lines: List[str] = field(default_factory=list)
    initial_value: str = ""
    is_modified: bool = False

    # Удобное строковое представление для отладки.
    def __repr__(self) -> str:
        return f"<BiosSetting {self.name}: {self.current_value}>"
    
    # Устанавливает новое значение и фиксирует факт изменения.
    def set_value(self, new_value: str) -> None:
        clean_new = new_value.strip()
        clean_current = self.current_value.strip()
        
        if clean_current != clean_new:
            self.current_value = clean_new
            self.is_modified = (clean_new != self.initial_value)

    # Сбрасывает значение на BIOS Default, если доступно.
    def reset_to_default(self) -> None:
        if self.bios_default and self.bios_default != "-":
            self.set_value(self.bios_default)
    
    # Возвращает значение к исходному состоянию.
    def reset_to_initial(self) -> None:
        self.current_value = self.initial_value
        self.is_modified = False

class BiosParser:
    # Parses NVRAM text into settings and rebuilds updated content.
    
    RE_QUESTION = re.compile(r"^\s*Setup Question\s*=\s*(.*)")
    RE_HELP = re.compile(r"^\s*Help String\s*=\s*(.*)")
    RE_TOKEN = re.compile(r"^\s*Token\s*=\s*(.*)")
    RE_OFFSET = re.compile(r"^\s*Offset\s*=\s*(.*)")
    RE_DEFAULT = re.compile(r"^\s*BIOS Default\s*=\s*(.*)")
    RE_VALUE = re.compile(r"^\s*Value\s*=\s*(.*)")
    RE_OPTION = re.compile(r"(\*?)\[([0-9A-Fa-f]+)\]\s*(.*)")
    
    # Подготавливает хранилище заголовка файла.
    def __init__(self):
        self.header_lines: List[str] = []

    # Основной разбор текстового дампа NVRAM на настройки.
    def parse_file(self, content: str) -> List[BiosSetting]:
        # Parse raw NVRAM text into a list of BiosSetting objects.
        settings = []
        lines = content.splitlines()
        current_setting: Optional[BiosSetting] = None
        self.header_lines = []
        
        for i, line in enumerate(lines):
            match_question = self.RE_QUESTION.match(line)
            if match_question:
                if current_setting:
                    self._finalize_setting_block(current_setting, i, lines)
                    settings.append(current_setting)
                else:
                    if i > 0:
                        self.header_lines = lines[0:i]
                
                current_setting = BiosSetting()
                current_setting.line_start = i
                current_setting.name = match_question.group(1).strip()
                continue
            
            if current_setting:
                self._parse_line_for_setting(current_setting, line, self.RE_HELP, 'help_string')
                self._parse_line_for_setting(current_setting, line, self.RE_TOKEN, 'token')
                self._parse_line_for_setting(current_setting, line, self.RE_OFFSET, 'offset')
                self._parse_line_for_setting(current_setting, line, self.RE_DEFAULT, 'bios_default')
                
                match_value = self.RE_VALUE.match(line)
                if match_value:
                    val = match_value.group(1).split('//')[0].strip()
                    current_setting.raw_value = val
                    if not current_setting.current_value:
                        current_setting.current_value = val
                    current_setting.is_numeric = True
                    continue

                if "[" in line and "]" in line:
                    match_opt = self.RE_OPTION.search(line)
                    if match_opt:
                        is_active = match_opt.group(1) == '*'
                        opt_id = match_opt.group(2)
                        remainder = match_opt.group(3)
                        opt_text = remainder.split('//')[0].strip()
                        
                        current_setting.options.append((opt_id, opt_text))
                        current_setting.options_map[opt_text] = opt_id
                        
                        if is_active:
                            current_setting.current_value = opt_text

        if current_setting:
            self._finalize_setting_block(current_setting, len(lines), lines)
            settings.append(current_setting)
            
        return settings

    # Универсальный разбор метаданных строки по регекспу.
    def _parse_line_for_setting(self, setting, line, regex, attr):
        # Extract a single metadata field from a line when it matches.
        match = regex.match(line)
        if match:
            val = match.group(1).split('//')[0].strip()
            setattr(setting, attr, val)

    # Завершает блок настройки и сохраняет исходные строки.
    def _finalize_setting_block(self, setting, current_line_idx, lines):
        # Finalize a settings block and capture its original text.
        setting.line_end = current_line_idx - 1
        setting.original_lines = lines[setting.line_start : current_line_idx]
        if setting.bios_default:
            match = re.match(r"(\[.*?\])?(.*)", setting.bios_default)
            if match:
                setting.bios_default = match.group(2).strip()
        setting.initial_value = setting.current_value

    # Собирает новый текст NVRAM с учетом измененных значений.
    def generate_content(self, settings: List[BiosSetting]) -> str:
        # Rebuild the NVRAM file content using current setting values.
        output_lines = []
        if hasattr(self, 'header_lines'):
            output_lines.extend([line for line in self.header_lines if line.strip()])
            output_lines.append("") 
        
        re_option_line = re.compile(r"^(.*?)(\*?)(\[[0-9A-Fa-f]+\]\s*)(.*)$")
        re_value_line = re.compile(r"^(\s*Value\s*=\s*)(.*)")
        re_meta_field = re.compile(r"^(\s*)(Setup Question|Help String|Token|Offset|Width|BIOS Default|Options)(\s*=\s*)(.*)", re.IGNORECASE)

        for i, setting in enumerate(settings):
            if i > 0: output_lines.append("") 
            lines = list(setting.original_lines)
            target_value = setting.current_value
            for line in lines:
                match_meta = re_meta_field.match(line)
                if match_meta:
                    indent, key, _, val = match_meta.groups()
                    sep = "\t= " if key in ["Setup Question", "Help String"] else "\t="
                    line = f"{indent}{key}{sep}{val}"
                if setting.is_numeric:
                    match_val = re_value_line.match(line)
                    if match_val:
                        val_str = target_value
                        if setting.raw_value.startswith('<') and not val_str.startswith('<'):
                             val_str = f"<{val_str}>"
                        if setting.raw_value in line:
                             line = line.replace(setting.raw_value, val_str)
                    output_lines.append(line)
                elif setting.options:
                    match_opt = re_option_line.match(line)
                    if match_opt and "Setup Question" not in line and "BIOS Default" not in line:
                        prefix, asterisk, bracket_part, remainder = match_opt.groups()
                        opt_text_clean = remainder.split('//')[0].strip()
                        is_target = (opt_text_clean == target_value)
                        output_lines.append(f"{prefix}{'*' if is_target else ''}{bracket_part}{remainder}")
                    else:
                        output_lines.append(line)
                else:
                    output_lines.append(line)
        return "\n".join(output_lines)

class BiosService:
    # Handles SCEWIN dependencies and safe file IO for NVRAM files.
    
    # Сохраняет путь к исполняемому файлу SCEWIN.
    def __init__(self, scewin_path: str = "SCEWIN_64.exe"):
        self.base_dir = APP_DIR
        self.scewin_path = scewin_path
    
    def resolve_path(self, path: str) -> str:
        # Resolve relative paths against the application directory.
        if os.path.isabs(path):
            return path
        return os.path.join(self.base_dir, path)
    
    def get_required_files(self) -> List[str]:
        return [self.scewin_path, "amifldrv64.sys", "amigendrv64.sys"]

    def resolve_scewin_args(self, args: List[str]) -> List[str]:
        # SCEWIN uses the argument after /s as the input/output file path.
        resolved: List[str] = []
        previous = ""
        for arg in args:
            if previous.lower() == "/s":
                resolved.append(self.resolve_path(arg))
            else:
                resolved.append(arg)
            previous = arg
        return resolved
    
    # Проверяет наличие необходимых файлов рядом с приложением.
    def check_dependencies(self) -> Tuple[bool, List[str], List[str]]:
        # Verify required SCEWIN files are present and readable.
        missing: List[str] = []
        unreadable: List[str] = []
        for relative_name in self.get_required_files():
            abs_path = self.resolve_path(relative_name)
            if not os.path.exists(abs_path):
                missing.append(relative_name)
                continue
            try:
                with open(abs_path, "rb") as binary_file:
                    if not binary_file.read(64):
                        unreadable.append(relative_name)
            except OSError:
                unreadable.append(relative_name)
        return len(missing) == 0 and len(unreadable) == 0, missing, unreadable

    def get_readable_dependency_info(self) -> List[Tuple[str, str, int]]:
        # Return dependency info for files that can actually be opened.
        readable_files: List[Tuple[str, str, int]] = []
        for relative_name in self.get_required_files():
            abs_path = self.resolve_path(relative_name)
            try:
                with open(abs_path, "rb") as binary_file:
                    if binary_file.read(64):
                        readable_files.append((relative_name, abs_path, os.path.getsize(abs_path)))
            except OSError:
                continue
        return readable_files
    
    # Создает резервную копию NVRAM файла с таймстампом.
    def create_backup(self, source: str, backup_dir: str = "backups") -> str:
        # Copy the source NVRAM file into a timestamped backup.
        source_path = self.resolve_path(source)
        backup_path = self.resolve_path(backup_dir)
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Файл не найден: {source}")
        os.makedirs(backup_path, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = os.path.join(backup_path, f"nvram_backup_{timestamp}.txt")
        shutil.copy(source_path, dest)
        return dest
    
    # Пишет файл через временный файл для атомарности.
    def atomic_write(self, filepath: str, content: str) -> None:
        # Write data using a temp file and atomic replace.
        target_path = self.resolve_path(filepath)
        dir_path = os.path.dirname(target_path) or self.base_dir
        temp_fd, temp_path = tempfile.mkstemp(dir=dir_path, prefix='.tmp_nvram_', suffix='.txt')
        try:
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                f.write(content)
            os.replace(temp_path, target_path)
        except Exception:
            if os.path.exists(temp_path):
                try: os.unlink(temp_path)
                except: pass
            raise
    
    # Загружает текстовый файл с запасными кодировками.
    def load_file(self, filepath: str) -> str:
        # Load a text file with fallback encodings.
        resolved_path = self.resolve_path(filepath)
        if not os.path.exists(resolved_path):
            raise FileNotFoundError(f"Файл не найден: {filepath}")
        try:
            with open(resolved_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            pass
        try:
            with open(resolved_path, 'r', encoding='cp1252') as f:
                return f.read()
        except UnicodeDecodeError:
            pass
        with open(resolved_path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()

# Файлы/пути, с которыми работает приложение.
NVRAM_FILE: str = "nvram.txt"
NVRAM_NEW_FILE: str = "nvram_new.txt"
BACKUP_DIR: str = "backups"
SCEWIN_EXE: str = "SCEWIN_64.exe"

# Тайминги и задержки для UI и задач.
SUBPROCESS_TIMEOUT: int = 30
SEARCH_DEBOUNCE_MS: int = 150
SORT_DEBOUNCE_MS: int = 50
AUTO_LOAD_DELAY_MS: int = 200
WORKER_WAIT_MS: int = 1000

# Размеры и константы компоновки интерфейса.
COLUMN_WIDTH_PARAM: int = 420
COLUMN_WIDTH_VALUE: int = 200
COLUMN_WIDTH_DEFAULT: int = 160
COLUMN_WIDTH_STATUS: int = 150
ROW_HEIGHT: int = 42
WIDGET_HEIGHT: int = 32
SEARCH_BAR_WIDTH: int = 350
LOG_CARD_HEIGHT: int = 120
LOG_TEXT_WIDTH: int = 400
WINDOW_WIDTH: int = 1100
WINDOW_HEIGHT: int = 750
LAYOUT_MARGIN: int = 30
LAYOUT_SPACING: int = 15
BORDER_RADIUS: int = 8

# Метаданные приложения и настройки локализации.
APP_VERSION: str = "1.0.0"
APP_NAME: str = "Scewin GUI"
CONFIG_FILE: str = os.path.join(APP_DIR, "settings.ini")
DEFAULT_LANGUAGE: str = "ru"
LANG_OPTIONS: List[Tuple[str, str]] = [
    ("en", "English"),
    ("uk", "Українська"),
    ("ru", "Русский"),
]
# Словарь переводов интерфейса.
TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "ru": {
        "nav.editor": "Редактор NVRAM",
        "nav.backup": "Бэкап",
        "nav.about": "О программе",
        "nav.language": "Язык",
        "nav.language_tooltip": "Смена языка интерфейса",
        "editor.title": "Редактор BIOS NVRAM",
        "editor.subtitle": "Безопасное редактирование скрытых настроек.",
        "search.placeholder": "Поиск (Название, Токен, Смещение)...",
        "search.tooltip": "Ctrl+F для быстрого поиска, Esc для очистки",
        "table.param": "Параметр",
        "table.value": "Значение",
        "table.default": "BIOS Default",
        "table.status": "Статус",
        "table.id": "ID",
        "details.none": "Параметр не выбран",
        "details.select_row": "Выберите строку для деталей.",
        "details.no_description": "Нет описания",
        "button.import": "Импорт",
        "button.export": "Экспорт",
        "button.import_loaded": "Импорт файла",
        "button.apply": "Применить",
        "button.open_file": "Открыть файл",
        "tooltip.import": "Импортирует изменения из nvram_new.txt в BIOS",
        "tooltip.export": "Экспортирует текущие настройки BIOS в файл nvram.txt",
        "tooltip.import_loaded": "Импортирует загруженный файл в BIOS",
        "tooltip.apply": "Сохраняет изменения в файл nvram_new.txt",
        "tooltip.open_file": "Открыть файл",
        "action.export": "Экспорт NVRAM",
        "action.import": "Импорт NVRAM",
        "action.import_loaded": "Импорт загруженного файла",
        "status.modified": "Изменено",
        "status.reset_default": "BIOS Default",
        "status.revert": "Отменить изменения",
        "log.warning": "ВНИМАНИЕ: {message}",
        "log.reading": "Чтение файла: {file}",
        "log.loaded": "Успешно загружено: {count} настроек",
        "log.read_error": "Ошибка чтения: {error}",
        "apply.saved": "Сохранено {count} изменений в {file}",
        "log.changed": "Изменено: {name} -> {value}",
        "log.reset": "Сброс {name} BIOS Default",
        "log.started": "Запуск: {desc}...",
        "log.success": "УСПЕХ: {detail}",
        "log.error": "ОШИБКА: {detail}",
        "deps.missing": "Отсутствуют файлы: {files}",
        "deps.ready": "Система готова. Зависимости найдены.",
        "file.not_found_auto": "Файл {file} не найден. Запуск автоматического экспорта...",
        "infobar.startup_error": "Ошибка запуска",
        "title.backup": "Бэкап",
        "infobar.loaded_title": "Загружено",
        "infobar.loaded_content": "Прочитано {count} параметров",
        "infobar.warning": "Внимание",
        "infobar.no_file": "Нет файла {file}",
        "infobar.no_new_file": "Файл {file} не найден. Сначала примените изменения.",
        "infobar.error": "Ошибка",
        "infobar.no_changes_title": "Нет изменений",
        "infobar.no_changes_content": "Нечего сохранять",
        "infobar.no_loaded_file": "Файл не загружен",
        "infobar.ready_import_title": "Готово к импорту",
        "infobar.ready_import_content": "Файл {file} создан.",
        "infobar.loading_title": "Загрузка",
        "infobar.loading_content": "{desc} в процессе...",
        "infobar.success_content": "Завершено успешно",
        "infobar.see_logs": "См. логи",
        "dialog.open_nvram": "Открыть NVRAM",
        "dialog.file_filter": "Text (*.txt);;All (*.*)",
        "backup.title": "Бэкап NVRAM",
        "backup.subtitle": "Резервные копии после экспорта и вручную.",
        "backup.table.file": "Файл",
        "backup.table.date": "Дата",
        "backup.table.actions": "Действия",
        "button.create_backup": "Создать бэкап",
        "button.open_folder": "Открыть папку",
        "button.refresh": "Обновить",
        "button.restore": "Восстановить",
        "button.delete": "Удалить",
        "tooltip.refresh": "Обновить список",
        "tooltip.restore": "Импортировать этот бэкап в BIOS",
        "tooltip.delete_backup": "Удалить этот бэкап",
        "backup.created": "Бэкап создан: {path}",
        "backup.auto_created": "Автобэкап создан: {path}",
        "backup.deleted": "Удален бэкап: {path}",
        "backup.error": "Ошибка бэкапа: {error}",
        "backup.saved": "Сохранено в {path}",
        "backup.deleted_short": "Бэкап удален.",
        "backup.deleted_title": "Удалено",
        "backup.restore_desc": "Восстановление из {name}",
        "backup.file_missing": "Файл бэкапа не найден.",
        "backup.select_for_delete": "Выберите бэкап для удаления.",
        "backup.no_backup": "Не удалось определить файл бэкапа.",
        "backup.delete_title": "Удаление бэкапа",
        "backup.delete_text": "Удалить файл?\n{name}",
        "backup.summary_total": "Всего бэкапов",
        "backup.summary_last": "Последний бэкап",
        "backup.summary_size": "Размер папки",
        "backup.summary_none": "Нет",
        "backup.empty": "Пока нет бэкапов",
        "about.developer": "Разработчик",
        "about.docs": "Документация",
        "about.version": "Версия {version}",
        "about.footer": "© 2024-{year} cat_fire. Все права защищены.",
        "about.docs_title": "Документация",
        "about.docs_header": "Документация Scewin GUI",
        "about.coffee": "☕ Купи мне кофе",
        "docs.text": """
📖 ДОКУМЕНТАЦИЯ SCEWIN GUI

═══════════════════════════════════════
🔧 ОСНОВНЫЕ КНОПКИ
═══════════════════════════════════════

• Экспорт — Экспортирует текущие настройки BIOS в файл nvram.txt
• Импорт — Импортирует изменения из nvram_new.txt в BIOS
• Применить — Сохраняет изменения в файл nvram_new.txt

═══════════════════════════════════════
📁 ПАНЕЛЬ ИНСТРУМЕНТОВ
═══════════════════════════════════════

• 🔍 Поиск — Фильтрует параметры по названию, токену или смещению
• 📂 Открыть файл — Загружает NVRAM файл вручную

═══════════════════════════════════════
⌨️ ГОРЯЧИЕ КЛАВИШИ
═══════════════════════════════════════

• Ctrl+F — Фокус на поле поиска
• ESC — Очистить поле поиска
• ↑↓ — Навигация по параметрам

═══════════════════════════════════════
📊 КОЛОНКА СТАТУС
═══════════════════════════════════════

• 🟢 Изменено — Параметр был изменен
• 🔁 BIOS Default — Сбросить к заводским настройкам
• 🕐 Отменить — Отменить изменения

═══════════════════════════════════════
💡 СОВЕТЫ
═══════════════════════════════════════

1. Перед изменениями создайте бэкап!
2. После «Применить» нажмите «Импорт» для записи в BIOS
3. Перезагрузите ПК для применения изменений
4. Бэкапы создаются автоматически после экспорта и вручную во вкладке «Бэкап»

═══════════════════════════════════════
⚠️ ПРЕДУПРЕЖДЕНИЯ
═══════════════════════════════════════

• Изменение настроек BIOS может привести к нестабильности системы
• Всегда сохраняйте бэкап перед внесением изменений
• Используйте программу на свой страх и риск
""".strip(),
        "single.title": "Scewin GUI уже запущен",
        "single.text": "Приложение Scewin GUI уже запущено.",
        "single.info": "Одновременная работа нескольких копий программы запрещена.",
        "language.menu_title": "Выбор языка",
    },
    "uk": {
        "nav.editor": "Редактор NVRAM",
        "nav.backup": "Бекап",
        "nav.about": "Про програму",
        "nav.language": "Мова",
        "nav.language_tooltip": "Зміна мови інтерфейсу",
        "editor.title": "Редактор BIOS NVRAM",
        "editor.subtitle": "Безпечне редагування прихованих налаштувань.",
        "search.placeholder": "Пошук (Назва, Токен, Зміщення)...",
        "search.tooltip": "Ctrl+F для швидкого пошуку, Esc для очищення",
        "table.param": "Параметр",
        "table.value": "Значення",
        "table.default": "BIOS Default",
        "table.status": "Статус",
        "table.id": "ID",
        "details.none": "Параметр не вибрано",
        "details.select_row": "Виберіть рядок для деталей.",
        "details.no_description": "Немає опису",
        "button.import": "Імпорт",
        "button.export": "Експорт",
        "button.import_loaded": "Імпорт файлу",
        "button.apply": "Застосувати",
        "button.open_file": "Відкрити файл",
        "tooltip.import": "Імпортує зміни з nvram_new.txt у BIOS",
        "tooltip.export": "Експортує поточні налаштування BIOS у файл nvram.txt",
        "tooltip.import_loaded": "Імпортує завантажений файл у BIOS",
        "tooltip.apply": "Зберігає зміни у файл nvram_new.txt",
        "tooltip.open_file": "Відкрити файл",
        "action.export": "Експорт NVRAM",
        "action.import": "Імпорт NVRAM",
        "action.import_loaded": "Імпорт завантаженого файлу",
        "status.modified": "Змінено",
        "status.reset_default": "BIOS Default",
        "status.revert": "Скасувати зміни",
        "log.warning": "УВАГА: {message}",
        "log.reading": "Читання файлу: {file}",
        "log.loaded": "Успішно завантажено: {count} налаштувань",
        "log.read_error": "Помилка читання: {error}",
        "apply.saved": "Збережено {count} змін у {file}",
        "log.changed": "Змінено: {name} -> {value}",
        "log.reset": "Скидання {name} BIOS Default",
        "log.started": "Запуск: {desc}...",
        "log.success": "УСПІХ: {detail}",
        "log.error": "ПОМИЛКА: {detail}",
        "deps.missing": "Відсутні файли: {files}",
        "deps.ready": "Система готова. Залежності знайдено.",
        "file.not_found_auto": "Файл {file} не знайдено. Запуск автоматичного експорту...",
        "infobar.startup_error": "Помилка запуску",
        "title.backup": "Бекап",
        "infobar.loaded_title": "Завантажено",
        "infobar.loaded_content": "Прочитано {count} параметрів",
        "infobar.warning": "Увага",
        "infobar.no_file": "Немає файлу {file}",
        "infobar.no_new_file": "Файл {file} не знайдено. Спочатку застосуйте зміни.",
        "infobar.error": "Помилка",
        "infobar.no_changes_title": "Немає змін",
        "infobar.no_changes_content": "Нічого зберігати",
        "infobar.no_loaded_file": "Файл не завантажено",
        "infobar.ready_import_title": "Готово до імпорту",
        "infobar.ready_import_content": "Файл {file} створено.",
        "infobar.loading_title": "Завантаження",
        "infobar.loading_content": "{desc} в процесі...",
        "infobar.success_content": "Завершено успішно",
        "infobar.see_logs": "Див. логи",
        "dialog.open_nvram": "Відкрити NVRAM",
        "dialog.file_filter": "Текст (*.txt);;Усі (*.*)",
        "backup.title": "Бекап NVRAM",
        "backup.subtitle": "Резервні копії після експорту та вручну.",
        "backup.table.file": "Файл",
        "backup.table.date": "Дата",
        "backup.table.actions": "Дії",
        "button.create_backup": "Створити бекап",
        "button.open_folder": "Відкрити папку",
        "button.refresh": "Оновити",
        "button.restore": "Відновити",
        "button.delete": "Видалити",
        "tooltip.refresh": "Оновити список",
        "tooltip.restore": "Імпортувати цей бекап у BIOS",
        "tooltip.delete_backup": "Видалити цей бекап",
        "backup.created": "Бекап створено: {path}",
        "backup.auto_created": "Автобекап створено: {path}",
        "backup.deleted": "Видалено бекап: {path}",
        "backup.error": "Помилка бекапу: {error}",
        "backup.saved": "Збережено у {path}",
        "backup.deleted_short": "Бекап видалено.",
        "backup.deleted_title": "Видалено",
        "backup.restore_desc": "Відновлення з {name}",
        "backup.file_missing": "Файл бекапу не знайдено.",
        "backup.select_for_delete": "Виберіть бекап для видалення.",
        "backup.no_backup": "Не вдалося визначити файл бекапу.",
        "backup.delete_title": "Видалення бекапу",
        "backup.delete_text": "Видалити файл?\n{name}",
        "backup.summary_total": "Всього бекапів",
        "backup.summary_last": "Останній бекап",
        "backup.summary_size": "Розмір папки",
        "backup.summary_none": "Немає",
        "backup.empty": "Поки що немає бекапів",
        "about.developer": "Розробник",
        "about.docs": "Документація",
        "about.version": "Версія {version}",
        "about.footer": "© 2024-{year} cat_fire. Усі права захищені.",
        "about.docs_title": "Документація",
        "about.docs_header": "Документація Scewin GUI",
        "about.coffee": "☕ Купи мені каву",
        "docs.text": """
📖 ДОКУМЕНТАЦІЯ SCEWIN GUI

═══════════════════════════════════════
🔧 ОСНОВНІ КНОПКИ
═══════════════════════════════════════

• Експорт — Експортує поточні налаштування BIOS у файл nvram.txt
• Імпорт — Імпортує зміни з nvram_new.txt у BIOS
• Застосувати — Зберігає зміни у файл nvram_new.txt

═══════════════════════════════════════
📁 ПАНЕЛЬ ІНСТРУМЕНТІВ
═══════════════════════════════════════

• 🔍 Пошук — Фільтрує параметри за назвою, токеном або зміщенням
• 📂 Відкрити файл — Завантажує NVRAM файл вручну

═══════════════════════════════════════
⌨️ ГАРЯЧІ КЛАВІШІ
═══════════════════════════════════════

• Ctrl+F — Фокус на полі пошуку
• ESC — Очистити поле пошуку
• ↑↓ — Навігація по параметрах

═══════════════════════════════════════
📊 КОЛОНКА СТАТУС
═══════════════════════════════════════

• 🟢 Змінено — Параметр було змінено
• 🔁 BIOS Default — Скинути до заводських налаштувань
• 🕐 Скасувати — Скасувати зміни

═══════════════════════════════════════
💡 ПОРАДИ
═══════════════════════════════════════

1. Перед змінами створіть бекап!
2. Після «Застосувати» натисніть «Імпорт» для запису в BIOS
3. Перезавантажте ПК для застосування змін
4. Бекапи створюються автоматично після експорту та вручну у вкладці «Бекап»

═══════════════════════════════════════
⚠️ ПОПЕРЕДЖЕННЯ
═══════════════════════════════════════

• Зміна налаштувань BIOS може призвести до нестабільності системи
• Завжди зберігайте бекап перед внесенням змін
• Використовуйте програму на свій страх і ризик
""".strip(),
        "single.title": "Scewin GUI вже запущено",
        "single.text": "Застосунок Scewin GUI вже запущено.",
        "single.info": "Одночасна робота кількох копій програми заборонена.",
        "language.menu_title": "Вибір мови",
    },
    "en": {
        "nav.editor": "NVRAM Editor",
        "nav.backup": "Backup",
        "nav.about": "About",
        "nav.language": "Language",
        "nav.language_tooltip": "Change interface language",
        "editor.title": "BIOS NVRAM Editor",
        "editor.subtitle": "Safe editing of hidden settings.",
        "search.placeholder": "Search (Name, Token, Offset)...",
        "search.tooltip": "Ctrl+F to search, Esc to clear",
        "table.param": "Parameter",
        "table.value": "Value",
        "table.default": "BIOS Default",
        "table.status": "Status",
        "table.id": "ID",
        "details.none": "No parameter selected",
        "details.select_row": "Select a row for details.",
        "details.no_description": "No description",
        "button.import": "Import",
        "button.export": "Export",
        "button.import_loaded": "Import file",
        "button.apply": "Apply",
        "button.open_file": "Open file",
        "tooltip.import": "Imports changes from nvram_new.txt into BIOS",
        "tooltip.export": "Exports current BIOS settings to nvram.txt",
        "tooltip.import_loaded": "Imports the loaded file into BIOS",
        "tooltip.apply": "Saves changes to nvram_new.txt",
        "tooltip.open_file": "Open file",
        "action.export": "Export NVRAM",
        "action.import": "Import NVRAM",
        "action.import_loaded": "Import loaded file",
        "status.modified": "Modified",
        "status.reset_default": "BIOS Default",
        "status.revert": "Revert changes",
        "log.warning": "WARNING: {message}",
        "log.reading": "Reading file: {file}",
        "log.loaded": "Loaded successfully: {count} settings",
        "log.read_error": "Read error: {error}",
        "apply.saved": "Saved {count} changes to {file}",
        "log.changed": "Changed: {name} -> {value}",
        "log.reset": "Reset {name} to BIOS Default",
        "log.started": "Start: {desc}...",
        "log.success": "SUCCESS: {detail}",
        "log.error": "ERROR: {detail}",
        "deps.missing": "Missing files: {files}",
        "deps.ready": "System ready. Dependencies found.",
        "file.not_found_auto": "File {file} not found. Starting auto export...",
        "infobar.startup_error": "Startup error",
        "title.backup": "Backup",
        "infobar.loaded_title": "Loaded",
        "infobar.loaded_content": "Read {count} parameters",
        "infobar.warning": "Warning",
        "infobar.no_file": "File {file} not found",
        "infobar.no_new_file": "File {file} not found. Apply changes first.",
        "infobar.error": "Error",
        "infobar.no_changes_title": "No changes",
        "infobar.no_changes_content": "Nothing to save",
        "infobar.no_loaded_file": "No file loaded",
        "infobar.ready_import_title": "Ready to import",
        "infobar.ready_import_content": "File {file} created.",
        "infobar.loading_title": "Loading",
        "infobar.loading_content": "{desc} in progress...",
        "infobar.success_content": "Completed successfully",
        "infobar.see_logs": "See logs",
        "dialog.open_nvram": "Open NVRAM",
        "dialog.file_filter": "Text (*.txt);;All (*.*)",
        "backup.title": "NVRAM Backup",
        "backup.subtitle": "Backups after export and manual ones.",
        "backup.table.file": "File",
        "backup.table.date": "Date",
        "backup.table.actions": "Actions",
        "button.create_backup": "Create backup",
        "button.open_folder": "Open folder",
        "button.refresh": "Refresh",
        "button.restore": "Restore",
        "button.delete": "Delete",
        "tooltip.refresh": "Refresh list",
        "tooltip.restore": "Import this backup into BIOS",
        "tooltip.delete_backup": "Delete this backup",
        "backup.created": "Backup created: {path}",
        "backup.auto_created": "Auto backup created: {path}",
        "backup.deleted": "Backup deleted: {path}",
        "backup.error": "Backup error: {error}",
        "backup.saved": "Saved to {path}",
        "backup.deleted_short": "Backup deleted.",
        "backup.deleted_title": "Deleted",
        "backup.restore_desc": "Restore from {name}",
        "backup.file_missing": "Backup file not found.",
        "backup.select_for_delete": "Select a backup to delete.",
        "backup.no_backup": "Unable to determine the backup file.",
        "backup.delete_title": "Delete backup",
        "backup.delete_text": "Delete file?\n{name}",
        "backup.summary_total": "Total backups",
        "backup.summary_last": "Last backup",
        "backup.summary_size": "Folder size",
        "backup.summary_none": "None",
        "backup.empty": "No backups yet",
        "about.developer": "Developer",
        "about.docs": "Documentation",
        "about.version": "Version {version}",
        "about.footer": "© 2024-{year} cat_fire. All rights reserved.",
        "about.docs_title": "Documentation",
        "about.docs_header": "Scewin GUI Documentation",
        "about.coffee": "☕ Buy me a coffee",
        "docs.text": """
📖 SCEWIN GUI DOCUMENTATION

═══════════════════════════════════════
🔧 MAIN BUTTONS
═══════════════════════════════════════

• Export — Exports current BIOS settings to nvram.txt
• Import — Imports changes from nvram_new.txt into BIOS
• Apply — Saves changes to nvram_new.txt

═══════════════════════════════════════
📁 TOOLBAR
═══════════════════════════════════════

• 🔍 Search — Filters parameters by name, token, or offset
• 📂 Open file — Loads an NVRAM file manually

═══════════════════════════════════════
⌨️ HOTKEYS
═══════════════════════════════════════

• Ctrl+F — Focus search field
• ESC — Clear search field
• ↑↓ — Navigate parameters

═══════════════════════════════════════
📊 STATUS COLUMN
═══════════════════════════════════════

• 🟢 Modified — Parameter was changed
• 🔁 BIOS Default — Reset to defaults
• 🕐 Revert — Revert changes

═══════════════════════════════════════
💡 TIPS
═══════════════════════════════════════

1. Create a backup before changes!
2. After “Apply”, click “Import” to write to BIOS
3. Reboot the PC to apply changes
4. Backups are created automatically after export and manually in the “Backup” tab

═══════════════════════════════════════
⚠️ WARNINGS
═══════════════════════════════════════

• Changing BIOS settings may lead to system instability
• Always keep a backup before changes
• Use this program at your own risk
""".strip(),
        "single.title": "Scewin GUI is already running",
        "single.text": "The Scewin GUI application is already running.",
        "single.info": "Running multiple instances of the program is not allowed.",
        "language.menu_title": "Select language",
    },
}

class LanguageManager(QObject):
    # Tracks current UI language and resolves translation keys.
    # Сигнал: язык был изменен.
    language_changed = pyqtSignal(str)

    # Инициализирует язык интерфейса и проверяет наличие перевода.
    def __init__(self, default_language: str = DEFAULT_LANGUAGE):
        super().__init__()
        self._language = default_language if default_language in TRANSLATIONS else "ru"

    # Возвращает текущий код языка.
    def language(self) -> str:
        return self._language

    # Устанавливает язык, если он поддерживается, и уведомляет подписчиков.
    def set_language(self, language: str) -> None:
        if language == self._language:
            return
        if language not in TRANSLATIONS:
            return
        self._language = language
        self.language_changed.emit(language)

    # Возвращает локализованный текст по ключу.
    def tr(self, key: str, **kwargs) -> str:
        lang_map = TRANSLATIONS.get(self._language, {})
        text = lang_map.get(key) or TRANSLATIONS["ru"].get(key) or key
        if kwargs:
            return text.format(**kwargs)
        return text

def tr_global(key: str, **kwargs) -> str:
    # Глобальный перевод для ранних диалогов (до создания окна).
    lang_map = TRANSLATIONS.get(DEFAULT_LANGUAGE, {})
    text = lang_map.get(key) or TRANSLATIONS["ru"].get(key) or key
    if kwargs:
        return text.format(**kwargs)
    return text

def load_language_setting() -> str:
    # Читает язык интерфейса из settings.ini.
    settings = QSettings(CONFIG_FILE, QSettings.Format.IniFormat)
    lang = settings.value("ui/language", DEFAULT_LANGUAGE)
    return lang if isinstance(lang, str) else DEFAULT_LANGUAGE

def save_language_setting(language: str) -> None:
    # Сохраняет выбранный язык в settings.ini.
    settings = QSettings(CONFIG_FILE, QSettings.Format.IniFormat)
    settings.setValue("ui/language", language)

class BiosWorker(QThread):
    # Runs SCEWIN commands in a background thread and reports results.
    finished = pyqtSignal(bool, str, str)
    # Сохраняет параметры команды для фонового запуска.
    def __init__(self, command: str, args: List[str], desc: str):
        super().__init__()
        self.command = command
        self.args = args
        self.desc = desc
    # Выполняет команду SCEWIN с таймаутом и эмитит результат.
    def run(self):
        # Executes the command with a timeout and emits success or error.
        try:
            full_cmd = [self.command] + self.args
            creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            result = subprocess.run(full_cmd, capture_output=True, text=True, creationflags=creation_flags, timeout=SUBPROCESS_TIMEOUT)
            if result.returncode == 0:
                self.finished.emit(True, self.desc, result.stdout)
            else:
                self.finished.emit(False, self.desc, f"Ошибка (Код: {result.returncode})\n{result.stderr}")
        except Exception as e:
            self.finished.emit(False, self.desc, f"Системная ошибка: {str(e)}")

class NVRAMLoadWorker(QThread):
    # Loads and parses NVRAM text outside the GUI thread.
    finished = pyqtSignal(bool, str, object, object)

    def __init__(self, filepath: str):
        super().__init__()
        self.filepath = filepath

    def run(self):
        try:
            service = BiosService(SCEWIN_EXE)
            parser = BiosParser()
            content = service.load_file(self.filepath)
            settings = parser.parse_file(content)
            self.finished.emit(True, self.filepath, settings, parser.header_lines)
        except Exception as e:
            self.finished.emit(False, str(e), None, None)


class NVRAMInterface(QWidget):
    # Main editor UI for viewing and modifying NVRAM settings.
    # Инициализирует состояние интерфейса редактора и таймеры.
    def __init__(self, parent=None, lang_manager: Optional[LanguageManager] = None):
        super().__init__(parent=parent)
        self.setObjectName("NVRAMInterface")
        self.parser = BiosParser()
        self.service = BiosService(SCEWIN_EXE)
        self.lang_manager = lang_manager or LanguageManager()
        self.settings: List[BiosSetting] = []
        self.loaded_filepath: Optional[str] = None
        self.worker: Optional[BiosWorker] = None
        self.load_worker: Optional[NVRAMLoadWorker] = None
        self.sort_state: dict = {}
        self._pending_sort_index: Optional[int] = None
        self._last_worker_action: Optional[str] = None
        
        self._sort_timer = QTimer(self)
        self._sort_timer.setSingleShot(True)
        self._sort_timer.setInterval(SORT_DEBOUNCE_MS)
        self._sort_timer.timeout.connect(self._execute_sort)
        
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(SEARCH_DEBOUNCE_MS)
        self._search_timer.timeout.connect(self._execute_filter)
        
        self.tooltip_filter = DelayedToolTipEventFilter(delay_ms=500)
        self.init_ui()
        self.lang_manager.language_changed.connect(self.apply_language)
        self.apply_language()
        QTimer.singleShot(100, self.check_dependencies)
        
        if os.path.exists(self.service.resolve_path(NVRAM_FILE)):
            QTimer.singleShot(AUTO_LOAD_DELAY_MS, lambda: self.load_data(NVRAM_FILE))
        else:
            QTimer.singleShot(AUTO_LOAD_DELAY_MS, self.action_export_bios)

    # Укороченный доступ к переводу строк.
    def t(self, key: str, **kwargs) -> str:
        return self.lang_manager.tr(key, **kwargs)

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
        header.addLayout(titles)
        header.addStretch(1)
        
        self.btn_import = PushButton(FIF.DOWNLOAD, "", self)
        self.btn_import.clicked.connect(self.action_import_bios)
        self.btn_export = PushButton(FIF.SHARE, "", self)
        self.btn_export.clicked.connect(self.action_export_bios)
        self.btn_import_loaded = PushButton(FIF.DOCUMENT, "", self)
        self.btn_import_loaded.clicked.connect(self.action_import_loaded)
        self.btn_save = PrimaryPushButton(FIF.SAVE, "", self)
        self.btn_save.clicked.connect(self.action_apply_changes)
        self.btn_save.setDefault(False)
        self.btn_save.setAutoDefault(False)
        
        header.addWidget(self.btn_export)
        header.addWidget(self.btn_import)
        header.addWidget(self.btn_import_loaded)
        header.addSpacing(10)
        header.addWidget(self.btn_save)
        self.btn_export.installEventFilter(self.tooltip_filter)
        self.btn_import.installEventFilter(self.tooltip_filter)
        self.btn_import_loaded.installEventFilter(self.tooltip_filter)
        self.btn_save.installEventFilter(self.tooltip_filter)
        self.v_layout.addLayout(header)

        # Toolbar: search field, shortcuts, and file open button.
        toolbar = QHBoxLayout()
        self.search_bar = SearchLineEdit(self)
        self.search_bar.setFixedWidth(SEARCH_BAR_WIDTH)
        self.search_bar.textChanged.connect(self._on_search_changed)
        
        self.shortcut_search = QShortcut(QKeySequence("Ctrl+F"), self)
        self.shortcut_search.activated.connect(self.search_bar.setFocus)
        
        self.shortcut_esc = QShortcut(QKeySequence("Escape"), self.search_bar)
        self.shortcut_esc.activated.connect(self.search_bar.clear)
        
        self.btn_open = TransparentToolButton(FIF.FOLDER, self)
        self.btn_open.clicked.connect(self.open_file_dialog)

        toolbar.addWidget(self.search_bar)
        toolbar.addStretch(1)
        toolbar.addWidget(self.btn_open)
        self.v_layout.addLayout(toolbar)

        # Settings table: list, selection, and sorting controls.
        self.table_card = CardWidget(self)
        self.table = TableWidget(self)
        self.table.setBorderVisible(True)
        self.table.setBorderRadius(BORDER_RADIUS)
        self.table.setColumnCount(5)
        
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setShowGrid(False)
        if hasattr(self.table, "setCheckedColor"):
            transparent = QColor(0, 0, 0, 0)
            self.table.setCheckedColor(transparent, transparent)
        
        self.table.setSortingEnabled(False) 
        self.table.horizontalHeader().setSortIndicatorShown(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().hide()
        
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setAutoScroll(False)
        
        self.table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        
        self.table.setColumnWidth(0, COLUMN_WIDTH_PARAM)
        self.table.setColumnWidth(1, COLUMN_WIDTH_VALUE)
        self.table.setColumnWidth(2, COLUMN_WIDTH_DEFAULT)
        self.table.setColumnWidth(3, COLUMN_WIDTH_STATUS)
        self.table.setColumnHidden(4, True)
        
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.cellClicked.connect(self.on_table_click)
        self.table.currentCellChanged.connect(self.on_cell_changed)
        
        self.table.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.horizontalHeader().customContextMenuRequested.connect(self.show_header_menu)
        self.table.horizontalHeader().sectionClicked.connect(self.handle_header_click)
        
        table_layout = QVBoxLayout(self.table_card)
        table_layout.setContentsMargins(0,0,0,0)
        table_layout.addWidget(self.table)
        self.v_layout.addWidget(self.table_card, 1)

        self.log_card = CardWidget(self)
        self.log_card.setFixedHeight(LOG_CARD_HEIGHT)
        log_h_layout = QHBoxLayout(self.log_card)
        
        info_layout = QVBoxLayout()
        self.lbl_p_name = SubtitleLabel("", self)
        self.lbl_p_name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        
        self.line = QFrame(self)
        self.line.setFrameShape(QFrame.Shape.HLine)
        self.line.setFrameShadow(QFrame.Shadow.Sunken)
        self.line.setFixedHeight(1)
        self.line.setStyleSheet("background-color: rgba(255, 255, 255, 30);")
        
        self.lbl_p_desc = BodyLabel("", self)
        self.lbl_p_desc.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_p_desc.setWordWrap(True)
        self.lbl_p_desc.setTextColor(QColor(220, 220, 220), QColor(240, 240, 240))
        info_layout.addWidget(self.lbl_p_name)
        info_layout.addWidget(self.line)
        info_layout.addWidget(self.lbl_p_desc)
        info_layout.addStretch()
        
        self.txt_log = TextEdit(self)
        self.txt_log.setReadOnly(True)
        self.txt_log.setFixedWidth(LOG_TEXT_WIDTH)
        
        log_h_layout.addLayout(info_layout, 1)
        log_h_layout.addWidget(self.txt_log)
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
        self.btn_save.setText(self.t("button.apply"))
        self.btn_save.setToolTip(self.t("tooltip.apply"))
        self.search_bar.setPlaceholderText(self.t("search.placeholder"))
        self.search_bar.setToolTip(self.t("search.tooltip"))
        self.btn_open.setToolTip(self.t("tooltip.open_file"))
        self.table.setHorizontalHeaderLabels([
            self.t("table.param"),
            self.t("table.value"),
            self.t("table.default"),
            self.t("table.status"),
            self.t("table.id"),
        ])
        if self.table.currentRow() >= 0:
            self._update_details(self.table.currentRow())
        else:
            self.lbl_p_name.setText(self.t("details.none"))
            self.lbl_p_desc.setText(self.t("details.select_row"))
        for row, setting in enumerate(self.settings):
            self.update_status_cell(row, setting)

    # Добавляет строку в лог-панель.
    def log(self, msg: str) -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.txt_log.append(f"[{ts}] {msg}")
        self.txt_log.moveCursor(TEXT_CURSOR_END)

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
    def load_data(self, filepath):
        if self.load_worker is not None and self.load_worker.isRunning():
            InfoBar.warning(
                self.t("infobar.warning"),
                self.t("infobar.loading_content", desc=filepath),
                parent=self
            )
            return
        self.log(self.t("log.reading", file=filepath))
        self.load_worker = NVRAMLoadWorker(filepath)
        self.load_worker.finished.connect(self.on_load_finished)
        self.load_worker.start()

    def on_load_finished(self, success, detail, settings, header_lines):
        if self.load_worker is not None:
            try:
                self.load_worker.finished.disconnect(self.on_load_finished)
            except TypeError:
                pass
            self.load_worker.deleteLater()
            self.load_worker = None

        if not success:
            self.log(self.t("log.error", detail=detail))
            InfoBar.error(self.t("infobar.error"), str(detail), parent=self)
            return

        self.parser.header_lines = header_lines or []
        self.settings = settings or []
        self.populate_table()
        self.loaded_filepath = detail
        self.log(self.t("log.loaded", count=len(self.settings)))
        InfoBar.success(
            self.t("infobar.loaded_title"),
            self.t("infobar.loaded_content", count=len(self.settings)),
            parent=self
        )

    # Заполняет таблицу параметров данными из парсера.
    def populate_table(self):
        self.table.setUpdatesEnabled(False) 
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.table.setRowCount(len(self.settings))
        for i, setting in enumerate(self.settings):
            item_name = QTableWidgetItem(setting.name)
            item_name.setData(Qt.ItemDataRole.UserRole, setting)
            item_name.setFlags(item_name.flags() ^ Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(i, 0, item_name)
            if setting.options:
                widget = ComboBox()
                widget.setFixedHeight(WIDGET_HEIGHT)
                widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                seen_texts = set()
                for opt_id, opt_text in setting.options:
                    if opt_text not in seen_texts:
                        widget.addItem(opt_text, userData=opt_id)
                        seen_texts.add(opt_text)
                
                if setting.current_value not in seen_texts:
                     widget.addItem(setting.current_value)
                     
                widget.setCurrentText(setting.current_value)
                widget.currentTextChanged.connect(partial(self.on_combo_changed, setting, widget))
                self.table.setCellWidget(i, 1, widget)
            elif setting.is_numeric:
                widget = LineEdit()
                widget.setFixedHeight(WIDGET_HEIGHT)
                if hasattr(widget, "setCustomFocusedBorderColor"):
                    transparent = QColor(0, 0, 0, 0)
                    widget.setCustomFocusedBorderColor(transparent, transparent)
                raw = setting.raw_value.strip('<>')
                widget.setText(raw)
                widget.setValidator(QRegularExpressionValidator(QRegularExpression(r'^(0x)?[0-9A-Fa-f]+$')))
                widget.editingFinished.connect(partial(self.on_edit_changed, setting, widget))
                self.table.setCellWidget(i, 1, widget)
            else:
                self.table.setItem(i, 1, QTableWidgetItem(setting.current_value))
            item_def = QTableWidgetItem(setting.bios_default or "-")
            item_def.setForeground(QBrush(QColor(220, 220, 220)))
            item_def.setFlags(item_def.flags() ^ Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(i, 2, item_def)
            self.update_status_cell(i, setting)
            
            item_idx = QTableWidgetItem()
            item_idx.setData(Qt.ItemDataRole.DisplayRole, i)
            self.table.setItem(i, 4, item_idx)
            if i and i % 100 == 0:
                QApplication.processEvents()
            
        self.table.setUpdatesEnabled(True) 
        self.filter_table()

    # Обновляет колонку статуса для конкретной строки.
    def update_status_cell(self, row, setting):
        name_item = self.table.item(row, 0)
        if name_item:
            font = name_item.font()
            font.setBold(setting.is_modified)
            name_item.setFont(font)
        
        has_bios_default = setting.bios_default and setting.bios_default != "-"
        differs_from_default = has_bios_default and setting.current_value.strip() != setting.bios_default.strip()
        
        show_buttons = setting.is_modified or differs_from_default
        
        item_status = QTableWidgetItem(self.t("status.modified") if setting.is_modified else "")
        item_status.setFlags(item_status.flags() ^ Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, 3, item_status)

        if show_buttons:
            item_status.setForeground(QBrush(QColor(0, 0, 0, 0)))
            
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            layout = QHBoxLayout(container)
            layout.setContentsMargins(5, 0, 20, 0)
            layout.setSpacing(4)
            
            if setting.is_modified:
                lbl_status = BodyLabel(self.t("status.modified"))
                lbl_status.setTextColor(QColor("#00c853"), QColor("#00c853"))
                layout.addWidget(lbl_status)
            
            layout.addStretch(1)
            
            if differs_from_default:
                btn_reset = TransparentToolButton(FIF.SYNC, self)
                btn_reset.setToolTip(self.t("status.reset_default"))
                btn_reset.setFixedSize(26, 26)
                btn_reset.clicked.connect(partial(self.reset_setting, setting))
                layout.addWidget(btn_reset)
            
            if setting.is_modified:
                btn_revert = TransparentToolButton(FIF.HISTORY, self)
                btn_revert.setToolTip(self.t("status.revert"))
                btn_revert.setFixedSize(26, 26)
                btn_revert.clicked.connect(partial(self.revert_setting, setting))
                layout.addWidget(btn_revert)
            
            self.table.setCellWidget(row, 3, container)
        else:
            self.table.removeCellWidget(row, 3)

    # Обрабатывает выбор значения в ComboBox.
    def on_combo_changed(self, setting, widget, text):
        index = self.table.indexAt(widget.pos())
        row = index.row()
        if row < 0: return

        if setting.current_value != text:
            setting.set_value(text)
            self.update_status_cell(row, setting)
            self.log(self.t("log.changed", name=setting.name, value=text))

    # Обрабатывает ввод значения в LineEdit.
    def on_edit_changed(self, setting, widget):
        index = self.table.indexAt(widget.pos())
        row = index.row()
        if row < 0: return

        new_text = widget.text()
        formatted = f"<{new_text}>" if setting.raw_value.startswith('<') else new_text
        if setting.current_value != formatted:
            setting.set_value(formatted)
            self.update_status_cell(row, setting)
            self.log(self.t("log.changed", name=setting.name, value=formatted))

    # Запускает таймер дебаунса поиска.
    def _on_search_changed(self, text: str) -> None:
        self._search_timer.start()
    
    # Выполняет фильтрацию после задержки.
    def _execute_filter(self) -> None:
        self.filter_table()
    
    # Фильтрует таблицу по тексту поиска.
    def filter_table(self) -> None:
        text = self.search_bar.text().lower().strip()
        self.table.setUpdatesEnabled(False)
        try:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if not item: 
                    continue
                s = item.data(Qt.ItemDataRole.UserRole)
                if not s:
                    continue
                matches = (
                    text in s.name.lower() or 
                    text in s.help_string.lower() or 
                    text in s.token.lower() or 
                    text in s.offset.lower()
                )
                self.table.setRowHidden(row, not matches)
        finally:
            self.table.setUpdatesEnabled(True)

    # Обновляет детали при клике по строке таблицы.
    def on_table_click(self, row, col):
        self._update_details(row)

    # Следит за сменой активной строки и прокруткой.
    def on_cell_changed(self, row, col, prev_row, prev_col):
        if row >= 0:
            self._update_details(row)
            item = self.table.item(row, 0)
            if item:
                self.table.scrollToItem(item, QAbstractItemView.ScrollHint.EnsureVisible)

    # Выводит подробности выбранной настройки.
    def _update_details(self, row):
        item = self.table.item(row, 0)
        if item:
            s = item.data(Qt.ItemDataRole.UserRole)
            self.lbl_p_name.setText(s.name)
            desc = s.help_string or self.t("details.no_description")
            extras = []
            if s.token: extras.append(f"Token: {s.token}")
            if s.offset: extras.append(f"Offset: {s.offset}")
            if extras: desc += "\n\n" + " | ".join(extras)
            self.lbl_p_desc.setText(desc)

    # Управляет состоянием сортировки при клике по заголовку.
    def handle_header_click(self, index):
        header = self.table.horizontalHeader()
        
        if index == 1:
            header.setSortIndicatorShown(False)
            self.sort_state = {}
            self._pending_sort_index = -1
            self._sort_timer.start()
            return
        
        for col in list(self.sort_state.keys()):
            if col != index: self.sort_state[col] = 0
        
        current = self.sort_state.get(index, 0)
        if current == 0: next_state = 2
        elif current == 2: next_state = 1
        else: next_state = 0
        
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
    def _execute_sort(self):
        index = self._pending_sort_index
        if index is None: return
        
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

    # Контекстное меню строки (можно расширить при необходимости).
    def show_context_menu(self, pos):
        pass

    # Контекстное меню заголовка таблицы (сброс фильтра).
    def show_header_menu(self, pos):
        menu = RoundMenu(parent=self)
        if self.search_bar.text():
            action_clear_filter = Action(FIF.CANCEL, "Сбросить фильтр", self)
            action_clear_filter.triggered.connect(self.search_bar.clear)
            menu.addAction(action_clear_filter)
        if not menu.actions(): return
        menu.exec(self.table.horizontalHeader().mapToGlobal(pos))

    # Ищет индекс строки таблицы по объекту настройки.
    def _find_row_by_setting(self, setting) -> int:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) is setting:
                return row
        return -1

    # Сбрасывает настройку на BIOS Default.
    def reset_setting(self, setting):
        row = self._find_row_by_setting(setting)
        if row < 0: return

        if not setting.bios_default or setting.bios_default == "-": return
        target_value = setting.bios_default
        widget = self.table.cellWidget(row, 1)
        if isinstance(widget, ComboBox):
            widget.blockSignals(True)
            idx = -1
            for i in range(widget.count()):
                if widget.itemText(i) == target_value:
                    idx = i
                    break
            if idx < 0:
                for i in range(widget.count()):
                    if target_value in widget.itemText(i) or widget.itemText(i) in target_value:
                        idx = i
                        break
            if idx >= 0:
                widget.setCurrentIndex(idx)
                target_value = widget.currentText()
            else:
                widget.setCurrentText(target_value)
            widget.blockSignals(False)
            setting.set_value(target_value)
            self.update_status_cell(row, setting)
        elif isinstance(widget, LineEdit):
            clean = setting.bios_default.strip('<>')
            widget.setText(clean)
            formatted = f"<{clean}>" if setting.raw_value.startswith('<') else clean
            setting.set_value(formatted)
            self.update_status_cell(row, setting)
        self.log(self.t("log.reset", name=setting.name))

    # Возвращает настройку к исходному значению.
    def revert_setting(self, setting):
        row = self._find_row_by_setting(setting)
        if row < 0: return

        target_value = setting.initial_value
        widget = self.table.cellWidget(row, 1)
        if isinstance(widget, ComboBox):
            widget.blockSignals(True)
            idx = -1
            for i in range(widget.count()):
                if widget.itemText(i) == target_value:
                    idx = i
                    break
            if idx < 0:
                for i in range(widget.count()):
                    if target_value in widget.itemText(i) or widget.itemText(i) in target_value:
                        idx = i
                        break
            if idx >= 0:
                widget.setCurrentIndex(idx)
                target_value = widget.currentText()
            else:
                widget.setCurrentText(target_value)
            widget.blockSignals(False)
            setting.set_value(target_value)
            setting.is_modified = False
            self.update_status_cell(row, setting)
        elif isinstance(widget, LineEdit):
            clean = target_value.strip('<>')
            widget.setText(clean)
            formatted = f"<{clean}>" if setting.raw_value.startswith('<') else clean
            setting.set_value(formatted)
            setting.is_modified = False
            self.update_status_cell(row, setting)

    # Диалог выбора NVRAM файла для загрузки.
    # Диалог выбора NVRAM файла для загрузки.
    def open_file_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.t("dialog.open_nvram"),
            "",
            self.t("dialog.file_filter")
        )
        if path: self.load_data(path)

    # Применяет изменения и сохраняет nvram_new.txt.
    def action_apply_changes(self):
        modified = [s for s in self.settings if s.is_modified]
        if not modified:
            InfoBar.info(
                self.t("infobar.no_changes_title"),
                self.t("infobar.no_changes_content"),
                parent=self
            )
            return
        try:
            content = self.parser.generate_content(modified)
            self.service.atomic_write(NVRAM_NEW_FILE, content)
            self.log(self.t("apply.saved", count=len(modified), file=NVRAM_NEW_FILE))
            InfoBar.success(
                self.t("infobar.ready_import_title"),
                self.t("infobar.ready_import_content", file=NVRAM_NEW_FILE),
                parent=self
            )
        except Exception as e:
            self.log(self.t("log.read_error", error=e))
            InfoBar.error(self.t("infobar.error"), str(e), parent=self)

    # Импортирует загруженный файл в BIOS через SCEWIN.
    def action_import_loaded(self):
        if not self.settings or not self.loaded_filepath:
            InfoBar.warning(
                self.t("infobar.warning"),
                self.t("infobar.no_loaded_file"),
                parent=self
            )
            return
        self._last_worker_action = "import_loaded"
        self.run_worker(
            SCEWIN_EXE,
            ["/i", "/s", self.loaded_filepath],
            self.t("action.import_loaded")
        )

    # Экспортирует текущие настройки BIOS в nvram.txt.
    def action_export_bios(self):
        self._last_worker_action = "export"
        self.run_worker(SCEWIN_EXE, ["/o", "/s", NVRAM_FILE], self.t("action.export"))

    # Импортирует nvram_new.txt в BIOS.
    def action_import_bios(self):
        if not os.path.exists(self.service.resolve_path(NVRAM_NEW_FILE)):
            InfoBar.error(
                self.t("infobar.error"),
                self.t("infobar.no_new_file", file=NVRAM_NEW_FILE),
                parent=self
            )
            return
        self._last_worker_action = "import"
        self.run_worker(SCEWIN_EXE, ["/i", "/s", NVRAM_NEW_FILE], self.t("action.import"))

    def run_worker(self, cmd: str, args: List[str], desc: str) -> None:
        if self.worker is not None:
            if self.worker.isRunning():
                InfoBar.warning(
                    self.t("infobar.warning"),
                    self.t("infobar.loading_content", desc=self.worker.desc),
                    parent=self
                )
                return
            try:
                self.worker.finished.disconnect(self.on_worker_finished)
            except TypeError:
                pass
            self.worker.deleteLater()
        
        self.log(self.t("log.started", desc=desc))
        resolved_cmd = self.service.resolve_path(cmd)
        resolved_args = self.service.resolve_scewin_args(args)
        self.worker = BiosWorker(resolved_cmd, resolved_args, desc)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()
        InfoBar.info(
            self.t("infobar.loading_title"),
            self.t("infobar.loading_content", desc=desc),
            parent=self
        )

    def on_worker_finished(self, success, title, detail):
        if success:
            self.log(self.t("log.success", detail=detail.strip()))
            InfoBar.success(title, self.t("infobar.success_content"), parent=self)
            if self._last_worker_action == "export":
                self.load_data(NVRAM_FILE)
                try:
                    backup_path = self.service.create_backup(NVRAM_FILE, BACKUP_DIR)
                    self.log(self.t("backup.auto_created", path=backup_path))
                    InfoBar.success(
                        self.t("title.backup"),
                        self.t("backup.saved", path=backup_path),
                        parent=self
                    )
                except Exception as e:
                    self.log(self.t("log.error", detail=e))
        else:
            self.log(self.t("log.error", detail=detail))
            InfoBar.error(title, self.t("infobar.see_logs"), parent=self)
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None

class BackupInterface(QWidget):
    # UI for listing, creating, restoring, and deleting backups.
    
    # Инициализирует интерфейс управления бэкапами.
    def __init__(self, parent=None, lang_manager: Optional[LanguageManager] = None):
        super().__init__(parent=parent)
        self.setObjectName("BackupInterface")
        self.service = BiosService(SCEWIN_EXE)
        self.lang_manager = lang_manager or LanguageManager()
        self.worker: Optional[BiosWorker] = None
        self.init_ui()
        self.lang_manager.language_changed.connect(self.apply_language)
        self.apply_language()
        self.refresh_backups()

    # Укороченный доступ к переводу строк.
    def t(self, key: str, **kwargs) -> str:
        return self.lang_manager.tr(key, **kwargs)
    
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
        self.backup_scroll.setStyleSheet("SmoothScrollArea { border: none; background: transparent; }")

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
    def _create_summary_item(self) -> Dict[str, QWidget]:
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

    # Обновляет блок сводки по списку бэкапов.
    def _update_summary(self, items: List[Tuple[str, float, int]]) -> None:
        total = len(items)
        last = self.t("backup.summary_none")
        if items:
            last_ts = items[0][1]
            last = datetime.datetime.fromtimestamp(last_ts).strftime("%Y-%m-%d %H:%M")
        size_total = sum(s for _, _, s in items)
        self.summary_total["value"].setText(str(total))
        self.summary_last["value"].setText(last)
        self.summary_size["value"].setText(self._format_size(size_total))

    # Добавляет строку в лог-панель бэкапов.
    def log(self, msg: str) -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.txt_log.append(f"[{ts}] {msg}")
        self.txt_log.moveCursor(TEXT_CURSOR_END)
    
    # Перестраивает список бэкапов и сводку.
    def refresh_backups(self) -> None:
        backup_path = self.service.resolve_path(BACKUP_DIR)
        while self.backup_list_layout.count():
            item = self.backup_list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        if not os.path.exists(backup_path):
            self.lbl_empty.setVisible(True)
            self.backup_scroll.setVisible(False)
            self._update_summary([])
            return
        items = []
        for name in os.listdir(backup_path):
            path = os.path.join(backup_path, name)
            if not os.path.isfile(path):
                continue
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                continue
            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0
            items.append((path, mtime, size))
        items.sort(key=lambda x: x[1], reverse=True)
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
                self.t("infobar.warning"),
                self.t("infobar.no_file", file=NVRAM_FILE),
                parent=self
            )
            return
        try:
            path = self.service.create_backup(NVRAM_FILE, BACKUP_DIR)
            InfoBar.success(
                self.t("title.backup"),
                self.t("backup.saved", path=path),
                parent=self
            )
            self.log(self.t("backup.created", path=path))
            self.refresh_backups()
        except Exception as e:
            self.log(self.t("backup.error", error=e))
            InfoBar.error(self.t("infobar.error"), str(e), parent=self)
    
    # Открывает папку бэкапов в проводнике.
    def action_open_backup_dir(self) -> None:
        backup_path = self.service.resolve_path(BACKUP_DIR)
        if not os.path.exists(backup_path):
            os.makedirs(backup_path, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(backup_path))
    
    # Удаляет выбранный бэкап после подтверждения.
    def action_delete_backup_by_path(self, path: str) -> None:
        if not path or not os.path.exists(path):
            InfoBar.warning(
                self.t("infobar.warning"),
                self.t("backup.file_missing"),
                parent=self
            )
            return
        reply = QMessageBox.question(
            self,
            self.t("backup.delete_title"),
            self.t("backup.delete_text", name=os.path.basename(path)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            os.remove(path)
            InfoBar.success(
                self.t("backup.deleted_title"),
                self.t("backup.deleted_short"),
                parent=self
            )
            self.log(self.t("backup.deleted", path=path))
            self.refresh_backups()
        except Exception as e:
            self.log(self.t("log.error", detail=e))
            InfoBar.error(self.t("infobar.error"), str(e), parent=self)
    
    # Восстанавливает выбранный бэкап через SCEWIN.
    def action_restore_backup(self, path: str) -> None:
        if not path or not os.path.exists(path):
            InfoBar.warning(
                self.t("infobar.warning"),
                self.t("backup.file_missing"),
                parent=self
            )
            return
        self.run_worker(
            SCEWIN_EXE,
            ["/i", "/s", path],
            self.t("backup.restore_desc", name=os.path.basename(path))
        )
    
    # Запускает worker-поток и показывает инфобар прогресса.
    # Запускает worker-поток и показывает инфобар прогресса.
    def run_worker(self, cmd: str, args: List[str], desc: str) -> None:
        if self.worker is not None:
            if self.worker.isRunning():
                InfoBar.warning(
                    self.t("infobar.warning"),
                    self.t("infobar.loading_content", desc=self.worker.desc),
                    parent=self
                )
                return
            try:
                self.worker.finished.disconnect(self.on_worker_finished)
            except TypeError:
                pass
            self.worker.deleteLater()
        
        self.log(self.t("log.started", desc=desc))
        resolved_cmd = self.service.resolve_path(cmd)
        resolved_args = self.service.resolve_scewin_args(args)
        self.worker = BiosWorker(resolved_cmd, resolved_args, desc)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()
        InfoBar.info(
            self.t("infobar.loading_title"),
            self.t("infobar.loading_content", desc=desc),
            parent=self
        )
    
    # Обрабатывает завершение фоновой задачи.
    # Обрабатывает завершение фоновой задачи.
    def on_worker_finished(self, success, title, detail):
        if success:
            self.log(self.t("log.success", detail=detail.strip()))
            InfoBar.success(title, self.t("infobar.success_content"), parent=self)
        else:
            self.log(self.t("log.error", detail=detail))
            InfoBar.error(title, self.t("infobar.see_logs"), parent=self)
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None
    
class AboutInterface(QWidget):
    # UI for app metadata, links, and documentation dialog.
    
    # Инициализирует экран "О программе".
    def __init__(self, parent=None, lang_manager: Optional[LanguageManager] = None):
        super().__init__(parent=parent)
        self.setObjectName("AboutInterface")
        self.lang_manager = lang_manager or LanguageManager()
        self.init_ui()
        self.lang_manager.language_changed.connect(self.apply_language)
        self.apply_language()

    # Укороченный доступ к переводу строк.
    def t(self, key: str, **kwargs) -> str:
        return self.lang_manager.tr(key, **kwargs)
    
    # Собирает интерфейс карточек и кнопок.
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 50, 50, 50)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        
        title_layout = QHBoxLayout()
        title_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_layout.setSpacing(15)
        
        icon_path = os.path.join(APP_DIR, "icon.ico")
        if os.path.exists(icon_path):
            icon_label = QLabel(self)
            icon = QIcon(icon_path)
            pixmap = icon.pixmap(QSize(48, 48))
            icon_label.setPixmap(pixmap)
            icon_label.setFixedSize(48, 48)
            title_layout.addWidget(icon_label)
        
        title = TitleLabel(APP_NAME, self)
        title_layout.addWidget(title)
        
        layout.addLayout(title_layout)
        
        self.lbl_version = BodyLabel("", self)
        self.lbl_version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_version.setTextColor(QColor(150, 150, 150), QColor(200, 200, 200))
        layout.addWidget(self.lbl_version)
        
        layout.addSpacing(20)
        
        author_card = CardWidget(self)
        author_layout = QVBoxLayout(author_card)
        author_layout.setContentsMargins(20, 20, 20, 20)
        author_layout.setSpacing(15)
        
        self.lbl_author_title = SubtitleLabel("", self)
        author_layout.addWidget(self.lbl_author_title)
        
        author_name = BodyLabel("🔥 cat_fire", self)
        author_layout.addWidget(author_name)
        
        
        self.btn_coffee = PushButton("", self)
        self.btn_coffee.setStyleSheet("""
            PushButton {
                background-color: #FFDD00;
                color: #000000;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
            }
            PushButton:hover {
                background-color: #E5C700;
            }
            PushButton:pressed {
                background-color: #CCB100;
            }
        """)
        self.btn_coffee.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://buymeacoffee.com/cat_fire")))
        author_layout.addWidget(self.btn_coffee)
        
        layout.addWidget(author_card)
        
        self.btn_docs = PrimaryPushButton(FIF.DOCUMENT, "", self)
        self.btn_docs.clicked.connect(self.show_documentation)
        layout.addWidget(self.btn_docs)
        
        layout.addStretch(1)
        
        current_year = datetime.datetime.now().year
        self.lbl_footer = BodyLabel("", self)
        self.lbl_footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_footer.setTextColor(QColor(100, 100, 100), QColor(150, 150, 150))
        layout.addWidget(self.lbl_footer)

    # Обновляет локализованные строки экрана.
    def apply_language(self) -> None:
        self.lbl_version.setText(self.t("about.version", version=APP_VERSION))
        self.lbl_author_title.setText(self.t("about.developer"))
        self.btn_coffee.setText(self.t("about.coffee"))
        self.btn_docs.setText(self.t("about.docs"))
        current_year = datetime.datetime.now().year
        self.lbl_footer.setText(self.t("about.footer", year=current_year))
    
    # Открывает диалог с документацией.
    def show_documentation(self):
        from qfluentwidgets import SmoothScrollArea
        
        docs_text = self.t("docs.text")
        
        dialog = QDialog(self)
        dialog.setWindowTitle(self.t("about.docs_title"))
        dialog.setFixedSize(550, 500)
        dialog.setStyleSheet("background-color: #2d2d2d;")
        
        dialog_layout = QVBoxLayout(dialog)
        dialog_layout.setContentsMargins(20, 20, 20, 20)
        dialog_layout.setSpacing(15)
        
        title = SubtitleLabel(self.t("about.docs_header"), dialog)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dialog_layout.addWidget(title)
        
        scroll = SmoothScrollArea(dialog)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("SmoothScrollArea { border: none; background-color: transparent; }")
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(15, 15, 15, 15)
        
        docs_label = BodyLabel(docs_text.strip(), content_widget)
        docs_label.setWordWrap(True)
        docs_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        content_layout.addWidget(docs_label)
        
        scroll.setWidget(content_widget)
        dialog_layout.addWidget(scroll, 1)
        
        dialog.exec()

class MainWindow(FluentWindow):
    # Main application window with navigation and theme setup.
    
    # Подготавливает главное окно и страницы приложения.
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.lang_manager = LanguageManager(load_language_setting())
        self._setup_icon()
        setTheme(Theme.DARK)
        self._setup_interfaces()
        self._setup_language_selector()
        self.lang_manager.language_changed.connect(self.apply_language)
        self.lang_manager.language_changed.connect(save_language_setting)
        self.apply_language()
    
    # Устанавливает иконку приложения.
    def _setup_icon(self) -> None:
        icon_path = os.path.join(APP_DIR, "icon.ico")
        if os.path.exists(icon_path):
            icon = QIcon(icon_path)
            self.setWindowIcon(icon)
            QApplication.setWindowIcon(icon)
    
    # Создает основные вкладки и элементы навигации.
    def _setup_interfaces(self) -> None:
        self.interface = NVRAMInterface(self, self.lang_manager)
        self.nav_item_editor = self.addSubInterface(
            self.interface,
            FIF.EDIT,
            self.lang_manager.tr("nav.editor")
        )
        self.backup_interface = BackupInterface(self, self.lang_manager)
        self.nav_item_backup = self.addSubInterface(
            self.backup_interface,
            FIF.SAVE,
            self.lang_manager.tr("nav.backup")
        )
        self.about_interface = AboutInterface(self, self.lang_manager)
        self.nav_item_about = self.addSubInterface(
            self.about_interface,
            FIF.INFO,
            self.lang_manager.tr("nav.about")
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
            tooltip=self.lang_manager.tr("nav.language_tooltip")
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

if __name__ == '__main__':
    # Enforce single-instance behavior before creating the main UI.
    guard = SingleInstanceGuard(APP_NAME)
    
    if guard.is_already_running():
        temp_app = QApplication(sys.argv)
        
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle(tr_global("single.title"))
        msg.setText(tr_global("single.text"))
        msg.setInformativeText(tr_global("single.info"))
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()
        
        sys.exit(0)
    
    try:
        import ctypes
        myappid = 'ScewinGUI.BiosEditor.v1.0'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass

    # Create and run the Qt application.
    if hasattr(QApplication, "setHighDpiScaleFactorRoundingPolicy") and hasattr(Qt, "HighDpiScaleFactorRoundingPolicy"):
        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setStyleSheet(app.styleSheet() + """
        QToolTip {
            background-color: rgba(50, 50, 50, 240);
            color: white;
            border: 1px solid rgba(100, 100, 100, 180);
            border-radius: 6px;
            padding: 8px 12px;
            font-size: 13px;
        }
    """)
    
    window = MainWindow()
    window.show()
    
    exit_code = app.exec()
    guard.release()
    sys.exit(exit_code)
