"""Dota 2 auto-watcher: следит за процессом dota2.exe и состоянием GSI,
пишет события в watcher_events.log + watcher_state.json. Stdlib-only.
Запуск: python watcher.py  (можно свернуть/в фон)
Остановка: Ctrl+C
"""
import contextlib
import json
import logging
import os
import subprocess
import sys
import threading
import time

import auto_accept
import voice_coach

logger = logging.getLogger(__name__)

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(BASE, "watcher_events.log")
STATE = os.path.join(BASE, "watcher_state.json")
GSI_FILE = os.path.join(BASE, "gsi_latest.json")
POLL = 2


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    if sys.stdout is not None:
        with contextlib.suppress(OSError, ValueError):
            print(line, flush=True)
    with contextlib.suppress(OSError, ValueError), open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def save_state(obj):
    try:
        with open(STATE, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
    except (OSError, TypeError, ValueError) as e:
        logger.debug("Failed to save watcher state: %s", e)


def play_voice(filename):
    """Plays Drow Ranger voice line in background (0 tokens cost)."""
    try:
        paths = [
            os.path.join(r"C:\AI\desktop-control", filename),
            os.path.join(r"C:\AI\desktop-control\voices_drow", filename)
        ]
        target = next((p for p in paths if os.path.exists(p)), None)
        if target:
            sys.path.insert(0, r"C:\AI\desktop-control")
            import audio
            audio.play_audio(target)
    except Exception as e:  # Optional external audio module boundary
        logger.debug("play_voice failed: %s", e)


def notify(title, msg):
    """Windows-тост без модулей. Тихо игнорирует ошибки."""
    try:
        t = title.replace('"', "'")[:120]
        m = msg.replace('"', "'")[:200]
        ps = (
            "$xml=@\"\n"
            "<toast><visual><binding template='ToastGeneric'>"
            f"<text>{t}</text><text>{m}</text>"
            "</binding></visual></toast>\n"
            "\"@; "
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null; "
            "$doc=[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType=WindowsRuntime]::new(); "
            "$doc.LoadXml($xml); "
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Dota2 MCP').Show("
            "[Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType=WindowsRuntime]::new($doc))"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            check=False,
            capture_output=True,
            timeout=15,
            creationflags=0x08000000,
        )
    except (OSError, subprocess.SubprocessError, ValueError, TypeError) as e:
        logger.debug("Toast notify failed: %s", e)


def dota_running():
    try:
        import psutil
    except ImportError:
        psutil = None

    if psutil is not None:
        try:
            for p in psutil.process_iter(["name"]):
                name = p.info.get("name")
                if name and name.lower() == "dota2.exe":
                    return True
            return False
        except (psutil.Error, OSError) as e:
            logger.debug("psutil process_iter failed: %s", e)

    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq dota2.exe", "/FO", "CSV", "/NH"],
            check=False,
            capture_output=True,
            timeout=5,
            creationflags=0x08000000,
        )
        txt = (out.stdout or b"").decode("utf-8", "replace").lower()
        return "dota2.exe" in txt
    except (OSError, subprocess.SubprocessError, ValueError):
        return False


def gsi_info():
    try:
        with open(GSI_FILE, encoding="utf-8") as f:
            d = json.load(f)
        age = time.time() - float(d.get("_received_at", 0))
        mp = d.get("map") or {}
        hero = (d.get("hero") or {}).get("name", "?")
        pl = d.get("player") or {}
        # spectator: hero id 0, team spectator
        spect = (pl.get("team_name") == "spectator") or ((d.get("hero") or {}).get("id", 1) in (0, None))
        ev = d.get("events") or []
        bld = d.get("buildings") or {}
        return {"age": age,
                "stage": mp.get("game_state"),
                "hero": hero,
                "spectator": spect,
                "matchid": mp.get("matchid"),
                "score": f"{mp.get('radiant_score', '?')}:{mp.get('dire_score', '?')}",
                "clock": mp.get("clock_time", mp.get("game_time")),
                "kda": f"{pl.get('kills', '?')}/{pl.get('deaths', '?')}/{pl.get('assists', '?')}",
                "gpm": pl.get("gold_per_min"),
                "hp": (d.get("hero") or {}).get("health"),
                "events_n": len(ev),
                "has_buildings": bool(bld),
                "paused": mp.get("paused")}
    except (OSError, json.JSONDecodeError, TypeError, ValueError, AttributeError):
        return None


