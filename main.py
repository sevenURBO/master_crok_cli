import json
import random
import time
import os
import builtins
import unicodedata

# --- GLOBAL EVENT DELAY ---
EVENT_DELAY_SECONDS = 3
IN_ROUND = False
DELAY_ACTIVE = False
ABILITY_SEQ = 0
_GROUP_EMOJI_CACHE = None
PASSIVE_DELAYED_CODES = {"buff_power_if_more_intelligent", "buff_per_opponent", "force_attack_next_turn_def_buff"}

def _event_print(*args, **kwargs):
    builtins.print(*args, **kwargs)
    # No per-line delay; delays are handled between blocks.

def _set_delay_active(active: bool):
    global DELAY_ACTIVE
    DELAY_ACTIVE = bool(active)

def _block_pause():
    if IN_ROUND and DELAY_ACTIVE:
        time.sleep(EVENT_DELAY_SECONDS)

def _next_ability_seq():
    global ABILITY_SEQ
    ABILITY_SEQ += 1
    return ABILITY_SEQ

def print_block_header(title, width=72):
    text = f" {title} "
    if len(text) >= width:
        print(f"\n{text.strip()}")
        return
    left = (width - len(text)) // 2
    right = width - len(text) - left
    print("\n" + ("=" * left) + text + ("=" * right))

def choose_stat_human(prompt_text="Típus: "):
    while True:
        choice = input(prompt_text).strip()
        if choice == "1":
            return "erő"
        if choice == "2":
            return "intelligencia"
        if choice == "3":
            return "reflex"
        print("Hibás érték. Csak 1, 2 vagy 3 adható meg.")

def choose_int_in_range(prompt_text, min_val, max_val):
    while True:
        try:
            val = int(input(prompt_text))
        except Exception:
            print("Hibás érték. Csak számot adj meg.")
            continue
        if min_val <= val <= max_val:
            return val
        print(f"Hibás érték. Csak {min_val} és {max_val} közötti szám adható meg.")

def get_ability_label(card):
    return card.ability_name or card.ability_code or "képesség"

def get_ability_prefix(card):
    try:
        grp = normalize_group(getattr(card, 'group', None))
    except Exception:
        grp = None
    if grp == "master":
        return ""
    emoji = get_group_emoji(grp) if grp else ""
    if emoji:
        return f"{emoji}\u2009" if grp == "yinyang" else emoji
    return "⚡"

def ability_effect(player, card, msg):
    label = get_ability_label(card)
    prefix = get_ability_prefix(card)
    if isinstance(msg, str) and msg:
        msg = msg[0].upper() + msg[1:]
    prefix_display = prefix if prefix else "  "
    print(f"{prefix_display} {player.name} – {card.name} ({label}): {msg}")

def print_scoreboard(score_players):
    name_w = max(7, max(len(p.name) for p in score_players)) + 2
    win_w = max(6, max(len(str(len(p.won_cards))) for p in score_players)) + 4
    deck_w = 7
    hand_w = 5
    won_w = max(10, len("Nyertes") + 4)
    lost_w = max(10, len("Vesztes") + 4)
    total_w = name_w + win_w + deck_w + hand_w + won_w + lost_w + 7  # separators
    target_w = 72
    if total_w < target_w:
        name_w += (target_w - total_w)
        total_w = target_w
    sep = "+" + "+".join([
        "-" * name_w,
        "-" * win_w,
        "-" * deck_w,
        "-" * hand_w,
        "-" * won_w,
        "-" * lost_w,
    ]) + "+"
    title = "PONTÁLLÁS + LAPMÉRLEGEK"
    title_line = "|" + title.center(total_w - 2) + "|"
    header = "|" + "Név".center(name_w) + "|" + "Győzelem".center(win_w) + "|" + "Pakli".center(deck_w) + "|" + "Kéz".center(hand_w) + "|" + "Nyertes".center(won_w) + "|" + "Vesztes".center(lost_w) + "|"
    print(sep)
    print(title_line)
    print(sep)
    print(header)
    print(sep)
    for p in score_players:
        print(
            "|" + p.name.center(name_w) +
            "|" + str(len(p.won_cards)).center(win_w) +
            "|" + str(len(p.deck)).center(deck_w) +
            "|" + str(len(p.hand)).center(hand_w) +
            "|" + str(len(p.won_cards)).center(won_w) +
            "|" + str(len(p.lost_cards)).center(lost_w) +
            "|"
        )
    print(sep)

def get_card_owner(card, battle_context, fallback_player):
    if battle_context:
        if battle_context.get('attacker_card') is card:
            players_for_battle = battle_context.get('players_for_battle') or []
            attacker_index = battle_context.get('attacker_index', 0)
            if 0 <= attacker_index < len(players_for_battle):
                return players_for_battle[attacker_index]
        for idx, dc in (battle_context.get('defender_cards') or {}).items():
            if dc is card:
                players_for_battle = battle_context.get('players_for_battle') or []
                if 0 <= idx < len(players_for_battle):
                    return players_for_battle[idx]
    return fallback_player

def apply_army_swap_bonus(battle_context, fallback_player):
    if not battle_context:
        return
    participants = []
    if battle_context.get('attacker_card'):
        participants.append(battle_context['attacker_card'])
    defender_cards = battle_context.get('defender_cards') or {}
    participants.extend(list(defender_cards.values()))
    for pcard in participants:
        if pcard and getattr(pcard, 'ability_code', None) == 'buff_per_opponent':
            # Track swap-based extra opponents only if Army hasn't activated yet
            if not getattr(pcard, 'ability_used', False):
                pcard._army_pending_swaps = getattr(pcard, '_army_pending_swaps', 0) + 1

# Override print to add delay after each event output
print = _event_print


def normalize_group(gstr):
    # Normalize group names coming from JSON (remove emoji/prefixes and extra spaces)
    if not isinstance(gstr, str):
        return gstr
    parts = gstr.strip().split()
    if not parts:
        return ""
    # Assume the meaningful group name is the last token (e.g. '🐐 master' -> 'master')
    return parts[-1].lower()

def get_base_stat(card, stat_key):
    """Return base stat, respecting any temporary overrides."""
    if card is None:
        return 0
    overrides = getattr(card, 'tmp_stat_overrides', None)
    if isinstance(overrides, dict) and stat_key in overrides:
        return overrides[stat_key]
    return card.stats.get(stat_key, 0)

# --- 1. ADATSTRUKTÚRA ---
class Card:
    def __init__(self, name, group, power, intelligence, reflex, card_id=None):
        self.name = name
        self.group = group
        self.card_id = card_id
        self.stats = {
            "erő": power,
            "intelligencia": intelligence,
            "reflex": reflex
        }
        self.ability_code = "none"
        self.ability_type = "passive"
        self.ability_used = False
        self.ability_reserved = False  # True if reserved for later use in this battle
        self.ability_permanently_skipped = False  # True if player decided not to use
        self.ability_name = None
        self.ability_text = None
        self.tmp_original_ability_code = None
        self.tmp_original_ability_type = None
        self.tmp_original_ability_name = None
        self.tmp_original_ability_text = None
        # Temporary per-battle bonuses to show buffs without mutating base stats
        self.tmp_bonuses = {"erő": 0, "intelligencia": 0, "reflex": 0}
        # Temporary per-battle stat overrides (e.g., Karate Crok strength replacement)
        self.tmp_stat_overrides = {}

    def __str__(self):
        ability_part = ""
        name = getattr(self, 'ability_name', None)
        text = getattr(self, 'ability_text', None)
        code = getattr(self, 'ability_code', None)
        if name and text:
            ability_part = f"  - {name}: {text}"
        elif name:
            ability_part = f"  - {name}"
        elif text:
            ability_part = f"  - {text}"
        elif code and code != 'none':
            ability_part = f"  - {code}"
        # Show buffs as +X next to base values when present
        e_base = get_base_stat(self, 'erő')
        i_base = get_base_stat(self, 'intelligencia')
        r_base = get_base_stat(self, 'reflex')
        e_buff = self.tmp_bonuses.get('erő', 0)
        i_buff = self.tmp_bonuses.get('intelligencia', 0)
        r_buff = self.tmp_bonuses.get('reflex', 0)
        e_part = f"{e_base}"
        i_part = f"{i_base}"
        r_part = f"{r_base}"
        # Show buffs as base(+bonus) when positive
        if e_buff:
            e_part = f"{e_base}(+{e_buff})"
        if i_buff:
            i_part = f"{i_base}(+{i_buff})"
        if r_buff:
            r_part = f"{r_base}(+{r_buff})"
        # Group display (with emoji)
        if getattr(self, 'group', None):
            group_normalized = normalize_group(self.group)
            grp = format_group_label(group_normalized) or self.group.capitalize()
            grp_part = f" ({grp})"
        else:
            grp_part = ''
        return f"{self.name}{grp_part}  [E:{e_part} I:{i_part} R:{r_part}]" + ability_part
    
    def copy(self):
        new_card = Card(
            self.name,
            self.group,
            self.stats['erő'],
            self.stats['intelligencia'],
            self.stats['reflex'],
            self.card_id
        )
        new_card.ability_code = self.ability_code
        new_card.ability_type = self.ability_type
        new_card.ability_name = self.ability_name
        new_card.ability_text = self.ability_text
        new_card.ability_used = False
        new_card.ability_reserved = False
        new_card.ability_permanently_skipped = False
        new_card.tmp_original_ability_code = None
        new_card.tmp_original_ability_type = None
        new_card.tmp_original_ability_name = None
        new_card.tmp_original_ability_text = None
        new_card.tmp_bonuses = {"erő": 0, "intelligencia": 0, "reflex": 0}
        new_card.tmp_stat_overrides = {}
        return new_card


# --- 2. JÁTÉKOS OSZTÁLY ---
class Player:
    def __init__(self, name, is_bot=False):
        self.name = name
        self.is_bot = is_bot
        self.deck = []
        self.hand = []
        self.won_cards = []
        self.lost_cards = []
        self.group_victories = {}
        # Cave Crok selection (per battle)
        self.cave_crok_target = None
        # Flags for some abilities that affect next turns/battles
        self.force_blind_next = False
        self.force_blind_seq = 0
        self.next_turn_buff_all_1 = False
        self.force_attack_next = False
        self.force_attack_seq = 0

    def draw_card(self):
        if len(self.deck) > 0:
            card = self.deck.pop(0)
            self.hand.append(card)
            return True
        return False

    def play_card(self, index):
        if 0 <= index < len(self.hand):
            return self.hand.pop(index)
        return None

    def get_blind_card(self):
        if len(self.deck) > 0:
            return self.deck.pop(0)
        elif len(self.hand) > 0:
            return self.hand.pop(random.randint(0, len(self.hand)-1))
        return None

    def add_won_card(self, card):
        self.won_cards.append(card)
        # Group victory calculation is handled in get_group_victories()

    def get_group_victories(self):
        """
        Returns number of distinct groups won (Master Crok does not count).
        """
        base_groups = set()
        for card in self.won_cards:
            key = normalize_group(card.group)
            if not key or key == "master":
                continue
            base_groups.add(key)
        return len(base_groups)

    def get_group_counts(self):
        group_counts = {}
        for card in self.won_cards:
            key = normalize_group(card.group)
            if not key or key == "master":
                continue
            group_counts[key] = group_counts.get(key, 0) + 1
        return group_counts

    def reset_abilities_for_battle(self):
        for card in self.hand:
            card.ability_used = False
            card.ability_reserved = False
            card.ability_permanently_skipped = False
        for card in self.deck:
            card.ability_used = False
            card.ability_reserved = False
            card.ability_permanently_skipped = False
        for card in self.won_cards:
            card.ability_used = False
            card.ability_reserved = False
            card.ability_permanently_skipped = False
        for card in self.lost_cards:
            card.ability_used = False
            card.ability_reserved = False
            card.ability_permanently_skipped = False
        for pile in (self.hand, self.deck, self.won_cards, self.lost_cards):
            for card in pile:
                if getattr(card, 'tmp_original_ability_code', None):
                    card.ability_code = card.tmp_original_ability_code
                    card.tmp_original_ability_code = None
                if getattr(card, 'tmp_original_ability_type', None):
                    card.ability_type = card.tmp_original_ability_type
                    card.tmp_original_ability_type = None
                if getattr(card, 'tmp_original_ability_name', None) is not None:
                    card.ability_name = card.tmp_original_ability_name
                    card.tmp_original_ability_name = None
                if getattr(card, 'tmp_original_ability_text', None) is not None:
                    card.ability_text = card.tmp_original_ability_text
                    card.tmp_original_ability_text = None
                card.ability_used = False
                # reset temporary buffs
                if getattr(card, 'tmp_bonuses', None) is not None:
                    card.tmp_bonuses = {"erő": 0, "intelligencia": 0, "reflex": 0}
                # reset temporary stat overrides
                if getattr(card, 'tmp_stat_overrides', None) is not None:
                    card.tmp_stat_overrides = {}
                # reset temporary flags
                if hasattr(card, '_win_on_draw'):
                    delattr(card, '_win_on_draw')
                if hasattr(card, '_instant_win'):
                    delattr(card, '_instant_win')
                if hasattr(card, '_boy_def_buff_applied'):
                    delattr(card, '_boy_def_buff_applied')
                if hasattr(card, '_abilities_disabled_in_battle'):
                    delattr(card, '_abilities_disabled_in_battle')
                if hasattr(card, '_priest_pending_draw'):
                    delattr(card, '_priest_pending_draw')
                if hasattr(card, '_entered_battle_via_swap'):
                    delattr(card, '_entered_battle_via_swap')
                if hasattr(card, '_army_pending_swaps'):
                    delattr(card, '_army_pending_swaps')
                if hasattr(card, '_army_applied_base'):
                    delattr(card, '_army_applied_base')
                if hasattr(card, '_army_applied_swaps'):
                    delattr(card, '_army_applied_swaps')
                if hasattr(card, '_army_recalc_needed'):
                    delattr(card, '_army_recalc_needed')
                # restore any temporary hand display additions
                if hasattr(card, '_hand_display_added'):
                    try:
                        added = getattr(card, '_hand_display_added')
                        for k, v in added.items():
                            card.tmp_bonuses[k] = card.tmp_bonuses.get(k, 0) - v
                    except Exception:
                        pass
                    delattr(card, '_hand_display_added')
                if hasattr(card, '_hand_display_applied'):
                    delattr(card, '_hand_display_applied')
            # Reset Cave Crok target selection for this battle
            self.cave_crok_target = None
    
