from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Expected {label} was not found")
    return text.replace(old, new, 1)


gui_path = Path("book_resale_finder/gui.py")
gui = gui_path.read_text(encoding="utf-8")
gui = replace_once(
    gui,
    "import asyncio\nimport time\nfrom pathlib import Path",
    "import asyncio\nimport time\nfrom datetime import datetime, tzinfo\nfrom pathlib import Path",
    "GUI import block",
)
gui = replace_once(
    gui,
    '''        if summary.quota.reset_at:
            lines.append(f"Quota reset: {summary.quota.reset_at}")
''',
    '''        if summary.quota.reset_at:
            lines.append(f"Quota reset: {self._format_quota_reset(summary.quota.reset_at)}")
''',
    "quota reset output block",
)
gui = replace_once(
    gui,
    '''    @staticmethod
    def _format_elapsed(seconds: float) -> str:
''',
    '''    @staticmethod
    def _format_quota_reset(value: str, local_timezone: tzinfo | None = None) -> str:
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.astimezone()
            else:
                parsed = parsed.astimezone(local_timezone)
            formatted = parsed.strftime("%m-%d-%Y %I:%M %p")
            date_part, time_part, meridiem = formatted.split()
            return f"{date_part} {time_part.lstrip('0')} {meridiem}"
        except (AttributeError, TypeError, ValueError):
            return value

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
''',
    "elapsed formatter marker",
)
gui_path.write_text(gui, encoding="utf-8")

replacements = {
    Path("book_resale_finder/constants.py"): ('VERSION = "1.1.2"', 'VERSION = "1.1.3"'),
    Path("book_resale_finder/__init__.py"): ('__version__ = "1.1.2"', '__version__ = "1.1.3"'),
    Path("pyproject.toml"): ('version = "1.1.2"', 'version = "1.1.3"'),
}
for path, (old_version, new_version) in replacements.items():
    text = path.read_text(encoding="utf-8")
    path.write_text(replace_once(text, old_version, new_version, str(path)), encoding="utf-8")

changelog = Path("CHANGELOG.md")
text = changelog.read_text(encoding="utf-8")
entry = '''# Changelog

## 1.1.3

- Convert eBay's UTC quota-reset timestamp to the user's local system time.
- Display the reset as `MM-DD-YYYY h:mm AM/PM` instead of raw ISO 8601.

'''
if not text.startswith("# Changelog\n"):
    raise RuntimeError("Unexpected changelog format")
changelog.write_text(entry + text[len("# Changelog\n\n"):], encoding="utf-8")

test_path = Path("tests/test_gui_presentation.py")
tests = test_path.read_text(encoding="utf-8")
tests = replace_once(
    tests,
    "import inspect\n",
    "import inspect\nfrom datetime import timedelta, timezone\n",
    "test import block",
)
tests += '''


def test_quota_reset_is_converted_to_local_12_hour_time():
    eastern_daylight = timezone(timedelta(hours=-4))
    assert MainWindow._format_quota_reset(
        "2026-08-05T07:00:00.000Z", eastern_daylight
    ) == "08-05-2026 3:00 AM"


def test_invalid_quota_reset_is_left_readable():
    assert MainWindow._format_quota_reset("unknown") == "unknown"
'''
test_path.write_text(tests, encoding="utf-8")
