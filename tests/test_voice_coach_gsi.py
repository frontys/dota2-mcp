"""
Synthetic GSI Integration Test for Dota 2 Autonomous Offline Voice Coach.
Validates live HTTP POST ingestion via gsi_server.py and triggers:
- 15s Bounty & Wisdom rune pre-warnings
- Neutral camp stacking reminders (XX:45-XX:53)
- Neutral item tier unlock alerts (T1: 7m, T2: 17m...)
- Roshan death and 8-11 min respawn window
- Anti-spam deduplication and volume control
"""

import json
import os
import sys
import threading
import time
import urllib.request
from http.server import HTTPServer

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import gsi_server
import voice_coach


def send_gsi_post(payload: dict, port: int = 3000) -> dict:
    url = f"http://127.0.0.1:{port}/"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=3.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_gsi_voice_coach_integration():
    print("=== Starting Synthetic GSI Voice Coach Integration Test ===")
    port = 3055

    # Start gsi_server in background thread on isolated test port
    server = HTTPServer(("127.0.0.1", port), gsi_server.Handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    time.sleep(0.3)

    coach = voice_coach.coach
    coach.reset_match("match_synthetic_test")
    coach.last_speech_time = 0.0

    print("1. Testing GSI POST / Pre-Game start...")
    p1 = {
        "map": {
            "matchid": "match_synthetic_test",
            "game_state": "DOTA_GAMERULES_STATE_PRE_GAME",
            "clock_time": -30
        }
    }
    r1 = send_gsi_post(p1, port)
    assert r1.get("ok") is True
    assert "pre_game" in coach.triggered_events
    print("   -> Pre-Game triggered successfully.")

    print("\n2. Testing GSI POST / Bounty Rune (clock=225, 15s before 04:00)...")
    coach.last_speech_time = 0.0
    p2 = {
        "map": {
            "matchid": "match_synthetic_test",
            "game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
            "clock_time": 225
        }
    }
    r2 = send_gsi_post(p2, port)
    assert r2.get("ok") is True
    assert "bounty_240" in coach.triggered_events
    print("   -> Bounty 15s pre-warning triggered (bounty_240).")

    print("\n3. Testing Anti-Spam (duplicate packet at clock=225)...")
    initial_history_len = len(coach.history)
    r_dup = send_gsi_post(p2, port)
    assert r_dup.get("ok") is True
    assert len(coach.history) == initial_history_len, "Duplicate trigger was not blocked!"
    print("   -> Anti-spam deduplication verified.")

    print("\n4. Testing GSI POST / Wisdom Rune (clock=405, 15s before 07:00)...")
    coach.last_speech_time = 0.0
    p3 = {
        "map": {
            "matchid": "match_synthetic_test",
            "game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
            "clock_time": 405
        }
    }
    send_gsi_post(p3, port)
    assert "wisdom_420" in coach.triggered_events
    print("   -> Wisdom 15s pre-warning triggered (wisdom_420).")

    print("\n5. Testing GSI POST / Jungle Camp Stacking (clock=108s = 01:48)...")
    coach.last_speech_time = 0.0
    p4 = {
        "map": {
            "matchid": "match_synthetic_test",
            "game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
            "clock_time": 108
        }
    }
    send_gsi_post(p4, port)
    assert "stack_min_1" in coach.triggered_events
    print("   -> Jungle stack reminder triggered (stack_min_1).")

    print("\n6. Testing GSI POST / Neutral Item Tier 1 (clock=420s = 07:00)...")
    coach.last_speech_time = 0.0
    p5 = {
        "map": {
            "matchid": "match_synthetic_test",
            "game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
            "clock_time": 420
        }
    }
    send_gsi_post(p5, port)
    assert "neutral_tier_1" in coach.triggered_events
    print("   -> Neutral Tier 1 unlock triggered (neutral_tier_1).")

    print("\n7. Testing GSI POST / Roshan Death Event (clock=600s = 10:00)...")
    coach.last_speech_time = 0.0
    p6 = {
        "map": {
            "matchid": "match_synthetic_test",
            "game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
            "clock_time": 600
        },
        "events": [
            {"event_type": "roshan_killed", "game_time": 600}
        ]
    }
    send_gsi_post(p6, port)
    assert coach.roshan_killed_time == 600
    assert "rosh_death_600" in coach.triggered_events
    print("   -> Roshan death registered, 8-11 min window initialized.")

    print("\n8. Testing GSI POST / Roshan 15s Pre-Window Alert (clock=1065s)...")
    coach.last_speech_time = 0.0
    p7 = {
        "map": {
            "matchid": "match_synthetic_test",
            "game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
            "clock_time": 1065
        }
    }
    send_gsi_post(p7, port)
    assert "rosh_pre_window_600" in coach.triggered_events
    print("   -> Roshan 15s pre-window alert triggered.")

    print("\n9. Testing GSI POST / Roshan Window Open (clock=1080s)...")
    coach.last_speech_time = 0.0
    p8 = {
        "map": {
            "matchid": "match_synthetic_test",
            "game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
            "clock_time": 1080
        }
    }
    send_gsi_post(p8, port)
    assert "rosh_window_open_600" in coach.triggered_events
    print("   -> Roshan window open alert triggered.")

    print("\n10. Testing GSI POST / Roshan Guaranteed Respawn (clock=1260s)...")
    coach.last_speech_time = 0.0
    p9 = {
        "map": {
            "matchid": "match_synthetic_test",
            "game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
            "clock_time": 1260
        }
    }
    send_gsi_post(p9, port)
    assert "rosh_respawn_guaranteed_600" in coach.triggered_events
    assert coach.roshan_killed_time is None
    print("   -> Roshan guaranteed respawn triggered, state reset.")

    print("\n11. Testing Volume & Diagnostic Status API...")
    coach.set_volume(0.9)
    assert coach.volume == 0.9
    st = coach.get_status()
    assert st["volume"] == 0.9
    assert st["triggers_count"] >= 7
    print(f"   -> Diagnostic status: triggers={st['triggers_count']}, volume={st['volume']}.")

    server.shutdown()
    server.server_close()
    print("\n=== ALL GSI INTEGRATION TESTS COMPLETED WITH 100% SUCCESS! ===")


if __name__ == "__main__":
    test_gsi_voice_coach_integration()