# --- 3. BETÖLTÉS ÉS ELŐKÉSZÍTÉS ---
def load_cards_from_file():
    # Megkeressük a script (master_crok.py) pontos helyét a gépen:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Összerakjuk az útvonalat: mappa + cards.json
    file_path = os.path.join(script_dir, 'cards.json')

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            cards_list = []
            for item in data:
                new_card = Card(
                    item['name'], 
                    item.get('group', ''), 
                    item['stats']['erő'], 
                    item['stats']['intelligencia'], 
                    item['stats']['reflex'],
                    item.get('id')
                )
                if 'ability' in item:
                    new_card.ability_code = item['ability']['code']
                    new_card.ability_type = item['ability'].get('type', 'passive')
                    # Load human-readable ability fields
                    new_card.ability_name = item['ability'].get('name')
                    new_card.ability_text = item['ability'].get('text')
                
                cards_list.append(new_card)
            return cards_list
            
    except FileNotFoundError:
        print("\n!!! HIBA !!!")
        print(f"Nem találom a fájlt ezen az útvonalon:\n{file_path}")
        print("Ellenőrizd, hogy a 'cards.json' és a 'master_crok.py' EGY MAPPÁBAN vannak-e!")
        return []
    except json.JSONDecodeError:
        print("HIBA: A cards.json fájl formátuma rossz (valahol hiányzik egy vessző vagy zárójel).")
        return []

def get_group_emoji(group_name):
    """Return emoji for a normalized group name"""
    if isinstance(group_name, str) and group_name.lower() == "master":
        return ""
    global _GROUP_EMOJI_CACHE
    if _GROUP_EMOJI_CACHE is None:
        _GROUP_EMOJI_CACHE = {}
        try:
            for c in load_cards_from_file():
                raw = getattr(c, 'group', '')
                if isinstance(raw, str):
                    parts = raw.strip().split()
                    if len(parts) >= 2:
                        emoji = parts[0]
                        key = normalize_group(raw)
                        # Accept if emoji token is non-alphanumeric
                        if any(not ch.isalnum() for ch in emoji):
                            _GROUP_EMOJI_CACHE[key] = emoji
        except Exception:
            _GROUP_EMOJI_CACHE = {}

    if isinstance(group_name, str):
        cached = _GROUP_EMOJI_CACHE.get(group_name.lower())
        if cached:
            return cached
    emoji_map = {
        "pistol": "🔫",
        "hell": "🔥",
        "yinyang": "\u262F\uFE0F",
        "holy": "👼",
        "adventurer": "🧭",
        "soldier": "🔪",
        "martial": "🏆",
        "lightning": "⚡",
        "jolly": "🌼",
        "western": "⭐"
    }
    return emoji_map.get(group_name.lower(), "")

def format_group_label(group_key: str) -> str:
    if not group_key:
        return ""
    emoji = get_group_emoji(group_key)
    name = group_key.capitalize()
    if not emoji:
        return f"   {name}"
    gap = "  " if group_key == "yinyang" else " "
    return f"{emoji}{gap}{name}"

def get_all_groups():
    """Get all unique groups from the cards file"""
    unique_cards = load_cards_from_file()
    # Return normalized group keys (exclude master key)
    return set(
        g for g in (normalize_group(card.group) for card in unique_cards)
        if g and g != "master"
    )

def get_turn_order(players, attacker_index):
    """Return players ordered clockwise starting from the attacker."""
    if not players:
        return []
    idx = attacker_index % len(players)
    return players[idx:] + players[:idx]


def apply_hand_display_bonuses(player, players_list, is_defending=False):
    """Apply temporary display-only bonuses to cards in a player's hand.
    Adds to card.tmp_bonuses and records added amounts on the card so they can be restored later.
    Returns list of cards modified.
    """
    applied = []
    for card in player.hand:
        if getattr(card, '_hand_display_applied', False):
            continue
        added = {"erő":0, "intelligencia":0, "reflex":0}
        # Sensei Crok: show +1 on all stats for the next battle (display-only)
        if getattr(player, 'next_turn_buff_all_1', False):
            for k in added.keys():
                added[k] += 1
        # Army Crok: DO NOT show passive in hand (will apply only when placed)
        if any(v != 0 for v in added.values()):
            # Apply added values and remember them for later restoration
            for k, v in added.items():
                card.tmp_bonuses[k] = card.tmp_bonuses.get(k, 0) + v
            card._hand_display_added = added
            card._hand_display_applied = True
            applied.append(card)
    return applied


def restore_hand_display_bonuses(player):
    """Restore any display-only bonuses applied to the player's hand."""
    for card in list(player.hand):
        if getattr(card, '_hand_display_added', None):
            try:
                added = getattr(card, '_hand_display_added')
                for k, v in added.items():
                    card.tmp_bonuses[k] = card.tmp_bonuses.get(k, 0) - v
            except Exception:
                pass
            try:
                delattr(card, '_hand_display_added')
            except Exception:
                pass
        if getattr(card, '_hand_display_applied', False):
            try:
                delattr(card, '_hand_display_applied')
            except Exception:
                pass

def remove_hand_display_bonus(card):
    """Remove display-only bonuses from a single card if they were applied."""
    if not card:
        return
    if getattr(card, '_hand_display_added', None):
        try:
            added = getattr(card, '_hand_display_added')
            for k, v in added.items():
                card.tmp_bonuses[k] = card.tmp_bonuses.get(k, 0) - v
        except Exception:
            pass
        try:
            delattr(card, '_hand_display_added')
        except Exception:
            pass
    if getattr(card, '_hand_display_applied', False):
        try:
            delattr(card, '_hand_display_applied')
        except Exception:
            pass

def choose_blind_card_for_player(player, is_human_player=False):
    if player.deck:
        return player.deck.pop(0)
    if not player.hand:
        return None
    if not is_human_player:
        return player.hand.pop(random.randint(0, len(player.hand) - 1))
    print(f"{player.name}, a pakli üres. Válassz egy lapot a kezedből a vakharcra:")
    for i, c in enumerate(player.hand, 1):
        print(f"{i}. {c}")
    sel = choose_int_in_range("Válassz (szám): ", 1, len(player.hand))
    return player.hand.pop(sel - 1)

def choose_cave_crok_target(player, candidates, is_human_player=False, announce=False):
    """Select which opponent's wins to use for Cave Crok in multiplayer."""
    if not candidates:
        return None
    # Normalize candidates list (unique, keep order)
    unique_candidates = []
    for c in candidates:
        if c is not None and c not in unique_candidates and c is not player:
            unique_candidates.append(c)
    if not unique_candidates:
        return None
    # Only opponents with more won cards are valid for Cave Crok's catch-up (human choice)
    eligible_candidates = [p for p in unique_candidates if len(p.won_cards) > len(player.won_cards)]
    if not is_human_player:
        # Bot: always compare to the opponent with the most wins
        target = max(unique_candidates, key=lambda p: len(p.won_cards))
        if len(target.won_cards) <= len(player.won_cards):
            return None
        return target
    if not eligible_candidates:
        return None
    # If already selected for this battle and still valid, reuse it
    if getattr(player, 'cave_crok_target', None) in eligible_candidates:
        return player.cave_crok_target
    cave_prefix = f"{get_group_emoji('lightning') or '⚡'} "
    print(f"\n{cave_prefix}Dühöngés: Válaszd ki, melyik ellenfél nyerteseit vegyük figyelembe:")
    print(f"Saját nyertes lapok: {len(player.won_cards)}")
    for i, p in enumerate(eligible_candidates, 1):
        print(f"{i}. {p.name} - nyertes lapok: {len(p.won_cards)}")
    sel = choose_int_in_range("Válassz (szám): ", 1, len(eligible_candidates))
    target = eligible_candidates[sel-1]
    player.cave_crok_target = target
    return target

def format_hand_display(hand):
    """
    Format a list of cards for display in a nicely aligned, columnar format.
    Returns a list of formatted strings (one per card with index).
    """
    if not hand:
        return []
    
    # Pre-process all cards to extract components
    card_data = []
    for idx, card in enumerate(hand, 1):
        # Name
        name = card.name
        
        # Group (with emoji)
        if hasattr(card, 'group') and card.group:
            group_normalized = normalize_group(card.group)
            grp = format_group_label(group_normalized) or card.group.capitalize()
        else:
            grp = ''
        
        # Stats with buffs
        e_base = get_base_stat(card, 'erő')
        i_base = get_base_stat(card, 'intelligencia')
        r_base = get_base_stat(card, 'reflex')
        e_buff = card.tmp_bonuses.get('erő', 0) if hasattr(card, 'tmp_bonuses') else 0
        i_buff = card.tmp_bonuses.get('intelligencia', 0) if hasattr(card, 'tmp_bonuses') else 0
        r_buff = card.tmp_bonuses.get('reflex', 0) if hasattr(card, 'tmp_bonuses') else 0
        
        e_part = f"{e_base}" if not e_buff else f"{e_base}(+{e_buff})"
        i_part = f"{i_base}" if not i_buff else f"{i_base}(+{i_buff})"
        r_part = f"{r_base}" if not r_buff else f"{r_base}(+{r_buff})"
        
        stats_str = f"E:{e_part} I:{i_part} R:{r_part}"
        
        # Ability
        ability_name = getattr(card, 'ability_name', None)
        ability_text = getattr(card, 'ability_text', None)
        ability_code = getattr(card, 'ability_code', None)
        
        if ability_name and ability_text:
            ability_str = f"{ability_name}: {ability_text}"
        elif ability_name:
            ability_str = ability_name
        elif ability_text:
            ability_str = ability_text
        elif ability_code and ability_code != 'none':
            ability_str = ability_code
        else:
            ability_str = ""
        
        card_data.append({
            'idx': idx,
            'name': name,
            'group': grp,
            'stats': stats_str,
            'ability': ability_str
        })
    
    def _visual_width(text: str) -> int:
        if not text:
            return 0
        width = 0
        for ch in str(text):
            # Ignore combining marks / variation selectors in width
            if unicodedata.combining(ch) or unicodedata.category(ch) in ("Mn", "Me"):
                continue
            # YinYang is rendered narrow in many terminals; treat as width 1
            if ch == "☯":
                width += 1
                continue
            # Treat non-ASCII (emoji) as width 2 for terminal alignment
            width += 1 if ch.isascii() else 2
        return width

    # Calculate max widths for alignment
    max_name_len = max(len(c['name']) for c in card_data)
    max_group_visual = max(_visual_width(c['group']) for c in card_data)
    max_stats_len = max(len(c['stats']) for c in card_data)
    
    # Format each card with aligned columns
    formatted = []
    for c in card_data:
        # Index + Name (left-aligned, padded)
        line = f"{c['idx']:2}. {c['name']:<{max_name_len}}"
        # Group (left-aligned, padded) using visual width to handle emoji
        group_pad = max_group_visual - _visual_width(c['group'])
        line += f" | {c['group']}" + (" " * max(0, group_pad))
        # Stats (left-aligned, padded)
        line += f" | {c['stats']:<{max_stats_len}}"
        # Ability (if present)
        if c['ability']:
            line += f" | {c['ability']}"
        formatted.append(line)
    
    return formatted

def format_battle_display(attacker_name, attacker_card, defender_names_cards, show_ability=True, stat_focus_key=None):
    """Format battle cards (attacker + defenders) aligned like hand display."""
    rows = []
    def _visual_width(text: str) -> int:
        if not text:
            return 0
        width = 0
        for ch in str(text):
            if unicodedata.combining(ch) or unicodedata.category(ch) in ("Mn", "Me", "Cf"):
                continue
            width += 2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1
        return width

    def _pad(text, width):
        text = str(text)
        tw = _visual_width(text)
        if tw >= width:
            return text
        return text + (" " * (width - tw))

    def _pad_center(text, width):
        text = str(text)
        tw = _visual_width(text)
        if tw >= width:
            return text
        pad = width - tw
        left = pad // 2
        right = pad - left
        return (" " * left) + text + (" " * right)

    def _card_parts(card):
        name = card.name
        group_normalized = normalize_group(card.group) if getattr(card, 'group', None) else None
        if group_normalized:
            grp = format_group_label(group_normalized) or card.group.capitalize()
        else:
            grp = card.group.capitalize() if getattr(card, 'group', None) else ""
        e_base = get_base_stat(card, 'erő')
        i_base = get_base_stat(card, 'intelligencia')
        r_base = get_base_stat(card, 'reflex')
        e_buff = card.tmp_bonuses.get('erő', 0) if hasattr(card, 'tmp_bonuses') else 0
        i_buff = card.tmp_bonuses.get('intelligencia', 0) if hasattr(card, 'tmp_bonuses') else 0
        r_buff = card.tmp_bonuses.get('reflex', 0) if hasattr(card, 'tmp_bonuses') else 0
        e_part = f"{e_base}" if not e_buff else f"{e_base}(+{e_buff})"
        i_part = f"{i_base}" if not i_buff else f"{i_base}(+{i_buff})"
        r_part = f"{r_base}" if not r_buff else f"{r_base}(+{r_buff})"
        stats_str = f"E:{e_part} I:{i_part} R:{r_part}"
        focus_str = ""
        if stat_focus_key:
            base = get_base_stat(card, stat_focus_key)
            bonus = card.tmp_bonuses.get(stat_focus_key, 0) if hasattr(card, 'tmp_bonuses') else 0
            total = base + bonus
            focus_label = stat_focus_key.upper()
            if bonus:
                focus_str = f"{focus_label}: {base}+{bonus}={total}"
            else:
                focus_str = f"{focus_label}: {base}"
        ability_str = ""
        if show_ability:
            ability_name = getattr(card, 'ability_name', None)
            ability_text = getattr(card, 'ability_text', None)
            ability_code = getattr(card, 'ability_code', None)
            if ability_name and ability_text:
                ability_str = f"{ability_name}: {ability_text}"
            elif ability_name:
                ability_str = ability_name
            elif ability_text:
                ability_str = ability_text
            elif ability_code and ability_code != 'none':
                ability_str = ability_code
        return name, grp, stats_str, ability_str, focus_str

    # Build row data
    name, grp, stats, ability, focus = _card_parts(attacker_card)
    rows.append({"role": "Támadó", "player": attacker_name, "name": name, "group": grp, "stats": stats, "ability": ability, "focus": focus})
    for player_name, card in defender_names_cards:
        name, grp, stats, ability, focus = _card_parts(card)
        rows.append({"role": "Védő", "player": player_name, "name": name, "group": grp, "stats": stats, "ability": ability, "focus": focus})

    # Column widths
    role_w = max(_visual_width(r["role"]) for r in rows)
    player_w = max(_visual_width(r["player"]) for r in rows)
    name_w = max(_visual_width(r["name"]) for r in rows)
    group_w = max(_visual_width(r["group"]) for r in rows)
    stats_w = max(_visual_width(r["stats"]) for r in rows)
    focus_w = max(_visual_width(r["focus"]) for r in rows) if any(r.get("focus") for r in rows) else 0

    formatted = []
    for r in rows:
        line = (
            f"{_pad(r['role'], role_w)} ({_pad_center(r['player'], player_w)}): "
            f"{_pad(r['name'], name_w)} | { _pad(r['group'], group_w)} | { _pad(r['stats'], stats_w)}"
        )
        if r['ability']:
            line += f" | {r['ability']}"
        if focus_w:
            line += f" | {_pad(r['focus'], focus_w)}"
        formatted.append(line)
    return formatted

