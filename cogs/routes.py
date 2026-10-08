import io
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button

from utils.i18n import t
from utils import embeds, data as db
from utils.sprites import build_route_image

# ── PokeAPI helpers ───────────────────────────────────────────────────────────

async def fetch_json(session: aiohttp.ClientSession, url: str) -> dict | None:
    async with session.get(url) as resp:
        if resp.status == 200:
            return await resp.json()
    return None

async def get_sprite(session: aiohttp.ClientSession, english_name: str) -> str | None:
    data = await fetch_json(session, f"https://pokeapi.co/api/v2/pokemon/{english_name.lower()}")
    if data:
        sprite = data["sprites"].get("front_default")
        if sprite:
            return sprite
        pid = data.get("id")
        if pid:
            return f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{pid}.png"
    species = await fetch_json(session, f"https://pokeapi.co/api/v2/pokemon-species/{english_name.lower()}")
    if species:
        pid = species.get("id")
        if pid:
            return f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{pid}.png"
    return None

async def get_evolution_line(session: aiohttp.ClientSession, english_name: str) -> list[str]:
    species = await fetch_json(session, f"https://pokeapi.co/api/v2/pokemon-species/{english_name.lower()}")
    if not species:
        return [english_name]
    chain_data = await fetch_json(session, species["evolution_chain"]["url"])
    if not chain_data:
        return [english_name]

    def extract(node):
        result = [node["species"]["name"]]
        for evo in node["evolves_to"]:
            result.extend(extract(evo))
        return result

    return extract(chain_data["chain"])


async def send_route_image(
    interaction: discord.Interaction,
    route_name: str,
    players: dict,
    de_to_en: dict,
    dead_pokemon: set[str],
    footer: str,
    title: str | None = None,
    followup: bool = True,
):
    """Shared helper: build + send a sprite row image embed for one route."""
    async with aiohttp.ClientSession() as session:
        sprite_urls: dict[str, str | None] = {}
        for player, evo_line in players.items():
            if evo_line:
                final_en = de_to_en.get(evo_line[-1].lower(), evo_line[-1].lower())
                sprite_urls[player] = await get_sprite(session, final_en)
            else:
                sprite_urls[player] = None

        img_buf = await build_route_image(session, players, sprite_urls, dead_pokemon)

    safe_name = route_name.replace(" ", "_")
    file      = discord.File(img_buf, filename=f"{safe_name}.png")
    embed     = embeds.info(
        title=title or f"📍 {route_name}",
        footer=footer,
    )
    embed.set_image(url=f"attachment://{safe_name}.png")

    if followup:
        await interaction.followup.send(embed=embed, file=file)
    else:
        await interaction.response.send_message(embed=embed, file=file)


# ── Cog ───────────────────────────────────────────────────────────────────────

