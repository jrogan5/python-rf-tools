"""Shared CLI utilities: interactive prompts and temperature validation."""

from pathlib import Path

TEMP_MIN: float = -100.0
TEMP_MAX: float = 100.0


def prompt_missing(prompt: str, cast_type):
    """Prompt the user for a value, retrying on invalid input."""
    while True:
        raw = input(f"{prompt}: ").strip()
        if len(raw) >= 2 and raw[0] in ('"', "'") and raw[-1] == raw[0]:
            raw = raw[1:-1].strip()
        if cast_type is float:
            try:
                return float(int(raw))
            except ValueError:
                try:
                    return float(raw)
                except ValueError as exc:
                    print(f"Invalid number – {exc}")
                    continue
        try:
            return cast_type(raw)
        except ValueError as exc:
            print(f"Invalid input – {exc}")


def validate_temperature(temp: float) -> None:
    if not (TEMP_MIN <= temp <= TEMP_MAX):
        raise ValueError(
            f"Temperature {temp} °C is outside the allowed range [{TEMP_MIN}, {TEMP_MAX}]"
        )


def prompt_validated(prompt: str, validate):
    """
    Prompt until validate(raw_input) returns (True, value).

    *validate* must be a callable that accepts a stripped string and returns
    ``(True, value)`` on success or ``(False, error_message)`` on failure.
    Surrounding quotes are stripped from the input before validation.

    Example::

        def must_be_dir(p):
            d = Path(p)
            return (True, d) if d.is_dir() else (False, f"Not a directory: {d}")

        path = prompt_validated("Input directory", must_be_dir)
    """
    while True:
        raw = input(f"{prompt}: ").strip()
        if len(raw) >= 2 and raw[0] in ('"', "'") and raw[-1] == raw[0]:
            raw = raw[1:-1].strip()
        ok, result = validate(raw)
        if ok:
            return result
        print(f"  Error: {result}")
