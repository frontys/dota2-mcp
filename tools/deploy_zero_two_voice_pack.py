"""
Deploys 100% genuine Russian Zero Two (Cleo-chan, AniLibria) voice lines for Dota 2 Coach.
Replaces generic TTS with authentic high-fidelity anime acting.
"""

import contextlib
import shutil
import sys
from pathlib import Path

with contextlib.suppress(AttributeError, OSError, ValueError):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(r"c:\AI\dota2-mcp")
AUDIO_DIR = BASE_DIR / "audio_cute"
CUES_DIR = Path(r"C:\Users\fronty\Downloads\ZeroTwo_Voice_Cues")

MAPPING = {
    # Match flow
    "match_found.mp3": ("Ep01/Ep01_068_А_ты_готов_к_смерти.mp3", "А ты готов к смерти?"),
    "game_start.mp3": ("Ep05/Ep05_001_О_Привет_любимый.mp3", "О! Привет, любимый."),
    "victory.mp3": ("Ep02/Ep02_003_Ты_был_восхитителен_мой_любимый.mp3", "Ты был восхитителен, мой любимый."),

    # Runes
    "water_15s.mp3": ("Ep01/Ep01_008_Сейчас_бы_искупаться.mp3", "Сейчас бы искупаться."),
    "river_15s.mp3": ("Ep01/Ep01_036_Вкус_опасности.mp3", "Вкус опасности."),
    "wisdom_20s.mp3": ("Ep07/Ep07_001_Любимый_пойдём.mp3", "Любимый, пойдём!"),
    # bounty_20s.mp3 keeps neural F5-TTS or we can use another line if desired

    # Creep stack
    "stack_53s.mp3": ("Ep01/Ep01_046_Время_вышло.mp3", "Время вышло."),

    # Neutral items T1-T5
    "neutral_tier1.mp3": ("Ep01/Ep01_024_Но_ты_хотел_мне_помочь.mp3", "Но… ты хотел мне помочь, это похвально."),
    "neutral_tier2.mp3": ("Ep06/Ep06_002_Смотри_любимый.mp3", "Смотри, любимый."),
    "neutral_tier3.mp3": ("Ep08/Ep08_028_Любимый_держись_за_меня_крепче.mp3", "Любимый, держись за меня крепче."),
    "neutral_tier4.mp3": ("Ep20/Ep20_002_Каждый_из_них_сильнее_любого.mp3", "Каждый из них сильнее любого из вас."),
    "neutral_tier5.mp3": ("Ep12/Ep12_047_Я_всех_их_уничтожу_и.mp3", "Я всех их уничтожу и стану человеком!"),

    # Objectives (Roshan & Tormentor)
    "roshan_killed.mp3": ("Ep01/Ep01_055_В_смысле_Охочусь_на_чудищ.mp3", "В смысле? Охочусь на чудищ."),
    "roshan_window_warning.mp3": ("Ep04/Ep04_025_Любимый_похоже_время_вышло.mp3", "Любимый, похоже, время вышло."),
    "roshan_window_open.mp3": ("Ep11/Ep11_009_Ах_ты_чудище.mp3", "Ах ты чудище!"),
    "roshan_respawn.mp3": ("Ep06/Ep06_006_Скорей_бы_в_бой.mp3", "Скорей бы в бой."),
    "roshan_move_20s.mp3": ("Ep01/Ep01_056_Мне_пора.mp3", "Мне пора."),
    "tormentor_30s.mp3": ("Ep12/Ep12_042_Убей_побольше_чудищ_и_сделай.mp3", "Убей побольше чудищ!"),
}


def deploy():
    print("=== Deploying Authentic Zero Two (AniLibria - Cleo-chan) Audio Pack ===")
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    deployed = 0
    for target_name, (rel_path, quote) in MAPPING.items():
        src_path = CUES_DIR / rel_path
        dst_path = AUDIO_DIR / target_name
        if src_path.exists():
            shutil.copyfile(src_path, dst_path)
            print(f"  ✓ {target_name:24s} -> \"{quote}\"")
            deployed += 1
        else:
            print(f"  ✖ File not found: {src_path}")

    print(f"\nSuccessfully deployed {deployed} authentic cues to {AUDIO_DIR}")


if __name__ == "__main__":
    deploy()
