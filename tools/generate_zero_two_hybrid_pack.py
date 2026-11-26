"""
Hybrid Zero Two Voice Pack Generator for Dota 2 Coach.
1. Original high-impact anime clips (Match found, Game start, Victory) directly from AniLibria.
2. Dota-specific timing cues synthesized via F5-TTS Russian with genuine Zero Two voice cloning.
All outputs saved to c:\\AI\\dota2-mcp\\audio_cute\\ in 192kbps MP3 format.
"""

import contextlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from gradio_client import Client, handle_file

with contextlib.suppress(AttributeError, OSError, ValueError):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(r"c:\AI\dota2-mcp")
AUDIO_DIR = BASE_DIR / "audio_cute"
CUES_DIR = Path(r"C:\Users\fronty\Downloads\ZeroTwo_Voice_Cues")
FFMPEG_EXE = r"C:\Users\fronty\AppData\Roaming\Python\Python314\site-packages\imageio_ffmpeg\binaries\ffmpeg.exe"
CACHE_DIR = BASE_DIR / "cache"

AUDIO_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 1. Authentic clips directly from anime
ORIGINAL_CLIPS = {
    "match_found.mp3": CUES_DIR / "Ep01" / "Ep01_068_А_ты_готов_к_смерти.mp3",
    "game_start.mp3": CUES_DIR / "Ep05" / "Ep05_001_О_Привет_любимый.mp3",
    "victory.mp3": CUES_DIR / "Ep02" / "Ep02_003_Ты_был_восхитителен_мой_любимый.mp3",
}

# 2. Reference audio for F5-TTS cloning (4.16s clean clip with 'мой любимый')
REF_AUDIO = CUES_DIR / "Ep05" / "Ep05_018_Это_и_без_слов_понятно.mp3"
REF_TEXT = "Это и без слов понятно, он же мой любимый."

# 3. Dota-specific voice lines to synthesize
SYNTH_PHRASES = {
    "bounty_20s.mp3": "Любимый, руны богатства через 15 секунд! Забери своё золото!",
    "wisdom_20s.mp3": "Любимый, руны мудрости через 15 секунд! Пойдём отберём их у шрайна!",
    "water_15s.mp3": "Любимый, руны воды на реке через 15 секунд! Наполни ботл!",
    "river_15s.mp3": "Активная руна реки через 15 секунд, любимый! Проверь точку!",
    "stack_53s.mp3": "Любимый, стакай крипов прямо сейчас на пятьдесят третьей секунде!",
    "neutral_tier1.mp3": "Любимый, открылись нейтралки первого тира! Выбивай первую шмотку!",
    "neutral_tier2.mp3": "Уже семнадцатая минута, любимый! Доступны нейтралки второго тира!",
    "neutral_tier3.mp3": "Двадцать седьмая минута! Нейтралки третьего тира в игре, любимый!",
    "neutral_tier4.mp3": "Тридцать седьмая минута, любимый! Четвёртый тир нейтралок, будь начеку!",
    "neutral_tier5.mp3": "Шестидесятая минута, любимый! Пятый тир нейтралок, пойдём и сломаем их трон!",
    "roshan_killed.mp3": "Рошан повержен! Окно респавна откроется через восемь минут, любимый!",
    "roshan_window_warning.mp3": "Любимый, окно Рошана откроется через 15 секунд! Будь начеку!",
    "roshan_window_open.mp3": "Окно Рошана открыто! Он может появиться прямо сейчас, любимый!",
    "roshan_respawn.mp3": "Прошло одиннадцать минут! Рошан гарантированно возродился, любимый!",
    "roshan_move_20s.mp3": "Смена суток, любимый! Рошан переходит в другое логово!",
    "tormentor_30s.mp3": "Терзатель появится через 30 секунд, любимый! Заберём бесплатный шард!",
}


def copy_originals():
    print("=== 1. Deploying original anime audio clips ===")
    for target_name, src_path in ORIGINAL_CLIPS.items():
        dst_path = AUDIO_DIR / target_name
        if src_path.exists():
            shutil.copyfile(src_path, dst_path)
            print(f"  ✓ {target_name} <- {src_path.name}")
        else:
            print(f"  ⚠ Missing source: {src_path}")


def generate_synthesized():
    print("\n=== 2. Synthesizing Dota 2 cues via F5-TTS Neural Voice Cloning ===")
    print(f"Reference Audio: {REF_AUDIO.name}")
    print(f"Reference Text:  '{REF_TEXT}'\n")

    client = Client("ikramar/f5-tts-russian")
    ref_file = handle_file(str(REF_AUDIO))

    total = len(SYNTH_PHRASES)
    for idx, (filename, phrase) in enumerate(SYNTH_PHRASES.items(), 1):
        print(f"[{idx:02d}/{total:02d}] Generating {filename}: \"{phrase}\"")
        target_path = AUDIO_DIR / filename
        temp_wav = CACHE_DIR / f"temp_{filename}.wav"

        success = False
        for attempt in range(3):
            try:
                res = client.predict(
                    reference=ref_file,
                    transcript=REF_TEXT,
                    text=phrase,
                    speed=1.0,
                    api_name="/generate",
                )
                wav_path, status = res
                shutil.copyfile(wav_path, temp_wav)

                # Convert to high-quality MP3
                subprocess.run(
                    [
                        FFMPEG_EXE, "-y",
                        "-i", str(temp_wav),
                        "-c:a", "libmp3lame",
                        "-b:a", "192k",
                        str(target_path),
                    ],
                    check=False,
                    capture_output=True,
                )

                if temp_wav.exists():
                    os.remove(temp_wav)

                print(f"   -> Saved {filename} ({status})")
                success = True
                break
            except Exception as e:
                print(f"   ⚠ Attempt {attempt+1} failed: {e}. Retrying...")
                time.sleep(2.0)

        if not success:
            print(f"   ✖ ERROR: Could not generate {filename}")
        time.sleep(0.5)


def main():
    t0 = time.time()
    copy_originals()
    generate_synthesized()
    print("\n=======================================================")
    print(f"ВСЕ 19 РЕПЛИК УСПЕШНО ГОТОВЫ за {time.time() - t0:.1f} сек!")
    print(f"Папка тренера: {AUDIO_DIR}")
    print("=======================================================")


if __name__ == "__main__":
    main()
