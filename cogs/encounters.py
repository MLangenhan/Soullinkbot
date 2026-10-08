"""
/available — shows which encounter routes have and haven't been logged yet.
Detects the game from the active run's meta, then fuzzy-matches logged route
names against the canonical location list for that game.
"""
import discord
from discord import app_commands
from discord.ext import commands

from utils.i18n import t
from utils import embeds, data as db
from utils.encounter_data import (
    detect_region, get_locations, get_region_display_name, resolve_logged_routes
)

PAGE_SIZE = 20

class AvailableView(discord.ui.View):
    def __init__(self, pages: list[discord.Embed]):
        super().__init__(timeout=120)
        self.pages   = pages
        self.current = 0
        self._sync_buttons()

    def _sync_buttons(self):
        self.prev_btn.disabled = self.current == 0
        self.next_btn.disabled = self.current == len(self.pages) - 1

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, _):
        self.current -= 1
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, _):
        self.current += 1
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)


class EncountersCog(commands.Cog):
    def __init__(self, bot: commands.Bot, guild_id: int):
        self.bot      = bot
        self.guild_id = guild_id

    def _require_run(self, interaction):
        run_id = db.get_active_run_id()
        if not run_id:
            return None, None
        return run_id, db.get_run_meta(run_id)

    @app_commands.command(name="available", description="Show which encounter routes are still available")
    async def available(self, interaction: discord.Interaction):
        run_id, meta = self._require_run(interaction)
        if not run_id:
            await interaction.response.send_message(
                embed=embeds.danger(t(interaction, "run_not_found"), footer=t(interaction, "footer")),
                ephemeral=True,
            )
            return

        # Detect region from game name
        game_name  = meta.get("game", "")
        region_key = detect_region(game_name)

        if not region_key:
            await interaction.response.send_message(
                embed=embeds.warning(
                    title="🗺️ Spiel nicht erkannt",
                    description=(
                        f"Das Spiel **{game_name}** konnte keiner bekannten Region zugeordnet werden.\n"
                        f"Bekannte Spiele: Kanto, Johto, Hoenn, Sinnoh, Einall, Kalos."
                    ),
                    footer=t(interaction, "footer"),
                ),
                ephemeral=True,
            )
            return

        region_display = get_region_display_name(region_key)
        all_locations  = get_locations(region_key)
        routes         = db.get_routes(run_id)
        matched        = resolve_logged_routes(list(routes.keys()), region_key)

        claimed_canonical = set(matched.values())
        unknown_logged    = [k for k in routes if k not in matched]

        rows_available = [f"🟡  {loc}" for loc in all_locations if loc not in claimed_canonical]
        rows_claimed   = [f"✅  ~~{loc}~~" for loc in all_locations if loc in claimed_canonical]

        total     = len(all_locations)
        n_claimed = len(rows_claimed)
        progress  = round((n_claimed / total) * 100) if total else 0
        bar       = "█" * round(progress / 5) + "░" * (20 - round(progress / 5))
        summary   = f"`{bar}` {progress}%  —  {n_claimed}/{total} beansprucht"

        # Build combined list: available first, then claimed
        all_rows = rows_available + ([""] if rows_claimed else []) + rows_claimed
        if unknown_logged:
            all_rows += ["", "**❓ Nicht erkannt (bitte Route prüfen):**"]
            all_rows += [f"❓  {k}" for k in unknown_logged]

        # Paginate
        pages_text, chunk, chars = [], [], 0
        for row in all_rows:
            if chars + len(row) + 1 > 3600:
                pages_text.append("\n".join(chunk))
                chunk, chars = [row], len(row)
            else:
                chunk.append(row)
                chars += len(row) + 1
        if chunk:
            pages_text.append("\n".join(chunk))

        if not pages_text:
            await interaction.response.send_message(
                embed=embeds.info("🗺️ Keine Routen gefunden.", footer=t(interaction, "footer"))
            )
            return

        n_pages = len(pages_text)
        pages   = [
            embeds.info(
                title=f"🗺️ Verfügbare Begegnungen — {meta['name']} ({region_display})",
                description=f"{summary}\n\n{text}",
                footer=f"Seite {i+1}/{n_pages}  •  Soullink Bot",
            )
            for i, text in enumerate(pages_text)
        ]

        if len(pages) > 1:
            await interaction.response.send_message(embed=pages[0], view=AvailableView(pages))
        else:
            await interaction.response.send_message(embed=pages[0])


