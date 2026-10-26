"""
Generates high-quality Zero Two (02 from Darling in the Franxx) Russian Voice Pack for Dota 2 Voice Coach.
Style: Cleo-chan (AniLibria) — seductive, daring, confident, playful anime heroine calling player "Милый!".
Zero GPU latency, 100% offline playback via WinMM.
"""

import asyncio
import os
import sys
from pathlib import Path
import edge_tts

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
AUDIO_DIR = BASE_DIR / "audio_cute"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# Acoustic profile tuned to Zero Two (AniLibria / Cleo-chan):
# Mature, seductive, slightly playful with deep warm undertone (+8Hz, +4% rate)
VOICE = "ru-RU-SvetlanaNeural"
PITCH = "+8Hz"
RATE = "+4%"

PHRASES = {
    # Match states
    "match_found.mp3": "Матч найден! Принимай игру, милый, я уже жду тебя!",
    "game_start.mp3": "Привет, милый! Пора показать им, на что мы способны. Не отставай!",
    "victory.mp3": "Вот видишь, милый? Мы с тобой лучшие, я никогда в тебе не сомневалась!",

    # Runes
    "bounty_20s.mp3": "Милый, руны богатства через 15 секунд! Забери своё золото!",
    "wisdom_20s.mp3": "Милый, руны мудрости через 15 секунд! Пойдём отберём их у шрайна!",
    "water_15s.mp3": "Милый, руны воды на реке через 15 секунд! Наполни ботл!",
    "river_15s.mp3": "Активная руна реки через 15 секунд, милый! Проверь точку!",

    # Jungle & Neutrals
    "stack_53s.mp3": "Милый, стакай крипов прямо сейчас на пятьдесят третьей секунде!",
    "neutral_tier1.mp3": "Милый, открылись нейтралки первого тира! Быстрее выбивай первую шмотку!",
    "neutral_tier2.mp3": "Уже семнадцатая минута, милый! Доступны нейтралки второго тира!",
    "neutral_tier3.mp3": "Двадцать седьмая минута! Нейтралки третьего тира в игре, милый!",
    "neutral_tier4.mp3": "Тридцать седьмая минута, милый! Четвёртый тир нейтралок, будь начеку!",
    "neutral_tier5.mp3": "Шестидесятая минута, милый! Пятый тир нейтралок, пойдём и разорвём их трон!",

    # Objectives (Roshan & Tormentor)
    "roshan_killed.mp3": "Рошан повержен! Окно респавна откроется через восемь минут, милый!",
    "roshan_window_warning.mp3": "Милый, окно Рошана откроется через 15 секунд! Будь начеку!",
    "roshan_window_open.mp3": "Окно Рошана открыто! Он может появиться прямо сейчас, милый!",
    "roshan_respawn.mp3": "Прошло одиннадцать минут! Рошан гарантированно возродился, милый!",
    "roshan_move_20s.mp3": "Смена суток, милый! Рошан переходит в другое логово!",
    "tormentor_30s.mp3": "Терзатель появится через 30 секунд, милый! Пойдём заберём бесплатный шард!",
}


async def generate_single(filename: str, text: str):
    target = AUDIO_DIR / filename
    print(f"Generating Zero Two cue '{filename}': \"{text}\"")
    comm = edge_tts.Communicate(text, voice=VOICE, pitch=PITCH, rate=RATE)
    await comm.save(str(target))
    size_kb = target.stat().st_size / 1024
    print(f" -> Saved {filename} ({size_kb:.1f} KB)")


async def main():
    print(f"=== Generating Zero Two (AniLibria style) Voice Pack ({len(PHRASES)} cues) ===")
    print(f"Voice: {VOICE} | Pitch: {PITCH} | Rate: {RATE}\n")
    for filename, text in PHRASES.items():
        await generate_single(filename, text)
        await asyncio.sleep(0.12)
    print("\n=== ALL ZERO TWO VOICE PACK CUES GENERATED SUCCESSFULLY! ===")


if __name__ == "__main__":
    asyncio.run(main())
