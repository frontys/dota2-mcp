"""
Generates high-quality Russian Cute Anime Girl Voice Pack for Dota 2 Voice Coach.
Uses Neural TTS with anime waifu pitch-shift and friendly cheerful intonation.
Zero API cost, zero tokens.
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

VOICE = "ru-RU-SvetlanaNeural"
PITCH = "+24Hz"  # Cute anime girl pitch
RATE = "+8%"    # Slightly faster lively anime speech tempo

PHRASES = {
    # Match states
    "match_found.mp3": "Матч найден! Жми скорее принять, я уже в предвкушении!",
    "game_start.mp3": "Добро пожаловать в Доту! Удачной игры, я верю в тебя!",
    "victory.mp3": "Ура, победа! Ты сыграл просто потрясающе!",

    # Runes
    "bounty_20s.mp3": "Руны богатства через 15 секунд! Забери своё золото!",
    "wisdom_20s.mp3": "Руны мудрости через 15 секунд! Пойдём отберём их у шрайна!",
    "water_15s.mp3": "Руны воды на реке через 15 секунд! Заряди ботл!",
    "river_15s.mp3": "Активная руна реки через 15 секунд! Проверь точку!",

    # Jungle & Neutrals
    "stack_53s.mp3": "Время для стака! Сделай удар по лесным крипам на пятьдесят третьей секунде!",
    "neutral_tier1.mp3": "Открылись нейтралки первого тира! Быстрее выбивай первую шмотку!",
    "neutral_tier2.mp3": "Уже семнадцатая минута! Доступны нейтралки второго тира!",
    "neutral_tier3.mp3": "Двадцать седьмая минута! Нейтральные предметы третьего тира в игре!",
    "neutral_tier4.mp3": "Тридцать седьмая минута! Доступен четвёртый тир нейтралок!",
    "neutral_tier5.mp3": "Шестидесятая минута! Время тир пять нейтралок, пойдём заканчивать!",

    # Objectives (Roshan & Tormentor)
    "roshan_killed.mp3": "Рошан повержен! Окно респавна откроется через восемь минут!",
    "roshan_window_warning.mp3": "Внимание! Окно Рошана откроется через 15 секунд, будь начеку!",
    "roshan_window_open.mp3": "Окно Рошана открыто! Он может появиться прямо сейчас!",
    "roshan_respawn.mp3": "Прошло одиннадцать минут! Рошан гарантированно возродился в логове!",
    "roshan_move_20s.mp3": "Смена времени суток! Рошан переходит в другое логово!",
    "tormentor_30s.mp3": "Терзатель появится через 30 секунд! Заберём бесплатный шард!",
}


async def generate_single(filename: str, text: str):
    target = AUDIO_DIR / filename
    print(f"Generating '{filename}': \"{text}\"")
    comm = edge_tts.Communicate(text, voice=VOICE, pitch=PITCH, rate=RATE)
    await comm.save(str(target))
    size_kb = target.stat().st_size / 1024
    print(f" -> Saved {filename} ({size_kb:.1f} KB)")


async def main():
    print(f"=== Generating Russian Cute Anime Voice Pack ({len(PHRASES)} cues) ===")
    print(f"Voice: {VOICE} | Pitch: {PITCH} | Rate: {RATE}\n")
    for filename, text in PHRASES.items():
        await generate_single(filename, text)
        await asyncio.sleep(0.15)
    print("\n=== ALL ANIME VOICE PACK CUES GENERATED SUCCESSFULLY! ===")


if __name__ == "__main__":
    asyncio.run(main())