class RoutesCog(commands.Cog):
    def __init__(self, bot: commands.Bot, guild_id: int, mapping: dict):
        self.bot      = bot
        self.guild_id = guild_id
        self.de_to_en: dict[str, str] = mapping
        self.en_to_de: dict[str, str] = {v: k for k, v in mapping.items()}

    def _require_run(self, interaction: discord.Interaction):
        run_id = db.get_active_run_id()
        if not run_id:
            return None, None
        return run_id, db.get_run_meta(run_id)

    # ── autocomplete ──────────────────────────────────────────────────────────

    async def route_autocomplete(self, interaction: discord.Interaction, current: str):
        run_id = db.get_active_run_id()
        if not run_id:
            return []
        routes = db.get_routes(run_id)
        return [
            app_commands.Choice(name=k, value=k)
            for k in routes if current.lower() in k.lower()
        ][:25]

    async def pokemon_autocomplete(self, interaction: discord.Interaction, current: str):
        return [
            app_commands.Choice(name=name.title(), value=name.title())
            for name in self.de_to_en
            if name.startswith(current.lower())
        ][:25]

    # ── /add ──────────────────────────────────────────────────────────────────

    @app_commands.command(name="add", description="Add a new route entry")
    @app_commands.describe(key="Route name")
    async def add(self, interaction: discord.Interaction, key: str):
        run_id, meta = self._require_run(interaction)
        if not run_id:
            await interaction.response.send_message(
                embed=embeds.danger(t(interaction, "run_not_found"), footer=t(interaction, "footer")),
                ephemeral=True,
            )
            return
        modal = AddRouteModal(key, meta["players"], self.de_to_en, self.en_to_de, run_id)
        await interaction.response.send_modal(modal)

    add.autocomplete("key")(route_autocomplete)

    # ── /lookup ───────────────────────────────────────────────────────────────

    @app_commands.command(name="lookup", description="Look up a route")
    @app_commands.describe(key="Route name")
    async def lookup(self, interaction: discord.Interaction, key: str):
        run_id, _ = self._require_run(interaction)
        if not run_id:
            await interaction.response.send_message(
                embed=embeds.danger(t(interaction, "run_not_found"), footer=t(interaction, "footer")),
                ephemeral=True,
            )
            return

        routes = db.get_routes(run_id)
        entry  = routes.get(key)
        if not entry:
            await interaction.response.send_message(
                embed=embeds.danger(t(interaction, "route_not_found", route=key), footer=t(interaction, "footer")),
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        dead = db.get_dead_pokemon(run_id)
        await send_route_image(
            interaction, key, entry, self.de_to_en, dead,
            footer=t(interaction, "lookup_footer"),
            title=t(interaction, "embed_route_lookup", route=key),
        )

    lookup.autocomplete("key")(route_autocomplete)

    # ── /delete ───────────────────────────────────────────────────────────────

    @app_commands.command(name="delete", description="Delete a route")
    @app_commands.describe(key="Route name")
    async def delete(self, interaction: discord.Interaction, key: str):
        run_id, _ = self._require_run(interaction)
        if not run_id:
            await interaction.response.send_message(
                embed=embeds.danger(t(interaction, "run_not_found"), footer=t(interaction, "footer")),
                ephemeral=True,
            )
            return

        routes = db.get_routes(run_id)
        if key not in routes:
            await interaction.response.send_message(
                embed=embeds.danger(t(interaction, "route_not_found", route=key), footer=t(interaction, "footer")),
                ephemeral=True,
            )
            return

        del routes[key]
        db.save_routes(run_id, routes)
        await interaction.response.send_message(
            embed=embeds.success(t(interaction, "route_deleted", route=key), footer=t(interaction, "footer"))
        )

    delete.autocomplete("key")(route_autocomplete)

    # ── /deleteall ────────────────────────────────────────────────────────────

    @app_commands.command(name="deleteall", description="⚠️ Delete all routes")
    async def deleteall(self, interaction: discord.Interaction):
        run_id, _ = self._require_run(interaction)
        if not run_id:
            await interaction.response.send_message(
                embed=embeds.danger(t(interaction, "run_not_found"), footer=t(interaction, "footer")),
                ephemeral=True,
            )
            return

        confirm_text = t(interaction, "confirm_delete_all")
        cleared_text = t(interaction, "routes_cleared")
        cancel_text  = t(interaction, "reset_cancelled")
        confirm_btn  = t(interaction, "confirm_btn")
        cancel_btn   = t(interaction, "cancel_btn")

        class ConfirmView(View):
            def __init__(self):
                super().__init__(timeout=30)

            @discord.ui.button(label=confirm_btn, style=discord.ButtonStyle.danger)
            async def confirm(self_, i: discord.Interaction, _: Button):
                db.save_routes(run_id, {})
                await i.response.edit_message(
                    embed=embeds.danger(cleared_text, footer=t(i, "footer")), view=None
                )
                self_.stop()

            @discord.ui.button(label=cancel_btn, style=discord.ButtonStyle.secondary)
            async def cancel(self_, i: discord.Interaction, _: Button):
                await i.response.edit_message(
                    embed=embeds.warning(cancel_text, footer=t(i, "footer")), view=None
                )
                self_.stop()

        await interaction.response.send_message(
            embed=embeds.warning(confirm_text, footer=t(interaction, "footer")),
            view=ConfirmView(),
            ephemeral=True,
        )

    # ── /listall ──────────────────────────────────────────────────────────────

    @app_commands.command(name="listall", description="Show all routes")
    async def listall(self, interaction: discord.Interaction):
        run_id, _ = self._require_run(interaction)
        if not run_id:
            await interaction.response.send_message(
                embed=embeds.danger(t(interaction, "run_not_found"), footer=t(interaction, "footer")),
                ephemeral=True,
            )
            return

        routes = db.get_routes(run_id)
        if not routes:
            await interaction.response.send_message(
                embed=embeds.info(t(interaction, "routes_empty"), footer=t(interaction, "footer"))
            )
            return

        await interaction.response.defer()
        dead   = db.get_dead_pokemon(run_id)
        footer = t(interaction, "all_routes_footer")

        async with aiohttp.ClientSession() as session:
            for route_name, players in routes.items():
                sprite_urls: dict[str, str | None] = {}
                for player, evo_line in players.items():
                    if evo_line:
                        final_en = self.de_to_en.get(evo_line[-1].lower(), evo_line[-1].lower())
                        sprite_urls[player] = await get_sprite(session, final_en)
                    else:
                        sprite_urls[player] = None

                img_buf   = await build_route_image(session, players, sprite_urls, dead)
                safe_name = route_name.replace(" ", "_")
                file      = discord.File(img_buf, filename=f"{safe_name}.png")
                embed     = embeds.info(title=f"📍 {route_name}", footer=footer)
                embed.set_image(url=f"attachment://{safe_name}.png")
                await interaction.followup.send(embed=embed, file=file)

    # ── /whereis ──────────────────────────────────────────────────────────────

    @app_commands.command(name="whereis", description="Find the route a Pokémon is on")
    @app_commands.describe(pokemon="Pokémon name")
    async def whereis(self, interaction: discord.Interaction, pokemon: str):
        run_id, _ = self._require_run(interaction)
        if not run_id:
            await interaction.response.send_message(
                embed=embeds.danger(t(interaction, "run_not_found"), footer=t(interaction, "footer")),
                ephemeral=True,
            )
            return

        poke_lower = pokemon.lower()
        routes     = db.get_routes(run_id)

        # Collect ALL routes where this pokemon appears
        matches: list[str] = []
        for route_name, players in routes.items():
            for player, evo_line in players.items():
                if any(poke_lower == n.lower() for n in evo_line):
                    matches.append(route_name)
                    break  # one match per route is enough

        if not matches:
            await interaction.response.send_message(
                embed=embeds.danger(t(interaction, "pokemon_not_logged", pokemon=pokemon.title()), footer=t(interaction, "footer")),
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        dead = db.get_dead_pokemon(run_id)

        for route_name in matches:
            players = routes[route_name]
            await send_route_image(
                interaction, route_name, players, self.de_to_en, dead,
                footer=t(interaction, "footer"),
                title=t(interaction, "pokemon_logged", pokemon=pokemon.title(), route=route_name),
            )

    whereis.autocomplete("pokemon")(pokemon_autocomplete)


# ── AddRouteModal ─────────────────────────────────────────────────────────────

class AddRouteModal(discord.ui.Modal):
    def __init__(self, key: str, players: list[str], de_to_en: dict, en_to_de: dict, run_id: str):
        super().__init__(title=f"Route: {key}")
        self.key      = key
        self.players  = players
        self.de_to_en = de_to_en
        self.en_to_de = en_to_de
        self.run_id   = run_id
        self.fields   = []

        for player in players[:5]:
            field = discord.ui.TextInput(
                label=player,
                placeholder=f"{player}'s Pokémon (z.B. Bidoof)",
                max_length=50,
                required=True,
            )
            self.add_item(field)
            self.fields.append((player, field))

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        routes = db.get_routes(self.run_id)
        entry: dict[str, list[str]] = {}

        async with aiohttp.ClientSession() as session:
            for player, field in self.fields:
                raw_name = field.value.strip()
                en_name  = self.de_to_en.get(raw_name.lower(), raw_name.lower())
                evo_en   = await get_evolution_line(session, en_name)
                evo_de   = [self.en_to_de.get(n, n) for n in evo_en]
                entry[player] = [n.title() for n in evo_de]

            routes[self.key] = entry
            db.save_routes(self.run_id, routes)

            # Build sprite URLs for the confirmation image
            dead = db.get_dead_pokemon(self.run_id)
            sprite_urls: dict[str, str | None] = {}
            for player, evo_line in entry.items():
                if evo_line:
                    final_en = self.de_to_en.get(evo_line[-1].lower(), evo_line[-1].lower())
                    sprite_urls[player] = await get_sprite(session, final_en)
                else:
                    sprite_urls[player] = None

            img_buf   = await build_route_image(session, entry, sprite_urls, dead)
            safe_name = self.key.replace(" ", "_")
            file      = discord.File(img_buf, filename=f"{safe_name}.png")
            embed     = embeds.success(title=f"✅ Route hinzugefügt: {self.key}", footer="Soullink Bot")
            embed.set_image(url=f"attachment://{safe_name}.png")

        await interaction.followup.send(embed=embed, file=file)


# ── setup ─────────────────────────────────────────────────────────────────────

async def setup(bot: commands.Bot, guild_id: int, mapping: dict):
    cog   = RoutesCog(bot, guild_id, mapping)
    guild = discord.Object(id=guild_id)
    await bot.add_cog(cog)
    bot.tree.add_command(cog.add,       guild=guild)
    bot.tree.add_command(cog.lookup,    guild=guild)
    bot.tree.add_command(cog.delete,    guild=guild)
    bot.tree.add_command(cog.deleteall, guild=guild)
    bot.tree.add_command(cog.listall,   guild=guild)
    bot.tree.add_command(cog.whereis,   guild=guild)