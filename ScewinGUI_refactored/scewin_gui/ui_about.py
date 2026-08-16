"""About page and documentation dialog."""

from __future__ import annotations

import datetime

from .config import APP_CONFIG
from .i18n import LanguageManager
from .qt_compat import (
    FIF,
    BodyLabel,
    CardWidget,
    PrimaryPushButton,
    PushButton,
    QColor,
    QDesktopServices,
    QDialog,
    QHBoxLayout,
    QIcon,
    QLabel,
    QSize,
    Qt,
    QUrl,
    QVBoxLayout,
    QWidget,
    SmoothScrollArea,
    SubtitleLabel,
    TitleLabel,
)
from .ui_common import LocalizedInterface

APP_NAME = APP_CONFIG.app_name
APP_VERSION = APP_CONFIG.app_version


class AboutInterface(LocalizedInterface):
    """Display application metadata, links, and documentation."""

    def __init__(
        self,
        parent: QWidget | None = None,
        lang_manager: LanguageManager | None = None,
    ) -> None:
        super().__init__(parent=parent, lang_manager=lang_manager)
        self.setObjectName("AboutInterface")
        self.init_ui()
        self.apply_language()

    # Собирает интерфейс карточек и кнопок.
    def init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 50, 50, 50)
        layout.setSpacing(20)
        layout.setAlignment(  # type: ignore[call-overload]
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter
        )

        title_layout = QHBoxLayout()
        title_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_layout.setSpacing(15)

        icon_path = APP_CONFIG.icon_path
        if icon_path.exists():
            icon_label = QLabel(self)
            icon = QIcon(str(icon_path))
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
        self.btn_coffee.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://buymeacoffee.com/cat_fire"))
        )
        author_layout.addWidget(self.btn_coffee)

        layout.addWidget(author_card)

        self.btn_docs = PrimaryPushButton(FIF.DOCUMENT, "", self)
        self.btn_docs.clicked.connect(self.show_documentation)
        layout.addWidget(self.btn_docs)

        layout.addStretch(1)

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
        current_year = datetime.date.today().year
        self.lbl_footer.setText(self.t("about.footer", year=current_year))

    # Открывает диалог с документацией.
    def show_documentation(self) -> None:
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