def format_values_display(rows):
    """Format value breakdown rows aligned (name, base, bonus, total)."""
    name_w = max(len(r["name"]) for r in rows)
    base_w = max(len(str(r["base"])) for r in rows)
    bonus_w = max(len(str(r["bonus"])) for r in rows)
    total_w = max(len(str(r["total"])) for r in rows)
    formatted = []
    for r in rows:
        formatted.append(
            f"{r['name']^{name_w}}: {str(r['base']):>{base_w}} (alapérték) + {str(r['bonus']):>{bonus_w}} (bónusz) = {str(r['total']):>{total_w}}"
        )
    return formatted

def check_and_trigger_loss_abilities(lost_card, loser_player, *, from_battle=True):
    """
    Check if a card that was lost has abilities that trigger on loss.
    For example, Pancrator Crok's blind_fight_on_loss ability.
    Only triggers for actual battle losses when from_battle=True.
    """
    if not from_battle:
        return
    if getattr(lost_card, '_abilities_disabled_in_battle', False):
        return
    if lost_card.ability_code == "blind_fight_on_loss":
        if getattr(loser_player, '_suppress_force_blind_next', False):
            return
        loser_player.force_blind_next = True
        loser_player.force_blind_seq = _next_ability_seq()
        ability_effect(loser_player, lost_card, "vakharc következik, ő választ típust.")

def display_group_standings(player1, player2):
    """Display group standings in a visually pleasing way (distinct groups; Master ignored)."""
    players = [player1, player2]
    display_players_group_standings(players)

def display_players_card_counts(players):
    """Display counts of cards in deck/hand/won/lost for each player."""
    header = f"{'Játékos':<14} | {'Pakli':^5} | {'Kéz':^4} | {'Nyertes':^7} | {'Vesztes':^7}"
    sep = "-" * len(header)
    print(f"\n{sep}")
    title = "🃏 LAPMÉRLEGEK"
    pad = max(0, len(sep) - len(title))
    left = pad // 2
    right = pad - left
    print(" " * left + title + " " * right)
    print(sep)
    print(header)
    print(sep)
    for p in players:
        deck_count = len(p.deck)
        hand_count = len(p.hand)
        won_count = len(p.won_cards)
        lost_count = len(p.lost_cards)
        print(f"{p.name:^14} | {deck_count:^5} | {hand_count:^4} | {won_count:^7} | {lost_count:^7}")
    print(sep)

def apply_sensei_bonuses(players):
    """Apply Sensei (+1 all stats) once for players who have the flag set."""
    for p in players:
        if getattr(p, 'next_turn_buff_all_1', False):
            all_piles = [p.hand, p.deck, p.won_cards, p.lost_cards]
            for pile in all_piles:
                for c in pile:
                    if getattr(c, 'tmp_bonuses', None) is None:
                        c.tmp_bonuses = {"erő":0,"intelligencia":0,"reflex":0}
                    for stat in ('erő', 'intelligencia', 'reflex'):
                        c.tmp_bonuses[stat] = c.tmp_bonuses.get(stat, 0) + 1
                    c._sensei_bonus_applied = getattr(c, '_sensei_bonus_applied', 0) + 1
            p.next_turn_buff_all_1 = False

def remove_sensei_bonuses(players):
    """Remove any Sensei bonuses that were applied globally."""
    for p in players:
        all_piles = [p.hand, p.deck, p.won_cards, p.lost_cards]
        for pile in all_piles:
            for c in pile:
                applied = getattr(c, '_sensei_bonus_applied', 0)
                if applied:
                    for stat in ('erő', 'intelligencia', 'reflex'):
                        c.tmp_bonuses[stat] = c.tmp_bonuses.get(stat, 0) - applied
                    delattr(c, '_sensei_bonus_applied')

def reset_card_for_battle(card):
    if card is None:
        return
    card.ability_used = False
    card.ability_reserved = False
    card.ability_permanently_skipped = False
    for attr in (
        '_boy_def_buff_applied',
        '_abilities_disabled_in_battle',
        '_priest_pending_draw',
        '_entered_battle_via_swap',
        '_immediate_on_entry_pending',
        '_swap_attacker_card',
    ):
        if hasattr(card, attr):
            try:
                delattr(card, attr)
            except Exception:
                pass

def pre_disable_samurai(battlefield_cards):
    samurai_cards = [c for c in battlefield_cards if c and getattr(c, 'ability_code', None) == 'disable_opponent_ability']
    if samurai_cards:
        for c in battlefield_cards:
            if c is None:
                continue
            if c not in samurai_cards:
                c._abilities_disabled_in_battle = True
    return samurai_cards

def make_battle_context(attacker_card, defender_cards, attacker_index, players, current_stat=None):
    return {
        'attacker_card': attacker_card,
        'defender_cards': defender_cards,
        'attacker_index': attacker_index,
        'players_for_battle': players,
        'current_stat': current_stat
    }

def trigger_initial_passives(attacker_card, defender_cards, attacker_index, defender_index, players):
    battle_context = make_battle_context(attacker_card, defender_cards, attacker_index, players)
    battlefield_cards = [attacker_card] + list(defender_cards.values())
    pre_disable_samurai(battlefield_cards)
    return battle_context

def display_players_group_standings(players):
    """Standings table with centered cell contents."""
    base_groups = list(get_all_groups())
    order = ["pistol", "hell", "yinyang", "holy", "adventurer", "soldier", "martial", "lightning", "jolly", "western"]
    # Keep specified order first, then append any other groups not listed
    all_groups = [g for g in order if g in base_groups]
    for g in sorted(base_groups):
        if g not in all_groups:
            all_groups.append(g)
    progress_groups = [g for g in all_groups]

    def _visual_width(text: str) -> int:
        if not text:
            return 0
        width = 0
        for ch in str(text):
            # Ignore combining marks / variation selectors / formatting chars in width
            if unicodedata.combining(ch) or unicodedata.category(ch) in ("Mn", "Me", "Cf"):
                continue
            # East Asian wide/fullwidth count as 2, others as 1
            width += 2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1
        return width

    def _pad(text, width, align="center"):
        text = str(text)
        tw = _visual_width(text)
        if tw >= width:
            return text
        pad = width - tw
        if align == "left":
            left, right = 0, pad
        elif align == "right":
            left, right = pad, 0
        else:
            left = pad // 2
            right = pad - left
        return (" " * left) + text + (" " * right)

    def _compute_progress(p):
        base_groups = set()
        for card in p.won_cards:
            key = normalize_group(card.group)
            if not key or key == "master":
                continue
            base_groups.add(key)
        filled_groups = set(base_groups)
        return base_groups, filled_groups

    def _group_display(group):
        return format_group_label(group) or group.capitalize()

    progress = {p: _compute_progress(p) for p in players}
    total = 6
    def _format_total(base_groups):
        return f"{len(base_groups)}/{total}"
    summary_rows = [
        ("Összes", lambda p, prog: _format_total(prog[0])),
        ("Győzelem", lambda p, prog: f"{len(p.won_cards)}"),
    ]

    group_labels = [_group_display(g) for g in all_groups]
    group_col_width = max(
        12,
        _visual_width("Csoport"),
        _visual_width("Összes"),
        _visual_width("Győzelem"),
        *( _visual_width(s) for s in group_labels )
    )

    player_col_widths = []
    for p in players:
        values = [p.name]
        base_groups, _ = progress[p]
        for group in all_groups:
            if group in base_groups:
                cell = "✅"
            else:
                cell = "⬜"
            values.append(cell)
        for _, value_fn in summary_rows:
            values.append(value_fn(p, progress[p]))
        player_col_widths.append(max(_visual_width(v) for v in values))

    col_widths = [group_col_width] + player_col_widths
    target_total_width = 72
    current_total_width = sum(col_widths) + len(col_widths) + 1
    if current_total_width < target_total_width and len(player_col_widths) > 0:
        extra = target_total_width - current_total_width
        per = extra // len(player_col_widths)
        rem = extra % len(player_col_widths)
        for i in range(1, len(col_widths)):
            col_widths[i] += per
        for i in range(rem):
            col_widths[1 + i] += 1

    def _row_line(cells):
        return "|" + "|".join(_pad(cell, w, "center") for cell, w in zip(cells, col_widths)) + "|"

    sep = "+" + "+".join("-" * w for w in col_widths) + "+"
    title_text = "🏁 CSOPORTGYŐZELMEK (KÜLÖNBÖZŐ CSOPORTOK)"
    table_width = sum(col_widths) + len(col_widths) - 1

    print("\n" + sep)
    print("|" + _pad(title_text, table_width, "center") + "|")
    print(sep)
    print(_row_line(["Csoport"] + [p.name for p in players]))
    print(sep)

    for group in all_groups:
        row_cells = [_group_display(group)]
        for p in players:
            base_groups, _ = progress[p]
            if group in base_groups:
                cell = "✅"
            else:
                cell = "⬜"
            row_cells.append(cell)
        print(_row_line(row_cells))

    print(sep)

    for label, value_fn in summary_rows:
        row_cells = [label]
        for p in players:
            row_cells.append(value_fn(p, progress[p]))
        print(_row_line(row_cells))

    print(sep + "\n")

