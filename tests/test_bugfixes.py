"""Offline unit tests for bug fixes, formatting safety, and public interfaces."""

import io
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import auto_scout
import coach_cli
import dota_core
import dota_tools_a
import dota_tools_b
import draft_engine
import gsi_server
import scout_engine
import server


def test_draft_aliases_unique_and_resolve():
    assert draft_engine.ALIASES["панда"] == "Brewmaster"
    assert draft_engine.ALIASES["бист"] == "Primal Beast"
    assert draft_engine.ALIASES["медведь"] == "Lone Druid"
    assert draft_engine.resolve_hero("панда")["localized_name"] == "Brewmaster"
    assert draft_engine.resolve_hero("бист")["localized_name"] == "Primal Beast"
    assert draft_engine.resolve_hero("медведь")["localized_name"] == "Lone Druid"


def test_auto_scout_player_slot_team_and_zero_slot():
    mgr = auto_scout.AutoScoutManager()
    mgr.update_from_gsi(
        {
            "map": {"matchid": "999000111", "game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION"},
            "allplayers": {
                "player0": {"accountid": "100001", "name": "Rad0", "player_slot": 0},
                "player5": {"accountid": "100002", "name": "Dire5", "player_slot": 5},
                "player6": {"accountid": "100003", "name": "Dire128", "player_slot": 128},
            },
        }
    )
    assert mgr.players_meta[100001]["team"] == "radiant"
    assert mgr.players_meta[100001]["slot"] == 0
    assert mgr.players_meta[100002]["team"] == "dire"
    assert mgr.players_meta[100002]["slot"] == 5
    assert mgr.players_meta[100003]["team"] == "dire"
    assert mgr.players_meta[100003]["slot"] == 128


def test_coach_cli_fmt_tick_with_float_rate():
    tick = {
        "ok": True,
        "fresh": True,
        "сейчас": {"game_time": 125, "gold": 1234, "gpm_gsi": 500, "radiant_score": 3, "dire_score": 2},
        "темп": {
            "60сек": {"золото_в_мин_факт": 412.7},
            "5мин": {"золото_в_мин_факт": 505.4, "kills_дельта": 1.0},
        },
        "summary": {"возраст_пакета_сек": 1.2},
    }
    txt = coach_cli.fmt_tick(tick)
    assert "[2:05]" in txt
    assert "темп1м +412/мин" in txt
    assert "темп5м +505/мин" in txt


def test_fmt_match_handles_none_kda():
    out = dota_core.fmt_match({"match_id": 123, "hero_id": 1, "kills": None, "deaths": 2, "assists": 3})
    assert out == "123 | hero 1 | 0/2/3 | ?"


def test_server_handle_basic_rpc():
    init = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init["result"]["serverInfo"]["name"] == "dota2-mcp"

    tools = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in tools["result"]["tools"]}
    assert {"dota_scout_player", "dota_pick_advice", "dota_gsi_status", "dota_item_guide"} <= names

    guide = server.handle(
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "dota_item_guide", "arguments": {"hero": "pudge"}}}
    )
    payload = json.loads(guide["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["герой"] == "pudge"


def test_gsi_post_invalid_content_length_does_not_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(gsi_server, "STATE_FILE", str(tmp_path / "gsi.json"))

    class FakeHandler(gsi_server.Handler):
        def __init__(self):
            self.path = "/"
            self.headers = {"Content-Length": "not-an-int"}
            self.rfile = io.BytesIO(b"")
            self.wfile = io.BytesIO()
            self.responses = []

        def send_response(self, code, message=None):
            self.responses.append(code)

        def send_header(self, keyword, value):
            pass

        def end_headers(self):
            pass

    h = FakeHandler()
    h.do_POST()
    assert h.responses == [200]
    assert json.loads(h.wfile.getvalue().decode("utf-8")) == {"ok": True}


def test_public_interfaces_importable():
    assert callable(scout_engine.scout_player)
    assert callable(dota_tools_a.t_gsi_status)
    assert callable(dota_tools_b.t_pick_advice)
    assert hasattr(gsi_server, "Handler")
