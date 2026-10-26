"""
Dota 2 Autonomous Offline Voice Coach & Real-Time In-Game Timer Assistant.
VAC-Safe, 100% offline, zero API cost, powered by local SAPI5 pyttsx3 & WinMM.

Key Features:
- 15s pre-warning for Bounty runes (every 4 min) & Wisdom runes (7:00, 14:00, 21:00...)
- Neutral camp stack reminders at XX:45-XX:53
- Neutral item tier unlock alerts (T1: 7m, T2: 17m, T3: 27m, T4: 37m, T5: 60m)
- Roshan timer with 8-11 min respawn window notifications
- Anti-spam rate limiting, per-event cooldowns, volume & speech rate control
- Robust background worker queue with thread-safe COM initialization
"""

import argparse
import ctypes
import json
import os
import queue
import threading
import time
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
AUDIO_DIR = BASE_DIR / "audio_cute"
CONFIG_FILE = BASE_DIR / "config.json"
STATE_FILE = BASE_DIR / "gsi_latest.json"

# Optional COM initialization for SAPI5 pyttsx3 in Windows worker thread
try:
    import pythoncom
    HAS_PYTHONCOM = True
except Exception:
    HAS_PYTHONCOM = False

try:
    import pyttsx3
    HAS_PYTTSX3 = True
except Exception:
    HAS_PYTTSX3 = False


def _play_winmm_audio(file_path: Path) -> bool:
    """Plays audio (mp3/wav) via Windows MultiMedia API without blocking and 0 external dependencies."""
    if not file_path.exists() or not hasattr(ctypes, "windll"):
        return False
    alias = f"dota_cue_{int(time.time() * 1000) % 100000}"
    mci = ctypes.windll.winmm.mciSendStringW
    try:
        p_str = str(file_path.resolve())
        # Close any previous instance with alias
        mci(f'close "{alias}"', None, 0, None)
        open_cmd = f'open "{p_str}" type mpegvideo alias {alias}'
        res = mci(open_cmd, None, 0, None)
        if res == 0:
            mci(f'play {alias} wait', None, 0, None)
            mci(f'close {alias}', None, 0, None)
            return True
        return False
    except Exception:
        return False


class VoiceWorker(threading.Thread):
    """
    Dedicated background worker thread for thread-safe TTS synthesis and audio playback.
    Ensures SAPI5 COM calls never block GSI processing or HTTP threads.
    """

    def __init__(self, volume: float = 0.85, rate: int = 180, voice_pref: str = "auto"):
        super().__init__(name="VoiceCoachWorker", daemon=True)
        self.queue: queue.Queue = queue.Queue(maxsize=32)
        self.volume = max(0.0, min(1.0, float(volume)))
        self.rate = max(100, min(300, int(rate)))
        self.voice_pref = voice_pref
        self._engine = None
        self._running = True
        self.start()

    def run(self):
        if HAS_PYTHONCOM:
            try:
                pythoncom.CoInitialize()
            except Exception:
                pass

        if HAS_PYTTSX3:
            try:
                self._engine = pyttsx3.init("sapi5")
                self._engine.setProperty("volume", self.volume)
                self._engine.setProperty("rate", self.rate)
                # Pick preferred voice (Zira female desktop voice preferred if available)
                voices = self._engine.getProperty("voices") or []
                selected_voice = None
                for v in voices:
                    v_name = getattr(v, "name", "").lower()
                    if self.voice_pref != "auto" and self.voice_pref.lower() in v_name:
                        selected_voice = v.id
                        break
                    if "zira" in v_name:
                        selected_voice = v.id
                        break
                if selected_voice:
                    self._engine.setProperty("voice", selected_voice)
            except Exception:
                self._engine = None

        while self._running:
            try:
                task = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if task is None:
                break

            action, arg = task
            try:
                if action == "say":
                    if self._engine is not None:
                        self._engine.say(str(arg))
                        self._engine.runAndWait()
                    time.sleep(0.4)
                elif action == "play":
                    _play_winmm_audio(Path(arg))
                    time.sleep(0.4)
                elif action == "volume":
                    self.volume = max(0.0, min(1.0, float(arg)))
                    if self._engine:
                        self._engine.setProperty("volume", self.volume)
                elif action == "rate":
                    self.rate = max(100, min(300, int(arg)))
                    if self._engine:
                        self._engine.setProperty("rate", self.rate)
            except Exception:
                pass
            finally:
                self.queue.task_done()

        if HAS_PYTHONCOM:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    def stop(self):
        self._running = False
        self.queue.put(None)