def trigger_ability(card, player, opponent, is_human_player, is_attacker, battle_context=None, silent=False):
    """
    Trigger a card's ability after reveal, before battle resolution.
    Returns tuple: (ability_used, winning_card_for_records, new_fight_type_or_None)
    For active abilities, offers choice to use/skip/reserve (if human player).
    """
    # Don't trigger abilities on cards revealed by battle_royale - only use their stats
    if getattr(card, '_battle_royale_revealed', False):
        return False, card, None

    # If abilities are disabled in this battle (Samurai Crok), skip entirely
    if getattr(card, '_abilities_disabled_in_battle', False):
        return False, card, None
    
    if card.ability_code == "none" or card.ability_used or card.ability_permanently_skipped:
        if is_human_player and not silent and (card.ability_used or card.ability_permanently_skipped):
            # Debug: jelezzük, ha valami miatt nem fut le a képesség
            pass  # Commented out debug message
        return False, card, None
    
    # PASSIVE: Boy Crok gets +2 reflex when defending
    # Only apply when this card is actually a defender in the current battle (avoid applying from hand/deck),
    # and only once per battle using a temporary marker on the card.
    if card.ability_code == "force_attack_next_turn_def_buff" and not is_attacker and card.ability_type == "passive":
        # Must have battle_context and be present among defender_cards
        if battle_context and (battle_context.get('defender_cards') is not None):
            defender_cards = list((battle_context.get('defender_cards') or {}).values())
            if card in defender_cards:
                # Only apply once per battle
                if not getattr(card, '_boy_def_buff_applied', False):
                    if getattr(card, 'tmp_bonuses', None) is None:
                        card.tmp_bonuses = {"erő": 0, "intelligencia": 0, "reflex": 0}
                    card.tmp_bonuses['reflex'] = card.tmp_bonuses.get('reflex', 0) + 2
                    card._boy_def_buff_applied = True
                player.force_attack_next = True
                player.force_attack_seq = _next_ability_seq()
                card.ability_used = True
                if not silent:
                    ability_effect(player, card, "+2 reflexet kapott. A következő körben ő támad.")
                return True, card, None
        # Passive ability does not count as an active action; never extend active ability rounds
        return False, card, None
    
    # PASSIVE: Boy Crok - force attack next turn (when played)
    if card.ability_code == "force_attack_next_turn_def_buff" and card.ability_type == "passive":
        player.force_attack_next = True
        player.force_attack_seq = _next_ability_seq()
        card.ability_used = True
        if not silent:
            ability_effect(player, card, "következő körben támadni fog.")
        return True, card, None
    
    # PASSIVE: Sensei Crok - buff all cards next turn
    if card.ability_code == "buff_next_turn_all_1" and card.ability_type == "passive":
        player.next_turn_buff_all_1 = True
        card.ability_used = True
        if not silent:
            ability_effect(player, card, "A következő harcban Crokjaid minden értéke +1 lesz.")
        return True, card, None
    
    # For active abilities, ask player if they want to use, skip, or reserve
    if card.ability_type == "active" and is_human_player:
        # Special case: Gladiator Crok cannot activate when fight type is already power
        if card.ability_code == "force_power_fight":
            if battle_context and battle_context.get('current_stat') == "erő":
                card.ability_used = True
                if not silent:
                    ability_effect(player, card, "A képesség nem aktiválható: a harc típusa már most is erő.")
                return False, card, None
        # Special case: Police Crok must have valid candidates to use the ability
        if card.ability_code == "win_by_discarding_duplicate":
            if battle_context:
                battle_names = set()
                players_for_battle = battle_context.get('players_for_battle') or []
                attacker_idx = battle_context.get('attacker_index')
                ac = battle_context.get('attacker_card')
                if ac is not None and attacker_idx is not None:
                    try:
                        if players_for_battle[attacker_idx] is not player:
                            battle_names.add(ac.name)
                    except Exception:
                        pass
                for idx, dc in (battle_context.get('defender_cards') or {}).items():
                    try:
                        if players_for_battle[idx] is not player:
                            battle_names.add(dc.name)
                    except Exception:
                        pass
                candidates = [c for c in player.hand if c.name in battle_names]
                if not candidates:
                    # Nincs megfelelő lapod a képességhez, automatikusan skippeljen
                    ability_effect(player, card, "nem aktiválható: nincs olyan Crokod a kezedben, mely megtalálható a harctéren.")
                    card.ability_permanently_skipped = True
                    return False, card, None
        
        # Special case: Devil Crok must have valid candidates (lost cards) to use the ability
        if card.ability_code == "copy_lost_ability":
            players_source = GLOBAL_PLAYERS if 'GLOBAL_PLAYERS' in globals() and isinstance(GLOBAL_PLAYERS, list) else []
            has_any_lost = False
            for p in players_source:
                if p is not player and len(p.lost_cards) > 0:
                    has_any_lost = True
                    break
            if not has_any_lost:
                # Nincs vesztes lap másik játékosoknál
                ability_effect(player, card, "Nem aktiválható: nincs még vesztes lapja más játékosoknak.")
                card.ability_permanently_skipped = True
                return False, card, None
        
        # Special case: Angel Crok must have lost cards to use the ability
        if card.ability_code == "revive_from_lost":
            if not player.lost_cards:
                # Nincs vesztes lapja
                print(f"⚠️ {get_ability_label(card)} nem aktiválható: nincs vesztes lapod, amit visszahozhatnál.")
                card.ability_permanently_skipped = True
                return False, card, None
        
        # If already reserved, present a shorter menu (use now / keep reserved / skip)
        if getattr(card, 'ability_reserved', False):
            print(f"\n{get_ability_prefix(card)} {card.name} (tartalékolt) — Mit szeretnél most tenni?")
            print("1. Használod most")
            print("2. Továbbra is tartalékolod")
            print("0. Nem használod")
            choice = choose_int_in_range("Válaszd (0-2): ", 0, 2)
            if choice == 1:
                # Fall through to actual ability execution
                card.ability_reserved = False
            elif choice == 0:
                card.ability_permanently_skipped = True
                card.ability_reserved = False
                return False, card, None
            else:
                return False, card, None
        else:
            print(f"\n{get_ability_prefix(card)} {get_ability_label(card)}")
            if card.ability_text:
                print(f"   {card.ability_text}")
            print("Mit szeretnél tenni?")
            print("1. Használod")
            if len(player.won_cards) > 0:
                print("2. Tartalékolod (költség: 1 nyertes lap a vesztesek közé)")
            else:
                print("2. Tartalékolod (NINCS ELÉG NYERT LAP - nem elérhető)")
            print("0. Nem használod")
            
            choice = choose_int_in_range("Válaszd (0-2): ", 0, 2)
            if choice == 1:
                pass  # fall through to execution
            elif choice == 0:
                ability_effect(player, card, "A képesség nem került felhasználásra.")
                card.ability_permanently_skipped = True
                return False, card, None
            elif choice == 2 and len(player.won_cards) > 0:
                print(f"   {get_ability_label(card)} tartalékolva. Válaszd ki, melyik nyertes lapodat teszed a vesztesek közé:")
                # If multiple won cards, ask which one to sacrifice
                for i, wc in enumerate(player.won_cards, 1):
                    print(f"{i}. {wc}")
                print("0. Mégsem")
                sel = choose_int_in_range("Válassz (0 vagy szám): ", 0, len(player.won_cards))
                if sel == 0:
                    return False, card, None
                lost_card = player.won_cards.pop(sel-1)
                check_and_trigger_loss_abilities(lost_card, player, from_battle=False)
                player.lost_cards.append(lost_card)
                card.ability_reserved = True
                return False, card, None
            else:
                return False, card, None
    
    # For active abilities with bot, skip for now
    if card.ability_type == "active" and not is_human_player and card.ability_code != "force_power_fight":
        # Bot doesn't use this ability automatically for now
        card.ability_permanently_skipped = True
        if not silent:
            ability_effect(player, card, "A képesség nem került felhasználásra.")
        return False, card, None
    
    # Master Crok: swap_with_hand
    if card.ability_code == "swap_with_hand":
        # List available cards to swap with
        available_cards = [c for c in player.hand if c.name != "Master Crok"]
        
        if not available_cards:
            print("Nincs másik kártyád a cseréléshez.")
            return False, card, None
        
        print("Elérhető cserepárok:")
        for i, c in enumerate(available_cards):
            print(f"{i+1}. {c}")
        print("0. Mégsem")

        choice = choose_int_in_range("Válassz (0 vagy szám): ", 0, len(available_cards))
        if choice == 0:
            ability_effect(player, card, "A képesség nem került felhasználásra.")
            card.ability_permanently_skipped = True
            return False, card, None

        swap_card = available_cards[choice - 1]

        # Remove the chosen card from hand
        player.hand.remove(swap_card)
        # Add the Master Crok back to hand
        player.hand.append(card)

        card.ability_used = True
        ability_effect(player, card, f"csere történt: {card.name} ⇄ {swap_card.name}.")
        print(f"  {card.name}: [E:{card.stats.get('erő',0)} I:{card.stats.get('intelligencia',0)} R:{card.stats.get('reflex',0)}]")
        print(f"  {swap_card.name}: [E:{swap_card.stats.get('erő',0)} I:{swap_card.stats.get('intelligencia',0)} R:{swap_card.stats.get('reflex',0)}]")
        # If this swap happened as part of an ongoing battle, increment Army Crok buffs by +1
        apply_army_swap_bonus(battle_context, player)
        # Mark the swapped-in card as entering the battlefield via swap
        if swap_card is not None:
            swap_card._entered_battle_via_swap = True
            swap_card._immediate_on_entry_pending = True
        # Return the swap_card as the one that goes to won_cards
        return True, swap_card, None
    
    # Bond Crok: change_fight_type
    if card.ability_code == "change_fight_type":
        if card.ability_type == "active" and not is_human_player:
            # Bot doesn't use this ability automatically for now
            return False, card, None
        
        print(f"\n{get_ability_prefix(card)} {card.name} képessége aktiválható: Megváltoztathatod a harc típusát: erő, intelligencia vagy reflex.")
        
        print("Válaszd meg a harc típusát:")
        print("1. Erő")
        print("2. Intelligencia")
        print("3. Reflex")
        print("0. Nem használod a képességet")
        
        choice = choose_int_in_range("Válassz (0-3): ", 0, 3)
        if choice == 0:
            ability_effect(player, card, "A képesség nem került felhasználásra.")
            card.ability_permanently_skipped = True
            return False, card, None

        fight_types = {1: "erő", 2: "intelligencia", 3: "reflex"}
        card.current_fight_type = fight_types[choice]
        card.ability_used = True
        ability_effect(player, card, f"a harc típusa {fight_types[choice]} lett.")
        return True, card, fight_types[choice]

    # Devil Crok: copy_lost_ability
    if card.ability_code == "copy_lost_ability":
        # Can copy an ability from opponent's lost cards
        if opponent is None:
            return False, card, None

        # Candidates: lost cards with usable abilities (not none and not copy_lost_ability)
        # In multiplayer, Devil Crok can look at ALL players' lost cards.
        seen_names = set()
        candidates = []
        candidates_owner = []
        players_source = None
        if 'GLOBAL_PLAYERS' in globals() and isinstance(GLOBAL_PLAYERS, list):
            players_source = GLOBAL_PLAYERS
        elif opponent is not None:
            players_source = [opponent]
        else:
            players_source = []

        for p in players_source:
            # skip self
            if p is player:
                continue
            for c in p.lost_cards:
                if c.ability_code and c.ability_code != "none" and c.ability_code != "copy_lost_ability" and c.name not in seen_names:
                    candidates.append(c)
                    candidates_owner.append(p)
                    seen_names.add(c.name)

        if not candidates:
            all_lost = sum(len(p.lost_cards) for p in players_source if p is not player)
            print(f"\n⚠️ {card.name} megpróbálta használni a Lélekrablás képességet, de nincs elérhető vesztes lap a játékosoknál.")
            print(f"   (Összes vesztes lap másoknál: {all_lost})")
            return False, card, None

        if is_human_player:
            print(f"\n{get_ability_prefix(card)} {get_ability_label(card)}: Másik játékos vesztes lapjának képességét másolhatod.")
            print("Elérhető vesztes lapok a játékosoknál:")
            for i, c in enumerate(candidates):
                owner = candidates_owner[i]
                # Show ability name and text when available
                ability_desc = c.ability_name or c.ability_code
                if c.ability_text:
                    ability_desc = f"{ability_desc}: {c.ability_text}"
                print(f"{i+1}. {c.name} (vesztett: {owner.name}) -> {ability_desc}")
            print("0. Nem használod a képességet")
            choice = choose_int_in_range("Válassz (0 vagy szám): ", 0, len(candidates))
            if choice == 0:
                ability_effect(player, card, "A képesség nem került felhasználásra.")
                card.ability_permanently_skipped = True
                return False, card, None
            chosen = candidates[choice-1]
        else:
            # Bot: pick random candidate
            chosen = random.choice(candidates)

        # Temporarily replace this card's ability and human-readable fields with the chosen one for this battle
        card.tmp_original_ability_code = card.ability_code
        card.tmp_original_ability_type = card.ability_type
        card.tmp_original_ability_name = card.ability_name
        card.tmp_original_ability_text = card.ability_text
        card.ability_code = chosen.ability_code
        card.ability_type = chosen.ability_type
        card.ability_name = chosen.ability_name
        card.ability_text = chosen.ability_text
        # Suppress verbose copy message; the copied ability's own outcome will be logged

        # Try to immediately trigger the copied ability (avoid copying another copy)
        if chosen.ability_code != "copy_lost_ability":
            used, new_card, new_ft = trigger_ability(card, player, opponent, is_human_player, is_attacker, battle_context=battle_context)
            card.ability_used = card.ability_used or used
            if used:
                return True, new_card, new_ft

        # If we couldn't or didn't trigger immediately, mark as used so it won't be re-triggered
        card.ability_used = True
        return True, card, None

    # Samurai Crok: disable_opponent_ability (immediate)
    if card.ability_code == "disable_opponent_ability":
        # Disable all opponent abilities in this battle
        # If we have battle context, disable abilities of all cards currently in the battle
        if battle_context is not None:
            # disable attacker and all defender played cards
            ac = battle_context.get('attacker_card')
            if ac is not None:
                ac.ability_used = True
                ac._abilities_disabled_in_battle = True
            for dc in (battle_context.get('defender_cards') or {}).values():
                dc.ability_used = True
                dc._abilities_disabled_in_battle = True
            ability_effect(player, card, "Hatástalanította a csatában lévő ellenfelek képességeit.")
            card.ability_used = True
            return True, card, None
        # Fallback: try to disable abilities in opponent's collections
        if opponent is not None:
            for opp_card in opponent.hand + opponent.won_cards:
                opp_card.ability_used = True
            ability_effect(player, card, "Hatástalanította az ellenfelek képességeit.")
            card.ability_used = True
            return True, card, None
        return False, card, None

    # Angel Crok: revive_from_lost
    if card.ability_code == "revive_from_lost":
        if not player.lost_cards:
            print(f"{card.name}: Nincs vesztes lapod, amit visszahozhatnál.")
            return False, card, None
        if is_human_player:
            while True:
                if not player.lost_cards:
                    print(f"{card.name}: Nincs vesztes lapod, amit visszahozhatnál.")
                    return False, card, None
                print(f"\n{get_ability_prefix(card)} {get_ability_label(card)}: Válassz egy vesztes lapot, amit visszaveszel a kezedbe:")
                for i, lc in enumerate(player.lost_cards, 1):
                    print(f"{i}. {lc}")
                print("0. Mégsem")
                sel = choose_int_in_range("Válassz (0 vagy szám): ", 0, len(player.lost_cards))
                if sel == 0:
                    ability_effect(player, card, "A képesség nem került felhasználásra.")
                    card.ability_permanently_skipped = True
                    return False, card, None
                if 1 <= sel <= len(player.lost_cards):
                    revived = player.lost_cards.pop(sel-1)
                    break
        else:
            revived = player.lost_cards.pop(0)
        # Reset ability flags when reviving a card
        revived.ability_used = False
        revived.ability_reserved = False
        revived.ability_permanently_skipped = False
        player.hand.append(revived)
        card.ability_used = True
        ability_effect(player, card, f"visszahelyezve a kezedbe: {revived.name}.")
        return True, card, None

    # Captain Crok: battle_royale
    if card.ability_code == "battle_royale":
        # Battle royale: reveal the top card of each player's deck, show them,
        # and add the revealed card's stats to that player's active battlefield card
        if battle_context and battle_context.get('players_for_battle') is not None:
            players_for_battle = battle_context.get('players_for_battle') or []
            attacker_idx = battle_context.get('attacker_index', 0)
            defender_cards = battle_context.get('defender_cards') or {}
            ordered_indices = [attacker_idx] + [di for di in defender_cards.keys() if di != attacker_idx]
            players_src = [(idx, players_for_battle[idx]) for idx in ordered_indices]
        else:
            players_src = [(idx, p) for idx, p in enumerate(GLOBAL_PLAYERS if 'GLOBAL_PLAYERS' in globals() else [])]
        if players_src and all(len(p.deck) == 0 for _, p in players_src):
            print(f"⚠️ {get_ability_label(card)} nem aktiválható: nincs már lap a paklikban.")
            return False, card, None

        ability_effect(player, card, "aktiválódott: Nagy ütközet - mindenki paklijának legfelső lapja csatlakozik a harchoz!")
        revealed = []
        for idx, p in players_src:
            if p.deck:
                top = p.deck.pop(0)  # Actually remove the card from deck
                # Mark this card as a battle_royale revealed card (abilities should not trigger)
                top._battle_royale_revealed = True
                revealed.append((idx, p, top))
                e_base = get_base_stat(top, 'erő')
                i_base = get_base_stat(top, 'intelligencia')
                r_base = get_base_stat(top, 'reflex')
                e_buff = top.tmp_bonuses.get('erő', 0)
                i_buff = top.tmp_bonuses.get('intelligencia', 0)
                r_buff = top.tmp_bonuses.get('reflex', 0)
                e_part = f"{e_base}" if not e_buff else f"{e_base}(+{e_buff})"
                i_part = f"{i_base}" if not i_buff else f"{i_base}(+{i_buff})"
                r_part = f"{r_base}" if not r_buff else f"{r_base}(+{r_buff})"
                print(f" - {p.name}: {top.name} [E:{e_part} I:{i_part} R:{r_part}]")
            else:
                revealed.append((idx, p, None))
                print(f" - {p.name}: pakli üres (0)")

        # If a battle context is provided, apply all revealed stats (not just erő) as temporary bonuses
        if battle_context:
            attacker_card = battle_context.get('attacker_card')
            defender_cards = battle_context.get('defender_cards') or {}
            attacker_index = battle_context.get('attacker_index', -1)
            players_for_battle = battle_context.get('players_for_battle') or []

            for idx, p, top in revealed:
                if top is None:
                    continue
                battle_player_idx = idx if players_for_battle else None
                
                # Determine the target card
                target_card = None
                if battle_player_idx == attacker_index:
                    # This player is the attacker
                    target_card = attacker_card
                elif battle_player_idx in defender_cards:
                    # This player is a defender
                    target_card = defender_cards[battle_player_idx]

                if target_card is not None:
                    if getattr(target_card, 'tmp_bonuses', None) is None:
                        target_card.tmp_bonuses = {"erő": 0, "intelligencia": 0, "reflex": 0}
                    # Store the revealed card reference for later (when deciding winners/losers)
                    target_card.battle_royal_card = top
                    # add all stats from the revealed top card to the corresponding tmp_bonuses
                    for stat in ('erő', 'intelligencia', 'reflex'):
                        addv = get_base_stat(top, stat) + top.tmp_bonuses.get(stat, 0)
                        target_card.tmp_bonuses[stat] = target_card.tmp_bonuses.get(stat, 0) + addv
                    pe = get_base_stat(top, 'erő') + top.tmp_bonuses.get('erő', 0)
                    pi = get_base_stat(top, 'intelligencia') + top.tmp_bonuses.get('intelligencia', 0)
                    pr = get_base_stat(top, 'reflex') + top.tmp_bonuses.get('reflex', 0)

            # Army Crok extra opponents: revealed cards count as new opponents
            participants = [attacker_card] + list(defender_cards.values())
            for pcard in participants:
                if pcard and getattr(pcard, 'ability_code', None) == 'buff_per_opponent':
                    owner = get_card_owner(pcard, battle_context, player)
                    extra_opponents = sum(1 for _, rp, _ in revealed if rp is not owner)
                    if extra_opponents > 0:
                        if getattr(pcard, 'ability_used', False):
                            continue
                        if getattr(pcard, 'tmp_bonuses', None) is None:
                            pcard.tmp_bonuses = {"erő": 0, "intelligencia": 0, "reflex": 0}
                        for k in ('erő', 'intelligencia', 'reflex'):
                            pcard.tmp_bonuses[k] = pcard.tmp_bonuses.get(k, 0) + extra_opponents
                        ability_effect(owner, pcard, f"minden értéke +{extra_opponents} lett (új ellenfelek a Nagy ütközet miatt).")

        card.ability_used = True
        return True, card, None

    # Executor Crok: force_discard_to_lost
    if card.ability_code == "force_discard_to_lost":
        # Choose a target player and force them to discard one hand card to their lost pile
        players_src = GLOBAL_PLAYERS if 'GLOBAL_PLAYERS' in globals() else []
        targets = [p for p in players_src if p is not player]
        if not targets:
            return False, card, None
        if is_human_player:
            print(f"\n{get_ability_prefix(card)} {get_ability_label(card)}: Válassz célszemélyt:")
            for i, t in enumerate(targets, 1):
                print(f"{i}. {t.name}")
            sel = choose_int_in_range("Válassz (szám): ", 1, len(targets))
            target = targets[sel-1]
        else:
            target = random.choice(targets)
        if not target.hand:
            print(f"{target.name}-nek nincs lapja, amit elveszíthetne.")
            return False, card, None
        if not target.is_bot:
            print(f"{target.name}, választanod kell egy lapot, amit a vesztesek közé teszel:")
            for i, c in enumerate(target.hand, 1):
                print(f"{i}. {c}")
            sel = choose_int_in_range("Válassz (szám): ", 1, len(target.hand))
            lost_card = target.hand.pop(sel-1)
        else:
            lost_card = target.hand.pop(0)
        check_and_trigger_loss_abilities(lost_card, target, from_battle=False)
        target.lost_cards.append(lost_card)
        card.ability_used = True
        ability_effect(player, card, f"{target.name} elveszítette: {lost_card.name}.")
        return True, card, None

    # Jungle Crok: swap_with_deck_blind
    if card.ability_code == "swap_with_deck_blind":
        if not player.deck:
            print("Nincs elég lap a pakliban a vak cseréhez.")
            return False, card, None
        top = player.deck.pop(0)
        # Put current card on top of deck
        player.deck.insert(0, card)
        card.ability_used = True
        ability_effect(player, card, "vak csere végrehajtva.")
        print(f"  Kiváltó lap: {card.name} [E:{card.stats.get('erő',0)} I:{card.stats.get('intelligencia',0)} R:{card.stats.get('reflex',0)}]")
        print(f"  Pakli tetejéről bekerült: {top.name} [E:{top.stats.get('erő',0)} I:{top.stats.get('intelligencia',0)} R:{top.stats.get('reflex',0)}]")
        # Increment Army Crok buffs in play if this swap happened during a battle
        apply_army_swap_bonus(battle_context, player)
        # Mark the swapped-in card as entering the battlefield via swap
        if top is not None:
            top._entered_battle_via_swap = True
            top._immediate_on_entry_pending = True
        return True, top, None

    # Sensei Crok képesség: most már passzív, lásd fentebb a trigger_ability elején

    # Sumo Crok: buff_power_if_more_intelligent (passive helper)
    if card.ability_code == "buff_power_if_more_intelligent":
        # Determine all battlefield cards and require this card to be smarter than ALL of them.
        battlefield_cards = []
        if battle_context:
            ac = battle_context.get('attacker_card')
            if ac is not None:
                battlefield_cards.append(ac)
            battlefield_cards.extend(list((battle_context.get('defender_cards') or {}).values()))

        # Fallback: if we couldn't gather from battle_context, use the opponent parameter
        if not battlefield_cards and opponent is not None:
            battlefield_cards = [opponent]

        # Exclude self from comparison
        battlefield_cards = [c for c in battlefield_cards if c is not None and c is not card]

        if not battlefield_cards:
            card.ability_used = True
            return False, card, None

        # Check if this card's intelligencia is higher than ALL battlefield cards (include temp bonuses/overrides)
        card_int = get_base_stat(card, 'intelligencia') + card.tmp_bonuses.get('intelligencia', 0)
        if all(card_int > (get_base_stat(opp, 'intelligencia') + opp.tmp_bonuses.get('intelligencia', 0)) for opp in battlefield_cards):
            card.tmp_bonuses['erő'] = card.tmp_bonuses.get('erő', 0) + 2
            card.ability_used = True
            if not silent:
                ability_effect(player, card, "ereje +2 lett (intelligencia alapú feltétel).")
            return True, card, None
        card.ability_used = True
        if not silent:
            ability_effect(player, card, "A feltétel nem teljesül.")
        return False, card, None

    # Pancrator Crok: blind_fight_on_loss
    # NOTE: This ability MUST only trigger when the card is placed into the LOST pile (i.e., when it actually loses).
    # The loss-triggering logic is handled centrally by check_and_trigger_loss_abilities(lost_card, loser_player),
    # so we do NOT perform the 'mark for blind' action here during passive/active reveal phases.
    if card.ability_code == "blind_fight_on_loss":
        if not silent:
            ability_effect(player, card, "Még nem tudjuk a harc végeredményét.")
            card.ability_used = True
        return False, card, None

    # Army Crok: buff_per_opponent
    if card.ability_code == "buff_per_opponent":
        # Passive: set one-time buff equal to number of other players in the game.
        players_src = GLOBAL_PLAYERS if 'GLOBAL_PLAYERS' in globals() else []
        try:
            num_opponents = sum(1 for p in players_src if p is not player and p is not None)
        except Exception:
            num_opponents = max(0, len(players_src) - 1)

        # Ensure tmp_bonuses exists
        if getattr(card, 'tmp_bonuses', None) is None:
            card.tmp_bonuses = {"erő":0, "intelligencia":0, "reflex":0}

        pending_swaps = getattr(card, '_army_pending_swaps', 0)
        prev_base = getattr(card, '_army_applied_base', 0)
        prev_swaps = getattr(card, '_army_applied_swaps', 0)
        desired_base = num_opponents
        desired_swaps = pending_swaps
        delta = (desired_base + desired_swaps) - (prev_base + prev_swaps)
        if delta:
            for k in ('erő','intelligencia','reflex'):
                # Add only the delta on top of existing bonuses (e.g., Sensei)
                card.tmp_bonuses[k] = card.tmp_bonuses.get(k, 0) + delta
        card._army_applied_base = desired_base
        card._army_applied_swaps = desired_swaps
        card._army_recalc_needed = False
        card.ability_used = True
        if not silent:
            if desired_swaps:
                ability_effect(player, card, f"Minden értéke +{desired_base} (ellenfelek száma alapján) és +{desired_swaps} (csere miatt).")
            else:
                ability_effect(player, card, f"Minden értéke +{desired_base} (ellenfelek száma alapján).")
        return True, card, None

    # Boy Crok képesség: most már passzív, lásd fentebb a trigger_ability elején

    # Cave Crok: catchup_bonus
    if card.ability_code == "catchup_bonus":
        opp_candidates = []
        if battle_context and battle_context.get('players_for_battle') is not None:
            players_src = battle_context.get('players_for_battle') or []
            opp_candidates = [p for p in players_src if p is not None and p is not player]
        elif opponent is not None and opponent is not player:
            opp_candidates = [opponent]
        if not opp_candidates:
            card.ability_used = True
            if not silent:
                ability_effect(player, card, "Nincs választható ellenfél a képességhez.")
            return False, card, None
        target = choose_cave_crok_target(player, opp_candidates, is_human_player=is_human_player, announce=False)
        if target is None:
            card.ability_used = True
            if not silent:
                ability_effect(player, card, "Nincs választható ellenfél a képességhez.")
            return False, card, None
        diff = max(0, len(target.won_cards) - len(player.won_cards))
        for k in ('erő','intelligencia','reflex'):
            card.tmp_bonuses[k] = card.tmp_bonuses.get(k,0) + diff
        card.ability_used = True
        if not silent:
            if not is_human_player:
                ability_effect(player, card, f"Kapott +{diff} bónuszt minden értékére (célpont: {target.name}).")
            else:
                ability_effect(player, card, f"Kapott +{diff} bónuszt minden értékére.")
        return True, card, None

    # Funny Crok: force_swap_opponent_bottom
    if card.ability_code == "force_swap_opponent_bottom":
        players_src = GLOBAL_PLAYERS if 'GLOBAL_PLAYERS' in globals() else []
        # If we're in a battle, prefer targeting players who have played cards (defender cards)
        if battle_context and battle_context.get('defender_cards'):
            defender_cards = battle_context.get('defender_cards')
            possible_idxs = [idx for idx in defender_cards.keys() if players_src[idx] is not player]
            # Allow targeting the attacker when the user is a defender
            attacker_idx = battle_context.get('attacker_index')
            if attacker_idx is not None and players_src and players_src[attacker_idx] is not player:
                possible_idxs.append(attacker_idx)
            # Sort targets by player name for consistent ordering
            possible_idxs = sorted(possible_idxs, key=lambda i: players_src[i].name)
            if not possible_idxs:
                return False, card, None
            if is_human_player:
                print(f"\n{get_ability_prefix(card)} {get_ability_label(card)}: Válassz célszemélyt (csak a csatatéren lévők közül):")
                for i, idx in enumerate(possible_idxs, 1):
                    if idx == attacker_idx:
                        print(f"{i}. {players_src[idx].name} - játszott lap: {battle_context.get('attacker_card')}")
                    else:
                        print(f"{i}. {players_src[idx].name} - játszott lap: {defender_cards[idx]}")
                sel = choose_int_in_range("Válassz (szám): ", 1, len(possible_idxs))
                target_idx = possible_idxs[sel-1]
            else:
                target_idx = random.choice(possible_idxs)
            target = players_src[target_idx]
            # The currently played card on battlefield for that player
            if target_idx == attacker_idx:
                played = battle_context.get('attacker_card')
            else:
                played = defender_cards.get(target_idx)
            if not played:
                return False, card, None
            # Need a bottom card to swap with
            if not target.deck:
                print(f"{target.name} paklija üres, nem lehet kicserélni.")
                return False, card, None
            bottom = target.deck.pop(-1)
            # Put the played card to bottom
            target.deck.append(played)
            # Replace the played card on the battlefield with the previous bottom card
            new_played = bottom
            # Update the battle context so the target's played card becomes the bottom card
            if target_idx == attacker_idx:
                battle_context['attacker_card'] = new_played
                card._swap_attacker_card = new_played
            else:
                defender_cards[target_idx] = new_played
            card.ability_used = True
            # Always announce the swap clearly (useful in blind fights)
            ability_effect(player, card, f"{target.name} játéktere kicserélődött.")
            print(f"  A korábban játékban lévő lap: {played}")
            print(f"  A pakli aljáról játékba került: {new_played}")
            # Increment any Army Crok buffs in play due to this swap
            apply_army_swap_bonus(battle_context, player)
            # Mark the swapped-in card as entering the battlefield via swap
            if new_played is not None:
                new_played._entered_battle_via_swap = True
                new_played._immediate_on_entry_pending = True
            # Return the initiator's card (no replacement of initiator's played card)
            return True, card, None
        else:
            # Fallback: operate on target's hand (non-battle situation)
            targets = [p for p in players_src if p is not player]
            targets = sorted(targets, key=lambda p: p.name)
            if not targets:
                return False, card, None
            if is_human_player:
                print(f"\n{get_ability_prefix(card)} {get_ability_label(card)}: Válassz célszemélyt:")
                for i, t in enumerate(targets, 1):
                    print(f"{i}. {t.name}")
                sel = choose_int_in_range("Válassz (szám): ", 1, len(targets))
                target = targets[sel-1]
            else:
                target = random.choice(targets)
            # Force swap: choose a card from target.hand and put it to bottom of their deck
            if not target.hand:
                return False, card, None
            if not target.is_bot:
                print(f"{target.name}, válassz egy lapot a kezedből (amit a pakli aljára helyezünk):")
                for i, c in enumerate(target.hand,1):
                    print(f"{i}. {c}")
                sel = choose_int_in_range("Válassz (szám): ", 1, len(target.hand))
                chosen = target.hand.pop(sel-1)
            else:
                chosen = target.hand.pop(0)
            target.deck.append(chosen)
            card.ability_used = True
            ability_effect(player, card, f"csere a kéz és a pakli alja között: {chosen.name} került {target.name} paklijának aljára.")
            print(f"  {chosen.name}: [E:{chosen.stats.get('erő',0)} I:{chosen.stats.get('intelligencia',0)} R:{chosen.stats.get('reflex',0)}]")
            return True, card, None

    # Gladiator Crok: force_power_fight
    if card.ability_code == "force_power_fight":
        if battle_context and battle_context.get('current_stat') == "erő":
            card.ability_used = True
            if not silent:
                ability_effect(player, card, "A képesség nem aktiválható: a harc típusa már most is erő.")
            return False, card, None
        card.ability_used = True
        ability_effect(player, card, "A harc típusát erőre változtatta.")
        return True, card, "erő"

    # Indian Crok: scry_6
    if card.ability_code == "scry_6":
        if len(player.deck) == 0:
            return False, card, None
        top_n = player.deck[:6]
        if is_human_player:
            print("Felső 6 lapod:")
            for i, c in enumerate(top_n,1):
                print(f"{i}. {c}")
            print("Adj meg új sorrendet a számokkal szóközzel elválasztva (pl. '3 1 2 ...') vagy 0 a változtatás nélkül:")
            while True:
                s = input("Új sorrend: ").strip()
                if s == "0" or not s:
                    ability_effect(player, card, "A képesség nem került felhasználásra.")
                    card.ability_permanently_skipped = True
                    return False, card, None
                try:
                    idxs = [int(x)-1 for x in s.split()]
                except Exception:
                    print("Hibás érték. Csak számokat adj meg.")
                    continue
                if len(idxs) != len(top_n):
                    print("Hibás érték. Pontosan 6 számot adj meg.")
                    continue
                if any(i < 0 or i >= len(top_n) for i in idxs) or len(set(idxs)) != len(top_n):
                    print("Hibás érték. 1 és 6 közötti, ismétlés nélküli számokat adj meg.")
                    continue
                new_top = [top_n[i] for i in idxs]
                player.deck[:6] = new_top
                card.ability_used = True
                ability_effect(player, card, "a pakli teteje át lett rendezve.")
                return True, card, None
        else:
            # Bot: do nothing
            return False, card, None

    # Karate Crok: sacrifice_for_power
    if card.ability_code == "sacrifice_for_power":
        if not player.hand:
            return False, card, None
        if is_human_player:
            print("Válassz egy lapot a kezedből, amit elveszítesz a harc erejéért:")
            for i, c in enumerate(player.hand,1):
                print(f"{i}. {c}")
            sel = choose_int_in_range("Válassz (szám): ", 1, len(player.hand))
            sacrifice = player.hand.pop(sel-1)
        else:
            sacrifice = player.hand.pop(0)
        check_and_trigger_loss_abilities(sacrifice, player, from_battle=False)
        player.lost_cards.append(sacrifice)
        gained = sacrifice.stats.get('erő',0)
        # Replace base erő with the sacrificed card's erő (not a bonus)
        if getattr(card, 'tmp_stat_overrides', None) is None:
            card.tmp_stat_overrides = {}
        card.tmp_stat_overrides['erő'] = gained
        card.ability_used = True
        ability_effect(player, card, f"feláldoztad {sacrifice.name}-t: erőd helyette {gained} lett.")
        return True, card, None

    # Police Crok: win_by_discarding_duplicate
    if card.ability_code == "win_by_discarding_duplicate":
        # If player has a card in hand that matches name of any other player's current cards (hand/won), they can discard it to instantly win
        # This ability only works during an active battle and only if you can discard a hand card
        # whose name exactly matches a card currently on the battlefield (attacker or any defender).
        if not battle_context:
            return False, card, None
        battle_names = set()
        players_for_battle = battle_context.get('players_for_battle') or []
        attacker_idx = battle_context.get('attacker_index')
        ac = battle_context.get('attacker_card')
        if ac is not None and attacker_idx is not None:
            try:
                if players_for_battle[attacker_idx] is not player:
                    battle_names.add(ac.name)
            except Exception:
                pass
        for idx, dc in (battle_context.get('defender_cards') or {}).items():
            try:
                if players_for_battle[idx] is not player:
                    battle_names.add(dc.name)
            except Exception:
                pass
        # candidates are only hand cards whose name is in battlefield
        candidates = [c for c in player.hand if c.name in battle_names]
        if not candidates:
            return False, card, None
        if is_human_player:
            print("Válaszd ki a kezedből azt a lapot, amit a vesztesek közé teszel (csak a játéktéren lévők közül választhatsz):")
            for i, c in enumerate(candidates,1):
                print(f"{i}. {c}")
            sel = choose_int_in_range("Válassz (szám): ", 1, len(candidates))
            used = candidates[sel-1]
            if used in player.hand:
                player.hand.remove(used)
        else:
            used = candidates[0]
            if used in player.hand:
                player.hand.remove(used)
        check_and_trigger_loss_abilities(used, player, from_battle=False)
        if used not in player.lost_cards:
            player.lost_cards.append(used)
        # Mark immediate win; battle resolution will end without value comparison
        card._instant_win = True
        card.ability_used = True
        ability_effect(player, card, f"aktiválva: {used.name} vesztesek közé került.")
        return True, card, None

    # Priest Crok: disable_underworld_or_draw (immediate, but with choice)
    if card.ability_code == "disable_underworld_or_draw":
        # If pending draw (active phase), handle draw choice now
        if getattr(card, '_priest_pending_draw', False):
            # Pending draw should be treated as an active choice
            if is_human_player:
                print(f"\n{get_ability_prefix(card)} {get_ability_label(card)}: Nincs 🔥 típusú kártya, húzhatsz egy lapot.")
                try:
                    choice = input("Húzol egy lapot? (I/N): ").lower()
                except Exception:
                    choice = 'i'
                if choice in ('i', 'igen', 'y', 'yes'):
                    drew = player.draw_card()
                    if drew:
                        ability_effect(player, card, "Húzott egy lapot.")
                        card.ability_used = True
                        card._priest_pending_draw = False
                        return True, card, None
                    card._priest_pending_draw = False
                    return False, card, None
                else:
                    card._priest_pending_draw = False
                    ability_effect(player, card, "A képesség nem került felhasználásra.")
                    card.ability_permanently_skipped = True
                    return False, card, None
            else:
                # Bot always draws when pending
                drew = player.draw_card()
                if drew:
                    ability_effect(player, card, "Húzott egy lapot.")
                    card.ability_used = True
                    card._priest_pending_draw = False
                    return True, card, None
                card._priest_pending_draw = False
                return False, card, None
        # Check if any opponent has underworld (hell) group cards
        players_src = GLOBAL_PLAYERS if 'GLOBAL_PLAYERS' in globals() else []
        inferno_cards = []
        valid_groups = {"hell"}

        # 1) Check battlefield (if available)
        if battle_context:
            bc_att = battle_context.get('attacker_card')
            bc_defs = list((battle_context.get('defender_cards') or {}).values())
            for c in [bc_att] + bc_defs:
                if c is None:
                    continue
                if normalize_group(getattr(c, 'group', None)) in valid_groups:
                    inferno_cards.append((None, c))

        # NOTE: Only battlefield cards should count for disabling Hell abilities.
        
        # If there are inferno cards, automatically disable them
        if inferno_cards:
            for p, c in inferno_cards:
                c.ability_used = True
            ability_effect(player, card, "automatikusan hatástalanította a 🔥 képességeket.")
            card.ability_used = True
            return True, card, None
        else:
            # No inferno cards: defer draw to active phase
            card._priest_pending_draw = True
            return False, card, None

    # Sheriff Crok: win_on_draw (passive placeholder)
    if card.ability_code == "win_on_draw":
        # Mark card so that in a tie it can be detected by outer logic (requires outer loop support)
        card._win_on_draw = True
        if not silent:
            ability_effect(player, card, "Döntetlen esetén nyer.")
            card.ability_used = True
        return False, card, None

    return False, card, None
    

