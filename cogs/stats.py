import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button

from utils.i18n import t
from utils import embeds, data as db
from utils.sprites import build_route_image


class StatsCog(commands.Cog):
    def __init__(self, bot: commands.Bot, guild_id: int):
        self.bot      = bot
        self.guild_id = guild_id

    def _guild(self):
        return discord.Object(id=self.guild_id)

    def _require_run(self, interaction: discord.Interaction):
        run_id = db.get_active_run_id()
        if not run_id:
            return None, None
        meta = db.get_run_meta(run_id)
        return run_id, meta

    async def player_autocomplete(self, interaction: discord.Interaction, current: str):
        run_id = db.get_active_run_id()
        if not run_id:
            return []
        meta = db.get_run_meta(run_id)
        if not meta:
            return []
        return [
            app_commands.Choice(name=p, value=p)
            for p in meta["players"] if current.lower() in p.lower()
        ][:25]

    # ── /adddeath ───────────────────────────────────────────────────────────

    @app_commands.command(name="adddeath", description="Add 1 to a player's death counter")
    @app_commands.describe(player="Player name")
    async def adddeath(self, interaction: discord.Interaction, player: str):
        run_id, _ = self._require_run(interaction)
        if not run_id:
            await interaction.response.send_message(
                embed=embeds.danger(t(interaction, "run_not_found"), footer=t(interaction, "footer")),
                ephemeral=True,
            )
            return

        db.ensure_player_in_stats(run_id, player)
        stats = db.get_stats(run_id)
        stats["deaths"][player]   = stats["deaths"].get(player, 0) + 1
        stats["alldeaths"][player] = stats["alldeaths"].get(player, 0) + 1
        db.save_stats(run_id, stats)

        await interaction.response.send_message(
            embed=self._death_embed(interaction, stats, highlight=player)
        )

    adddeath.autocomplete("player")(player_autocomplete)

    # ── /removedeath ────────────────────────────────────────────────────────

    @app_commands.command(name="removedeath", description="Remove 1 from a player's death counter")
    @app_commands.describe(player="Player name")
    async def removedeath(self, interaction: discord.Interaction, player: str):
        run_id, _ = self._require_run(interaction)
        if not run_id:
            await interaction.response.send_message(
                embed=embeds.danger(t(interaction, "run_not_found"), footer=t(interaction, "footer")),
                ephemeral=True,
            )
            return

        stats = db.get_stats(run_id)
        if player not in stats.get("deaths", {}):
            await interaction.response.send_message(
                embed=embeds.warning(t(interaction, "death_not_found", player=player), footer=t(interaction, "footer")),
                ephemeral=True,
            )
            return

        stats["deaths"][player]   = max(0, stats["deaths"][player] - 1)
        stats["alldeaths"][player] = max(0, stats["alldeaths"].get(player, 0) - 1)
        db.save_stats(run_id, stats)

        await interaction.response.send_message(
            embed=self._death_embed(interaction, stats, highlight=player)
        )

    removedeath.autocomplete("player")(player_autocomplete)

    # ── /deathcount ─────────────────────────────────────────────────────────

    @app_commands.command(name="deathcount", description="Show all players' death counts")
    async def deathcount(self, interaction: discord.Interaction):
        run_id, _ = self._require_run(interaction)
        if not run_id:
            await interaction.response.send_message(
                embed=embeds.danger(t(interaction, "run_not_found"), footer=t(interaction, "footer")),
                ephemeral=True,
            )
            return

        stats = db.get_stats(run_id)
        if not stats.get("deaths"):
            await interaction.response.send_message(
                embed=embeds.info(t(interaction, "deaths_empty"), footer=t(interaction, "footer"))
            )
            return

        await interaction.response.send_message(embed=self._death_embed(interaction, stats))

    # ── /resetdeaths ────────────────────────────────────────────────────────

    @app_commands.command(name="resetdeaths", description="⚠️ Reset all session death counters")
    async def resetdeaths(self, interaction: discord.Interaction):
        run_id, _ = self._require_run(interaction)
        if not run_id:
            await interaction.response.send_message(
                embed=embeds.danger(t(interaction, "run_not_found"), footer=t(interaction, "footer")),
                ephemeral=True,
            )
            return

        confirm_text = t(interaction, "confirm_reset_deaths")
        reset_text   = t(interaction, "deaths_reset")
        cancel_text  = t(interaction, "reset_cancelled")
        confirm_btn  = t(interaction, "confirm_btn")
        cancel_btn   = t(interaction, "cancel_btn")

        class ConfirmView(View):
            def __init__(self_):
                super().__init__(timeout=30)

            @discord.ui.button(label=confirm_btn, style=discord.ButtonStyle.danger)
            async def confirm(self_, i: discord.Interaction, _: Button):
                stats = db.get_stats(run_id)
                for p in stats.get("deaths", {}):
                    stats["deaths"][p] = 0
                db.save_stats(run_id, stats)
                await i.response.edit_message(
                    embed=embeds.success(reset_text, footer=t(i, "footer")), view=None
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

    # ── /addmissedencounter ─────────────────────────────────────────────────

    @app_commands.command(name="addmissedencounter", description="Log a missed encounter for a player")
    @app_commands.describe(player="Player name")
    async def addmissedencounter(self, interaction: discord.Interaction, player: str):
        run_id, _ = self._require_run(interaction)
        if not run_id:
            await interaction.response.send_message(
                embed=embeds.danger(t(interaction, "run_not_found"), footer=t(interaction, "footer")),
                ephemeral=True,
            )
            return

        db.ensure_player_in_stats(run_id, player)
        stats = db.get_stats(run_id)
        stats["missed_encounters"][player]         = stats["missed_encounters"].get(player, 0) + 1
        stats["overall_missed_encounters"][player] = stats["overall_missed_encounters"].get(player, 0) + 1
        db.save_stats(run_id, stats)

        await interaction.response.send_message(
            embed=self._missed_embed(interaction, stats, highlight=player)
        )

    addmissedencounter.autocomplete("player")(player_autocomplete)

    # ── /missedencounters ───────────────────────────────────────────────────

    @app_commands.command(name="missedencounters", description="Show all missed encounter counts")
    async def missedencounters(self, interaction: discord.Interaction):
        run_id, _ = self._require_run(interaction)
        if not run_id:
            await interaction.response.send_message(
                embed=embeds.danger(t(interaction, "run_not_found"), footer=t(interaction, "footer")),
                ephemeral=True,
            )
            return

        stats = db.get_stats(run_id)
        if not stats.get("missed_encounters"):
            await interaction.response.send_message(
                embed=embeds.info(t(interaction, "missed_empty"), footer=t(interaction, "footer"))
            )
            return

        await interaction.response.send_message(embed=self._missed_embed(interaction, stats))

    # ── /resetmissedencounters ──────────────────────────────────────────────

    @app_commands.command(name="resetmissedencounters", description="⚠️ Reset all missed encounters")
    async def resetmissedencounters(self, interaction: discord.Interaction):
        run_id, _ = self._require_run(interaction)
        if not run_id:
            await interaction.response.send_message(
                embed=embeds.danger(t(interaction, "run_not_found"), footer=t(interaction, "footer")),
                ephemeral=True,
            )
            return

        confirm_text = t(interaction, "confirm_reset_missed")
        reset_text   = t(interaction, "missed_reset")
        cancel_text  = t(interaction, "reset_cancelled")
        confirm_btn  = t(interaction, "confirm_btn")
        cancel_btn   = t(interaction, "cancel_btn")

        class ConfirmView(View):
            def __init__(self_):
                super().__init__(timeout=30)

            @discord.ui.button(label=confirm_btn, style=discord.ButtonStyle.danger)
            async def confirm(self_, i: discord.Interaction, _: Button):
                stats = db.get_stats(run_id)
                for p in stats.get("missed_encounters", {}):
                    stats["missed_encounters"][p] = 0
                db.save_stats(run_id, stats)
                await i.response.edit_message(
                    embed=embeds.success(reset_text, footer=t(i, "footer")), view=None
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

    # ── /resetall ───────────────────────────────────────────────────────────

    @app_commands.command(name="resetall", description="⚠️ Reset all data for the active run")
    @app_commands.describe(player="Who triggered the wipe")
    async def resetall(self, interaction: discord.Interaction, player: str):
        run_id, meta = self._require_run(interaction)
        if not run_id:
            await interaction.response.send_message(
                embed=embeds.danger(t(interaction, "run_not_found"), footer=t(interaction, "footer")),
                ephemeral=True,
            )
            return

        confirm_text = t(interaction, "confirm_reset_all")
        cancel_text  = t(interaction, "reset_cancelled")
        confirm_btn  = t(interaction, "confirm_btn")
        cancel_btn   = t(interaction, "cancel_btn")

        class ConfirmView(View):
            def __init__(self_):
                super().__init__(timeout=30)

            @discord.ui.button(label=confirm_btn, style=discord.ButtonStyle.danger)
            async def confirm(self_, i: discord.Interaction, _: Button):
                db.save_routes(run_id, {})
                stats = db.get_stats(run_id)
                for p in stats.get("deaths", {}):
                    stats["deaths"][p] = 0
                for p in stats.get("missed_encounters", {}):
                    stats["missed_encounters"][p] = 0
                stats["resets"] = stats.get("resets", 0) + 1
                stats.setdefault("wipes", {})[player] = stats["wipes"].get(player, 0) + 1
                db.save_stats(run_id, stats)

                total_wipes = "\n".join(f"{p}: **{c}**" for p, c in stats["wipes"].items())
                embed = embeds.danger(
                    title=t(i, "reset_all_done"),
                    fields=[
                        (t(i, "total_resets"), str(stats["resets"]),  True),
                        (t(i, "total_wipes"),  total_wipes or "—",    False),
                    ],
                    footer=t(i, "footer"),
                )
                await i.response.edit_message(embed=embed, view=None)
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

    resetall.autocomplete("player")(player_autocomplete)

    # ── /resets ─────────────────────────────────────────────────────────────

    @app_commands.command(name="resets", description="Show the reset counter")
    async def resets(self, interaction: discord.Interaction):
        run_id, _ = self._require_run(interaction)
        if not run_id:
            await interaction.response.send_message(
                embed=embeds.danger(t(interaction, "run_not_found"), footer=t(interaction, "footer")),
                ephemeral=True,
            )
            return

        stats = db.get_stats(run_id)
        total = stats.get("resets", 0)
        wipes = stats.get("wipes", {})

        fields = [(t(interaction, "total_resets"), str(total), True)]
        if wipes:
            fields.append((
                t(interaction, "total_wipes"),
                "\n".join(f"{p}: **{c}**" for p, c in wipes.items()),
                False,
            ))

        await interaction.response.send_message(
            embed=embeds.info(
                title="🔄 Resets",
                fields=fields,
                footer=t(interaction, "footer"),
            )
        )

    # ── embed builders ───────────────────────────────────────────────────────

    def _death_embed(self, interaction, stats: dict, highlight: str | None = None) -> discord.Embed:
        fields = []
        for player, count in stats.get("deaths", {}).items():
            overall = stats.get("alldeaths", {}).get(player, 0)
            marker  = "💀 " if player == highlight else ""
            fields.append((
                f"{marker}{player}",
                f"{t(interaction, 'session_deaths')}: **{count}**\n{t(interaction, 'total_deaths')}: **{overall}**",
                True,
            ))
        return embeds.danger(
            title=t(interaction, "embed_death_counts"),
            description=t(interaction, "embed_death_desc"),
            fields=fields,
            footer=t(interaction, "stay_alive"),
        )

    def _missed_embed(self, interaction, stats: dict, highlight: str | None = None) -> discord.Embed:
        fields = []
        for player, count in stats.get("missed_encounters", {}).items():
            overall = stats.get("overall_missed_encounters", {}).get(player, 0)
            marker  = "❌ " if player == highlight else ""
            fields.append((
                f"{marker}{player}",
                f"{t(interaction, 'session_missed')}: **{count}**\n{t(interaction, 'total_missed')}: **{overall}**",
                True,
            ))
        return embeds.warning(
            title=t(interaction, "embed_missed_counts"),
            description=t(interaction, "embed_missed_desc"),
            fields=fields,
            footer=t(interaction, "godspeed"),
        )


    # ── /markdead ───────────────────────────────────────────────────────────

    @app_commands.command(name="markdead", description="Mark a Pokémon as dead (triggers soul link)")
    @app_commands.describe(pokemon="Pokémon name to mark as dead")
    async def markdead(self, interaction: discord.Interaction, pokemon: str):
        run_id, _ = self._require_run(interaction)
        if not run_id:
            await interaction.response.send_message(
                embed=embeds.danger(t(interaction, "run_not_found"), footer=t(interaction, "footer")),
                ephemeral=True,
            )
            return

        # Find which route + player owns this pokemon
        routes     = db.get_routes(run_id)
        poke_lower = pokemon.lower()
        owner      = None
        owner_route = None

        for route_name, players in routes.items():
            for player, evo_line in players.items():
                if any(poke_lower == n.lower() for n in evo_line):
                    owner       = player
                    owner_route = route_name
                    break
            if owner:
                break

        # Mark the pokemon dead
        db.mark_pokemon_dead(run_id, poke_lower)

        # Find soul link partner pokemon on the same route
        partner_info = None
        if owner and owner_route:
            result = db.find_soul_link_partner(run_id, owner, routes)
            if result:
                partner, partner_evo = result
                if partner_evo:
                    partner_poke = partner_evo[-1].lower()
                    db.mark_pokemon_dead(run_id, partner_poke)
                    partner_info = (partner, partner_evo[-1].title())

        await interaction.response.defer()

        # Build description text
        desc_lines = [f"☠ **{pokemon.title()}** ({owner})" if owner else f"☠ **{pokemon.title()}**"]
        if partner_info:
            desc_lines.append(f"☠ **{partner_info[1]}** ({partner_info[0]}) — {t(interaction, 'death_soul_link')}")

        # If we know the route, show the full route image with both deaths applied
        if owner_route:
            from utils.sprites import build_route_image
            from cogs.routes import get_sprite
            dead        = db.get_dead_pokemon(run_id)
            route_entry = routes[owner_route]
            # We need the mapping — load it via bot mapping stored on bot
            # Use a simple approach: get en names from the route data directly via PokeAPI
            de_to_en: dict = {}
            try:
                import json, os
                mapping_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pokemonMapping.json")
                if os.path.exists(mapping_path):
                    with open(mapping_path, "r", encoding="utf-8") as mf:
                        de_to_en = json.load(mf)
            except Exception:
                pass

            async with aiohttp.ClientSession() as session:
                sprite_urls: dict[str, str | None] = {}
                for player, evo_line in route_entry.items():
                    if evo_line:
                        final_en = de_to_en.get(evo_line[-1].lower(), evo_line[-1].lower())
                        sprite_urls[player] = await get_sprite(session, final_en)
                    else:
                        sprite_urls[player] = None
                img_buf = await build_route_image(session, route_entry, sprite_urls, dead)

            safe_name = owner_route.replace(" ", "_")
            file      = discord.File(img_buf, filename=f"{safe_name}.png")
            embed     = embeds.danger(
                title=t(interaction, "death_marked_title"),
                description="\n".join(desc_lines),
                footer=t(interaction, "stay_alive"),
            )
            embed.set_image(url=f"attachment://{safe_name}.png")
            await interaction.followup.send(embed=embed, file=file)
        else:
            # Pokemon not found on any route — just show text response
            await interaction.followup.send(
                embed=embeds.danger(
                    title=t(interaction, "death_marked_title"),
                    description="\n".join(desc_lines),
                    footer=t(interaction, "stay_alive"),
                )
            )

    async def markdead_autocomplete(self, interaction: discord.Interaction, current: str):
        run_id = db.get_active_run_id()
        if not run_id:
            return []
        routes = db.get_routes(run_id)
        dead   = db.get_dead_pokemon(run_id)
        names  = set()
        for players in routes.values():
            for evo_line in players.values():
                for name in evo_line:
                    if name.lower() not in dead:
                        names.add(name.title())
        return [
            app_commands.Choice(name=n, value=n)
            for n in sorted(names) if current.lower() in n.lower()
        ][:25]

    markdead.autocomplete("pokemon")(markdead_autocomplete)

    # ── /markalive ──────────────────────────────────────────────────────────

    @app_commands.command(name="markalive", description="Unmark a Pokémon as dead")
    @app_commands.describe(pokemon="Pokémon name to revive")
    async def markalive(self, interaction: discord.Interaction, pokemon: str):
        run_id, _ = self._require_run(interaction)
        if not run_id:
            await interaction.response.send_message(
                embed=embeds.danger(t(interaction, "run_not_found"), footer=t(interaction, "footer")),
                ephemeral=True,
            )
            return

        db.unmark_pokemon_dead(run_id, pokemon.lower())
        await interaction.response.send_message(
            embed=embeds.success(
                title=t(interaction, "death_revived", pokemon=pokemon.title()),
                footer=t(interaction, "footer"),
            )
        )

    async def markalive_autocomplete(self, interaction: discord.Interaction, current: str):
        run_id = db.get_active_run_id()
        if not run_id:
            return []
        dead = db.get_dead_pokemon(run_id)
        return [
            app_commands.Choice(name=n.title(), value=n.title())
            for n in sorted(dead) if current.lower() in n.lower()
        ][:25]

    markalive.autocomplete("pokemon")(markalive_autocomplete)


async def setup(bot: commands.Bot, guild_id: int):
    cog   = StatsCog(bot, guild_id)
    guild = discord.Object(id=guild_id)
    await bot.add_cog(cog)
    bot.tree.add_command(cog.adddeath,              guild=guild)
    bot.tree.add_command(cog.removedeath,           guild=guild)
    bot.tree.add_command(cog.deathcount,            guild=guild)
    bot.tree.add_command(cog.resetdeaths,           guild=guild)
    bot.tree.add_command(cog.addmissedencounter,    guild=guild)
    bot.tree.add_command(cog.missedencounters,      guild=guild)
    bot.tree.add_command(cog.resetmissedencounters, guild=guild)
    bot.tree.add_command(cog.resetall,              guild=guild)
    bot.tree.add_command(cog.resets,               guild=guild)
    bot.tree.add_command(cog.markdead,             guild=guild)
    bot.tree.add_command(cog.markalive,            guild=guild)