def start_background_servers():
    """Запускает GSI-приёмник (порт 3000) и Live HUD (порт 8081) в фоновых потоках."""
    # 1. GSI сервер
    try:
        import gsi_server
        def _run_gsi():
            try:
                srv = gsi_server.HTTPServer((gsi_server.HOST, gsi_server.PORT), gsi_server.Handler)
                log(f"GSI сервер запущен на http://{gsi_server.HOST}:{gsi_server.PORT}")
                srv.serve_forever()
            except OSError as e:
                log(f"GSI сервер порт {gsi_server.PORT} уже занят (возможно запущен отдельно): {e}")
            except Exception as e:
                log(f"GSI сервер ошибка: {e}")
        t_gsi = threading.Thread(target=_run_gsi, daemon=True, name="GSIServerThread")
        t_gsi.start()
    except Exception as e:
        log(f"Не удалось запустить GSI сервер: {e}")

    # 2. Live HUD 2.0 (локальный сайт)
    try:
        import live_board
        def _run_board():
            try:
                live_board.C.track_tick()
                live_board.start_pipe_broadcaster()
                srv = live_board.HTTPServer((live_board.HOST, live_board.PORT), live_board.H)
                log(f"Live HUD 2.0 (локальный сайт) запущен на http://{live_board.HOST}:{live_board.PORT}")
                srv.serve_forever()
            except OSError as e:
                log(f"Live HUD порт {live_board.PORT} уже занят (возможно запущен отдельно): {e}")
            except Exception as e:
                log(f"Live HUD ошибка: {e}")
        t_board = threading.Thread(target=_run_board, daemon=True, name="LiveBoardThread")
        t_board.start()
    except Exception as e:
        log(f"Не удалось запустить Live HUD: {e}")



OVERLAY_EXE = os.path.join(BASE, "overlay_bin", "DotaOverlay.Wpf.exe")
_overlay_proc = None


def start_overlay():
    global _overlay_proc
    if _overlay_proc is not None and _overlay_proc.poll() is None:
        return
    if os.path.exists(OVERLAY_EXE):
        try:
            si = subprocess.STARTUPINFO()
            si.lpDesktop = r"winsta0\default"
            _overlay_proc = subprocess.Popen([OVERLAY_EXE], startupinfo=si, creationflags=0x08000000)
            log(f"WPF In-Game Overlay запущен (PID {_overlay_proc.pid})")
        except (OSError, ValueError, AttributeError) as e:
            log(f"Не удалось запустить WPF In-Game Overlay: {e}")


def stop_overlay():
    global _overlay_proc
    if _overlay_proc is not None:
        try:
            _overlay_proc.terminate()
            log("WPF In-Game Overlay остановлен")
        except (OSError, ProcessLookupError) as e:
            logger.debug("Failed to terminate overlay process: %s", e)
        _overlay_proc = None

