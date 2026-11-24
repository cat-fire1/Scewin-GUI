"""SCEWIN NVRAM text parser, classification heuristics, and diff generator."""

from __future__ import annotations

import re
from re import Pattern

from .document import BiosSetting, NvramDocument, NvramValidationError


def validate_settings(settings: list[BiosSetting]) -> None:
    """Reject parsed results that cannot represent a safe import."""
    if not settings:
        raise NvramValidationError("В файле не найдено ни одного параметра Setup Question")
    invalid = [setting for setting in settings if not setting.name.strip()]
    if invalid:
        raise NvramValidationError("Обнаружен параметр без имени")


def validate_nvram_content(content: str) -> NvramDocument:
    """Parse content and reject empty or structurally invalid documents."""
    if not content.strip():
        raise NvramValidationError("NVRAM-файл пуст")
    document = BiosParser().parse_file(content)
    validate_settings(document.settings)
    return document


class BiosParser:
    """Parse SCEWIN NVRAM text and rebuild changed setting blocks."""

    RE_QUESTION = re.compile(r"^\s*Setup Question\s*=\s*(.*)")
    RE_HELP = re.compile(r"^\s*Help String\s*=\s*(.*)")
    RE_TOKEN = re.compile(r"^\s*Token\s*=\s*(.*)")
    RE_OFFSET = re.compile(r"^\s*Offset\s*=\s*(.*)")
    RE_DEFAULT = re.compile(r"^\s*BIOS Default\s*=\s*(.*)")
    RE_VALUE = re.compile(r"^\s*Value\s*=\s*(.*)")
    RE_OPTION = re.compile(r"(\*?)\[([0-9A-Fa-f]+)\]\s*(.*)")
    RE_OPTION_LINE = re.compile(r"^(.*?)(\*?)(\[[0-9A-Fa-f]+\]\s*)(.*)$")
    RE_VALUE_LINE = re.compile(r"^(\s*Value\s*=\s*)(.*)")
    META_FIELDS: tuple[tuple[Pattern[str], str], ...] = (
        (RE_HELP, "help_string"),
        (RE_TOKEN, "token"),
        (RE_OFFSET, "offset"),
        (RE_DEFAULT, "bios_default"),
    )
    REG_PATTERNS = re.compile(
        r"(\bPMU\b|\bPHY\b|\bARdPtr|\bAWrPtr|\bRX2D|\bTX2D|\bDFE\b|\bVrefDAC|\bDQ Vref|\bSwing\b|\bEmphasis\b|\bPreshoot\b|\b(?:P[0-3]|R[0-1])\b|drive strengths|impedance)",
        re.IGNORECASE,
    )

    def parse_file(self, content: str) -> NvramDocument:
        """Parse raw NVRAM text into an explicit document object."""
        settings: list[BiosSetting] = []
        lines = content.splitlines()
        current_setting: BiosSetting | None = None

        for i, line in enumerate(lines):
            if "=" not in line and "[" not in line:
                continue
            match_question = self.RE_QUESTION.match(line)
            if match_question:
                if current_setting:
                    self._finalize_setting_block(current_setting, i)
                    settings.append(current_setting)
                current_setting = BiosSetting()
                current_setting.line_start = i
                current_setting.name = match_question.group(1).strip()
                continue

            if current_setting:
                for regex, attribute in self.META_FIELDS:
                    self._parse_line_for_setting(
                        current_setting,
                        line,
                        regex,
                        attribute,
                    )

                match_value = self.RE_VALUE.match(line)
                if match_value:
                    val = match_value.group(1).split("//")[0].strip()
                    current_setting.raw_value = val
                    if not current_setting.current_value:
                        current_setting.current_value = val
                    current_setting.is_numeric = True
                    continue

                if "BIOS Default" not in line and "Setup Question" not in line and "[" in line and "]" in line:
                    match_opt = self.RE_OPTION.search(line)
                    if match_opt:
                        is_active = match_opt.group(1) == "*"
                        opt_id = match_opt.group(2)
                        remainder = match_opt.group(3)
                        opt_text = remainder.split("//")[0].strip()

                        current_setting.options.append((opt_id, opt_text))
                        current_setting.option_labels[opt_id] = opt_text

                        if is_active:
                            current_setting.current_option_id = opt_id
                            current_setting.current_value = opt_text

        if current_setting:
            self._finalize_setting_block(current_setting, len(lines))
            settings.append(current_setting)

        self._classify_settings(settings)
        return NvramDocument(content, settings)

    def _classify_settings(self, settings: list[BiosSetting]) -> None:
        """Classify system/PHY registers and detect active user profile settings."""
        count = len(settings)
        for s in settings:
            s.is_system_register = (
                bool(self.REG_PATTERNS.search(s.name))
                or not s.bios_default
                or s.bios_default == "-"
            )

        active_keywords = (
            "frequency", "speed", "uclk", "fclk", "tcl", "trcd", "trp", "tras",
            "voltage", "power down", "gear down", "command rate",
        )
        active_values = [
            bool(
                s.current_value
                and s.current_value not in ("Auto", "<0>", "0", "-", "[FF]Auto")
            )
            for s in settings
        ]
        active_prefix = [0]
        for s, has_active_value in zip(settings, active_values):
            name = s.name.lower()
            contributes = has_active_value and any(kw in name for kw in active_keywords)
            active_prefix.append(active_prefix[-1] + contributes)

        for i, s in enumerate(settings):
            ctx_start = max(0, i - 2)
            ctx_end = min(count, i + 3)
            s.surrounding_context = [
                settings[j].name
                for j in range(ctx_start, ctx_end)
                if j != i
            ]

            if s.is_system_register:
                continue

            active_neighbors = (
                active_prefix[min(count, i + 9)] - active_prefix[max(0, i - 8)]
            )
            s.is_active_profile = active_values[i] or active_neighbors >= 2

    def _parse_line_for_setting(
        self,
        setting: BiosSetting,
        line: str,
        regex: Pattern[str],
        attribute: str,
    ) -> None:
        match = regex.match(line)
        if match:
            val = match.group(1).split("//")[0].strip()
            setattr(setting, attribute, val)

    def _finalize_setting_block(
        self,
        setting: BiosSetting,
        current_line_idx: int,
    ) -> None:
        setting.line_end = current_line_idx - 1
        if setting.bios_default:
            match = re.match(r"(?:\[([0-9A-Fa-f]+)\])?(.*)", setting.bios_default)
            if match:
                setting.default_option_id = match.group(1) or ""
                setting.bios_default = match.group(2).strip()
                if not setting.default_option_id and setting.options:
                    exact_ids = [
                        option_id
                        for option_id, label in setting.options
                        if label == setting.bios_default
                    ]
                    if len(exact_ids) == 1:
                        setting.default_option_id = exact_ids[0]
        setting.initial_value = setting.current_value
        setting.initial_option_id = setting.current_option_id

    def generate_content(self, document: NvramDocument) -> str:
        """Patch only modified value lines and preserve all other source bytes."""
        lines = document.source.splitlines(keepends=True)
        for setting in document.settings:
            if not setting.is_modified:
                continue
            for index in range(setting.line_start, setting.line_end + 1):
                line = lines[index]
                ending = line[len(line.rstrip("\r\n")) :]
                body = line[: len(line) - len(ending)] if ending else line
                if setting.is_numeric and self.RE_VALUE_LINE.match(body):
                    value = setting.current_value
                    if "\r" in value or "\n" in value:
                        raise ValueError(f"Обнаружена инъекция перевода строки в параметре {setting.name}")
                    if setting.raw_value.startswith("<") and not value.startswith("<"):
                        value = f"<{value}>"
                    lines[index] = body.replace(setting.raw_value, value, 1) + ending
                    continue
                match = self.RE_OPTION_LINE.match(body)
                if not match or "Setup Question" in body or "BIOS Default" in body:
                    continue
                prefix, _, bracket_part, remainder = match.groups()
                option_id = bracket_part.lstrip("[").split("]", 1)[0]
                marker = "*" if option_id == setting.current_option_id else ""
                lines[index] = f"{prefix}{marker}{bracket_part}{remainder}{ending}"
        return "".join(lines)

    def generate_changes(self, document: NvramDocument) -> str:
        """Render the exact source prefix followed by modified setting blocks."""
        rendered_lines = self.generate_content(document).splitlines(keepends=True)
        newline = "\r\n" if "\r\n" in document.source else "\n"
        first_setting_line = min(
            (setting.line_start for setting in document.settings),
            default=len(rendered_lines),
        )
        prefix = "".join(rendered_lines[:first_setting_line])
        blocks = [
            "".join(rendered_lines[setting.line_start : setting.line_end + 1]).rstrip(
                "\r\n"
            )
            for setting in document.settings
            if setting.is_modified
        ]
        return prefix + (newline * 2).join(blocks) + (newline if blocks else "")
