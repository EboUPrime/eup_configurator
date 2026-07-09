"""Kernlogik der ``configurator``-Bibliothek.

Enthält die Klassen :class:`ConfigElement` und :class:`Configurator`,
die eine YAML-Konfigurationsdatei laden und einen verschachtelten
Attributzugriff (dot-notation) darauf ermöglichen.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml

__all__ = ["ConfigElement", "Configurator"]


class ConfigElement:
    """Repräsentiert einen einzelnen Konfigurationswert oder -abschnitt.

    Bei verschachtelten Dictionaries werden rekursiv weitere
    ``ConfigElement``-Instanzen als Attribute angelegt, sodass z. B.
    ``config.mailer.host.value`` funktioniert.
    """

    def __init__(self, name: str, value: Any, parent_path: str = "") -> None:
        self.name = name
        self.value = value
        self.full_path = f"{parent_path}.{name}" if parent_path else name

        if isinstance(value, dict):
            for key, val in value.items():
                setattr(self, key, ConfigElement(key, val, self.full_path))

    def __repr__(self) -> str:
        shown = self.value if not isinstance(self.value, dict) else "{...}"
        return f"ConfigElement(path='{self.full_path}', value={shown})"

    def __str__(self) -> str:
        return str(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ConfigElement):
            return self.value == other.value
        return self.value == other

    def get(self, key: str, default: Any = None) -> "ConfigElement":
        """Liefert ein verschachteltes Element mit Fallback-Wert."""
        return getattr(self, key, ConfigElement(key, default, self.full_path))


class Configurator:
    """Lädt und verwaltet eine YAML-Konfigurationsdatei.

    Bietet verschachtelten Attributzugriff über :class:`ConfigElement`
    sowie Hilfsmethoden zum Lesen, Schreiben und Neuladen der Werte.
    """

    def __init__(self, config_file: str = "application.yaml", base_dir: Optional[str] = None) -> None:
        """
        :param config_file: Name bzw. Pfad der YAML-Datei.
        :param base_dir: Verzeichnis, in dem ``config_file`` liegt.
            Standardmäßig das Verzeichnis dieses Moduls.
        """
        self.config_file = config_file
        self.dir = Path(base_dir).resolve() if base_dir else Path(__file__).parent.resolve()
        self.config: dict = {}
        self.proj_dir = os.getenv("PROJECT_DIRECTORY", os.getcwd())
        self.config_path = self.dir / self.config_file
        self.load_config()
        self._set_attributes_from_config()

    def get_database_path(self, path: str) -> str:
        """Gibt den vollständigen Pfad zur Datenbankdatei zurück.

        :param path: Schlüssel unterhalb von ``database`` in der Konfiguration.
        :return: Vollständiger Pfad zur Datenbankdatei.
        """
        db_config = self.config.get("database", {})
        db_filename = db_config.get(path, "database.db")
        return os.path.join(self.proj_dir, db_filename)

    def load_config(self) -> None:
        """Lädt die Konfiguration aus der YAML-Datei."""

        try:
            with open(self.config_path, "r", encoding="utf-8") as stream:
                self.config = yaml.safe_load(stream) or {}
        except FileNotFoundError:
            print(f"Config file not found: {self.config_path}. Creating default config.")
            self.config = {}
            self.save_config()
        except yaml.YAMLError as exc:
            print(f"Error parsing YAML file: {exc}")
            self.config = {}

    def _set_attributes_from_config(self) -> None:
        """Setzt Attribute aus dem Konfigurations-Dict als ``ConfigElement``.

        Beispiel::

            {'mailer': {'password': 'secret', 'host': 'smtp.gmail.com'}}

            config.mailer.password.value  # 'secret'
            config.mailer.host.value      # 'smtp.gmail.com'
        """
        for key, value in self.config.items():
            setattr(self, key, ConfigElement(key, value))

    def get(self, key: str, default: Any = None) -> Any:
        """Liefert einen Wert direkt aus dem Root-Konfigurationsdict.

        :param key: Konfigurationsschlüssel.
        :param default: Rückgabewert, falls Schlüssel nicht existiert.
        """
        return self.config.get(key, default)

    def get_element(self, path: str) -> Optional[ConfigElement]:
        """Liefert ein ``ConfigElement`` per Dot-Notation-Pfad.

        :param path: Pfad wie ``'mailer.password'``.
        """
        parts = path.split(".")
        current: Any = self

        for part in parts:
            current = getattr(current, part, None)
            if current is None or not isinstance(current, ConfigElement):
                return None

        return current

    def get_value(self, path: str, default: Any = None) -> Any:
        """Liefert den Wert eines Elements per Dot-Notation-Pfad.

        :param path: Pfad wie ``'mailer.password'``.
        :param default: Rückgabewert, falls Pfad nicht existiert.
        """
        element = self.get_element(path)
        if element is not None:
            return element.value
        return default

    def set(self, key: str, value: Any) -> None:
        """Setzt einen Wert auf Root-Ebene und speichert die Datei.

        :param key: Konfigurationsschlüssel.
        :param value: Neuer Wert.
        """
        self.config[key] = value
        setattr(self, key, ConfigElement(key, value))
        self.save_config()

    def set_nested(self, path: str, value: Any) -> None:
        """Setzt einen verschachtelten Wert per Dot-Notation und speichert.

        :param path: Pfad wie ``'mailer.password'``.
        :param value: Neuer Wert.
        """
        parts = path.split(".")
        current = self.config

        for part in parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]

        current[parts[-1]] = value

        self._set_attributes_from_config()
        self.save_config()

    def save_config(self) -> None:
        """Speichert die aktuelle Konfiguration in die YAML-Datei."""
        config_path = self.dir / self.config_file

        try:
            with open(config_path, "w", encoding="utf-8") as file:
                yaml.safe_dump(self.config, file, default_flow_style=False, allow_unicode=True)
        except IOError as exc:
            print(f"Error saving config file: {exc}")

    def get_map(self, entity: Optional[str] = None) -> dict:
        """Liefert Einträge unterhalb von ``map`` in der Konfiguration.

        :param entity: Optionaler Schlüssel, um nur einen Teilbereich zu holen.
        """
        maps = self.config.get("map", {})

        if entity is None:
            return maps
        return maps.get(entity, {})

    def reload(self) -> None:
        """Lädt die Konfiguration neu von der Datei."""
        self.load_config()
        self._set_attributes_from_config()

    def list_elements(self, prefix: str = "") -> list[str]:
        """Listet alle ``ConfigElement``-Pfade auf.

        :param prefix: Optionaler Präfix zum Filtern der Ergebnisse.
        """
        elements: list[str] = []
        for attr_name in dir(self):
            attr = getattr(self, attr_name)
            if isinstance(attr, ConfigElement):
                elements.append(attr.full_path)
                elements.extend(self._get_nested_paths(attr))

        if prefix:
            return [e for e in elements if e.startswith(prefix)]
        return elements

    def _get_nested_paths(self, element: ConfigElement) -> list[str]:
        """Ermittelt rekursiv alle verschachtelten Pfade eines Elements."""
        paths: list[str] = []
        for attr_name in dir(element):
            if not attr_name.startswith("_"):
                attr = getattr(element, attr_name, None)
                if isinstance(attr, ConfigElement):
                    paths.append(attr.full_path)
                    paths.extend(self._get_nested_paths(attr))
        return paths

    def __repr__(self) -> str:
        return f"Configurator(config_file='{self.config_file}', keys={list(self.config.keys())})"
