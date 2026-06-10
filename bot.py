import os
import json
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

GUILD_ID      = int(os.getenv("SERVER_ID"))
MAPPING_FILE  = os.path.join(os.path.dirname(__file__), "pokemonMapping.json")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def load_mapping() -> dict:
    if os.path.exists(MAPPING_FILE):
        with open(MAPPING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

@bot.event
async def on_ready():
    mapping = load_mapping()
    guild   = discord.Object(id=GUILD_ID)

    # Clear stale global commands
    bot.tree.clear_commands(guild=None)
    await bot.tree.sync(guild=None)

    # Load cogs
    from cogs import runs, routes, stats, encounters
    await runs.setup(bot,       GUILD_ID)
    await routes.setup(bot,     GUILD_ID, mapping)
    await stats.setup(bot,      GUILD_ID)
    await encounters.setup(bot, GUILD_ID)

    # Sync guild commands
    await bot.tree.sync(guild=guild)

    guild_cmds = await bot.tree.fetch_commands(guild=guild)
    print(f"✅ {bot.user} ready — {len(guild_cmds)} guild commands synced.")
    for cmd in guild_cmds:
        print(f"   /{cmd.name}")

bot.run(os.getenv("SOULLINK_SECRET_KEY"))