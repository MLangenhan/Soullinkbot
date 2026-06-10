import json
import os
import discord

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALES_DIR = os.path.join(BASE_DIR, "locales")

_cache: dict[str, dict] = {}

def _load(lang: str) -> dict:
    if lang not in _cache:
        path = os.path.join(LOCALES_DIR, f"{lang}.json")
        fallback = os.path.join(LOCALES_DIR, "de.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                _cache[lang] = json.load(f)
        else:
            with open(fallback, "r", encoding="utf-8") as f:
                _cache[lang] = json.load(f)
    return _cache[lang]

def t(interaction: discord.Interaction, string_key: str, **kwargs) -> str:
    locale = str(interaction.locale)
    lang = "en" if locale.startswith("en") else "de"
    strings = _load(lang)
    if string_key not in strings:
        strings = _load("de")
    template = strings.get(string_key, f"[{string_key}]")
    return template.format(**kwargs) if kwargs else template

def t_raw(lang: str, string_key: str, **kwargs) -> str:
    """Get a string by language code directly, without an interaction object."""
    if lang.startswith("en"):
        lang = "en"
    else:
        lang = "de"
    strings = _load(lang)
    if string_key not in strings:
        strings = _load("de")
    template = strings.get(string_key, f"[{string_key}]")
    return template.format(**kwargs) if kwargs else template