class CuteVoiceCoach:
    """
    Real-Time Dota 2 Voice Coach.
    Processes GSI clock timings and events, queuing natural speech prompts.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.triggered_events: set[str] = set()
        self.last_speech_time = 0.0
        self.min_gap_sec = 2.5
        self.roshan_killed_time: int | None = None
        self.current_match_id: str | None = None
        self.history: list[dict[str, Any]] = []

        # Load config defaults
        cfg = self._load_config()
        v_cfg = cfg.get("voice_coach", {})
        self.enabled = bool(v_cfg.get("enabled", True))
        self.volume = float(v_cfg.get("volume", 0.85))
        self.rate = int(v_cfg.get("rate", 180))
        self.voice_pref = str(v_cfg.get("voice", "auto"))
        self.min_gap_sec = float(v_cfg.get("min_gap_sec", 2.5))
        self.prefer_audio_samples = bool(v_cfg.get("prefer_audio_samples", True))

        self.notify_bounty = bool(v_cfg.get("notify_bounty", True))
        self.notify_wisdom = bool(v_cfg.get("notify_wisdom", True))
        self.notify_stacks = bool(v_cfg.get("notify_stacks", True))
        self.notify_neutrals = bool(v_cfg.get("notify_neutrals", True))
        self.notify_roshan = bool(v_cfg.get("notify_roshan", True))

        # Start background TTS/audio worker
        self.worker = VoiceWorker(volume=self.volume, rate=self.rate, voice_pref=self.voice_pref)

    def _load_config(self) -> dict:
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def set_volume(self, volume: float):
        """Sets voice coach output volume (0.0 to 1.0)."""
        vol = max(0.0, min(1.0, float(volume)))
        self.volume = vol
        self.worker.queue.put(("volume", vol))

    def set_rate(self, rate: int):
        """Sets speech speed rate in words per minute (e.g. 150-220)."""
        r = max(100, min(300, int(rate)))
        self.rate = r
        self.worker.queue.put(("rate", r))

    def set_enabled(self, enabled: bool):
        """Enables or disables voice coach audio alerts."""
        self.enabled = bool(enabled)

    def speak_or_play(self, event_key: str, text: str, sample_file: str | None = None) -> bool:
        """
        Emits an audio prompt (pre-recorded sample or dynamic TTS) with anti-spam protection.
        Returns True if prompt was dispatched.
        """
        if not self.enabled:
            return False

        now = time.time()
        with self._lock:
            # Check per-event duplicate cooldown
            if event_key in self.triggered_events:
                return False

            # Check global speech interval to prevent overlapping phrases
            if now - self.last_speech_time < self.min_gap_sec:
                return False

            self.triggered_events.add(event_key)
            self.last_speech_time = now
            self.history.append({"time": now, "event": event_key, "text": text, "sample": sample_file})
            if len(self.history) > 50:
                self.history.pop(0)

        # Discard expired tasks if worker queue is backlogged
        if self.worker.queue.qsize() > 5:
            try:
                while not self.worker.queue.empty():
                    self.worker.queue.get_nowait()
                    self.worker.queue.task_done()
            except Exception:
                pass

        # Use pre-recorded sample if requested and file exists
        if self.prefer_audio_samples and sample_file:
            path = AUDIO_DIR / sample_file
            if path.exists():
                self.worker.queue.put(("play", str(path)))
                return True

        # Otherwise synthesize natural speech via pyttsx3 SAPI5
        self.worker.queue.put(("say", text))
        return True

    def reset_match(self, match_id: str | None = None):
        """Resets triggered alerts on new match or stage change."""
        with self._lock:
            self.triggered_events.clear()
            self.roshan_killed_time = None
            self.current_match_id = match_id
            self.last_speech_time = 0.0

    def record_roshan_death(self, clock_time: int) -> str:
        """
        Registers Roshan death at given clock_time (seconds).
        Triggers instant speech cue and initializes 8-11 min respawn window tracking.
        """
        c = int(clock_time)
        with self._lock:
            self.roshan_killed_time = c

        event_key = f"rosh_death_{c}"
        t_start = c + 480
        t_end = c + 660
        fmt_start = f"{t_start // 60:02d}:{t_start % 60:02d}"
        fmt_end = f"{t_end // 60:02d}:{t_end % 60:02d}"
        text = f"Roshan is down. Respawn window from {fmt_start} to {fmt_end}."
        self.speak_or_play(event_key, text, "roshan_killed.mp3")
        return event_key

    def check_timers(self, clock_time: int, is_in_game: bool = True) -> str | None:
        """
        Evaluates current in-game clock time (seconds) and emits timely voice alerts:
        1. 15s pre-warning for Bounty runes (every 4m: 4:00, 8:00, 12:00...)
        2. 15s pre-warning for Wisdom runes (7:00, 14:00, 21:00...)
        3. Neutral camp stack reminder on XX:45 - XX:53
        4. Neutral tier unlocks (T1: 7:00, T2: 17:00, T3: 27:00, T4: 37:00, T5: 60:00)
        5. Roshan respawn window (15s warning, window open at +8m, guaranteed at +11m)
        6. Water runes (02:00, 04:00) & Power runes (every 2m from 06:00)
        """
        if not is_in_game or clock_time is None or clock_time < 0:
            return None

        c = int(clock_time)
        triggered_cue: str | None = None

        # ---------------------------------------------------------
        # 1. Bounty Runes: every 4 min (240s: 04:00, 08:00, 12:00...)
        # Warning window: 14..16 sec before spawn
        # ---------------------------------------------------------
        if self.notify_bounty and c >= 60:
            rem_bounty = 240 - (c % 240)
            t_bounty = c + rem_bounty
            if 14 <= rem_bounty <= 16 and t_bounty >= 240:
                key = f"bounty_{t_bounty}"
                if self.speak_or_play(key, "Bounty runes spawning in 15 seconds.", "bounty_20s.mp3"):
                    triggered_cue = key

        # ---------------------------------------------------------
        # 2. Wisdom Runes: every 7 min (420s: 07:00, 14:00, 21:00...)
        # Warning window: 14..16 sec before spawn
        # ---------------------------------------------------------
        if self.notify_wisdom and c >= 60:
            rem_wisdom = 420 - (c % 420)
            t_wisdom = c + rem_wisdom
            if 14 <= rem_wisdom <= 16 and t_wisdom >= 420:
                key = f"wisdom_{t_wisdom}"
                if self.speak_or_play(key, "Wisdom runes spawning in 15 seconds. Contest the shrines.", "wisdom_20s.mp3"):
                    triggered_cue = key

        # ---------------------------------------------------------
        # 3. Jungle Camp Stacking: XX:45 - XX:53 of every minute
        # Triggered once per minute between :46 and :50 to allow walk time
        # ---------------------------------------------------------
        if self.notify_stacks and c >= 50:
            minute = c // 60
            sec_in_min = c % 60
            if 46 <= sec_in_min <= 50:
                key = f"stack_min_{minute}"
                if self.speak_or_play(key, "Stack jungle camps now at 53 seconds.", "stack_53s.mp3"):
                    triggered_cue = key

        # ---------------------------------------------------------
        # 4. Neutral Item Tiers (T1: 7m, T2: 17m, T3: 27m, T4: 37m, T5: 60m)
        # ---------------------------------------------------------
        if self.notify_neutrals:
            neutral_tiers = [
                (1, 420, "Tier 1 neutral items are now available!"),
                (2, 1020, "Tier 2 neutral items are now available!"),
                (3, 1620, "Tier 3 neutral items are now available!"),
                (4, 2220, "Tier 4 neutral items are now available!"),
                (5, 3600, "Tier 5 neutral items are now available!"),
            ]
            for tier, t_unlock, phrase in neutral_tiers:
                if t_unlock <= c <= t_unlock + 5:
                    key = f"neutral_tier_{tier}"
                    if self.speak_or_play(key, phrase, f"neutral_tier{tier}.mp3"):
                        triggered_cue = key
                        break

        # ---------------------------------------------------------
        # 5. Roshan Respawn Window (8 - 11 minutes after death)
        # Window start = death + 480s, window end = death + 660s
        # ---------------------------------------------------------
        if self.notify_roshan and self.roshan_killed_time is not None:
            t_death = self.roshan_killed_time
            w_start = t_death + 480
            w_end = t_death + 660

            # 15s warning before window opens
            if (w_start - 16) <= c <= (w_start - 14):
                key = f"rosh_pre_window_{t_death}"
                if self.speak_or_play(key, "Roshan respawn window opens in 15 seconds.", "roshan_window_warning.mp3"):
                    triggered_cue = key

            # Respawn window is now open (8:00)
            elif w_start <= c <= (w_start + 5):
                key = f"rosh_window_open_{t_death}"
                if self.speak_or_play(key, "Roshan respawn window is open! Roshan may spawn now.", "roshan_window_open.mp3"):
                    triggered_cue = key

            # Maximum respawn time reached (11:00 guaranteed)
            elif w_end <= c <= (w_end + 5):
                key = f"rosh_respawn_guaranteed_{t_death}"
                if self.speak_or_play(key, "Roshan has guaranteed respawned!", "roshan_respawn.mp3"):
                    triggered_cue = key
                    self.roshan_killed_time = None

        # ---------------------------------------------------------
        # 6. Water Runes (02:00 = 120s, 04:00 = 240s) 15s warning
        # ---------------------------------------------------------
        if 104 <= c <= 106:
            key = "water_120"
            if self.speak_or_play(key, "Water runes spawning in 15 seconds.", "water_15s.mp3"):
                triggered_cue = key
        elif 224 <= c <= 226:
            key = "water_240"
            if self.speak_or_play(key, "Water runes spawning in 15 seconds.", "water_15s.mp3"):
                triggered_cue = key

        # ---------------------------------------------------------
        # 7. Active River Power Runes: every 2 min starting at 06:00 (360s)
        # ---------------------------------------------------------
        if c >= 340:
            rem_river = 120 - (c % 120)
            t_river = c + rem_river
            if 14 <= rem_river <= 16 and t_river >= 360:
                key = f"river_{t_river}"
                if self.speak_or_play(key, "River power rune spawning in 15 seconds.", "river_15s.mp3"):
                    triggered_cue = key

        # ---------------------------------------------------------
        # 8. Tormentor (20:00 = 1200s) 30s warning
        # ---------------------------------------------------------
        if 1168 <= c <= 1172:
            key = "tormentor_1200"
            if self.speak_or_play(key, "Tormentor spawning in 30 seconds. Prepare for shard.", "tormentor_30s.mp3"):
                triggered_cue = key

        return triggered_cue

    def check_events(self, events: list[dict[str, Any]], clock_time: int | None = None) -> str | None:
        """Inspects GSI events list for game events like Roshan death."""
        if not events or not isinstance(events, list):
            return None

        c = clock_time if clock_time is not None else 0
        for ev in events:
            if not isinstance(ev, dict):
                continue
            e_type = ev.get("event_type")
            gt = ev.get("game_time", c)

            if e_type == "roshan_killed":
                return self.record_roshan_death(int(gt) if gt else int(c))

        return None

    def process_gsi_packet(self, payload: dict[str, Any]) -> str | None:
        """
        Top-level packet handler invoked directly by GSI HTTP server or daemon.
        Parses map state, clock time, and events.
        """
        if not payload or not isinstance(payload, dict):
            return None

        map_data = payload.get("map") or {}
        stage = map_data.get("game_state")
        clock_raw = map_data.get("clock_time")
        matchid = str(map_data.get("matchid") or "")

        # Check match reset
        if matchid and matchid != self.current_match_id:
            self.reset_match(matchid)

        # Stage transitions
        if stage == "DOTA_GAMERULES_STATE_PRE_GAME" and "pre_game" not in self.triggered_events:
            self.speak_or_play("pre_game", "Match started. Good luck and have fun!", "game_start.mp3")

        elif stage in ("DOTA_GAMERULES_STATE_POST_GAME", "DOTA_GAMERULES_STATE_GAME_OVER") and "game_over" not in self.triggered_events:
            self.speak_or_play("game_over", "Good game! Review your post-match stats.", "victory.mp3")

        # In-game active evaluations
        if stage == "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS" and isinstance(clock_raw, (int, float)):
            clock_sec = int(clock_raw)

            # Check discrete events (e.g. roshan_killed)
            ev_list = payload.get("events")
            if isinstance(ev_list, list):
                self.check_events(ev_list, clock_sec)

            # Evaluate scheduled timings
            return self.check_timers(clock_sec, is_in_game=True)

        return None

    def on_match_found(self):
        self.speak_or_play("match_found", "Match found! Ready up.", "match_found.mp3")

    def on_game_start(self):
        self.speak_or_play("game_start", "Welcome to Dota 2. Game starting!", "game_start.mp3")

    def on_victory(self):
        self.speak_or_play("victory", "Victory!", "victory.mp3")

    def get_status(self) -> dict[str, Any]:
        """Returns diagnostic status of Voice Coach."""
        with self._lock:
            rosh_info = None
            if self.roshan_killed_time is not None:
                rosh_info = {
                    "death_clock": self.roshan_killed_time,
                    "window_start": self.roshan_killed_time + 480,
                    "window_end": self.roshan_killed_time + 660,
                }
            return {
                "enabled": self.enabled,
                "volume": self.volume,
                "rate": self.rate,
                "voice_pref": self.voice_pref,
                "triggers_count": len(self.triggered_events),
                "roshan_tracking": rosh_info,
                "recent_history": self.history[-10:],
                "worker_queue_size": self.worker.queue.qsize(),
            }


# Singleton coach instance
coach = CuteVoiceCoach()


def run_daemon_listener(interval: float = 0.5):
    """Watches gsi_latest.json file autonomously and processes live packets."""
    print("Voice Coach Daemon running... (Ctrl+C to exit)")
    last_mtime = 0.0
    while True:
        try:
            if STATE_FILE.exists():
                mtime = os.path.getmtime(STATE_FILE)
                if mtime > last_mtime:
                    last_mtime = mtime
                    with open(STATE_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    cue = coach.process_gsi_packet(data)
                    if cue:
                        print(f"[{time.strftime('%H:%M:%S')}] Cue triggered: {cue}")
            time.sleep(interval)
        except KeyboardInterrupt:
            break
        except Exception:
            time.sleep(interval)


def test_suite():
    """Runs a synthetic verification test for all required timings and features."""
    print("=== Running Voice Coach Synthetic Test Suite ===")
    coach.reset_match("test_match_999")

    # Test 1: Bounty rune 15s warning (e.g. clock = 225s, 15s before 240s)
    print("\n1. Testing Bounty rune 15s warning at 03:45 (225s)...")
    cue1 = coach.check_timers(225)
    print(f"Result: {cue1} (Expected: bounty_240)")
    assert cue1 == "bounty_240", f"Failed: expected bounty_240, got {cue1}"

    # Test 2: Anti-spam duplicate check
    print("\n2. Testing Anti-spam duplicate rejection on same second...")
    cue_dup = coach.check_timers(225)
    print(f"Result: {cue_dup} (Expected: None)")
    assert cue_dup is None, "Failed: duplicate trigger was not blocked!"

    # Test 3: Wisdom rune 15s warning (e.g. clock = 405s, 15s before 420s / 7:00)
    print("\n3. Testing Wisdom rune 15s warning at 06:45 (405s)...")
    # Reset last_speech_time to bypass min_gap for automated test
    coach.last_speech_time = 0.0
    cue2 = coach.check_timers(405)
    print(f"Result: {cue2} (Expected: wisdom_420)")
    assert cue2 == "wisdom_420", f"Failed: expected wisdom_420, got {cue2}"

    # Test 4: Jungle camp stack reminder on XX:45 - XX:53 (e.g. clock = 108s = 01:48)
    print("\n4. Testing Jungle stack reminder at 01:48 (108s)...")
    coach.last_speech_time = 0.0
    cue3 = coach.check_timers(108)
    print(f"Result: {cue3} (Expected: stack_min_1)")
    assert cue3 == "stack_min_1", f"Failed: expected stack_min_1, got {cue3}"

    # Test 5: Neutral item tier unlocks (T1: 420s, T2: 1020s, T3: 1620s, T4: 2220s, T5: 3600s)
    print("\n5. Testing Neutral Tier unlocks (T1 at 420s, T2 at 1020s)...")
    coach.last_speech_time = 0.0
    cue_t1 = coach.check_timers(420)
    print(f"T1 Result: {cue_t1} (Expected: neutral_tier_1)")
    assert cue_t1 == "neutral_tier_1", f"Failed: expected neutral_tier_1, got {cue_t1}"

    coach.last_speech_time = 0.0
    cue_t2 = coach.check_timers(1020)
    print(f"T2 Result: {cue_t2} (Expected: neutral_tier_2)")
    assert cue_t2 == "neutral_tier_2", f"Failed: expected neutral_tier_2, got {cue_t2}"

    # Test 6: Roshan death and 8-11 min respawn window
    print("\n6. Testing Roshan respawn tracking (killed at 600s / 10:00)...")
    coach.last_speech_time = 0.0
    death_cue = coach.record_roshan_death(600)
    print(f"Death Cue: {death_cue}")
    assert coach.roshan_killed_time == 600

    # Window start is 600 + 480 = 1080s (18:00). 15s warning at 1065s.
    print("Testing Roshan 15s pre-window warning at 1065s...")
    coach.last_speech_time = 0.0
    cue_rosh_warn = coach.check_timers(1065)
    print(f"Rosh warning: {cue_rosh_warn} (Expected: rosh_pre_window_600)")
    assert cue_rosh_warn == "rosh_pre_window_600"

    # Window open at 1080s
    print("Testing Roshan window open at 1080s...")
    coach.last_speech_time = 0.0
    cue_rosh_open = coach.check_timers(1080)
    print(f"Rosh open: {cue_rosh_open} (Expected: rosh_window_open_600)")
    assert cue_rosh_open == "rosh_window_open_600"

    # Window guaranteed end at 600 + 660 = 1260s (21:00)
    print("Testing Roshan guaranteed respawn at 1260s...")
    coach.last_speech_time = 0.0
    cue_rosh_end = coach.check_timers(1260)
    print(f"Rosh respawned: {cue_rosh_end} (Expected: rosh_respawn_guaranteed_600)")
    assert cue_rosh_end == "rosh_respawn_guaranteed_600"
    assert coach.roshan_killed_time is None

    # Test 7: GSI Packet Processing
    print("\n7. Testing Full GSI Packet with roshan_killed event...")
    packet = {
        "map": {
            "matchid": "999",
            "game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
            "clock_time": 750,
        },
        "events": [
            {"event_type": "roshan_killed", "game_time": 750}
        ]
    }
    coach.last_speech_time = 0.0
    coach.process_gsi_packet(packet)
    assert coach.roshan_killed_time == 750, "Failed: GSI packet did not set roshan_killed_time"
    print("GSI Packet processed successfully!")

    print("\n=== ALL SYNTHETIC TESTS PASSED SUCCESSFULLY! ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dota 2 Autonomous Offline Voice Coach")
    parser.add_argument("--listen", action="store_true", help="Run daemon polling gsi_latest.json")
    parser.add_argument("--test", action="store_true", help="Run synthetic unit test suite")
    parser.add_argument("--status", action="store_true", help="Print coach status and config")
    parser.add_argument("--say", type=str, help="Speak custom phrase via offline TTS")
    parser.add_argument("--volume", type=float, help="Set volume (0.0 to 1.0)")
    args = parser.parse_args()

    if args.volume is not None:
        coach.set_volume(args.volume)
        print(f"Volume set to {coach.volume}")

    if args.say:
        print(f"Synthesizing: '{args.say}'...")
        coach.speak_or_play("cli_test", args.say)
        time.sleep(2.5)

    elif args.test:
        test_suite()

    elif args.status:
        print(json.dumps(coach.get_status(), indent=2, ensure_ascii=False))

    elif args.listen:
        run_daemon_listener()

    else:
        test_suite()
