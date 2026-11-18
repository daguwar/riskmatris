"""Server-side translations (issue #9, phase 3).

The API and WebSocket layer send *codes* instead of Swedish text; the client
maps them via its own dictionaries. This module holds the server-side texts
for the cases where the server itself must produce localized output (CSV
export) plus the canonical Swedish/English message table.
"""

from riskmatris.utils import LEVEL_THRESHOLDS

SUPPORTED_LANGS = ("sv", "en")

MESSAGES: dict[str, dict[str, str]] = {
    "session_not_found": {"sv": "Sessionen hittades inte.", "en": "Session not found."},
    "too_many_sessions": {
        "sv": "För många sessioner skapade. Försök igen om en stund.",
        "en": "Too many sessions created. Please try again later.",
    },
    "too_many_requests": {
        "sv": "För många förfrågningar. Försök igen om en stund.",
        "en": "Too many requests. Please try again later.",
    },
    "invalid_admin_token": {"sv": "Ogiltig administratörs-token.", "en": "Invalid admin token."},
    "invalid_handover": {
        "sv": "Ogiltig eller utgången överlämningskod.",
        "en": "Invalid or expired handover code.",
    },
    "url_too_long": {"sv": "URL:en är för lång.", "en": "The URL is too long."},
    "qr_generation_failed": {
        "sv": "Kunde inte generera QR-koden – kontrollera URL:en.",
        "en": "Could not generate the QR code – check the URL.",
    },
    "snapshot_too_large": {"sv": "Snapshot-filen är för stor.", "en": "The snapshot file is too large."},
    "invalid_snapshot_json": {"sv": "Ogiltig JSON i snapshot-filen.", "en": "Invalid JSON in the snapshot file."},
    "invalid_snapshot": {"sv": "Ogiltig snapshot-fil.", "en": "Invalid snapshot file."},
    "invalid_message": {"sv": "Ogiltigt meddelande.", "en": "Invalid message."},
    "invalid_json": {"sv": "Ogiltigt JSON-meddelande.", "en": "Invalid JSON message."},
    "message_too_large": {"sv": "Meddelandet är för stort.", "en": "The message is too large."},
    "not_json_object": {"sv": "Meddelandet måste vara ett JSON-objekt.", "en": "The message must be a JSON object."},
    "missing_action": {"sv": "Saknar giltig 'action'.", "en": "Missing valid 'action'."},
    "validation_error": {"sv": "Ogiltigt meddelande.", "en": "Invalid message."},
    "no_permission": {
        "sv": "Du saknar behörighet för denna åtgärd.",
        "en": "You do not have permission for this action.",
    },
    "unknown_admin_action": {"sv": "Okänd admin-action.", "en": "Unknown admin action."},
    "risk_locked": {
        "sv": "Denna risk är låst – röstning ej möjlig.",
        "en": "This risk is locked – voting is not possible.",
    },
    "invalid_values": {
        "sv": "Sannolikhet och Konsekvens måste vara heltal mellan 1 och matrisstorleken.",
        "en": "Probability and Consequence must be integers between 1 and the matrix size.",
    },
    "invalid_risk_number": {"sv": "Ogiltigt risknummer.", "en": "Invalid risk number."},
    "risk_not_found": {"sv": "Risken finns inte.", "en": "The risk does not exist."},
    "cannot_delete_only_risk": {
        "sv": "Kan inte ta bort den enda risken.",
        "en": "Cannot delete the only risk.",
    },
    "empty_title": {"sv": "Titel får inte vara tom.", "en": "The title must not be empty."},
    "invalid_threshold": {
        "sv": "Tröskelvärdet måste vara ett heltal 1–50.",
        "en": "The threshold must be an integer 1–50.",
    },
    "too_many_messages": {
        "sv": "För många meddelanden – sakta ner takten.",
        "en": "Too many messages – please slow down.",
    },
    "invalid_lang": {"sv": "Ogiltigt språk.", "en": "Invalid language."},
    "max_risks_reached": {
        "sv": "Max antal risker per session har nåtts.",
        "en": "The maximum number of risks per session has been reached.",
    },
    "max_votes_reached": {
        "sv": "Max antal röster för denna risk har nåtts.",
        "en": "The maximum number of votes for this risk has been reached.",
    },
}


