import discord
from discord.ext import commands
from discord import app_commands, Embed
import os
import json
from dotenv import load_dotenv
from discord.ui import View, Button
import requests

load_dotenv()

GUILD_ID = int(os.getenv('SERVER_ID'))

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree  # Access to slash commands

# === File paths ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data.json")
DEATH_FILE = os.path.join(BASE_DIR, "deaths.json")

# === Load/save ===
def load_json(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

my_dict = load_json(DATA_FILE)
death_list = load_json(DEATH_FILE)

@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)

    # Clear global commands (no await here)
    bot.tree.clear_commands(guild=None)
    await bot.tree.sync(guild=None)
    print("Cleared global commands")

    # Sync guild commands only
    await bot.tree.sync(guild=guild)
    print(f"✅ Logged in as {bot.user} and synced commands to guild {GUILD_ID}.")

    guild_commands = await bot.tree.fetch_commands(guild=guild)
    global_commands = await bot.tree.fetch_commands(guild=None)

    print("Guild Commands:")
    for cmd in guild_commands:
        print(f" - {cmd.name}")

    print("Global Commands:")
    for cmd in global_commands:
        print(f" - {cmd.name}")

# === AUTOCOMPLETE for route names ===
async def route_autocomplete(interaction: discord.Interaction, current: str):
    return [
        app_commands.Choice(name=key, value=key)
        for key in my_dict
        if current.lower() in key.lower()
    ][:25]

def get_pokemon_sprite(pokemon_name: str) -> str | None:
    """Helper to get sprite URL from Pokémon name."""
    english_name = german_to_english.get(pokemon_name.lower())
    if not english_name:
        return None
    url = f'https://pokeapi.co/api/v2/pokemon/{english_name}'
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data['sprites']['front_default']
    return None

def get_evolution_line(pokemon_name):
    species_url = f"https://pokeapi.co/api/v2/pokemon-species/{pokemon_name.lower()}"
    response = requests.get(species_url)
    if response.status_code != 200:
        print(f"Failed to fetch species data for {pokemon_name}")
        return []

    species_data = response.json()
    evolution_chain_url = species_data['evolution_chain']['url']

    response = requests.get(evolution_chain_url)
    if response.status_code != 200:
        print(f"Failed to fetch evolution chain for {pokemon_name}")
        return []

    chain_data = response.json()['chain']

    def extract_species(chain_node):
        species_list = [chain_node['species']['name']]
        for evo in chain_node['evolves_to']:
            species_list.extend(extract_species(evo))
        return species_list

    evolution_line = extract_species(chain_data)
    return evolution_line

def is_valid_sprite(url):
    resp = requests.head(url)
    return resp.status_code == 200

async def pokemon_autocomplete(interaction: discord.Interaction, current: str):
    # `current` is what the user has typed so far
    matching = [
        name.title()
        for name in german_to_english.keys()
        if name.startswith(current.lower())
    ]
    # Limit to max 25 suggestions (Discord API limit)
    return [app_commands.Choice(name=p, value=p) for p in matching[:25]]

# === /lookup ===
# Load the mapping once when the bot starts
with open('pokemonMapping.json', 'r', encoding='utf-8') as f:
    german_to_english = json.load(f)

english_to_german = {v: k for k, v in german_to_english.items()}

