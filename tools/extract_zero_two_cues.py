"""
Automated extractor of all Zero Two (02 / Cleo-chan) voice lines
from 'Darling in the FranXX' [AniLibria.TV HDTV-Rip 720p].
Extracts clean Russian audio segments matching ASS subtitle timestamps.
"""

import contextlib
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

with contextlib.suppress(AttributeError, OSError, ValueError):
    sys.stdout.reconfigure(encoding="utf-8")

FFMPEG_EXE = r"C:\Users\fronty\AppData\Roaming\Python\Python314\site-packages\imageio_ffmpeg\binaries\ffmpeg.exe"
SOURCE_DIR = Path(r"C:\Users\fronty\Downloads\Darling in the FranXX - AniLibria.TV [HDTV-Rip 720p]")
OUTPUT_DIR = Path(r"C:\Users\fronty\Downloads\ZeroTwo_Voice_Cues")
BEST_DIR = OUTPUT_DIR / "Best_References_for_VoiceStudio"
CACHE_DIR = Path(r"c:\AI\dota2-mcp\cache")

CACHE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
BEST_DIR.mkdir(parents=True, exist_ok=True)


def parse_ass_time(ts_str: str) -> float:
    """Converts H:MM:SS.cs to seconds."""
    parts = ts_str.strip().split(":")
    h = int(parts[0])
    m = int(parts[1])
    s, cs = parts[2].split(".")
    return h * 3600.0 + m * 60.0 + int(s) + int(cs) / 100.0


def clean_text_for_filename(text: str, max_words: int = 5, max_chars: int = 35) -> str:
    # Strip ASS tags
    t = re.sub(r"\{.*?\}", "", text).replace(r"\N", " ").strip()
    words = [re.sub(r"[^\w]", "", w) for w in t.split()]
    words = [w for w in words if w]
    chosen = words[:max_words]
    name = "_".join(chosen)
    return name[:max_chars].strip("_") or "cue"


def extract_cues_from_episode(mkv_path: Path, ep_num: int):
    # 1. Extract subtitle track to stdout
    p = subprocess.run(
        [FFMPEG_EXE, "-y", "-i", str(mkv_path), "-map", "0:4", "-f", "ass", "-"],
        check=False,
        capture_output=True,
    )
    ass_text = p.stdout.decode("utf-8", errors="replace")

    dialogue_cues = []
    for line in ass_text.splitlines():
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 9)
        if len(parts) < 10:
            continue
        speaker = parts[4].strip()
        if speaker != "Ноль Два 002":
            continue

        raw_start = parts[1].strip()
        raw_end = parts[2].strip()
        start_sec = parse_ass_time(raw_start)
        end_sec = parse_ass_time(raw_end)
        clean_text = re.sub(r"\{.*?\}", "", parts[9]).replace(r"\N", " ").strip()

        # Filter out empty or negligible (< 0.3s) sounds
        if end_sec - start_sec >= 0.3:
            dialogue_cues.append({
                "raw_start": raw_start,
                "raw_end": raw_end,
                "start_sec": start_sec,
                "end_sec": end_sec,
                "duration": round(end_sec - start_sec, 2),
                "text": clean_text,
            })

    return dialogue_cues


