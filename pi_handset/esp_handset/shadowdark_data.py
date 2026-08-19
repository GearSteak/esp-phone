"""Static Shadowdark tables extracted from the V4.9 core book (personal use)."""
from __future__ import annotations

import json
from pathlib import Path

_DATA = Path(__file__).resolve().parent / "data" / "shadowdark"

STATS = ("STR", "DEX", "CON", "INT", "WIS", "CHA")
ANCESTRY = ("Human", "Elf", "Dwarf", "Halfling", "Half-orc", "Goblin")
KLASS = ("Fighter", "Priest", "Thief", "Wizard")
ALIGN = ("Lawful", "Neutral", "Chaotic")

# XP to reach this level from previous (0-level → 1st = 10)
XP_NEXT = {0: 10, 1: 20, 2: 30, 3: 40, 4: 50, 5: 60, 6: 70, 7: 80, 8: 90, 9: 100}

RULES = [
    (
        "Checks",
        "Easy DC 9 · Normal 12 · Hard 15 · Extreme 18. Roll 1d20 + stat mod. "
        "Advantage = 2d20 keep high. Disadvantage = 2d20 keep low.",
    ),
    (
        "Combat",
        "Initiative each round. Attack: 1d20 + STR (melee) or DEX (ranged) vs AC. "
        "Natural 20 = critical (double damage dice). Natural 1 = miss + mishap risk.",
    ),
    (
        "Dying",
        "0 HP: death timer 1d4 + CON mod rounds (min 1). Each turn roll d20; 20 = 1 HP. "
        "Stabilize: close, DC 15 INT. Success = unconscious, not dying.",
    ),
    (
        "Magic",
        "Casting is an action. Wizard: 1d20+INT vs DC 10+tier. Priest: 1d20+WIS vs DC 10+tier. "
        "Fail = can't cast that spell until rest. Nat 1 wizard = mishap. Focus: recast check each turn.",
    ),
    (
        "Light",
        "Need light or total darkness (disadvantage + extra encounters). "
        "Torch: near light, 1 hour real time. Lantern: double near, 1 hour of oil. "
        "Second light rides the current timer, or snuff old and start fresh.",
    ),
    (
        "Distance",
        "Close 5' · Near 30' · Far = in sight. Climb half speed (STR/DEX); fail by 5+ = fall. "
        "Fall 1d6 / 10'. Swim half speed. Gear slots = STR (min 10).",
    ),
    (
        "Morale",
        "Enemies at half numbers (or a solo at half HP) flee on a failed DC 15 WIS. "
        "Large groups: one check using the leader.",
    ),
    (
        "XP",
        "Treasure grants XP. 0-level needs 10 XP for 1st. Then 10 × the level you are entering. "
        "Wandering monsters only 50% treasure.",
    ),
]

ARMOR = [
    {"name": "Leather", "cost": "10 gp", "slots": 1, "ac": "11+DEX", "notes": ""},
    {"name": "Chainmail", "cost": "60 gp", "slots": 2, "ac": "13+DEX", "notes": "Disadv stealth, swim"},
    {"name": "Plate", "cost": "130 gp", "slots": 3, "ac": "15", "notes": "No swim, disadv stealth"},
    {"name": "Shield", "cost": "10 gp", "slots": 1, "ac": "+2", "notes": "One hand"},
    {"name": "Mithral", "cost": "x4", "slots": "-1", "ac": "—", "notes": "No stealth/swim penalty"},
]

WEAPONS = [
    {"name": "Bastard sword", "cost": "10 gp", "dmg": "1d8/1d10", "notes": "V, 2 slots"},
    {"name": "Club", "cost": "5 cp", "dmg": "1d4", "notes": ""},
    {"name": "Crossbow", "cost": "8 gp", "dmg": "1d6", "notes": "2H, L, far"},
    {"name": "Dagger", "cost": "1 gp", "dmg": "1d4", "notes": "F, thrown near"},
    {"name": "Greataxe", "cost": "10 gp", "dmg": "1d8/1d10", "notes": "V, 2 slots"},
    {"name": "Greatsword", "cost": "12 gp", "dmg": "1d12", "notes": "2H, 2 slots"},
    {"name": "Javelin", "cost": "5 sp", "dmg": "1d4", "notes": "Thrown far"},
    {"name": "Longbow", "cost": "8 gp", "dmg": "1d8", "notes": "2H, far"},
    {"name": "Longsword", "cost": "9 gp", "dmg": "1d8", "notes": ""},
    {"name": "Mace", "cost": "5 gp", "dmg": "1d6", "notes": ""},
    {"name": "Shortbow", "cost": "6 gp", "dmg": "1d4", "notes": "2H, far"},
    {"name": "Shortsword", "cost": "7 gp", "dmg": "1d6", "notes": ""},
    {"name": "Spear", "cost": "5 sp", "dmg": "1d6", "notes": "Thrown near"},
    {"name": "Staff", "cost": "5 sp", "dmg": "1d4", "notes": "2H"},
    {"name": "Warhammer", "cost": "10 gp", "dmg": "1d10", "notes": "2H"},
]