def main():
    if sys.stdout is not None:
        with contextlib.suppress(AttributeError, OSError, ValueError):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    start_background_servers()
    log(f"watcher старт (опрос каждые {POLL} c)")
    was_running = None
    last_stage = None
    last_hero = None
    match_start = None
    while True:
        try:
            running = dota_running()
            if was_running is None:
                was_running = running
                log(f"dota2.exe: {'запущена' if running else 'не найдена'}")
                save_state({"dota_running": running, "ts": time.time()})
                if running:
                    start_overlay()
            elif running != was_running:
                was_running = running
                if running:
                    log("EVENT: Dota 2 ЗАПУЩЕНА")
                    notify("Dota 2 MCP", "Дота запущена. HUD: http://127.0.0.1:8081 | Оверлей: F8")
                    start_overlay()
                else:
                    log("EVENT: Dota 2 ЗАКРЫТА")
                    notify("Dota 2 MCP", "Дота закрыта.")
                    stop_overlay()
                    last_stage = None
                    match_start = None
                save_state({"dota_running": running, "ts": time.time()})

            if running:
                g = gsi_info()
                fresh = g is not None and g["age"] < 15
                stage = g["stage"] if g else None
                if g and fresh and stage != last_stage:
                    if g.get("spectator"):
                        log(
                            f"EVENT: стадия -> {stage} [SPECTATE матч {g.get('matchid')} "
                            f"счёт {g.get('score')} время {g['clock']}]"
                        )
                    else:
                        log(f"EVENT: стадия -> {stage} (герой {g['hero']}, время {g['clock']})")
                    last_stage = stage
                    if stage == "DOTA_GAMERULES_STATE_HERO_SELECTION":
                        log("EVENT: СТАДИЯ ВЫБОРА ГЕРОЕВ (Радар лобби и смурф-детектор активны)")
                        notify("Выбор героев", "Радар лобби активен! Проверяю смурфов и сигнатурки игроков.")
                        voice_coach.coach.on_game_start()
                    if stage in ("DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",) and match_start is None:
                        match_start = time.time()
                        log(f"EVENT: МАТЧ НАЧАЛСЯ ({g['hero']})")
                        hero_short = g["hero"].replace("npc_dota_hero_", "")
                        notify("Матч начался", f"{hero_short} — удачи! Напиши мне «что там?» для совета.")
                        voice_coach.coach.on_game_start()
                    if stage in ("DOTA_GAMERULES_STATE_POST_GAME", "DOTA_GAMERULES_STATE_GAME_OVER") and match_start:
                        dur = int((time.time() - match_start) / 60)
                        log(f"EVENT: МАТЧ ЗАКОНЧЕН ({g['hero']}, KDA {g['kda']}, длился ~{dur} мин)")
                        hero_short = g["hero"].replace("npc_dota_hero_", "")
                        notify(
                            "Матч окончен",
                            f"{hero_short}, KDA {g['kda']}, ~{dur} мин. Напиши мне для разбора!",
                        )
                        voice_coach.coach.on_victory()
                        match_start = None
                if g and fresh and g["hero"] != last_hero and g["hero"] != "?":
                    last_hero = g["hero"]
                    log(f"Герой: {g['hero']}")

                # Live Cute Voice Timers (Bounty, Wisdom, River runes)
                if g and fresh and stage == "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS" and isinstance(g.get("clock"), (int, float)):
                    cue = voice_coach.coach.check_timers(int(g["clock"]))
                    if cue:
                        log(f"EVENT: ОЗВУЧКА -> {cue} (время матча {int(g['clock'])})")

                # Auto-Accept match if in menu/queue
                if (
                    not (
                        g
                        and fresh
                        and stage in ("DOTA_GAMERULES_STATE_GAME_IN_PROGRESS", "DOTA_GAMERULES_STATE_HERO_SELECTION")
                    )
                    and auto_accept.try_accept_match()
                ):
                    log("EVENT: МАТЧ АВТО-ПРИНЯТ!")
                    notify("Dota 2 Auto-Accept", "Матч найден и успешно принят! ✅")
                save_state({"dota_running": True, "gsi_fresh": fresh,
                            "stage": stage if (g and fresh) else None,
                            "hero": (g["hero"] if g else None), "ts": time.time()})
            time.sleep(POLL)
        except KeyboardInterrupt:
            log("watcher остановлен")
            break
        except Exception as e:
            log(f"ошибка: {e}")
            time.sleep(POLL)


if __name__ == "__main__":
    main()