def process_all_episodes():
    print("=== Zero Two Voice Extractor (AniLibria - Cleo-chan) ===")
    print(f"Source: {SOURCE_DIR}")
    print(f"Output: {OUTPUT_DIR}\n")

    files = sorted([f for f in os.listdir(SOURCE_DIR) if f.endswith(".mkv")])
    if not files:
        print("ERROR: No MKV files found in source folder!")
        return

    all_metadata = []
    total_extracted = 0
    t_start_all = time.time()

    for idx, fname in enumerate(files, 1):
        mkv_path = SOURCE_DIR / fname
        ep_dir = OUTPUT_DIR / f"Ep{idx:02d}"
        ep_dir.mkdir(parents=True, exist_ok=True)

        cues = extract_cues_from_episode(mkv_path, idx)
        if not cues:
            print(f"[{idx:02d}/{len(files):02d}] {fname}: 0 cues found, skipping audio extraction.")
            continue

        print(f"[{idx:02d}/{len(files):02d}] {fname}: found {len(cues)} Zero Two cues. Extracting audio...")

        # Extract full Russian audio to temporary WAV for millisecond-fast slicing
        temp_wav = CACHE_DIR / f"temp_ep{idx:02d}_rus.wav"
        t0 = time.time()
        subprocess.run(
            [
                FFMPEG_EXE, "-y",
                "-i", str(mkv_path),
                "-map", "0:1",
                "-vn",
                "-c:a", "pcm_s16le",
                "-ar", "44100",
                str(temp_wav),
            ],
            check=False,
            capture_output=True,
        )

        if not temp_wav.exists() or temp_wav.stat().st_size < 1000:
            print(f"  ERROR: Failed to extract audio track for {fname}!")
            continue

        # Slicing each cue
        for c_idx, cue in enumerate(cues, 1):
            s_sec = max(0.0, cue["start_sec"] - 0.08)
            e_sec = cue["end_sec"] + 0.12
            dur = e_sec - s_sec

            fn_title = clean_text_for_filename(cue["text"])
            out_filename = f"Ep{idx:02d}_{c_idx:03d}_{fn_title}.mp3"
            out_path = ep_dir / out_filename

            subprocess.run(
                [
                    FFMPEG_EXE, "-y",
                    "-ss", f"{s_sec:.2f}",
                    "-t", f"{dur:.2f}",
                    "-i", str(temp_wav),
                    "-c:a", "libmp3lame",
                    "-b:a", "192k",
                    str(out_path),
                ],
                check=False,
                capture_output=True,
            )

            rel_path = f"Ep{idx:02d}/{out_filename}"
            meta_entry = {
                "episode": idx,
                "cue_index": c_idx,
                "filename": out_filename,
                "relative_path": rel_path,
                "start": cue["raw_start"],
                "end": cue["raw_end"],
                "duration": cue["duration"],
                "text": cue["text"],
            }
            all_metadata.append(meta_entry)
            total_extracted += 1

            # If good reference candidate (clean sentence, duration between 3.0 and 8.0 seconds, contains 'милый' or key words)
            if 3.0 <= cue["duration"] <= 8.5 and len(cue["text"].split()) >= 4:
                best_filename = f"ZeroTwo_Ref_Ep{idx:02d}_{c_idx:03d}_{fn_title}.mp3"
                best_path = BEST_DIR / best_filename
                with contextlib.suppress(OSError):
                    shutil.copyfile(out_path, best_path)

        # Cleanup temp wav
        with contextlib.suppress(OSError):
            if temp_wav.exists():
                os.remove(temp_wav)

        print(f"  ✓ Sliced {len(cues)} cues in {time.time() - t0:.1f}s.")

    # Save JSON metadata
    json_path = OUTPUT_DIR / "metadata.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_metadata, f, ensure_ascii=False, indent=2)

    # Save CSV metadata (LJSpeech dataset format: audio_relpath|text)
    csv_path = OUTPUT_DIR / "metadata.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="|")
        for item in all_metadata:
            writer.writerow([item["relative_path"], item["text"]])

    # Save README
    readme_path = OUTPUT_DIR / "README.txt"
    best_count = len(list(BEST_DIR.glob("*.mp3")))
    readme_text = f"""Датасет голосовых реплик Ноль Два (Zero Two / Код 002)
Аниме: Darling in the FranXX (Любимый во Франксе)
Озвучка: AniLibria.TV (актриса Cleo-chan)
Всего извлечено реплик: {total_extracted}
Файлов в папке Best_References_for_VoiceStudio: {best_count}

Структура:
- Ep01 .. Ep24/ — папки с репликами по сериям в MP3 192 kbps.
- Best_References_for_VoiceStudio/ — подборка самых чистых и выразительных фраз длительностью 3-8 секунд для быстрого обучения/клонирования в VoiceStudio.
- metadata.json — подробные таймкоды, номера серий и расшифровки.
- metadata.csv — разметка формата LJSpeech (audio_path|text) для TTS-движков.
"""
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_text)

    print("\n=======================================================")
    print(f"ГОТОВО! Успешно извлечено {total_extracted} реплик за {time.time() - t_start_all:.1f}s.")
    print(f"Папка с репликами: {OUTPUT_DIR}")
    print(f"Папка лучших референсов: {BEST_DIR} ({best_count} файлов)")
    print("Файлы метаданных: metadata.json, metadata.csv")
    print("=======================================================")


if __name__ == "__main__":
    process_all_episodes()
