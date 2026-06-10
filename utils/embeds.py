import discord
from discord import Embed

# === Colour palette ===
class Colour:
    SUCCESS  = 0x2ECC71   # green  — added / alive
    DANGER   = 0xE74C3C   # red    — death / delete / danger
    INFO     = 0x3498DB   # blue   — lookup / neutral info
    WARNING  = 0xF1C40F   # yellow — confirmations / warnings
    SPECIAL  = 0x9B59B6   # purple — hall of fame / special events
    DARK     = 0x2C2F33   # near-black — neutral / stats

def make(
    title: str,
    description: str = "",
    colour: int = Colour.INFO,
    footer: str = "Soullink Bot",
    thumbnail: str | None = None,
    fields: list[tuple[str, str, bool]] | None = None,
) -> Embed:
    """
    Build a consistent embed.
    fields: list of (name, value, inline) tuples
    """
    embed = Embed(title=title, description=description, color=colour)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    embed.set_footer(text=footer)
    return embed

def success(title: str, description: str = "", **kwargs) -> Embed:
    return make(title, description, colour=Colour.SUCCESS, **kwargs)

def danger(title: str, description: str = "", **kwargs) -> Embed:
    return make(title, description, colour=Colour.DANGER, **kwargs)

def info(title: str, description: str = "", **kwargs) -> Embed:
    return make(title, description, colour=Colour.INFO, **kwargs)

def warning(title: str, description: str = "", **kwargs) -> Embed:
    return make(title, description, colour=Colour.WARNING, **kwargs)

def special(title: str, description: str = "", **kwargs) -> Embed:
    return make(title, description, colour=Colour.SPECIAL, **kwargs)