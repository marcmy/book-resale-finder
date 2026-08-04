from __future__ import annotations

import csv
from pathlib import Path


class InputFileError(ValueError):
    pass


def _open_csv(path: Path):
    # utf-8-sig handles Keepa exports that include a BOM.
    return path.open("r", encoding="utf-8-sig", newline="")


def read_asins(path: Path) -> list[str]:
    if not path.exists():
        raise InputFileError(f"Input file not found: {path}")
    if path.suffix.lower() != ".csv":
        raise InputFileError("The input file must be a CSV file.")

    try:
        with _open_csv(path) as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise InputFileError("The CSV file has no header row.")

            normalized = {name.strip().casefold(): name for name in reader.fieldnames if name}
            source_header = normalized.get("asin")
            if source_header is None:
                raise InputFileError('The CSV file must contain a column named "ASIN".')

            values: list[str] = []
            for row in reader:
                value = str(row.get(source_header) or "").strip()
                if value:
                    values.append(value)
    except UnicodeDecodeError as exc:
        raise InputFileError("The CSV file is not valid UTF-8 text.") from exc
    except csv.Error as exc:
        raise InputFileError(f"The CSV file could not be parsed: {exc}") from exc

    if not values:
        raise InputFileError('The "ASIN" column contains no identifiers.')
    return values
