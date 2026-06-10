import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
import aiohttp

from utils.i18n import t
from utils import embeds, data as db

GUILD_ID = None  # set from bot.py via cog init

class CreateRunModal(discord.ui.Modal):
    def __init__(self, locale: str):
        from utils.i18n import t_raw
        super().__init__(title=t_raw(locale, "modal_run_title"))
        self.locale = locale

        self.run_name = discord.ui.TextInput(
            label=t_raw(locale, "modal_run_name_label"),
            placeholder=t_raw(locale, "modal_run_name_placeholder"),
            max_length=50,
        )
        self.game = discord.ui.TextInput(
            label=t_raw(locale, "modal_run_game_label"),
            placeholder=t_raw(locale, "modal_run_game_placeholder"),
            max_length=50,
        )
        self.players = discord.ui.TextInput(
            label=t_raw(locale, "modal_run_players_label"),
            placeholder=t_raw(locale, "modal_run_players_placeholder"),
            max_length=100,
        )
        self.add_item(self.run_name)
        self.add_item(self.game)
        self.add_item(self.players)

    async def on_submit(self, interaction: discord.Interaction):
        name    = self.run_name.value.strip()
        game    = self.game.value.strip()
        players = [p.strip() for p in self.players.value.split(",") if p.strip()]

        meta = db.create_run(name, game, players)

        embed = embeds.success(
            title=t(interaction, "run_created", name=name),
            fields=[
                (t(interaction, "run_game"),    game,                  True),
                (t(interaction, "run_players"), ", ".join(players),    True),
                (t(interaction, "run_started"), meta["created_at"],    True),
            ],
            footer=t(interaction, "footer"),
        )
        await interaction.response.send_message(embed=embed)


class RunsCog(commands.Cog):
    def __init__(self, bot: commands.Bot, guild_id: int):
        self.bot = bot
        self.guild_id = guild_id

    def _guild(self):
        return discord.Object(id=self.guild_id)

    # /createrun
    @app_commands.command(name="createrun", description="Create a new Soullink run")
    async def createrun(self, interaction: discord.Interaction):
        locale = str(interaction.locale)
        modal  = CreateRunModal(locale)
        await interaction.response.send_modal(modal)

    # /runs — list all runs
    @app_commands.command(name="runs", description="List all runs")
    async def runs(self, interaction: discord.Interaction):
        all_runs = db.list_runs()
        active_id = db.get_active_run_id()

        if not all_runs:
            await interaction.response.send_message(
                embed=embeds.info(t(interaction, "run_list_empty"), footer=t(interaction, "footer"))
            )
            return

        active_label  = t(interaction, "run_status_active")
        done_label    = t(interaction, "run_status_completed")

        fields = []
        for run in all_runs:
            status = f"{'▶ ' if run['id'] == active_id else ''}{active_label if run['status'] == 'active' else done_label}"
            fields.append((
                f"{run['name']} ({run['game']})",
                f"{t(interaction, 'run_players')}: {', '.join(run['players'])}\n"
                f"{t(interaction, 'run_started')}: {run['created_at']} — {status}",
                False,
            ))

        embed = embeds.info(
            title=t(interaction, "embed_run_list"),
            fields=fields,
            footer=t(interaction, "footer"),
        )
        await interaction.response.send_message(embed=embed)

    # /setrun — autocomplete + activate
    @app_commands.command(name="setrun", description="Switch the active run")
    @app_commands.describe(run_id="Run ID to activate")
    async def setrun(self, interaction: discord.Interaction, run_id: str):
        meta = db.get_run_meta(run_id)
        if not meta:
            await interaction.response.send_message(
                embed=embeds.danger(t(interaction, "run_not_found"), footer=t(interaction, "footer")),
                ephemeral=True,
            )
            return

        if db.get_active_run_id() == run_id:
            await interaction.response.send_message(
                embed=embeds.warning(t(interaction, "run_already_active"), footer=t(interaction, "footer")),
                ephemeral=True,
            )
            return

        db.set_active_run_id(run_id)
        embed = embeds.success(
            title=t(interaction, "run_activated", name=meta["name"]),
            fields=[
                (t(interaction, "run_game"),    meta["game"],                  True),
                (t(interaction, "run_players"), ", ".join(meta["players"]),    True),
            ],
            footer=t(interaction, "footer"),
        )
        await interaction.response.send_message(embed=embed)

    @setrun.autocomplete("run_id")
    async def setrun_autocomplete(self, interaction: discord.Interaction, current: str):
        return [
            app_commands.Choice(name=f"{r['name']} ({r['game']})", value=r["id"])
            for r in db.list_runs()
            if current.lower() in r["name"].lower() or current.lower() in r["id"].lower()
        ][:25]

    # /completerun
    @app_commands.command(name="completerun", description="Mark the active run as completed and add to Hall of Fame")
    async def completerun(self, interaction: discord.Interaction):
        run_id = db.get_active_run_id()
        if not run_id:
            await interaction.response.send_message(
                embed=embeds.danger(t(interaction, "run_not_found"), footer=t(interaction, "footer")),
                ephemeral=True,
            )
            return

        meta  = db.complete_run(run_id)
        stats = db.get_stats(run_id)

        hof_entry = {
            "name":         meta["name"],
            "game":         meta["game"],
            "players":      meta["players"],
            "completed_at": meta["completed_at"],
            "deaths":       stats.get("alldeaths", {}),
            "resets":       stats.get("resets", 0),
        }
        db.add_to_hof(hof_entry)

        embed = embeds.special(
            title=t(interaction, "run_completed", name=meta["name"]),
            fields=[
                (t(interaction, "run_game"),    meta["game"],                  True),
                (t(interaction, "run_players"), ", ".join(meta["players"]),    True),
                (t(interaction, "total_deaths"),
                 "\n".join(f"{p}: **{c}**" for p, c in stats.get("alldeaths", {}).items()), False),
            ],
            footer=t(interaction, "hof_footer"),
        )
        await interaction.response.send_message(embed=embed)

    # /halloffame
    @app_commands.command(name="halloffame", description="Show the Hall of Fame")
    async def halloffame(self, interaction: discord.Interaction):
        hof = db.get_hof()
        title = t(interaction, "embed_hall_of_fame")

        if not hof:
            await interaction.response.send_message(
                embed=embeds.special(
                    title=title,
                    description=t(interaction, "embed_hall_of_fame_empty"),
                    footer=t(interaction, "hof_footer"),
                )
            )
            return

        fields = []
        for entry in reversed(hof):  # most recent first
            deaths_str = ", ".join(f"{p}: {c}" for p, c in entry.get("deaths", {}).items())
            fields.append((
                f"🏅 {entry['name']} — {entry['game']}",
                f"{t(interaction, 'run_players')}: {', '.join(entry['players'])}\n"
                f"{t(interaction, 'total_deaths')}: {deaths_str}\n"
                f"✅ {entry['completed_at']}",
                False,
            ))

        embed = embeds.special(
            title=title,
            fields=fields,
            footer=t(interaction, "hof_footer"),
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot, guild_id: int):
    cog = RunsCog(bot, guild_id)
    await bot.add_cog(cog)
    guild = discord.Object(id=guild_id)
    for cmd in cog.__cog_app_commands__:
        cmd.guild_ids = [guild_id]
    bot.tree.add_command(cog.createrun,   guild=guild)
    bot.tree.add_command(cog.runs,        guild=guild)
    bot.tree.add_command(cog.setrun,      guild=guild)
    bot.tree.add_command(cog.completerun, guild=guild)
    bot.tree.add_command(cog.halloffame,  guild=guild)