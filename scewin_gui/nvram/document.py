"""NVRAM document and setting data models."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


class NvramValidationError(ValueError):
    """Raised when a selected file is not a valid SCEWIN NVRAM document."""


@dataclass(slots=True)
class BiosSetting:
    """One editable BIOS setup entry and its original file block."""

    name: str = ""
    help_string: str = ""
    token: str = ""
    offset: str = ""
    width: str = ""
    bios_default: str = ""
    default_option_id: str = ""
    current_value: str = ""
    current_option_id: str = ""
    options: list[tuple[str, str]] = field(default_factory=list)
    option_labels: dict[str, str] = field(default_factory=dict)
    raw_value: str = ""
    is_numeric: bool = False
    line_start: int = 0
    line_end: int = 0
    initial_value: str = ""
    initial_option_id: str = ""
    is_modified: bool = False
    is_system_register: bool = False
    is_active_profile: bool = False
    surrounding_context: list[str] = field(default_factory=list)

    def __repr__(self) -> str:
        return f"<BiosSetting {self.name}: {self.current_value}>"

    def set_value(self, new_value: str) -> None:
        """Update a numeric or raw value, checking for line injection."""
        if "\n" in new_value or "\r" in new_value:
            raise ValueError("Значение NVRAM не должно содержать символов перевода строки")
        clean_new = new_value.strip()
        if self.is_numeric:
            raw_stripped = clean_new.strip("<>")
            if not re.fullmatch(r"(?:0[xX])?[0-9A-Fa-f]+", raw_stripped):
                raise ValueError(f"Недопустимое числовое значение NVRAM: {new_value!r}")
        clean_current = self.current_value.strip()

        if clean_current != clean_new:
            self.current_value = clean_new
            self.is_modified = clean_new != self.initial_value

    def set_option(self, option_id: str) -> None:
        """Select an enumerated value by its stable SCEWIN identifier."""
        if "\n" in option_id or "\r" in option_id:
            raise ValueError("Option ID не должен содержать символов перевода строки")
        if option_id not in self.option_labels:
            raise ValueError(f"Unknown option ID {option_id!r} for {self.name}")
        self.current_option_id = option_id
        self.current_value = self.option_labels[option_id]
        self.is_modified = option_id != self.initial_option_id

    @property
    def differs_from_default(self) -> bool:
        if self.default_option_id:
            return self.current_option_id != self.default_option_id
        if self.options:
            return False
        return bool(
            self.bios_default
            and self.bios_default != "-"
            and self.current_value.strip() != self.bios_default.strip()
        )

    def reset_to_default(self) -> None:
        if self.default_option_id:
            self.set_option(self.default_option_id)
        elif not self.options and self.bios_default and self.bios_default != "-":
            self.set_value(self.bios_default)

    def reset_to_initial(self) -> None:
        self.current_option_id = self.initial_option_id
        self.current_value = self.initial_value
        self.is_modified = False


@dataclass(slots=True)
class NvramDocument:
    """A parsed NVRAM document with its exact original source text."""

    source: str
    settings: list[BiosSetting]
