"""
Generates a sprite row image for a single route.
Returns a BytesIO PNG ready to attach to a Discord message.
"""
import io
import aiohttp
from PIL import Image, ImageDraw, ImageFont

# ── layout constants ──────────────────────────────────────────────────────────
SPRITE_SIZE = 96
PAD         = 14
CARD_W      = SPRITE_SIZE + PAD * 2
CARD_H      = 24 + SPRITE_SIZE + 20 + 18 + PAD   # player + sprite + poke name + bottom pad
ACCENT_H    = 3

# ── colours ───────────────────────────────────────────────────────────────────
BG          = (30, 31, 34)
CARD_BG     = (43, 45, 49)
CARD_DEAD   = (55, 35, 35)
ACCENT      = (88, 101, 242)     # blurple — alive
ACCENT_DEAD = (231, 76, 60)      # red     — dead
WHITE       = (255, 255, 255)
MUTED       = (160, 163, 168)
RED         = (231, 76, 60)

FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]
FONT_PATHS_REG = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
]

def _load_font(paths: list[str], size: int) -> ImageFont.FreeTypeFont:
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()

async def _fetch_sprite(session: aiohttp.ClientSession, url: str) -> Image.Image | None:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
            if r.status == 200:
                data = await r.read()
                return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception:
        pass
    return None

def _placeholder(size: int) -> Image.Image:
    """Grey question-mark box for missing sprites."""
    img  = Image.new("RGBA", (size, size), (60, 60, 60, 180))
    draw = ImageDraw.Draw(img)
    f    = _load_font(FONT_PATHS, size // 3)
    draw.text((size // 2, size // 2), "?", font=f, fill=(180, 180, 180), anchor="mm")
    return img

async def build_route_image(
    session: aiohttp.ClientSession,
    players: dict[str, list[str]],        # {player: [evo_line_de]}
    sprite_urls: dict[str, str | None],   # {player: url or None}
    dead_pokemon: set[str] | None = None, # set of lowercase pokemon names that are dead
) -> io.BytesIO:
    """
    Render a horizontal sprite card row for one route.
    Returns a BytesIO PNG.
    """
    dead_pokemon = dead_pokemon or set()
    f_player = _load_font(FONT_PATHS,     13)
    f_poke   = _load_font(FONT_PATHS_REG, 11)

    player_list = list(players.keys())
    n = len(player_list)
    W = PAD + n * (CARD_W + PAD)
    H = ACCENT_H + PAD + CARD_H + PAD

    canvas = Image.new("RGB", (W, H), BG)
    draw   = ImageDraw.Draw(canvas)

    # Top accent bar
    draw.rectangle([0, 0, W, ACCENT_H], fill=ACCENT)

    for i, player in enumerate(player_list):
        evo_line = players[player]
        final_name = evo_line[-1].lower() if evo_line else ""
        is_dead    = final_name in dead_pokemon

        url    = sprite_urls.get(player)
        sprite = await _fetch_sprite(session, url) if url else None
        if sprite is None:
            sprite = _placeholder(SPRITE_SIZE)

        cx = PAD + i * (CARD_W + PAD)
        cy = ACCENT_H + PAD

        # Card background
        card_col = CARD_DEAD if is_dead else CARD_BG
        draw.rounded_rectangle([cx, cy, cx + CARD_W, cy + CARD_H], radius=8, fill=card_col)

        # Left accent stripe
        stripe = ACCENT_DEAD if is_dead else ACCENT
        draw.rounded_rectangle([cx, cy, cx + 3, cy + CARD_H], radius=2, fill=stripe)

        # Player name (bold, centered top)
        bb = draw.textbbox((0, 0), player, font=f_player)
        tw = bb[2] - bb[0]
        draw.text((cx + CARD_W // 2 - tw // 2, cy + 6), player, font=f_player, fill=WHITE)

        # Sprite — greyscale if dead
        s = sprite.resize((SPRITE_SIZE, SPRITE_SIZE), Image.LANCZOS)
        if is_dead:
            s = s.convert("LA").convert("RGBA")
        sx, sy = cx + PAD, cy + 24
        canvas.paste(s, (sx, sy), s)

        # Skull overlay if dead
        if is_dead:
            draw.text((cx + CARD_W - 18, cy + 8), "☠", font=f_player, fill=RED)

        # Pokémon name (muted, centered below sprite)
        display_name = evo_line[-1].title() if evo_line else "—"
        name_color   = RED if is_dead else MUTED
        bb2 = draw.textbbox((0, 0), display_name, font=f_poke)
        pw  = bb2[2] - bb2[0]
        draw.text((cx + CARD_W // 2 - pw // 2, sy + SPRITE_SIZE + 4), display_name, font=f_poke, fill=name_color)

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    buf.seek(0)
    return buf