GEAR = [
    {"name": "Arrows (20)", "cost": "1 gp", "slots": "1"},
    {"name": "Backpack", "cost": "2 gp", "slots": "0 first"},
    {"name": "Caltrops", "cost": "5 sp", "slots": "1"},
    {"name": "Crowbar", "cost": "5 sp", "slots": "1"},
    {"name": "Flint and steel", "cost": "5 sp", "slots": "1"},
    {"name": "Grappling hook", "cost": "1 gp", "slots": "1"},
    {"name": "Iron spikes (10)", "cost": "1 gp", "slots": "1"},
    {"name": "Lantern", "cost": "5 gp", "slots": "1"},
    {"name": "Oil flask", "cost": "5 sp", "slots": "1"},
    {"name": "Rations (3)", "cost": "5 sp", "slots": "1"},
    {"name": "Rope 60'", "cost": "1 gp", "slots": "1"},
    {"name": "Torch", "cost": "5 sp", "slots": "1"},
    {"name": "Crawling kit", "cost": "7 gp", "slots": "7"},
]

NAMES = {
    "Dwarf": "Hilde Torbin Marga Bruno Karina Naugrim Brenna Darvin Elga Alric Isolde Gendry Bruga Junnor Vidrid Torson Brielle Ulfgar Sarna Grimm".split(),
    "Elf": "Eliara Ryarn Sariel Tirolas Galira Varos Daeniel Axidor Hiralia Cyrwin Lothiel Zaphiel Nayra Ithior Amriel Elyon Jirwyn Natinel Fiora Ruhiel".split(),
    "Goblin": "Iggs Tark Nix Lenk Roke Fitz Tila Riggs Prim Zeb Finn Borg Yark Deeg Nibs Brak Fink Rizzo Squib Grix".split(),
    "Halfling": "Willow Benny Annie Tucker Marie Hobb Cora Gordie Rose Ardo Alma Norbert Jennie Barvin Tilly Pike Lydia Marlow Astrid Jasper".split(),
    "Half-orc": "Vara Gralk Ranna Korv Zasha Hrogar Klara Tragan Brolga Drago Yelena Krull Ulara Tulk Shiraal Wulf Ivara Hirok Aja Zoraan".split(),
    "Human": "Zali Bram Clara Nattias Rina Denton Mirena Aran Morgan Giralt Tamra Oscar Ishana Rogar Jasmin Tarin Yuri Malchor Lienna Godfrey".split(),
}

NPC_LOOK = "Balding;Stocky;Very tall;Beauty mark;One eye;Braided hair;Muscular;White hair;Scar;Willowy;Sweaty;Cleft chin;Frail;Big eyebrows;Tattooed;Floppy hat;Gold tooth;Six fingers;Very short;Large nose".split(";")
NPC_DOES = "Spits;Always eating;Moves quickly;Card tricks;Prays aloud;Writes in diary;Apologetic;Slaps backs;Drops things;Swears oaths;Makes puns;Rare accent;Easily spooked;Forgetful;Speaks quietly;Twitches;Moves slowly;Speaks loudly;Swaggers;Smokes pipe".split(";")
NPC_SECRET = "Hiding a fugitive;Adores baby animals;Obsessed with fire;In a religious cult;Is a half-demon;Was a wizard's apprentice;Needlessly picks pockets;Has a false identity;Afraid of storms;Has functional gills;In deep gambling debt;Works as a smuggler;Is a werewolf;Can smell lies;Cast out of wealthy family;In love with a bartender;Left the Thieves' Guild;Best friends with a prince;Retired crawler;Has a pet basilisk".split(";")
NPC_JOB = "Gravedigger Carpenter Scholar Blacksmith Tax-collector Farmer Bartender Beggar Baker Cook Sailor Butcher Locksmith Cobbler Friar Merchant".split()

ADVENTURE_1 = "Rescue Find Destroy Infiltrate Bypass Return Defeat Spy Bribe Deliver Escape Imprison Stop Befriend Pacify Persuade Steal Escort Banish Free".split()
ADVENTURE_2 = "Goblet Prisoner Sword Vault Cult Spirit Killer Demon Noble Hunter Hostage Thief Spy Werewolf Relic High-priest Merchant Witch Ritual Vampire".split()
ADVENTURE_3 = [
    "Of the evil wizard",
    "Stalking the wastes",
    "At the bottom of the river",
    "In the city sewers",
    "Under the barrow mounds",
    "Of the fallen hero",
    "In the magical library",
    "In the king's court",
    "Of the ancient lineage",
    "In the sorcerer's tower",
    "In the Murkwood",
    "Hiding in the slums",
    "Of the Dwarven lord",
    "In the musty tomb",
    "Of the royal knights",
    "Sacrificing innocents",
    "In the catacombs",
    "Blackmailing the baron",
    "In the Thieves' Guild",
    "Murdering townsfolk",
]

