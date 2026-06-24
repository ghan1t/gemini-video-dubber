from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class Language:
    label: str
    code: str

    @property
    def display(self) -> str:
        return f"{self.label} ({self.code})"


SUPPORTED_LANGUAGES: tuple[Language, ...] = (
    Language("Afrikaans", "af"),
    Language("Akan", "ak"),
    Language("Albanian", "sq"),
    Language("Amharic", "am"),
    Language("Arabic", "ar"),
    Language("Armenian", "hy"),
    Language("Azerbaijani", "az"),
    Language("Basque", "eu"),
    Language("Belarusian", "be"),
    Language("Bengali", "bn"),
    Language("Bulgarian", "bg"),
    Language("Burmese (Myanmar)", "my"),
    Language("Catalan", "ca"),
    Language("Chinese (Simplified)", "zh-Hans"),
    Language("Chinese (Traditional)", "zh-Hant"),
    Language("Croatian", "hr"),
    Language("Czech", "cs"),
    Language("Danish", "da"),
    Language("Dutch", "nl"),
    Language("English", "en"),
    Language("Estonian", "et"),
    Language("Filipino", "fil"),
    Language("Finnish", "fi"),
    Language("French", "fr"),
    Language("Galician", "gl"),
    Language("Georgian", "ka"),
    Language("German", "de"),
    Language("Greek", "el"),
    Language("Gujarati", "gu"),
    Language("Hausa", "ha"),
    Language("Hebrew", "he"),
    Language("Hindi", "hi"),
    Language("Hungarian", "hu"),
    Language("Icelandic", "is"),
    Language("Indonesian", "id"),
    Language("Italian", "it"),
    Language("Japanese", "ja"),
    Language("Javanese", "jv"),
    Language("Kannada", "kn"),
    Language("Kazakh", "kk"),
    Language("Khmer", "km"),
    Language("Kinyarwanda", "rw"),
    Language("Korean", "ko"),
    Language("Lao", "lo"),
    Language("Latvian", "lv"),
    Language("Lithuanian", "lt"),
    Language("Macedonian", "mk"),
    Language("Malay", "ms"),
    Language("Malayalam", "ml"),
    Language("Marathi", "mr"),
    Language("Mongolian", "mn"),
    Language("Nepali", "ne"),
    Language("Norwegian", "no"),
    Language("Norwegian Bokmal", "nb"),
    Language("Persian", "fa"),
    Language("Polish", "pl"),
    Language("Portuguese (Brazil)", "pt-BR"),
    Language("Portuguese (Portugal)", "pt-PT"),
    Language("Punjabi", "pa"),
    Language("Romanian", "ro"),
    Language("Russian", "ru"),
    Language("Serbian", "sr"),
    Language("Sindhi", "sd"),
    Language("Sinhala", "si"),
    Language("Slovak", "sk"),
    Language("Slovenian", "sl"),
    Language("Spanish", "es"),
    Language("Sundanese", "su"),
    Language("Swahili", "sw"),
    Language("Swedish", "sv"),
    Language("Tamil", "ta"),
    Language("Telugu", "te"),
    Language("Thai", "th"),
    Language("Turkish", "tr"),
    Language("Ukrainian", "uk"),
    Language("Urdu", "ur"),
    Language("Uzbek", "uz"),
    Language("Vietnamese", "vi"),
    Language("Zulu", "zu"),
)

LANGUAGE_BY_DISPLAY = {language.display: language for language in SUPPORTED_LANGUAGES}
LANGUAGE_BY_CODE = {language.code: language for language in SUPPORTED_LANGUAGES}

MP4_LANGUAGE_BY_CODE = {
    "de": "deu",
    "en": "eng",
    "es": "spa",
    "fr": "fra",
    "it": "ita",
    "ja": "jpn",
    "ko": "kor",
    "lv": "lav",
    "pt-BR": "por",
    "pt-PT": "por",
    "zh-Hans": "zho",
    "zh-Hant": "zho",
}


def code_for_display(display: str) -> str:
    return LANGUAGE_BY_DISPLAY[display].code


def display_for_code(code: str) -> str:
    return LANGUAGE_BY_CODE[code].display


def label_for_code(code: str) -> str:
    language = LANGUAGE_BY_CODE.get(code)
    return language.label if language else code


def mp4_language_for_code(code: str) -> str:
    return MP4_LANGUAGE_BY_CODE.get(code, code)