def create_deck(target_size=40):
    # 1. Betöltjük a kártyatípusokat (pl. a 10 félét a json-ből)
    unique_cards = load_cards_from_file()
    
    if not unique_cards:
        print("VÉSZHELYZET: Üres paklival indulunk.")
        return [Card("HibaLap", "Hiba", 1, 1, 1, card_id=0)] * 40
        
    deck = []
    TARGET_SIZE = max(10, int(target_size))  # Cél: 40 lapos pakli (ajánlott), min. 10
    
    # A szabályzat szerint: egy kártyatípusból ennyit lehet: 10 laponként 1
    # Tehát: 10-19 lap: max 1 másolat, 20-29: max 2, 30-39: max 3, 40+: max 4
    max_copies = max(1, TARGET_SIZE // 10)  # 40-nél: 4, 30-nál: 3, 20-nál: 2, 10-nél: 1
    
    # Ellenőrzés: Van-e elég kártyatípus?
    possible_total = len(unique_cards) * max_copies
    if possible_total < TARGET_SIZE:
        print(f"FIGYELEM: Nincs elég kártyatípus a {TARGET_SIZE} laphoz!")
        print(f"Jelenleg {len(unique_cards)} típus van * {max_copies} db = maximum {possible_total} lapos lesz a pakli.")
    
    # 2. "Pool" (Készlet) módszer:
    # Létrehozunk egy készletet, amiben minden létező kártyából benne van
    # a szabálynak megfelelő maximum mennyiség.
    card_pool = []
    for card in unique_cards:
        for _ in range(max_copies):
            # FONTOS: A .copy() használata, hogy független kártyák legyenek!
            card_pool.append(card.copy())
            
    # 3. Kiválasztás
    # Ha több kártyánk van a készletben mint TARGET_SIZE, akkor véletlenszerűen kiválasztunk.
    # Ha kevesebb, akkor berakjuk az összeset.
    if len(card_pool) > TARGET_SIZE:
        deck = random.sample(card_pool, TARGET_SIZE)
    else:
        deck = card_pool  # Ha nincs meg a cél, visszük mindet, ami van.
        
    # 4. Keverés
    random.shuffle(deck)
    
    print(f"Pakli létrehozva: {len(deck)} lap ({max_copies} másolat/típus szerint szerkesztett).")
    return deck

# --- 4. A FŐ JÁTÉKCIKLUS (EZ HIÁNYZOTT!) ---
def main():
    print("--- MASTER CROK: Python Edition ---")
    print("Kártyák betöltése...")
    # Choose number of players or show rules
    num = None
    while num is None:
        choice = input("A játék kezdéséhez írd be a játékosok számát (2-6) vagy '?' a szabályzat megjelenítéséhez: ").strip()
        if choice == "?":
            script_dir = os.path.dirname(os.path.abspath(__file__))
            rules_path = os.path.join(script_dir, "rules.txt")
            try:
                with open(rules_path, "r", encoding="utf-8") as f:
                    print("\n================ SZABÁLYZAT ================")
                    print(f.read())
                    print("===========================================\n")
            except FileNotFoundError:
                print("HIBA: Nem találom a szabályzatot (szabalyzat.txt).\n")
            continue
        try:
            num_val = int(choice)
        except Exception:
            print("Hibás érték. Adj meg 2 és 6 közötti számot, vagy '?' a szabályzathoz.\n")
            continue
        if 2 <= num_val <= 6:
            num = num_val
        else:
            print("Hibás érték. Csak 2 és 6 közötti szám fogadható el.\n")

    # Deck size selection (min 10, recommended 40)
    deck_size = 40
    try:
        ds_in = input("Pakliméret? (10-60, Ajánlott = 40): ").strip()
        if ds_in:
            deck_size = int(ds_in)
    except Exception:
        deck_size = 40
    if deck_size < 10:
        deck_size = 10
    if deck_size > 60:
        deck_size = 60

    players = []
    player_name = input("Add meg a játékos nevét: ").strip()
    if not player_name:
        player_name = "Játékos"
    players.append(Player(player_name))
    for i in range(1, num):
        players.append(Player(f"Robot {i}", is_bot=True))
    # Expose players list globally so abilities (Devil Crok) can access all players' lost_cards
    global GLOBAL_PLAYERS
    GLOBAL_PLAYERS = players



    # Create decks and draw starting hands (4 cards at the beginning)
    for p in players:
        p.deck = create_deck(deck_size)
        for _ in range(4):
            p.draw_card()
    time.sleep(EVENT_DELAY_SECONDS)
    # Randomly choose starting attacker according to the rules
    attacker_index = random.randint(0, len(players)-1)
    defender_index = (attacker_index + 1) % len(players)
    print(f"\nElső támadó: {players[attacker_index].name}")
    round_number = 1

    while True:
        global IN_ROUND
        IN_ROUND = True
        _set_delay_active(False)
        print_block_header(f"{round_number}. KÖR")
        print()
        ordered_players = get_turn_order(players, attacker_index)
        # Check if any player has force_blind_next flag (Pancrator Crok's ability)
        forced_player = None
        forced_candidates = [p for p in players if getattr(p, 'force_blind_next', False)]
        if forced_candidates:
            forced_player = max(forced_candidates, key=lambda p: getattr(p, 'force_blind_seq', 0))

        # Reset abilities for this battle
        for p in players:
            p.reset_abilities_for_battle()

        # Apply Sensei buff: if flagged, add +1 to ALL cards owned by the player
        # Must happen before any forced blind draws are removed from decks.
        apply_sensei_bonuses(players)

        # Húzás: vakharc esetén a kör eleji húzás a vakharcba kerül, nem a kézbe
        # First round already starts with 4 cards
        forced_blind_draws = {}
        if round_number > 1:
            if forced_player is None:
                for p in players:
                    p.draw_card()
            else:
                for p in players:
                    if p.deck:
                        forced_blind_draws[p] = p.deck.pop(0)
                    elif p.hand:
                        forced_blind_draws[p] = p.hand.pop(random.randint(0, len(p.hand)-1))
                    else:
                        forced_blind_draws[p] = None

        if round_number == 1:
            score_players = players
        else:
            score_players = sorted(players, key=lambda p: len(p.won_cards), reverse=True)
        print_scoreboard(score_players)

        # Check for any player out of cards
        for p in players:
            if len(p.deck) == 0 and len(p.hand) == 0:
                print("Valakinek elfogyott a lapja! Játék vége.")
                # Determine winner by group victories / total wins
                standings = sorted(players, key=lambda x: (x.get_group_victories(), len(x.won_cards)), reverse=True)
                winner = standings[0]
                print(f"\n🎉 A győztes: {winner.name} ({winner.get_group_victories()} csoportgyőzelem, {len(winner.won_cards)} összes győzelem)")
                return

        # Támadás
        _set_delay_active(True)
        chosen_stat = ""
        # Check if any player has force_attack_next flag (Boy Crok's ability)
        force_attack_player = None
        attack_candidates = [p for p in players if getattr(p, 'force_attack_next', False)]
        if attack_candidates:
            force_attack_player = max(attack_candidates, key=lambda p: getattr(p, 'force_attack_seq', 0))
        
        # If a player forced next attack, they become the attacker; otherwise use standard rotation
        if force_attack_player is not None:
            attacker_index = players.index(force_attack_player)
            defender_index = (attacker_index + 1) % len(players)
            boy_emoji = get_group_emoji("jolly") or "⚡"
            print(f"\n{boy_emoji} {force_attack_player.name} támad a körben (Boy Crok: Pimasz csínytevés)!")
            for p in players:
                p.force_attack_next = False
                p.force_attack_seq = 0
        
        attacker = players[attacker_index]
        defender = players[defender_index]
        attacker_card = None
        # Flag to indicate we're doing a forced blind round (Pancrator)
        is_force_blind_round = False
        
        if forced_player is not None:
            # Global forced blind: the flagged player causes the next battle to be a blind fight
            print(f"\n⚡ Vakharc következik (kikényszerítve: {forced_player.name})")
            attacker = players[attacker_index]
            defender = players[defender_index]
            # Forced player chooses the stat to be used in the upcoming blind fight
            if not forced_player.is_bot:
                print(f"{forced_player.name}, válaszd meg a vakharc típusát: (1) Erő, (2) Intelligencia, (3) Reflex")
                chosen_stat = choose_stat_human()
            else:
                chosen_stat = random.choice(["erő", "intelligencia", "reflex"])

            # All players draw blind cards for this battle (face-down; do NOT reveal the cards now)
            is_force_blind_round = True
            played_defender_cards = {}
            # Attacker draws blind (use round-start draw if available)
            attacker_card = forced_blind_draws.get(attacker)
            if attacker_card is None:
                attacker_card = attacker.get_blind_card()
            if not attacker_card:
                print("Valakinek elfogyott minden lapja! Vége.")
                return
            for di in range(len(players)):
                if di == attacker_index:
                    continue
                p = players[di]
                card = forced_blind_draws.get(p)
                if card is None:
                    card = p.get_blind_card()
                if not card:
                    print("Valakinek elfogyott minden lapja! Vége.")
                    return
                played_defender_cards[di] = card

            print("Mindenki kirakta a paklija legfelső lapját.")

            # Reset all forced blind flags after use
            for p in players:
                p.force_blind_next = False
                p.force_blind_seq = 0
        elif not attacker.is_bot:
            print(f"\n{attacker.name} a TÁMADÓ!")
            # Apply hand display bonuses (e.g., Army Crok passive) before showing hand
            apply_hand_display_bonuses(attacker, players, is_defending=False)
            print(f"{attacker.name} lapjai:")
            hand_snapshot = list(attacker.hand)
            for line in format_hand_display(hand_snapshot):
                print(line)
            print("Válassz típust: (1) Erő, (2) Intelligencia, (3) Reflex")
            chosen_stat = choose_stat_human()
            choice = choose_int_in_range("Válassz kártyát (szám): ", 1, len(hand_snapshot)) - 1
            selected = hand_snapshot[choice]
            if selected in attacker.hand:
                attacker.hand.remove(selected)
                attacker_card = selected
            else:
                attacker_card = attacker.play_card(choice)
            # If the chosen card had display-only bonuses, remove them from the played card
            remove_hand_display_bonus(attacker_card)
            # Restore hand display bonuses for remaining cards
            restore_hand_display_bonuses(attacker)
            # Attacker ability decision will be asked during the ability activation phase
        else:
            # Bot támad
            print(f"\n{attacker.name} támad!")
            chosen_stat = random.choice(["erő", "intelligencia", "reflex"])
            # Choose the best card for the chosen stat
            if attacker.hand:
                best_idx = max(range(len(attacker.hand)), key=lambda i: attacker.hand[i].stats.get(chosen_stat, 0))
                attacker_card = attacker.play_card(best_idx)
            else:
                attacker_card = attacker.play_card(0)
            print(f"{attacker.name} választott. Harc típusa: {chosen_stat.upper()}")

        # Védekezés: minden más játékos lerak egy védőlapot (óramutató járása szerint, ha nem vakharc)
        num_players_in_game = len(players)
        defender_order = [(attacker_index + offset) % num_players_in_game for offset in range(1, num_players_in_game)]
        if not is_force_blind_round:
            played_defender_cards = {}
            # Defender order: clockwise from attacker (attacker_index + 1, +2, +3, ...)
            for di in defender_order:
                p = players[di]
                if not p.is_bot:
                    # Apply hand display bonuses (e.g., Boy Crok when defending, Army Crok always)
                    apply_hand_display_bonuses(p, players, is_defending=True)
                    print(f"\n{p.name}, VÉDEKEZEL! ({chosen_stat.upper()})")
                    print("A lapjaid:")
                    hand_snapshot = list(p.hand)
                    for line in format_hand_display(hand_snapshot):
                        print(line)
                    choice = choose_int_in_range("Válassz kártyát (szám): ", 1, len(hand_snapshot)) - 1
                    selected = hand_snapshot[choice]
                    if selected in p.hand:
                        p.hand.remove(selected)
                        played_defender_cards[di] = selected
                    else:
                        played_defender_cards[di] = p.play_card(choice)
                    # If the chosen card had display-only bonuses, remove them from the played card
                    remove_hand_display_bonus(played_defender_cards[di])
                    # Restore any display bonuses for remaining cards
                    restore_hand_display_bonuses(p)
                else:
                    # Bot defender - also follows clockwise order
                    played_defender_cards[di] = p.play_card(random.randint(0, len(p.hand)-1))
                    print(f"{p.name} kiválasztotta a védekező lapját.")
        else:
            # Vakharc: mindenki már kirakta a paklija legfelső lapját (face-down)
            pass

        # Felfedés (attacker vs all defenders) - header will be printed with stat once below
        # Collect defender cards from the played_defender_cards map in clockwise order
        defender_cards = {di: played_defender_cards[di] for di in defender_order}
        # Trigger passive abilities for attacker and defenders now so their temporary buffs are visible immediately
        trigger_initial_passives(attacker_card, defender_cards, attacker_index, defender_index, players)

        # Print defenders — only announce selection; full details are shown at reveal
        if not is_force_blind_round:
            print("\nMinden védő kiválasztotta a lapját. Most következik a felfedés.")
            # (Lapok részleteit csak a felfedéskor mutatjuk.)
            print()

# --- HARC KIÉRTÉKELÉS (LOOP A VAKHARC MIATT) ---
        winner_of_round = None
        att_card = attacker_card
        # Keep a reference to an arbitrary defender index for legacy logic where needed
        first_def_index = next(iter(defender_cards))
        current_stat = chosen_stat

        while True:
            print_block_header(f"FELFEDÉS ({current_stat.upper()})")
            defender_list = [(players[di].name, defender_cards[di]) for di in defender_order]
            for line in format_battle_display(attacker.name, att_card, defender_list):
                print(line)
            _block_pause()

            # KÉPESSÉGEK AKTIVÁLÁSA (a felfedés után, kiértékelés előtt)
            # Sorrend: 1. Azonnali képességek (immediate, egyszerre kezelve), 2. Aktív képességek (multi-round with reserve)

            winning_att_card = att_card

            battlefield_cards = [att_card] + list(defender_cards.values())
            samurai_cards = [c for c in battlefield_cards if c and getattr(c, 'ability_code', None) == 'disable_opponent_ability']
            skip_abilities = False
            if samurai_cards:
                for c in battlefield_cards:
                    if c is None:
                        continue
                    if c not in samurai_cards:
                        c._abilities_disabled_in_battle = True
                for sc in samurai_cards:
                    sc.ability_used = True
                print_block_header("KÉPESSÉGEK AKTIVÁLÁSA")
                samurai_card = samurai_cards[0]
                samurai_owner = players[attacker_index] if samurai_card is att_card else None
                if samurai_owner is None:
                    for di, dc in defender_cards.items():
                        if dc is samurai_card:
                            samurai_owner = players[di]
                            break
                if samurai_owner is None:
                    samurai_owner = players[attacker_index]
                ability_effect(samurai_owner, samurai_card, "hatástalanította a csatában lévő ellenfelek képességeit.")
                skip_abilities = True
            else:
                print_block_header("KÉPESSÉGEK AKTIVÁLÁSA")
                # 1. AZONNALI KÉPESSÉGEK (egyszerre kezelve, nem körsorrend szerint)
                # Gyűjtsük össze az összes azonnali képességet a harctéren, majd egyetlen fázisban futtassuk le.
                immediate_queue = []
                if att_card.ability_type == "immediate" and att_card.ability_code != "none" and not att_card.ability_used:
                    immediate_queue.append((attacker_index, att_card, True))
                num_players_in_game = len(players)
                for offset in range(1, num_players_in_game):
                    di = (attacker_index + offset) % num_players_in_game
                    if di not in defender_cards:
                        continue
                    dc = defender_cards[di]
                    if dc.ability_type == "immediate" and dc.ability_code != "none" and not dc.ability_used:
                        immediate_queue.append((di, dc, False))

                for di, dc, is_att in immediate_queue:
                    is_human = not players[di].is_bot
                    ability_used, new_card, new_ft = trigger_ability(dc, players[di], players[attacker_index], is_human, is_att, battle_context=make_battle_context(att_card, defender_cards, attacker_index, players, current_stat))
                    if ability_used:
                        if is_att:
                            # If the ability replaced the attacker's card (e.g., Master swapped), use the new card for further checks
                            if new_card is not None and new_card is not att_card:
                                att_card = new_card
                            winning_att_card = new_card
                        else:
                            defender_cards[di] = new_card
                        if new_ft:
                            current_stat = new_ft
            
            # 2. AKTÍV KÉPESSÉGEK (multi-round: players can reserve and retry)
            if not skip_abilities:
                ability_round = 1
                while True:
                    # Determine if any ability is still pending before printing extra rounds
                    pending_exists = False
                    if att_card.ability_code != "none":
                        if att_card.ability_type == "passive":
                            pending_exists = pending_exists or (not att_card.ability_used and not att_card.ability_permanently_skipped)
                        elif att_card.ability_type == "active" or (att_card.ability_code == "disable_underworld_or_draw" and getattr(att_card, '_priest_pending_draw', False)):
                            pending_exists = pending_exists or (not att_card.ability_used and not att_card.ability_permanently_skipped and not att_card.ability_reserved)

                    for dc in defender_cards.values():
                        if dc.ability_code == "none":
                            continue
                        if dc.ability_type == "passive":
                            if not dc.ability_used and not dc.ability_permanently_skipped:
                                pending_exists = True
                                break
                        elif dc.ability_type == "active" or (dc.ability_code == "disable_underworld_or_draw" and getattr(dc, '_priest_pending_draw', False)):
                            if not dc.ability_used and not dc.ability_permanently_skipped:
                                pending_exists = True
                                break

                    if not pending_exists:
                        break

                    if ability_round > 1:
                        print_block_header(f"KÉPESSÉGEK AKTIVÁLÁSA (KÖR {ability_round})")
                    
                    action_taken = False

                    # Ordered abilities: attacker, then clockwise (passive or active)
                    num_players_in_game = len(players)
                    ordered_indices = [attacker_index] + [
                        (attacker_index + offset) % num_players_in_game
                        for offset in range(1, num_players_in_game)
                        if (attacker_index + offset) % num_players_in_game in defender_cards
                    ]

                    for di in ordered_indices:
                        is_att = di == attacker_index
                        card = att_card if is_att else defender_cards.get(di)
                        if card is None:
                            continue

                        # Passive ability
                        if card.ability_type == "passive" and card.ability_code != "none" and not card.ability_used and not card.ability_permanently_skipped:
                            is_human = not players[di].is_bot
                            ability_used, new_card, new_ft = trigger_ability(card, players[di], players[attacker_index], is_human, is_att, battle_context=make_battle_context(att_card, defender_cards, attacker_index, players, current_stat), silent=False)
                            if ability_used:
                                if is_att:
                                    if new_card is not None and new_card is not att_card:
                                        att_card = new_card
                                    winning_att_card = new_card
                                    if hasattr(att_card, '_swap_attacker_card'):
                                        att_card = att_card._swap_attacker_card
                                        winning_att_card = att_card
                                        delattr(att_card, '_swap_attacker_card')
                                else:
                                    defender_cards[di] = new_card
                                    if hasattr(card, '_swap_attacker_card'):
                                        att_card = card._swap_attacker_card
                                        winning_att_card = att_card
                                        delattr(card, '_swap_attacker_card')
                                if new_ft:
                                    current_stat = new_ft
                                action_taken = True
                            _block_pause()
                            continue

                        # Active ability
                        if (
                            (card.ability_type == "active" or (
                                card.ability_code == "disable_underworld_or_draw"
                                and getattr(card, '_priest_pending_draw', False)
                                and (not getattr(card, '_entered_battle_via_swap', False) or ability_round > 1)
                            ))
                            and card.ability_code != "none" and not card.ability_used and not card.ability_permanently_skipped
                        ):
                            is_human = not players[di].is_bot
                            ability_used, new_card, new_ft = trigger_ability(card, players[di], players[attacker_index], is_human, is_att, battle_context=make_battle_context(att_card, defender_cards, attacker_index, players, current_stat))
                            if ability_used:
                                if is_att:
                                    if new_card is not None and new_card is not att_card:
                                        att_card = new_card
                                    winning_att_card = new_card
                                    if hasattr(att_card, '_swap_attacker_card'):
                                        att_card = att_card._swap_attacker_card
                                        winning_att_card = att_card
                                        delattr(att_card, '_swap_attacker_card')
                                else:
                                    defender_cards[di] = new_card
                                    if hasattr(card, '_swap_attacker_card'):
                                        att_card = card._swap_attacker_card
                                        winning_att_card = att_card
                                        delattr(card, '_swap_attacker_card')
                                if new_ft:
                                    current_stat = new_ft
                                # Trigger immediate abilities for any cards that entered via swap
                                battle_ctx = make_battle_context(att_card, defender_cards, attacker_index, players, current_stat)
                                pending_cards = [att_card] + list(defender_cards.values())
                                for pcard in pending_cards:
                                    if not getattr(pcard, '_immediate_on_entry_pending', False):
                                        continue
                                    # Clear pending flag regardless to avoid repeated attempts
                                    pcard._immediate_on_entry_pending = False
                                    if pcard.ability_type != "immediate" or pcard.ability_code == "none" or pcard.ability_used:
                                        continue
                                    # Determine owner and role
                                    p_is_att = (pcard is att_card)
                                    owner_idx = attacker_index
                                    if not p_is_att:
                                        for idx, dc in defender_cards.items():
                                            if dc is pcard:
                                                owner_idx = idx
                                                break
                                    is_human_owner = not players[owner_idx].is_bot
                                    imm_used, imm_new_card, imm_new_ft = trigger_ability(pcard, players[owner_idx], players[attacker_index], is_human_owner, p_is_att, battle_context=battle_ctx)
                                    if imm_used:
                                        if p_is_att:
                                            if imm_new_card is not None and imm_new_card is not att_card:
                                                att_card = imm_new_card
                                            winning_att_card = imm_new_card
                                        else:
                                            if imm_new_card is not None:
                                                defender_cards[owner_idx] = imm_new_card
                                        if imm_new_ft:
                                            current_stat = imm_new_ft
                                action_taken = True
                            elif card.ability_reserved:
                                action_taken = True
                            _block_pause()
                    
                    # Check if all players have made a final decision (used or permanently skipped)
                    all_decided = True
                    if att_card.ability_code != "none":
                        if att_card.ability_type == "passive":
                            if not att_card.ability_used and not att_card.ability_permanently_skipped:
                                all_decided = False
                        elif att_card.ability_type == "active" or (att_card.ability_code == "disable_underworld_or_draw" and getattr(att_card, '_priest_pending_draw', False)):
                            if not att_card.ability_used and not att_card.ability_permanently_skipped and not att_card.ability_reserved:
                                all_decided = False

                    for dc in defender_cards.values():
                        if dc.ability_code == "none":
                            continue
                        if dc.ability_type == "passive":
                            if not dc.ability_used and not dc.ability_permanently_skipped:
                                all_decided = False
                        elif dc.ability_type == "active" or (dc.ability_code == "disable_underworld_or_draw" and getattr(dc, '_priest_pending_draw', False)):
                            if not dc.ability_used and not dc.ability_permanently_skipped:
                                all_decided = False

                    # If everyone decided, exit loop
                    if all_decided:
                        break

                    # If no one took action in round 1, allow a second round (e.g., Priest pending draw after swap)
                    if not action_taken:
                        if ability_round == 1:
                            ability_round += 1
                            continue
                        break
                    
                    ability_round += 1

            _block_pause()

            # Immediate win check (e.g., Police Crok)
            if hasattr(winning_att_card, '_instant_win') and winning_att_card._instant_win:
                print(f"\n -> NYERTES: {attacker.name}!")
                attacker.add_won_card(winning_att_card)
                if hasattr(winning_att_card, 'battle_royal_card'):
                    attacker.add_won_card(winning_att_card.battle_royal_card)
                    delattr(winning_att_card, 'battle_royal_card')
                for di, dc in defender_cards.items():
                    check_and_trigger_loss_abilities(dc, players[di], from_battle=True)
                    players[di].lost_cards.append(dc)
                    if hasattr(dc, 'battle_royal_card'):
                        players[di].lost_cards.append(dc.battle_royal_card)
                        delattr(dc, 'battle_royal_card')
                winner_of_round = attacker
                break
            instant_defender_idx = None
            for di, dc in defender_cards.items():
                if hasattr(dc, '_instant_win') and dc._instant_win:
                    instant_defender_idx = di
                    break
            if instant_defender_idx is not None:
                winning_defender = players[instant_defender_idx]
                winning_def_card = defender_cards[instant_defender_idx]
                print(f"\n -> NYERTES: {winning_defender.name}!")
                winning_defender.add_won_card(winning_def_card)
                if hasattr(winning_def_card, 'battle_royal_card'):
                    winning_defender.add_won_card(winning_def_card.battle_royal_card)
                    delattr(winning_def_card, 'battle_royal_card')
                check_and_trigger_loss_abilities(winning_att_card, attacker, from_battle=True)
                attacker.lost_cards.append(winning_att_card)
                if hasattr(winning_att_card, 'battle_royal_card'):
                    attacker.lost_cards.append(winning_att_card.battle_royal_card)
                    delattr(winning_att_card, 'battle_royal_card')
                # All other defenders lose their played cards
                for di, dc in defender_cards.items():
                    if di == instant_defender_idx:
                        continue
                    check_and_trigger_loss_abilities(dc, players[di], from_battle=True)
                    players[di].lost_cards.append(dc)
                    if hasattr(dc, 'battle_royal_card'):
                        players[di].lost_cards.append(dc.battle_royal_card)
                        delattr(dc, 'battle_royal_card')
                winner_of_round = winning_defender
                break
            
            # Display cards AFTER abilities are triggered (so buffs are visible)
            print_block_header(f"VÉGSŐ ÉRTÉKEK: {current_stat.upper()}")
            defender_list = [(players[di].name, dc) for di, dc in defender_cards.items()]
            for line in format_battle_display(attacker.name, winning_att_card, defender_list, show_ability=False, stat_focus_key=current_stat):
                print(line)
            _block_pause()
            
            # Összes játékos értéke alapján döntünk (attacker/defender szerep nem számít)
            all_cards = {attacker_index: winning_att_card}
            for di, dc in defender_cards.items():
                all_cards[di] = dc
            values = {
                idx: get_base_stat(card, current_stat) + card.tmp_bonuses.get(current_stat, 0)
                for idx, card in all_cards.items()
            }
            max_value = max(values.values()) if values else -1
            top_idxs = [idx for idx, v in values.items() if v == max_value]

            # Sheriff (win_on_draw): ha döntetlen van a legjobb értéken és csak egy ilyen képességű lap van
            if len(top_idxs) > 1:
                sheriff_idxs = [idx for idx in top_idxs if hasattr(all_cards[idx], '_win_on_draw')]
                if len(sheriff_idxs) == 1:
                    top_idxs = sheriff_idxs
                elif len(sheriff_idxs) > 1:
                    # Több Sheriff döntetlenben: nincs előny, marad döntetlen
                    pass

            # Ha egyetlen nyertes van
            if len(top_idxs) == 1:
                win_idx = top_idxs[0]
                winner = players[win_idx]
                win_card = all_cards[win_idx]
                print(f"\n -> NYERTES: {winner.name}!")
                winner.add_won_card(win_card)
                if hasattr(win_card, 'battle_royal_card'):
                    winner.add_won_card(win_card.battle_royal_card)
                    delattr(win_card, 'battle_royal_card')

                # Mindenki más veszít
                for idx, card in all_cards.items():
                    if idx == win_idx:
                        continue
                    check_and_trigger_loss_abilities(card, players[idx], from_battle=True)
                    players[idx].lost_cards.append(card)
                    if hasattr(card, 'battle_royal_card'):
                        players[idx].lost_cards.append(card.battle_royal_card)
                        delattr(card, 'battle_royal_card')
                winner_of_round = winner
                break

            # 2. DÖNTETLEN - VAKHARC AZONNAL FOLYTATÓDIK (csak a legjobb értékűek között)
            else:
                print("\nDÖNTETLEN!")
                print("A játékosok Crokjai a vesztesek közé kerülnek és vakharc indul!")
                _block_pause()

                participants = list(all_cards.keys())

                # A döntetlenben résztvevők Pancrator képessége ne indítson újabb vakharcot
                for idx in participants:
                    setattr(players[idx], '_suppress_force_blind_next', True)

                # A nem résztvevők azonnal veszítenek
                for idx, card in all_cards.items():
                    if idx in participants:
                        continue
                    check_and_trigger_loss_abilities(card, players[idx], from_battle=True)
                    players[idx].lost_cards.append(card)
                    if hasattr(card, 'battle_royal_card'):
                        players[idx].lost_cards.append(card.battle_royal_card)
                        delattr(card, 'battle_royal_card')

                # A döntetlen résztvevőinek lapjai is a vesztesek közé kerülnek
                for idx in participants:
                    card = all_cards[idx]
                    check_and_trigger_loss_abilities(card, players[idx], from_battle=True)
                    players[idx].lost_cards.append(card)
                    if hasattr(card, 'battle_royal_card'):
                        players[idx].lost_cards.append(card.battle_royal_card)
                        delattr(card, 'battle_royal_card')

                for idx in participants:
                    if hasattr(players[idx], '_suppress_force_blind_next'):
                        delattr(players[idx], '_suppress_force_blind_next')

                # Az új támadó a harc legutolsó védő játékosa (turn-order szerinti utolsó védő)
                if defender_order:
                    new_attacker_index = defender_order[-1]
                else:
                    new_attacker_index = attacker_index
                new_attacker = players[new_attacker_index]
                
                print(f"\n😵 Vakharc: {new_attacker.name} lesz az új támadó!")
                
                # Új támadó választja meg a harc típusát
                if not new_attacker.is_bot:
                    print(f"{new_attacker.name}, válaszd meg a vakharc típusát: (1) Erő, (2) Intelligencia, (3) Reflex")
                    new_chosen_stat = choose_stat_human()
                else:
                    new_chosen_stat = random.choice(["erő", "intelligencia", "reflex"])
                
                # Vakharc: minden játékos tesz le lapot
                print("\nA játékosok vakon lehelyeztek egy lapot.")
                new_played_defender_cards = {}

                # Sensei buff should only apply to the next single fight
                remove_sensei_bonuses(players)
                # Apply Sensei buff to the immediate blind fight if it was triggered
                apply_sensei_bonuses(players)

                # Új támadó vak lapja
                new_att_card = choose_blind_card_for_player(new_attacker, is_human_player=not new_attacker.is_bot)
                if not new_att_card:
                    print("Valakinek elfogyott minden lapja! Vége.")
                    return
                
                # Többi játékos vak lapja
                for di in participants:
                    if di == new_attacker_index:
                        continue
                    p = players[di]
                    new_card = choose_blind_card_for_player(p, is_human_player=not p.is_bot)
                    if not new_card:
                        print("Valakinek elfogyott minden lapja! Vége.")
                        return
                    new_played_defender_cards[di] = new_card

                # Announce all participants placed their blind cards (already stated above)
                # Átállítjuk az aktuális harci állapotot a vakharc résztvevőire
                attacker_index = new_attacker_index
                attacker = new_attacker
                attacker_card = new_att_card
                defender_cards = new_played_defender_cards
                chosen_stat = new_chosen_stat
                num_players_in_game = len(players)
                defender_order = [
                    (attacker_index + offset) % num_players_in_game
                    for offset in range(1, num_players_in_game)
                    if (attacker_index + offset) % num_players_in_game in defender_cards
                ]

                # Frissítsük a rövid változókat is
                att_card = attacker_card
                first_def_index = next(iter(defender_cards))
                defender_index = first_def_index
                current_stat = chosen_stat

                # Reset per-battle ability flags for the new blind fight
                reset_card_for_battle(attacker_card)
                for dc in defender_cards.values():
                    reset_card_for_battle(dc)

                # Trigger passive abilities for attacker and defenders now so their temporary buffs are visible immediately
                trigger_initial_passives(attacker_card, defender_cards, attacker_index, defender_index, players)
                
                # Vissza a while True ciklus elejére (felfedés és kiértékelés)
                continue


        # --- KÖR VÉGE, KÖVETKEZŐ KÖR ELŐKÉSZÍTÉSE ---
        # A szabály: A győztes lesz a következő kör támadója
        if winner_of_round is not None:
            attacker_index = players.index(winner_of_round)
            defender_index = (attacker_index + 1) % len(players)

        # --- WIN CONDITIONS CHECK ---
        # Check if any player reached 6 victories in a group
        for p in players:
            if p.get_group_victories() >= 6:
                print("\n================ JÁTÉK VÉGE ================")
                print(f"🎉 {p.name} nyert: 6 különböző csoportgyőzelem!")
                return

        # Display simple standings
        # Sensei buff expires after this round ends
        remove_sensei_bonuses(players)
        _block_pause()
        display_players_group_standings(players)

        # Condition: Someone played their last Crok -> end game and rank players
        for p in players:
            if len(p.deck) == 0 and len(p.hand) == 0:
                print("\n================ JÁTÉK VÉGE ================")
                standings = sorted(players, key=lambda x: (x.get_group_victories(), len(x.won_cards)), reverse=True)
                print("Végső sorrend:")
                for i, wp in enumerate(standings, 1):
                    print(f"{i}. {wp.name} - csoportgyőzelem: {wp.get_group_victories()} - összes győzelem: {len(wp.won_cards)}")
                return

        _block_pause()
        round_number += 1
        _set_delay_active(False)
        IN_ROUND = False

# Ez a sor indítja el a main függvényt:
if __name__ == "__main__":
    main()