def message(code: str, lang: str = "sv") -> str:
    """Returns the message for a code in the given language (Swedish fallback)."""
    entry = MESSAGES.get(code)
    if not entry:
        return code
    return entry.get(lang, entry["sv"])


CSV_TEXTS: dict[str, dict[str, object]] = {
    "sv": {
        "headers": [
            "Risk #",
            "Beskrivning / Etikett",
            "Status",
            "Antal röster",
            "Medel Sannolikhet",
            "Medel Konsekvens",
            "Sannolikhet (1-{n})",
            "Sannolikhet (Text)",
            "Konsekvens (1-{n})",
            "Konsekvens (Text)",
            "Riskvärde (1-{max})",
            "Risknivå",
            "Röstfördelning (Sannolikhet x Konsekvens: Antal)",
        ],
        "status_locked": "Låst i sammanställning",
        "status_open": "Öppen / Visad",
        "status_hidden": "Ej visad",
        "distribution": "S{p}xK{c}: {count} st",
        "levels": {"low": "Låg", "medium": "Medel", "high": "Hög", "very_high": "Mycket Hög"},
        "prob_labels_by_size": {
            "3": {1: "Låg", 2: "Medel", 3: "Hög"},
            "4": {1: "Osannolik", 2: "Möjlig", 3: "Sannolik", 4: "Mycket sannolik"},
            "5": {1: "Mycket osannolik", 2: "Osannolik", 3: "Möjlig", 4: "Trolig", 5: "Nästan säker"},
        },
        "cons_labels_by_size": {
            "3": {1: "Lindrig", 2: "Måttlig", 3: "Allvarlig"},
            "4": {1: "Försumbar", 2: "Måttlig", 3: "Allvarlig", 4: "Mycket allvarlig"},
            "5": {1: "Försumbar", 2: "Lindrig", 3: "Måttlig", 4: "Allvarlig", 5: "Katastrofal"},
        },
    },
    "en": {
        "headers": [
            "Risk #",
            "Label / Note",
            "Status",
            "Vote count",
            "Avg Probability",
            "Avg Consequence",
            "Probability (1-{n})",
            "Probability (Text)",
            "Consequence (1-{n})",
            "Consequence (Text)",
            "Risk score (1-{max})",
            "Risk level",
            "Vote distribution (Probability x Consequence: Count)",
        ],
        "status_locked": "Locked in summary",
        "status_open": "Open / Shown",
        "status_hidden": "Not shown",
        "distribution": "P{p}xC{c}: {count}",
        "levels": {"low": "Low", "medium": "Medium", "high": "High", "very_high": "Very high"},
        "prob_labels_by_size": {
            "3": {1: "Low", 2: "Medium", 3: "High"},
            "4": {1: "Unlikely", 2: "Possible", 3: "Likely", 4: "Very likely"},
            "5": {1: "Very rare", 2: "Rare", 3: "Possible", 4: "Likely", 5: "Almost certain"},
        },
        "cons_labels_by_size": {
            "3": {1: "Minor", 2: "Moderate", 3: "Severe"},
            "4": {1: "Negligible", 2: "Moderate", 3: "Serious", 4: "Very serious"},
            "5": {1: "Insignificant", 2: "Minor", 3: "Moderate", 4: "Major", 5: "Catastrophic"},
        },
    },
}


def csv_texts(lang: str) -> dict[str, object]:
    """CSV export strings for a language (Swedish fallback)."""
    return CSV_TEXTS.get(lang, CSV_TEXTS["sv"])


def level_key_for_score(score: int, matrix_size: int = 4) -> str:
    """Same thresholds as utils.get_risk_level, as a translation key."""
    green_max, yellow_max, orange_max = LEVEL_THRESHOLDS.get(matrix_size, LEVEL_THRESHOLDS[4])
    if score <= green_max:
        return "low"
    if score <= yellow_max:
        return "medium"
    if score <= orange_max:
        return "high"
    return "very_high"
