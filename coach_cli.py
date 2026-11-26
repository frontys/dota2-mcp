"""Консольный тренер без Claude Desktop. Stdlib-only.
Запуск:  python coach_cli.py
Команды: help, gsi, tip [герой] [минута], pick sniper riki, item invoker,
         scout [id...], profile, recent [N], match <id>, live, watch [сек],
         hero <hero_id>, launch [training], account <id>, quit
"""
import contextlib
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import dota_core as C
import dota_tools_a as A
import dota_tools_b as B

HELP = """Команды:
  gsi                  - живое состояние игры (нужен gsi_server.py + матч)
  live                 - 1 тик живого трекера: сейчас + темп за 1/5 мин (GPM факт!)
  watch [сек]          - LIVE каждые N сек (по умолч. 5): тик + дельты + вердикт
  tip [герой] [минута] - совет тренера (без аргументов = по живой игре)
  pick <враги...>      - глубокий контрпик (все 124+ героя, сленг: pick сф од или pick sniper riki)
  scout [id...]        - разведка игроков / смурф-радар (проверка на смурфа, винрейт, недавние герои)
  item <герой>         - закуп, напр: item invoker
  profile              - твой OpenDota-профиль
  recent [N]           - последние матчи
  match <id>           - глубокий пост-матч разбор (ошибки, KDA, урон, закуп)
  hero <hero_id>       - статистика на герое
  launch [training]    - запустить Dota 2
  account <id>         - сохранить account_id
  help / quit
"""

LIVE_N = 5  # интервал watch по умолчанию

FmtMin = lambda s: f"{int(s or 0) // 60}:{int(s or 0) % 60:02d}"


def fmt_tick(t):
    """Компактная строка тика для watch: время, золото, темп, счёт."""
    if not t.get("ok"):
        return f"LIVE нет: {t.get('error')}"
    cur = t.get("сейчас") or {}
    tempo = t.get("темп") or {}
    s = t.get("summary") or {}
    m1 = (tempo.get("60сек") or {})
    m5 = (tempo.get("5мин") or {})
    parts = []
    parts.append(f"[{FmtMin(cur.get('game_time', s.get('время_сек', 0)))}]")
    parts.append(f"золото {cur.get('gold')}")
    if "золото_в_мин_факт" in m1:
        parts.append(f"темп1м {int(m1['золото_в_мин_факт']):+d}/мин")
    if "золото_в_мин_факт" in m5:
        parts.append(f"темп5м {int(m5['золото_в_мин_факт']):+d}/мин")
    if cur.get("gpm_gsi") is not None:
        parts.append(f"gpm_gsi {cur.get('gpm_gsi')}")
    for k in ("kills_дельта", "deaths_дельта", "lh_дельта"):
        if k in m5:
            parts.append(f"{k.replace('_дельта', '')} {m5[k]:+.0f}/5м")
    parts.append(f"счёт {cur.get('radiant_score', '?')}:{cur.get('dire_score', '?')}")
    if t.get("вердикт"):
        parts.append("| " + t["вердикт"])
    if not t.get("fresh"):
        parts.append(f"(STALE-пакет {s.get('возраст_пакета_сек', -1):.0f}с)")
    return " ".join(str(p) for p in parts)


def show(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))

def cmd_watch(interval=LIVE_N, once=False):
    """Живой трекер: каждые N сек тик с дельтами."""
    try:
        interval = max(2, min(int(interval), 60))
    except (TypeError, ValueError):
        interval = LIVE_N
    print(f"LIVE-трекер: тик каждые {interval} сек. Ctrl+C — выйти.")
    try:
        while True:
            t = B.t_live_tick()
            print(fmt_tick(t))
            if once:
                show(t)
                break
            # раз в ~30 сек полный JSON чтобы не спамить, иначе строка
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Вышел из LIVE.")

def main():
    with contextlib.suppress(AttributeError, OSError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    print("Dota2 тренер. Введи help. Выйти: quit.")
    if not C.CFG.get("account_id"):
        print("Подсказка: узнай account_id на opendota.com и введи: account 123456789")
    while True:
        try:
            raw = input("dota> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nПока!")
            break
        if not raw:
            continue
        parts = raw.split()
        cmd, args = parts[0].lower(), parts[1:]
        if cmd in ("quit", "exit", "q"):
            print("Пока!")
            break
        elif cmd == "help":
            print(HELP)
        elif cmd == "gsi":
            show(A.t_gsi_latest())
        elif cmd == "tip":
            hero = args[0] if len(args) >= 1 and not args[0].isdigit() else None
            minute = None
            for a in args:
                if a.isdigit():
                    minute = int(a)
            show(B.t_coach_tip(hero, minute))
        elif cmd == "pick":
            res = B.t_pick_advice(args)
            if res.get("текст"):
                print(res["текст"])
            else:
                show(res)
        elif cmd == "scout":
            query = " ".join(args) if args else "auto"
            res = B.t_scout_lobby(query)
            if res.get("текст"):
                print(res["текст"])
            else:
                show(res)
        elif cmd == "item":
            show(B.t_item_guide(args[0] if args else ""))
        elif cmd == "profile":
            show(A.t_profile())
        elif cmd == "recent":
            show(B.t_recent_matches(int(args[0]) if args and args[0].isdigit() else 10))
        elif cmd == "match":
            if not args:
                print("Нужно: match <match_id>")
            else:
                res = B.t_match_details(args[0])
                if res.get("текст"):
                    print(res["текст"])
                else:
                    show(res)
        elif cmd == "watch":
            cmd_watch(args[0] if args and args[0].isdigit() else 5)
        elif cmd == "live":
            t = B.t_live_tick()
            print(fmt_tick(t))
            show(t)
        elif cmd == "hero":
            if not args:
                print("Нужно: hero <hero_id>")
            else:
                show(B.t_hero_stats(args[0]))
        elif cmd == "launch":
            show(A.t_launch(args[0] if args else "normal"))
        elif cmd == "account":
            if not args:
                print("Нужно: account <числовой id>")
            else:
                show(A.t_set_account(args[0]))
        else:
            print("Не знаю. Введи help.")

if __name__ == "__main__":
    main()