async def setup(bot: commands.Bot, guild_id: int):
    guild = discord.Object(id=guild_id)

    cog = EncountersCog(bot, guild_id)
    await bot.add_cog(cog)
    bot.tree.add_command(cog.available, guild=guild)

    caps_cog = LevelCapsCog(bot, guild_id)
    await bot.add_cog(caps_cog)
    bot.tree.add_command(caps_cog.levelcaps, guild=guild)


# ── Level caps ────────────────────────────────────────────────────────────────

import json as _json
import os as _os

_CAPS_FILE = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
    "data", "level_caps.json"
)
with open(_CAPS_FILE, "r", encoding="utf-8") as _f:
    _CAPS_DATA: dict = _json.load(_f)

# Flat alias list for fuzzy matching
_CAPS_ALIASES: list[tuple[str, str]] = [
    (key, alias)
    for key, entry in _CAPS_DATA.items()
    for alias in entry["game_names"]
]

def _detect_caps_key(game_name: str) -> str | None:
    from rapidfuzz import fuzz, process
    aliases = [alias for _, alias in _CAPS_ALIASES]
    result  = process.extractOne(game_name, aliases, scorer=fuzz.WRatio, score_cutoff=70)
    if not result:
        return None
    matched = result[0]
    for key, alias in _CAPS_ALIASES:
        if alias == matched:
            return key
    return None


class LevelCapsCog(commands.Cog):
    def __init__(self, bot: commands.Bot, guild_id: int):
        self.bot      = bot
        self.guild_id = guild_id

    @app_commands.command(name="levelcaps", description="Show level caps for the active run's game")
    async def levelcaps(self, interaction: discord.Interaction):
        run_id = db.get_active_run_id()
        if not run_id:
            await interaction.response.send_message(
                embed=embeds.danger(t(interaction, "run_not_found"), footer=t(interaction, "footer")),
                ephemeral=True,
            )
            return

        meta      = db.get_run_meta(run_id)
        game_name = meta.get("game", "")
        caps_key  = _detect_caps_key(game_name)

        if not caps_key:
            await interaction.response.send_message(
                embed=embeds.warning(
                    title="⚠️ Spiel nicht erkannt",
                    description=(
                        f"Für **{game_name}** wurden keine Level-Caps gefunden.\n"
                        f"Unterstützte Spiele: Kanto (RBY/FRLG), Johto (GSC/HGSS), "
                        f"Hoenn (RSE/ORAS), Sinnoh (DP/Pt), Einall (BW/BW2), Kalos (XY)."
                    ),
                    footer=t(interaction, "footer"),
                ),
                ephemeral=True,
            )
            return

        entry = _CAPS_DATA[caps_key]
        caps  = entry["caps"]

        # Build embed fields — group into gyms, elite four, champion, extras
        lines = []
        for cap in caps:
            if cap["level"] is None:
                # Section divider
                lines.append(f"\n**{cap['label']}**")
            else:
                lines.append(f"`Lv {cap['level']:>2}`  {cap['label']}")

        # Paginate if needed (dividers + many entries e.g. HGSS Kanto)
        pages_text, chunk, chars = [], [], 0
        for line in lines:
            if chars + len(line) + 1 > 3800:
                pages_text.append("\n".join(chunk))
                chunk, chars = [line], len(line)
            else:
                chunk.append(line)
                chars += len(line) + 1
        if chunk:
            pages_text.append("\n".join(chunk))

        n_pages = len(pages_text)
        pages = [
            embeds.info(
                title=f"🏆 Level-Caps — {game_name}",
                description=text,
                footer=f"Seite {i+1}/{n_pages}  •  Soullink Bot",
            )
            for i, text in enumerate(pages_text)
        ]

        if len(pages) > 1:
            await interaction.response.send_message(embed=pages[0], view=AvailableView(pages))
        else:
            await interaction.response.send_message(embed=pages[0])