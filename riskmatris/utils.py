"""Pure utility functions with no internal dependencies (beyond config)."""

import math
import socket
import unicodedata
from functools import cache
from typing import Any

from riskmatris.config import logger


def sanitize_user_text(value: str, max_length: int) -> str:
    """Strips control/format characters (e.g. newlines, RTL overrides) from
    user-supplied text and clamps its length. Keeps titles and labels safe to
    store, render and log."""
    return "".join(ch for ch in value if unicodedata.category(ch) not in ("Cc", "Cf")).strip()[:max_length]


# Leading characters that make Excel/LibreOffice interpret a CSV cell as a
# formula (OWASP CSV-injection guidance also covers tab and CR).
CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_csv_cell(value: Any) -> str:
    """Escapes a CSV cell against formula injection.

    A cell starting with =, +, -, @ (or tab/CR) is evaluated as a formula by
    Excel/LibreOffice when the file is opened (classic ``=cmd|' /C ...'``).
    Prefixing with a single quote forces text interpretation; the quote itself
    is not displayed by the spreadsheet application.
    """
    text = "" if value is None else str(value)
    # Spreadsheet apps ignore leading whitespace before evaluating a formula
    # prefix, so inspect the first non-space character (audit 2026-11 SEC-05)
    if text.lstrip()[:1] in CSV_FORMULA_PREFIXES:
        return "'" + text
    return text


def round_half_up(value: float, max_val: int = 4) -> int:
    """Rounds half up (cautious rounding: .5 rounds up) to an integer in 1..max_val."""
    rounded = int(math.floor(value + 0.5))
    return max(1, min(max_val, rounded))


# Allowed matrix sizes and their risk-level thresholds:
# (green_max, yellow_max, orange_max) – everything above orange_max is red.
# Score = probability x consequence, so the score range is 1..size^2.
MATRIX_SIZES = (3, 4, 5)
LEVEL_THRESHOLDS: dict[int, tuple[int, int, int]] = {
    3: (2, 4, 6),  # score 1..9
    4: (2, 6, 9),  # score 1..16 (unchanged default)
    5: (4, 9, 15),  # score 1..25
}


def get_risk_level(score: int, matrix_size: int = 4) -> dict[str, str]:
    """
    Risk score = Probability (1..N) x Consequence (1..N) -> 1..N^2, where N is
    the session's matrix size (3, 4 or 5; default 4).
    N=3 (1-9):   Green 1-2 Low, Yellow 3-4 Medium, Orange 6 High, Red 9 Very High
    N=4 (1-16):  Green 1-2 Low, Yellow 3-6 Medium, Orange 8-9 High, Red 12-16 Very High
    N=5 (1-25):  Green 1-4 Low, Yellow 5-9 Medium, Orange 10-15 High, Red 16-25 Very High
    """
    green_max, yellow_max, orange_max = LEVEL_THRESHOLDS.get(matrix_size, LEVEL_THRESHOLDS[4])
    if score <= green_max:
        return {"level": "Low", "color": "green"}
    elif score <= yellow_max:
        return {"level": "Medium", "color": "yellow"}
    elif score <= orange_max:
        return {"level": "High", "color": "orange"}
    else:
        return {"level": "Very high", "color": "red"}


@cache
def get_local_lan_ip() -> str:
    """Returns the machine's local network IP (cached – computed only once per process)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                logger.info("Local LAN IP: %s", ip)
                return ip
    except Exception:
        pass
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        if ip and not ip.startswith("127."):
            logger.info("Local LAN IP (via hostname %s): %s", hostname, ip)
            return ip
    except Exception:
        pass
    logger.info("Could not determine LAN IP – falling back to 127.0.0.1")
    return "127.0.0.1"


def _safe_int(msg: dict[str, Any], key: str, default: int, min_val: int = 0, max_val: int = 999) -> int | None:
    """Fetches an integer from a WS message with error handling and bounds checking."""
    raw = msg.get(key, default)
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return None
    if val < min_val or val > max_val:
        return None
    return val