@tree.command(name="lookup", description="Look up a route and get the Pokémon info", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(key="Route name")
@app_commands.autocomplete(key=route_autocomplete)
async def lookup(interaction: discord.Interaction, key: str):
    value = my_dict.get(key)
    if value:
        embeds = []

        if isinstance(value, list):
            if len(value) == 1 and '\n' in value[0]:
                lines = value[0].split('\n')
            else:
                lines = value
        elif isinstance(value, str):
            lines = value.split('\n')
        else:
            lines = value  # fallback

        for line in lines:
            if ': ' in line:
                trainer, pokemon_name = line.split(': ', 1)
                print(f"Trainer: {trainer}, Pokémon: {pokemon_name}")

                # Handle multiple names (comma-separated)
                pokemon_names = [name.strip() for name in pokemon_name.split(',')]
                english_names = [german_to_english.get(name.lower(), name.lower()) for name in pokemon_names]
                final_pokemon_en = english_names[-1] if english_names else None

                print(f"German names: {pokemon_names}")
                print(f"English names: {english_names}")
                print(f"Final evolution (for sprite): {final_pokemon_en}")

                # Fetch sprite only for final evolution
                if final_pokemon_en:
                    url = f'https://pokeapi.co/api/v2/pokemon/{final_pokemon_en}'
                    response = requests.get(url)
                    if response.status_code == 200:
                        data = response.json()
                        sprite_url = data['sprites']['front_default']
                    else:
                        sprite_url = None
                else:
                    sprite_url = None

                embed = Embed(
                    title=f"📍 Route Lookup: {key}",
                    description=f"**{trainer}**: {', '.join([name.title() for name in pokemon_names])}",
                    color=discord.Color.blue()
                )
                if sprite_url:
                    embed.set_thumbnail(url=sprite_url)
                embed.set_footer(text="Use /listall to see all routes.")
                embeds.append(embed)
            else:
                pass

        await interaction.response.send_message(embeds=embeds[:10])
    else:
        await interaction.response.send_message(f"❌ '{key}' not found.")


# === /add ===
@tree.command(name="add", description="Add a new route entry", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    key="Route name",
    moritz="Moritz's Pokémon",
    janne="Janne's Pokémon",
    elsmann="Elsmann's Pokémon",
    linus="Linus's Pokémon"
)
@app_commands.autocomplete(moritz=pokemon_autocomplete, janne=pokemon_autocomplete, elsmann=pokemon_autocomplete, linus=pokemon_autocomplete)
async def add(interaction: discord.Interaction, key: str, moritz: str, janne: str, elsmann: str, linus: str):
    # Convert to English
    moritz_english = german_to_english.get(moritz.lower(), moritz.lower())
    janne_english = german_to_english.get(janne.lower(), janne.lower())
    elsmann_english = german_to_english.get(elsmann.lower(), elsmann.lower())
    linus_english = german_to_english.get(linus.lower(), linus.lower())

    moritz_line_en = get_evolution_line(moritz_english)
    janne_line_en = get_evolution_line(janne_english)
    elsmann_line_en = get_evolution_line(elsmann_english)
    linus_line_en = get_evolution_line(linus_english)

    # Convert evolution lines back to German for storage
    moritz_line_de = [english_to_german.get(p, p) for p in moritz_line_en]
    janne_line_de = [english_to_german.get(p, p) for p in janne_line_en]
    elsmann_line_de = [english_to_german.get(p, p) for p in elsmann_line_en]
    linus_line_de = [english_to_german.get(p, p) for p in linus_line_en]

    res = (
        f"Moritz: {', '.join([p.title() for p in moritz_line_de])}\n"
        f"Janne: {', '.join([p.title() for p in janne_line_de])}\n"
        f"Elsmann: {', '.join([p.title() for p in elsmann_line_de])}\n"
        f"Linus: {', '.join([p.title() for p in linus_line_de])}"
    )

    if key in my_dict:
        if res not in my_dict[key]:
            my_dict[key].append(res)
            msg = f"✅ Added entry to **{key}**."
        else:
            msg = f"⚠️ That entry already exists in **{key}**."
    else:
        my_dict[key] = [res]
        msg = f"✅ Created new route **{key}**."

    save_json(DATA_FILE, my_dict)

    # Build embeds showing final evolution sprite
    embeds = []
    skipped = []  # to track which trainers were skipped

    for trainer, line_en, line_de in [
        ("Moritz", moritz_line_en, moritz_line_de),
        ("Janne", janne_line_en, janne_line_de),
        ("Elsmann", elsmann_line_en, elsmann_line_de),
        ("Linus", linus_line_en, linus_line_de)
    ]:
        if not line_en:
            skipped.append(trainer)
            continue  # skip if no data

        final_pokemon_en = line_en[-1]
        url = f'https://pokeapi.co/api/v2/pokemon/{final_pokemon_en}'
        print(url)
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            sprite_url = data['sprites']['front_default']
            print(f"Sprite URL for {final_pokemon_en}: {sprite_url}")
            if sprite_url and is_valid_sprite(sprite_url):
                # good, keep it
                pass
            else:
                pokedex_id = data.get('id')
                print(f"Using Pokedex ID for sprite: {pokedex_id}")
                sprite_url = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{pokedex_id}.png"
                print(f"Fallback sprite URL: {sprite_url}")
        elif response.status_code == 404:
            species_url = f'https://pokeapi.co/api/v2/pokemon-species/{final_pokemon_en}'
            species_response = requests.get(species_url)
            if species_response.status_code == 200:
                species_data = species_response.json()
                pokedex_id = species_data.get('id')
                print(f"Fetched Pokedex ID from species endpoint: {pokedex_id}")
                sprite_url = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{pokedex_id}.png"
                print(f"Fallback sprite URL: {sprite_url}")
            else:
                print(f"Could not fetch species data for {final_pokemon_en}")
        else:
            sprite_url = None

        embed = Embed(
            title=f"📍 Added to {key}",
            description=f"**{trainer}** ➔ {', '.join([p.title() for p in line_de])}",
            color=discord.Color.green()
        )
        if sprite_url:
            embed.set_thumbnail(url=sprite_url)
        else:
            fallback_url = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/{final_pokemon_en}.png"
            embed.set_thumbnail(url=fallback_url)
        embed.set_footer(text="Use /lookup to see more details.")
        embeds.append(embed)

    # Optional: inform user if some were skipped
    if skipped:
        msg += f"\n⚠️ No evolution data found for: {', '.join(skipped)}"

    await interaction.response.send_message(content=msg, embeds=embeds[:10])


# === /delete ===
@tree.command(name="delete", description="Delete a route", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(key="Route name")
@app_commands.autocomplete(key=route_autocomplete)
async def delete(interaction: discord.Interaction, key: str):
    if key in my_dict:
        del my_dict[key]
        save_json(DATA_FILE, my_dict)
        await interaction.response.send_message(f"🗑️ Deleted route **{key}**.")
    else:
        await interaction.response.send_message(f"❌ Route **{key}** not found.")

# === /logdeath ===
@tree.command(name="logdeath", description="Log a Pokémon as dead", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(pokemon="Pokémon name")
@app_commands.autocomplete(pokemon=pokemon_autocomplete)
async def logdeath(interaction: discord.Interaction, pokemon: str):
    pokemon = pokemon.capitalize()
    if "dead" not in death_list:
        death_list["dead"] = []
    if pokemon not in death_list["dead"]:
        death_list["dead"].append(pokemon)
        save_json(DEATH_FILE, death_list)
        await interaction.response.send_message(f"⚰️ {pokemon} logged as dead.")
    else:
        await interaction.response.send_message(f"{pokemon} is already on the death list.")

# === /islogged ===
@tree.command(name="islogged", description="Check if a Pokémon is in any route", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(pokemon="Pokémon name")
@app_commands.autocomplete(pokemon=pokemon_autocomplete)
async def islogged(interaction: discord.Interaction, pokemon: str):
    pokemon_lower = pokemon.lower()
    for key, entries in my_dict.items():
        for entry in entries:
            if pokemon_lower in entry.lower():
                sprite_url = get_pokemon_sprite(pokemon)
                embed = Embed(
                    title=f"✅ {pokemon.title()} is logged in {key}",
                    description=entry,
                    color=discord.Color.green()
                )
                if sprite_url:
                    embed.set_thumbnail(url=sprite_url)
                await interaction.response.send_message(embed=embed)
                return
    await interaction.response.send_message(f"❌ {pokemon.title()} not found in any route.")

# === /whereis ===
@tree.command(name="whereis", description="Find the route where a Pokémon is located", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(pokemon="Pokémon name")
@app_commands.autocomplete(pokemon=pokemon_autocomplete)
async def whereis(interaction: discord.Interaction, pokemon: str):
    pokemon_lower = pokemon.lower()
    for key, entries in my_dict.items():
        for entry in entries:
            if pokemon_lower in entry.lower():
                sprite_url = get_pokemon_sprite(pokemon)
                embed = Embed(
                    title=f"🔎 Found {pokemon.title()} in {key}",
                    description=entry,
                    color=discord.Color.blue()
                )
                if sprite_url:
                    embed.set_thumbnail(url=sprite_url)
                await interaction.response.send_message(embed=embed)
                return
    await interaction.response.send_message(f"❌ {pokemon.title()} not found in any route.")

# === /listall ===
@tree.command(name="listall", description="Show all routes and their entries", guild=discord.Object(id=GUILD_ID))
async def listall(interaction: discord.Interaction):
    if not my_dict:
        await interaction.response.send_message("📭 No entries found.")
        return

    embeds = []
    for key, entries in my_dict.items():
        for entry in entries:
            # Extract pokemon name(s) from entry string, e.g., "Moritz: Pikachu"
            # We'll extract the first Pokémon name after ': ' for sprite fetching.
            pokemon_name = None
            if ': ' in entry:
                _, poke = entry.split(': ', 1)
                # If multiple names, just pick first word for sprite lookup
                pokemon_name = poke.split()[0]
            
            sprite_url = get_pokemon_sprite(pokemon_name) if pokemon_name else None

            embed = Embed(
                title=f"📍 Route: {key}",
                description=entry,
                color=discord.Color.blue()
            )
            if sprite_url:
                embed.set_thumbnail(url=sprite_url)
            embed.set_footer(text="Use /listall to see all routes.")
            embeds.append(embed)

    # Discord max 10 embeds per message
    await interaction.response.send_message(embeds=embeds[:10])

# === /deleteall ===
@tree.command(name="deleteall", description="⚠️ Delete ALL routes from the dictionary", guild=discord.Object(id=GUILD_ID))
async def deleteall(interaction: discord.Interaction):
    # Create a view with confirm and cancel buttons
    class ConfirmView(View):
        def __init__(self):
            super().__init__(timeout=30)
            self.value = None

        @discord.ui.button(label="Confirm Delete", style=discord.ButtonStyle.danger)
        async def confirm(self, interaction_button: discord.Interaction, button: Button):
            my_dict.clear()
            save_json(DATA_FILE, my_dict)
            await interaction_button.response.edit_message(content="❌ All route entries have been deleted.", view=None)
            self.value = True
            self.stop()

        @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
        async def cancel(self, interaction_button: discord.Interaction, button: Button):
            await interaction_button.response.edit_message(content="❎ Deletion cancelled.", view=None)
            self.value = False
            self.stop()

    view = ConfirmView()
    await interaction.response.send_message("⚠️ Are you sure you want to delete **all** route entries?", view=view, ephemeral=True)

# === /adddeath ===
@tree.command(name="adddeath", description="Add 1 to a player's death counter", guild=discord.Object(id=GUILD_ID))
async def adddeath(interaction: discord.Interaction, player: str):
    player = player.capitalize()

    # Initialize structure if not present
    if "deaths" not in death_list:
        death_list["deaths"] = {}

    if "alldeaths" not in death_list:
        death_list["alldeaths"] = {}

    # Increment the death count
    death_list["deaths"][player] = death_list["deaths"].get(player, 0) + 1
    death_list["alldeaths"][player] = death_list["alldeaths"].get(player, 0) + 1
    save_json(DEATH_FILE, death_list)

    # Prepare the display
    death_counts = "session deaths:\n"
    death_counts += "\n".join(
        f"{name}: {count}" for name, count in death_list["deaths"].items()
    )
    death_counts += "\n\nall deaths:\n"
    death_counts += "\n".join(
        f"{name}: {count}" for name, count in death_list["alldeaths"].items()
    )

    await interaction.response.send_message(f"💀 1 death added to **{player}**.\n\n**Current death counts:**\n```{death_counts}```")

# === /removedeath ===
@tree.command(name="removedeath", description="Remove 1 from a player's death counter", guild=discord.Object(id=GUILD_ID))
async def removedeath(interaction: discord.Interaction, player: str):
    player = player.capitalize()

    if "deaths" not in death_list or player not in death_list["deaths"]:
        await interaction.response.send_message(f"⚠️ No death count found for **{player}**.")
        return
    
    if "alldeaths" not in death_list:
        await interaction.response.send_message(f"⚠️ No all death count found for **{player}**.")

    # Decrement (but not below 0)
    death_list["deaths"][player] = max(0, death_list["deaths"][player] - 1)
    death_list["alldeaths"][player] = max(0, death_list["alldeaths"][player] - 1)
    save_json(DEATH_FILE, death_list)

    death_counts = "session deaths:\n"
    death_counts += "\n".join(
        f"{name}: {count}" for name, count in death_list["deaths"].items()
    )
    death_counts += "\n\nall deaths:\n"
    death_counts += "\n".join(
        f"{name}: {count}" for name, count in death_list["alldeaths"].items()
    )

    await interaction.response.send_message(f"➖ 1 death removed from **{player}**.\n\n**Current death counts:**\n```{death_counts}```")

# === /resetdeaths ===
@tree.command(name="resetdeaths", description="⚠️ Reset all player death counters to 0", guild=discord.Object(id=GUILD_ID))
async def resetdeaths(interaction: discord.Interaction):
    class ConfirmReset(View):
        def __init__(self):
            super().__init__(timeout=30)

        @discord.ui.button(label="Confirm Reset", style=discord.ButtonStyle.danger)
        async def confirm(self, interaction_button: discord.Interaction, button: Button):
            if "deaths" in death_list:
                for player in death_list["deaths"]:
                    death_list["deaths"][player] = 0
                save_json(DEATH_FILE, death_list)
                await interaction_button.response.edit_message(content="🔄 All death counters have been reset to 0.", view=None)
            else:
                await interaction_button.response.edit_message(content="📭 No death counters to reset.", view=None)
            self.stop()

        @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
        async def cancel(self, interaction_button: discord.Interaction, button: Button):
            await interaction_button.response.edit_message(content="❎ Reset cancelled.", view=None)
            self.stop()

    view = ConfirmReset()
    await interaction.response.send_message("⚠️ Are you sure you want to reset **all** death counters to 0?", view=view, ephemeral=True)

# === /deathcount ===
@tree.command(name="deathcount", description="Show all players' death counts", guild=discord.Object(id=GUILD_ID))
async def deathcount(interaction: discord.Interaction):
    if "deaths" not in death_list or not death_list["deaths"]:
        await interaction.response.send_message("📭 No deaths recorded yet.")
        return

    embed = Embed(
        title="💀 Death Counts",
        description="Here are the current player death stats:",
        color=discord.Color.red()
    )

    for name, count in death_list["deaths"].items():
        overall = death_list["alldeaths"].get(name, 0)
        embed.add_field(
            name=f"{name}",
            value=f"Session deaths: **{count}**\nTotal deaths: **{overall}**",
            inline=False
        )

    embed.set_footer(text="Stay alive out there!")
    embed.set_thumbnail(url="https://i.imgur.com/RHTNWEv.png")  # Replace with any skull icon or your bot logo

    await interaction.response.send_message(embed=embed)

# === Helper: Split long messages ===
def split_chunks(entries: list, max_chars: int) -> list:
    chunks = []
    current = ""
    for entry in entries:
        if len(current) + len(entry) + 2 < max_chars:
            current += entry + "\n\n"
        else:
            chunks.append(current)
            current = entry + "\n\n"
    if current:
        chunks.append(current)
    return chunks

@tree.command(name="addmissedencounter", description="Show missed encounters", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(person="Person's name")
async def addmissedencounter(interaction: discord.Interaction, person: str):
    person = person.capitalize()
    if "missed_encounters" not in death_list:
        death_list["missed_encounters"] = {}
    if "overall_missed_encounters" not in death_list:
        death_list["overall_missed_encounters"] = {}

    if person not in death_list["missed_encounters"]:
        death_list["missed_encounters"][person] = 0
    if person not in death_list["overall_missed_encounters"]:
        death_list["overall_missed_encounters"][person] = 0

    death_list["overall_missed_encounters"][person] += 1
    death_list["missed_encounters"][person] += 1
    save_json(DEATH_FILE, death_list)

    missed_counts = "Missed encounters:\n"
    missed_counts += "\n".join(
        f"{name}: {count}" for name, count in death_list["missed_encounters"].items()
    )

    missed_counts += "\n\nOverall missed encounters:\n"
    missed_counts += "\n".join(
        f"{name}: {count}" for name, count in death_list.get("overall_missed_encounters", {}).items()
    )

    await interaction.response.send_message(
        f"➕ 1 missed encounter added for **{person}**. This attempt: {death_list['missed_encounters'][person]} missed encounters, overall: {death_list['overall_missed_encounters'][person]} missed encounters."
    )

@tree.command(name="missedencounters", description="Show all missed encounters", guild=discord.Object(id=GUILD_ID))
async def missedencounters(interaction: discord.Interaction):
    embed = Embed(
        title="❌ Missed Encounter Counts",
        description="Here are the current missed encounter stats:",
        color=discord.Color.red()
    )

    for name, count in death_list["missed_encounters"].items():
        overall = death_list["overall_missed_encounters"].get(name, 0)
        embed.add_field(
            name=f"{name}",
            value=f"Missed encounters this attempt: **{count}**\nTotal missed encounters: **{overall}**",
            inline=False
        )

    embed.set_footer(text="Godspeed!")
    embed.set_thumbnail(url="https://i.imgur.com/zOTv7bG.jpeg")  # Replace with any skull icon or your bot logo

    await interaction.response.send_message(embed=embed)

@tree.command(name="resetmissedencounters", description="⚠️ Reset all missed encounters", guild=discord.Object(id=GUILD_ID))
async def resetmissedencounters(interaction: discord.Interaction):
    class ConfirmResetMissed(View):
        def __init__(self):
            super().__init__(timeout=30)

        @discord.ui.button(label="Confirm Reset Missed", style=discord.ButtonStyle.danger)
        async def confirm(self, interaction_button: discord.Interaction, button: Button):
            if "missed_encounters" in death_list:
                for player in death_list["missed_encounters"]:
                    death_list["missed_encounters"][player] = 0
                save_json(DEATH_FILE, death_list)
                await interaction_button.response.edit_message(content="🔄 All missed encounters have been reset.", view=None)
            else:
                await interaction_button.response.edit_message(content="📭 No missed encounters to reset.", view=None)
            self.stop()

        @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
        async def cancel(self, interaction_button: discord.Interaction, button: Button):
            await interaction_button.response.edit_message(content="❎ Reset cancelled.", view=None)
            self.stop()

    view = ConfirmResetMissed()
    await interaction.response.send_message("⚠️ Are you sure you want to reset **all** missed encounters?", view=view, ephemeral=True)

@tree.command(name="resetall", description="⚠️ Reset all data (deaths, missed encounters, routes)", guild=discord.Object(id=GUILD_ID))
async def resetall(interaction: discord.Interaction, person: str):
    class ConfirmResetAll(View):
        def __init__(self):
            super().__init__(timeout=30)

        @discord.ui.button(label="Confirm Reset All", style=discord.ButtonStyle.danger)
        async def confirm(self, interaction_button: discord.Interaction, button: Button):
            my_dict.clear()
            if "whipes" not in death_list:
                death_list["whipes"] = {}
            if person not in death_list["whipes"]:
                death_list["whipes"][person] = 0
            if "missed_encounters" in death_list:
                for player in death_list["missed_encounters"]:
                    death_list["missed_encounters"][player] = 0
            if "deaths" in death_list:
                for player in death_list["deaths"]:
                    death_list["deaths"][player] = 0
            if "resets" in death_list:
                death_list["resets"] += 1
            if "whipes" in death_list:
                death_list["whipes"][person] += 1
            save_json(DATA_FILE, my_dict)
            save_json(DEATH_FILE, death_list)

            embed = Embed(
                title="❌ Reset Counter",
                description="Here is the current reset count:",
                color=discord.Color.red()
            )

            total_whipes = "Total whipes:\n"
            total_whipes += "\n".join(
                f"{name}: {count}" for name, count in death_list["whipes"].items()
    )

            embed.add_field(
                name="Resets",
                value=f"Total resets: **{death_list.get('resets', 0)}**\n **{total_whipes}**\n"
            )

            await interaction_button.response.edit_message(embed=embed, view=None)

            self.value = True
            self.stop()

        @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
        async def cancel(self, interaction_button: discord.Interaction, button: Button):
            await interaction_button.response.edit_message(content="❎ Reset cancelled.", view=None)
            self.value = False
            self.stop()

    view = ConfirmResetAll()
    await interaction.response.send_message("⚠️ Are you sure you want to reset **all** data?", view=view, ephemeral=True)

@tree.command(name="addreset", description="Add a count to the reset counter", guild=discord.Object(id=GUILD_ID))
async def addreset(interaction: discord.Interaction):
    if "resets" not in death_list:
        death_list["resets"] = 0
    death_list["resets"] += 1
    save_json(DEATH_FILE, death_list)

    await interaction.response.send_message(f"➕ Reset counter increased to **{death_list['resets']}**.")

@tree.command(name="resetresets", description="Reset the reset counter to 0", guild=discord.Object(id=GUILD_ID))
async def resetresets(interaction: discord.Interaction):
    if "resets" not in death_list:
        death_list["resets"] = 0
    death_list["resets"] = 0
    save_json(DEATH_FILE, death_list)

    await interaction.response.send_message("🔄 Reset counter has been reset to **0**.")

@tree.command(name="resets", description="Show the current reset counter", guild=discord.Object(id=GUILD_ID))
async def resets(interaction: discord.Interaction):
    if "resets" not in death_list:
        death_list["resets"] = 0

    await interaction.response.send_message(f"🔄 Current reset counter: **{death_list['resets']}**.")

# === Run the bot ===
bot.run(os.getenv("SOULLINK_SECRET_KEY"))
