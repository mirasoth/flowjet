#!/usr/bin/env python3
"""Prefer report language (BCP-47 tag) from timezone / locale signals.

Mechanical helper for agents and export defaults. Judgment still follows
references/LANGUAGE.md priority (explicit user request wins).

Supported tags include en, zh-CN, zh-TW, zh-HK, ja, ko, de, fr, es, pt-BR,
pt-PT, ru, ar, hi, it, nl, pl, tr, vi, th, id, ms, sv, da, fi, nb, uk, and
any other tag inferred from OS locale when timezone is ambiguous.

Usage:
  python prefer_language.py                 # print language tag
  python prefer_language.py --json          # full detection record
  python prefer_language.py --timezone Asia/Tokyo
  python prefer_language.py --list          # known timezone mappings
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

# Exact IANA / legacy zone → BCP-47 language tag (timezone wins over locale).
TIMEZONE_LANGUAGE: dict[str, str] = {
    # Chinese family
    "Asia/Shanghai": "zh-CN",
    "Asia/Chongqing": "zh-CN",
    "Asia/Harbin": "zh-CN",
    "Asia/Kashgar": "zh-CN",
    "Asia/Urumqi": "zh-CN",
    "PRC": "zh-CN",
    "Asia/Taipei": "zh-TW",
    "ROC": "zh-TW",
    "Asia/Hong_Kong": "zh-HK",
    "Hongkong": "zh-HK",
    "Asia/Macau": "zh-HK",
    "Asia/Macao": "zh-HK",
    # East / Southeast Asia
    "Asia/Tokyo": "ja",
    "Japan": "ja",
    "Asia/Seoul": "ko",
    "ROK": "ko",
    "Asia/Pyongyang": "ko",
    "Asia/Bangkok": "th",
    "Asia/Ho_Chi_Minh": "vi",
    "Asia/Saigon": "vi",
    "Asia/Jakarta": "id",
    "Asia/Pontianak": "id",
    "Asia/Makassar": "id",
    "Asia/Jayapura": "id",
    "Asia/Kuala_Lumpur": "ms",
    "Asia/Kuching": "ms",
    "Asia/Singapore": "en",  # English-primary business/research default
    "Asia/Manila": "en",
    "Asia/Kolkata": "hi",
    "Asia/Calcutta": "hi",
    "Asia/Dhaka": "bn",
    "Asia/Karachi": "ur",
    "Asia/Tehran": "fa",
    "Asia/Dubai": "ar",
    "Asia/Riyadh": "ar",
    "Asia/Qatar": "ar",
    "Asia/Kuwait": "ar",
    "Asia/Bahrain": "ar",
    "Asia/Muscat": "ar",
    "Asia/Baghdad": "ar",
    "Asia/Damascus": "ar",
    "Asia/Beirut": "ar",
    "Asia/Amman": "ar",
    "Africa/Cairo": "ar",
    "Africa/Casablanca": "ar",
    "Africa/Algiers": "ar",
    "Africa/Tunis": "ar",
    # Europe
    "Europe/Berlin": "de",
    "Europe/Vienna": "de",
    "Europe/Zurich": "de",
    "Europe/Paris": "fr",
    "Europe/Brussels": "fr",
    "Europe/Luxembourg": "fr",
    "Europe/Monaco": "fr",
    "Europe/Madrid": "es",
    "Atlantic/Canary": "es",
    "Europe/Lisbon": "pt-PT",
    "Atlantic/Azores": "pt-PT",
    "Atlantic/Madeira": "pt-PT",
    "Europe/Rome": "it",
    "Europe/Amsterdam": "nl",
    "Europe/Warsaw": "pl",
    "Europe/Moscow": "ru",
    "Europe/Kaliningrad": "ru",
    "Europe/Samara": "ru",
    "Europe/Kyiv": "uk",
    "Europe/Kiev": "uk",
    "Europe/Istanbul": "tr",
    "Europe/Stockholm": "sv",
    "Europe/Oslo": "nb",
    "Europe/Copenhagen": "da",
    "Europe/Helsinki": "fi",
    "Europe/Athens": "el",
    "Europe/Bucharest": "ro",
    "Europe/Budapest": "hu",
    "Europe/Prague": "cs",
    "Europe/Bratislava": "sk",
    "Europe/Sofia": "bg",
    "Europe/Belgrade": "sr",
    "Europe/Zagreb": "hr",
    "Europe/Ljubljana": "sl",
    "Europe/Dublin": "en",
    "Europe/London": "en",
    "Europe/Guernsey": "en",
    "Europe/Jersey": "en",
    "Europe/Isle_of_Man": "en",
    # Americas
    "America/Sao_Paulo": "pt-BR",
    "America/Fortaleza": "pt-BR",
    "America/Recife": "pt-BR",
    "America/Bahia": "pt-BR",
    "America/Manaus": "pt-BR",
    "America/Belem": "pt-BR",
    "America/Cuiaba": "pt-BR",
    "America/Porto_Velho": "pt-BR",
    "America/Boa_Vista": "pt-BR",
    "America/Rio_Branco": "pt-BR",
    "America/Argentina/Buenos_Aires": "es",
    "America/Argentina/Cordoba": "es",
    "America/Santiago": "es",
    "America/Lima": "es",
    "America/Bogota": "es",
    "America/Mexico_City": "es",
    "America/Monterrey": "es",
    "America/Caracas": "es",
    "America/Havana": "es",
    "America/New_York": "en",
    "America/Chicago": "en",
    "America/Denver": "en",
    "America/Los_Angeles": "en",
    "America/Phoenix": "en",
    "America/Toronto": "en",
    "America/Vancouver": "en",
    "America/Montreal": "fr",  # Quebec-leaning default; user can override
    "Pacific/Auckland": "en",
    "Australia/Sydney": "en",
    "Australia/Melbourne": "en",
    "Australia/Brisbane": "en",
    "Australia/Perth": "en",
    "Africa/Johannesburg": "en",
    "Africa/Lagos": "en",
    "Africa/Nairobi": "en",
}

# City / country name hints inside a tz string (order matters: first match wins).
TZ_NAME_HINTS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"(Shanghai|Chongqing|Harbin|Urumqi|Beijing|China)", re.IGNORECASE),
        "zh-CN",
    ),
    (re.compile(r"Taipei", re.IGNORECASE), "zh-TW"),
    (re.compile(r"(Hong.?Kong|Macau|Macao)", re.IGNORECASE), "zh-HK"),
    (re.compile(r"(Tokyo|Japan)", re.IGNORECASE), "ja"),
    (re.compile(r"(Seoul|Pyongyang)", re.IGNORECASE), "ko"),
    (re.compile(r"(Bangkok)", re.IGNORECASE), "th"),
    (re.compile(r"(Ho_Chi_Minh|Saigon|Hanoi)", re.IGNORECASE), "vi"),
    (re.compile(r"(Jakarta|Makassar|Jayapura)", re.IGNORECASE), "id"),
    (re.compile(r"(Kuala_Lumpur|Kuching)", re.IGNORECASE), "ms"),
    (re.compile(r"(Kolkata|Calcutta|Mumbai|Delhi)", re.IGNORECASE), "hi"),
    (
        re.compile(
            r"(Dubai|Riyadh|Qatar|Kuwait|Cairo|Casablanca|Baghdad)", re.IGNORECASE
        ),
        "ar",
    ),
    (re.compile(r"(Berlin|Vienna|Zurich)", re.IGNORECASE), "de"),
    (re.compile(r"(Paris|Brussels|Monaco)", re.IGNORECASE), "fr"),
    (
        re.compile(
            r"(Madrid|Canary|Buenos_Aires|Santiago|Lima|Bogota|Mexico_City)",
            re.IGNORECASE,
        ),
        "es",
    ),
    (re.compile(r"(Sao_Paulo|Fortaleza|Recife|Bahia|Manaus)", re.IGNORECASE), "pt-BR"),
    (re.compile(r"(Lisbon|Azores|Madeira)", re.IGNORECASE), "pt-PT"),
    (re.compile(r"(Rome)", re.IGNORECASE), "it"),
    (re.compile(r"(Amsterdam)", re.IGNORECASE), "nl"),
    (re.compile(r"(Warsaw)", re.IGNORECASE), "pl"),
    (re.compile(r"(Moscow|Kaliningrad|Samara)", re.IGNORECASE), "ru"),
    (re.compile(r"(Kyiv|Kiev)", re.IGNORECASE), "uk"),
    (re.compile(r"(Istanbul)", re.IGNORECASE), "tr"),
    (re.compile(r"(Stockholm)", re.IGNORECASE), "sv"),
    (re.compile(r"(Oslo)", re.IGNORECASE), "nb"),
    (re.compile(r"(Copenhagen)", re.IGNORECASE), "da"),
    (re.compile(r"(Helsinki)", re.IGNORECASE), "fi"),
    (re.compile(r"(Athens)", re.IGNORECASE), "el"),
    (
        re.compile(
            r"(London|Dublin|New_York|Chicago|Los_Angeles|Toronto|Sydney|Singapore|Manila)",
            re.IGNORECASE,
        ),
        "en",
    ),
]

# POSIX / BCP-47 locale language → OMR language tag.
LOCALE_LANGUAGE: dict[str, str] = {
    "zh": "zh-CN",
    "zh_cn": "zh-CN",
    "zh-cn": "zh-CN",
    "zh_sg": "zh-CN",
    "zh-sg": "zh-CN",
    "zh_tw": "zh-TW",
    "zh-tw": "zh-TW",
    "zh_hk": "zh-HK",
    "zh-hk": "zh-HK",
    "zh_mo": "zh-HK",
    "zh-mo": "zh-HK",
    "ja": "ja",
    "ko": "ko",
    "de": "de",
    "fr": "fr",
    "es": "es",
    "pt": "pt-BR",
    "pt_br": "pt-BR",
    "pt-br": "pt-BR",
    "pt_pt": "pt-PT",
    "pt-pt": "pt-PT",
    "ru": "ru",
    "ar": "ar",
    "hi": "hi",
    "bn": "bn",
    "ur": "ur",
    "fa": "fa",
    "th": "th",
    "vi": "vi",
    "id": "id",
    "ms": "ms",
    "it": "it",
    "nl": "nl",
    "pl": "pl",
    "tr": "tr",
    "sv": "sv",
    "da": "da",
    "fi": "fi",
    "nb": "nb",
    "nn": "nb",
    "no": "nb",
    "uk": "uk",
    "el": "el",
    "ro": "ro",
    "hu": "hu",
    "cs": "cs",
    "sk": "sk",
    "bg": "bg",
    "sr": "sr",
    "hr": "hr",
    "sl": "sl",
    "en": "en",
}

LANGUAGE_RE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")


def normalize_language(tag: str | None) -> str | None:
    if not tag:
        return None
    value = tag.strip().replace("_", "-")
    if not value or value in ("C", "POSIX"):
        return None
    # Drop encoding / modifier: zh_CN.UTF-8@euro → zh-CN
    value = value.split(".")[0].split("@")[0]
    parts = [p for p in value.split("-") if p]
    if not parts:
        return None
    lang = parts[0].lower()
    rest_parts: list[str] = []
    for p in parts[1:]:
        if len(p) == 2 and p.isalpha():
            rest_parts.append(p.upper())
        else:
            rest_parts.append(p)
    candidate = "-".join([lang, *rest_parts]) if rest_parts else lang
    # Prefer mapped canonical form when we know it
    key = value.lower().replace("-", "_")
    if key in LOCALE_LANGUAGE:
        return LOCALE_LANGUAGE[key]
    if lang in LOCALE_LANGUAGE:
        mapped = LOCALE_LANGUAGE[lang]
        if len(parts) > 1 and lang == "zh":
            region = parts[1].upper()
            if region == "TW":
                return "zh-TW"
            if region in ("HK", "MO"):
                return "zh-HK"
            if region in ("CN", "SG"):
                return "zh-CN"
        if lang == "pt" and len(parts) > 1:
            region = parts[1].upper()
            if region == "PT":
                return "pt-PT"
            if region == "BR":
                return "pt-BR"
        return mapped
    if LANGUAGE_RE.match(candidate):
        return candidate
    return None


def system_timezone_name() -> str | None:
    tz_env = os.environ.get("TZ") or os.environ.get("TIMEZONE")
    if tz_env:
        return tz_env.strip()

    # Debian/Ubuntu (and some other Linux distros) expose the zone name here.
    etc_timezone = Path("/etc/timezone")
    try:
        if etc_timezone.is_file():
            value = etc_timezone.read_text(encoding="utf-8", errors="ignore").strip()
            if value and "\n" not in value:
                return value
    except OSError:
        pass

    localtime = Path("/etc/localtime")
    try:
        if localtime.exists():
            resolved = localtime.resolve()
            parts = resolved.parts
            if "zoneinfo" in parts:
                idx = parts.index("zoneinfo")
                return "/".join(parts[idx + 1 :])
    except OSError:
        pass

    try:
        key = datetime.now().astimezone().tzinfo.key  # type: ignore[union-attr]
        if isinstance(key, str) and key:
            return key
    except AttributeError:
        pass

    try:
        return datetime.now().astimezone().tzname()
    except (AttributeError, OSError):
        return None


def locale_hints() -> list[str]:
    values: list[str] = []
    for key in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        raw = os.environ.get(key)
        if not raw:
            continue
        for part in raw.replace(";", ":").split(":"):
            part = part.strip()
            if part and part not in values:
                values.append(part)
    return values


def language_from_timezone(tz_name: str | None) -> str | None:
    if not tz_name:
        return None
    if tz_name in TIMEZONE_LANGUAGE:
        return TIMEZONE_LANGUAGE[tz_name]
    normalized = tz_name.replace(" ", "_")
    if normalized in TIMEZONE_LANGUAGE:
        return TIMEZONE_LANGUAGE[normalized]
    for pattern, language in TZ_NAME_HINTS:
        if pattern.search(tz_name):
            return language
    return None


def language_from_locales(locales: list[str]) -> str | None:
    for loc in locales:
        tagged = normalize_language(loc)
        if tagged and tagged != "en":
            return tagged
        if tagged == "en":
            # Keep scanning; a later non-English preference in LANGUAGE= may win
            continue
    for loc in locales:
        tagged = normalize_language(loc)
        if tagged:
            return tagged
    return None


def detect(timezone: str | None = None) -> dict[str, Any]:
    tz = timezone or system_timezone_name()
    locales = locale_hints()
    by_tz = language_from_timezone(tz)
    by_locale = language_from_locales(locales)

    if by_tz:
        language, source = by_tz, "timezone"
    elif by_locale:
        language, source = by_locale, "locale"
    else:
        language, source = "en", "default"

    return {
        "language": language,
        "source": source,
        "timezone": tz,
        "locales": locales,
        "signals": {
            "timezone_language": by_tz,
            "locale_language": by_locale,
        },
    }


def write_workspace_locale(
    workspace: Path, record: dict[str, Any] | None = None
) -> Path:
    """Persist preferred language under .omr/locale.json (create only when writing)."""
    record = record or detect()
    out = {
        "language": record["language"],
        "source": record["source"],
        "timezone": record.get("timezone"),
        "detected_at": datetime.now().astimezone().isoformat(),
    }
    path = workspace / ".omr" / "locale.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path


def read_workspace_locale(workspace: Path) -> str | None:
    path = workspace / ".omr" / "locale.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return normalize_language(data.get("language"))


def resolve_language(
    *,
    explicit: str | None = None,
    workspace: Path | None = None,
    timezone: str | None = None,
) -> dict[str, Any]:
    """Apply LANGUAGE.md priority for mechanical callers."""
    normalized_explicit = normalize_language(explicit) if explicit else None
    if normalized_explicit:
        return {
            "language": normalized_explicit,
            "source": "explicit",
            "timezone": timezone or system_timezone_name(),
        }
    if workspace is not None:
        stored = read_workspace_locale(workspace)
        if stored:
            return {
                "language": stored,
                "source": "workspace",
                "timezone": timezone or system_timezone_name(),
            }
    return detect(timezone)


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect preferred OMR report language")
    parser.add_argument("--timezone", default=None, help="Override IANA timezone name")
    parser.add_argument(
        "--json", action="store_true", help="Print full detection record"
    )
    parser.add_argument(
        "--list", action="store_true", help="List known timezone→language mappings"
    )
    parser.add_argument(
        "--write-workspace",
        type=Path,
        default=None,
        help="Write .omr/locale.json under this workspace",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=None,
        help="Prefer language from .omr/locale.json if present",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Explicit override BCP-47 tag (always wins), e.g. ja, de, zh-CN",
    )
    args = parser.parse_args()

    if args.list:
        print(
            json.dumps(
                dict(sorted(TIMEZONE_LANGUAGE.items())), indent=2, ensure_ascii=False
            )
        )
        return

    result = resolve_language(
        explicit=args.language,
        workspace=args.workspace.resolve() if args.workspace else None,
        timezone=args.timezone,
    )
    if args.write_workspace is not None:
        detected = detect(args.timezone)
        path = write_workspace_locale(args.write_workspace.resolve(), detected)
        result = {**detected, "wrote": str(path)}
    if args.json or args.write_workspace is not None:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(result["language"])


if __name__ == "__main__":
    main()
