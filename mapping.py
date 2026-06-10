import requests
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "germanPokemonNames.json")

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_all_german_pokemon_names():
    url = "https://pokeapi.co/api/v2/pokemon-species?limit=10000"
    response = requests.get(url)
    data = response.json()

    german_names = []

    for species in data['results']:
        species_url = species['url']
        species_data = requests.get(species_url).json()

        names = species_data.get('names', [])
        for name_entry in names:
            if name_entry['language']['name'] == 'de':
                german_name = name_entry['name']
                german_names.append(german_name)
                break  # only take the first German name

    return sorted(german_names)

german_pokemon_names = get_all_german_pokemon_names()
print(f"Found {len(german_pokemon_names)} German Pokémon names.")
save_json(DATA_FILE, german_pokemon_names)