SITE = [
    "Mines of the Cursed Flame",
    "Abbey of the Whispering Ghost",
    "Tower of the Bleeding Darkness",
    "Caves of the Shrouded Peak",
    "Barrow of the Lost Borderlands",
    "Warrens of the Dead King",
    "Crypt of the Deepwood Twilight",
    "Monastery of the Fallen Depths",
    "Ruin of the Revenant Jewel",
    "Tunnels of the Frozen God",
    "Citadel of the Shimmering Lands",
    "Tomb of the Chaos Storm",
    "Castle of the Abandoned Swamp",
    "Temple of the Blighted Ravine",
    "Fortress of the Forgotten Valley",
    "Isle of the Slumbering Horde",
    "Keep of the Savage Skull",
    "Dungeon of the Unholy Queen",
    "Necropolis of the Enchanted Wastes",
    "Shrine of the Immortal Hero",
]

# Treasure 0-3 (d100). Tuples are (max inclusive, item).
LOOT_0_3 = [
    (1, "Bent tin fork (1 cp)"),
    (3, "Muddy torch (2 cp)"),
    (5, "Bag of smooth pebbles (2 cp)"),
    (7, "10 cp in a greasy pouch"),
    (9, "Rusty lantern with shattered glass (1 gp)"),
    (11, "Silver tooth (1 gp)"),
    (13, "Dull dagger (1 gp)"),
    (15, "Two empty glass vials (6 gp)"),
    (17, "60 sp in a rotten boot"),
    (19, "Cracked handheld mirror (8 gp)"),
    (21, "Chipped greataxe (9 gp)"),
    (23, "10 gp in a moldy wood box"),
    (25, "Chip of an emerald (10 gp)"),
    (27, "Longbow and 40 arrows (10 gp)"),
    (29, "Dusty black leather armor (10 gp)"),
    (31, "Scuffed heavy shield (10 gp)"),
    (33, "Simple bastard sword (10 gp)"),
    (35, "12 gp in a ripped cloak"),
    (37, "Wavy-bladed greatsword (12 gp)"),
    (39, "Pair of elf-forged shortswords (14 gp)"),
    (41, "Golden bowl (15 gp)"),
    (43, "Obsidian statuette of Shune the Vile (15 gp)"),
    (45, "Undersized pearl (20 gp)"),
    (47, "Jade-and-gold scarab pin (20 gp)"),
    (53, "Mithral locket with a painting (20 gp)"),
    (55, "Two dwarven shields (20 gp)"),
    (57, "Pair of silvered daggers"),
    (59, "Copper-and-gold mead tankard (20 gp)"),
    (61, "Five red dragon scales"),
    (63, "Spidersilk cloak (25 gp)"),
    (65, "Ivory game pieces (25 gp)"),
    (67, "Half-finished chainmail (30 gp)"),
    (69, "Trio of warhammers"),
    (71, "Sapphire fragment (30 gp)"),
    (73, "Silk slippers and robe (35 gp)"),
    (75, "Silver-and-gold circlet (40 gp)"),
    (77, "Polished pearl (40 gp)"),
    (79, "Mithral dragon shield (40 gp)"),
    (81, "Gold monkey idol (60 gp)"),
    (83, "Fine chainmail (60 gp)"),
    (85, "Cracked emerald (60 gp)"),
    (87, "Two lustrous pearls"),
    (89, "1st-tier spell scroll (80 gp)"),
    (91, "Potion of Invisibility (80 gp)"),
    (93, "Magic wand, 2nd-tier (100 gp)"),
    (95, "Egg of The Cockatrice (100 gp)"),
    (97, "+1 armor (benefit, curse) (150 gp)"),
    (99, "Bag of Holding (150 gp)"),
    (100, "+1 magic weapon (200 gp)"),
]

CAVE_ENC = [
    "Dripping silence — nothing yet",
    "2d4 giant bats",
    "A collapsed tunnel (climb or dig)",
    "1d6 goblin scouts",
    "Carrion crawler",
    "Faint singing from deeper in",
    "1d4 skeletons on patrol",
    "Gelatinous cube (narrow hall)",
    "Kobold trap-makers at work",
    "Lost miner, dying",
    "Ochre jelly",
    "1d8 stirges",
    "Cave-in — DEX or 1d6",
    "Sleeping ogre",
    "Cultists of a buried god",
    "Black pudding smear on the walls",
    "1d6 bandits hiding loot",
    "Rust monster",
    "Ghost of a crawler",
    "Dragon's distant rumble",
]


def load_spells() -> list:
    path = _DATA / "spells.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return list(data) if isinstance(data, list) else []
    except Exception:
        return []


def book_candidates() -> list:
    from esp_handset import store as st

    st.ensure()
    found = []
    for folder in (st.BOOKS, st.DATA / "shadowdark", Path.home() / "Documents"):
        try:
            if not folder.is_dir():
                continue
            for p in sorted(folder.glob("*")):
                n = p.name.lower()
                if p.suffix.lower() == ".pdf" and "shadow" in n:
                    found.append(p)
                elif p.suffix.lower() in (".pdf", ".txt") and "shadowdark" in n:
                    found.append(p)
        except OSError:
            continue
    return found
