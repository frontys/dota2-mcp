"""auto_scout.py — Автономный разведчик лобби и смурф-радар для Dota 2.
Полностью автоматический режим:
1. GSI `allplayers` (данные движка Valve в реальном времени).
2. OpenDota `/api/live` по `match_id` (все 10 игроков с командами и слотами).
3. Dota 2 `console.log` (непрерывный скан логов движка Source 2 на Steam3/Steam64 ID).
4. Windows Clipboard (пассивный перехват скопированных ссылок/профилей).
100% бесплатно (0 токенов нейросетей, локальный кэш на диске) и 100% VAC-Safe (нет хуков и инъекций).
"""
import concurrent.futures
import ctypes
import http.client
import json
import logging
import os
import sys
import threading
import time
import urllib.error
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

import dota_core as C
import scout_engine

logger = logging.getLogger(__name__)


class AutoScoutManager:
    """Менеджер автоматической разведки лобби в реальном времени."""

    def __init__(self):
        self._lock = threading.Lock()
        self.match_id = "0"
        self.stage = "UNKNOWN"
        self.self_account_id = None
        self.self_team = "unknown"

        # Структура игрока: { account_id: int } -> dossier dict
        self.players_dossiers = {}
        # Метаданные слотов: { account_id: int } -> { team, slot, hero_id, hero_name, name }
        self.players_meta = {}

        self.last_opendota_fetch = 0.0
        self.last_clipboard_text = ""
        self.console_log_path = self._find_console_log()
        self.console_log_pos = 0

        self.is_running = False
        self._thread = None

    def _find_console_log(self):
        """Ищет активный файл console.log в установках Dota 2."""
        cfg = C.CFG or {}
        installs = cfg.get("dota_installs") or [
            r"E:\SteamLibrary\steamapps\common\dota 2 beta",
            r"D:\SteamLibrary\steamapps\common\dota 2 beta",
            r"C:\Program Files (x86)\Steam\steamapps\common\dota 2 beta",
        ]
        for root in installs:
            candidate = os.path.join(root, "game", "dota", "console.log")
            if os.path.exists(candidate):
                return candidate
        return None

    def start_background_sniffer(self):
        """Запускает фоновый поток опроса (если еще не запущен)."""
        with self._lock:
            if self.is_running:
                return
            self.is_running = True
            self._thread = threading.Thread(target=self._worker_loop, daemon=True)
            self._thread.start()

    def _worker_loop(self):
        """Бесконечный цикл фонового мониторинга консоли, буфера и OpenDota."""
        while self.is_running:
            try:
                self._check_clipboard()
                self._check_console_log()
                self._sync_opendota_live()
                self._scout_unscouted_players()
            except Exception as e:  # Daemon loop boundary: keep sniffer thread alive
                logger.debug("AutoScout worker error: %s", e)
            time.sleep(1.5)

    def _get_clipboard_text(self):
        """Безопасное чтение текста из буфера обмена Windows через ctypes (Win64-safe, чистый stdlib)."""
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            user32.OpenClipboard.argtypes = [ctypes.c_void_p]
            user32.OpenClipboard.restype = ctypes.c_bool
            user32.CloseClipboard.argtypes = []
            user32.CloseClipboard.restype = ctypes.c_bool
            user32.GetClipboardData.argtypes = [ctypes.c_uint]
            user32.GetClipboardData.restype = ctypes.c_void_p
            kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
            kernel32.GlobalLock.restype = ctypes.c_void_p
            kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
            kernel32.GlobalUnlock.restype = ctypes.c_bool

            if not user32.OpenClipboard(None):
                return ""
            try:
                h = user32.GetClipboardData(13)  # CF_UNICODETEXT
                if not h:
                    return ""
                ptr = kernel32.GlobalLock(h)
                if not ptr:
                    return ""
                try:
                    return ctypes.c_wchar_p(ptr).value or ""
                finally:
                    kernel32.GlobalUnlock(h)
            finally:
                user32.CloseClipboard()
        except (OSError, ctypes.ArgumentError, AttributeError, ValueError, TypeError):
            return ""

    def _check_clipboard(self):
        """Проверяет буфер обмена на наличие новых ID игроков или ссылок."""
        txt = self._get_clipboard_text()
        if not txt or txt == self.last_clipboard_text or len(txt) > 2000:
            return
        self.last_clipboard_text = txt

        ids = scout_engine.parse_player_identifiers(txt)
        if ids:
            with self._lock:
                for aid in ids:
                    if aid not in self.players_meta:
                        self.players_meta[aid] = {
                            "account_id": aid,
                            "team": "unassigned",
                            "source": "clipboard",
                        }

    def _check_console_log(self):
        """Сканирует новые строки console.log на наличие Steam3 / Steam64 ID."""
        if not self.console_log_path or not os.path.exists(self.console_log_path):
            self.console_log_path = self._find_console_log()
            if not self.console_log_path:
                return

        try:
            size = os.path.getsize(self.console_log_path)
            if size < self.console_log_pos:
                # Файл был перезаписан или очищен при перезапуске Dota
                self.console_log_pos = 0

            if size == self.console_log_pos:
                return

            with open(self.console_log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self.console_log_pos)
                new_text = f.read()
                self.console_log_pos = f.tell()

            if not new_text:
                return

            ids = scout_engine.parse_player_identifiers(new_text)
            if ids:
                with self._lock:
                    for aid in ids:
                        if aid not in self.players_meta:
                            self.players_meta[aid] = {
                                "account_id": aid,
                                "team": "unassigned",
                                "source": "console_log",
                            }
        except (OSError, ValueError, TypeError) as e:
            logger.debug("Failed to scan console.log: %s", e)

    def update_from_gsi(self, data):
        """Парсит входящий пакет GSI (allplayers, player, map, draft)."""
        if not isinstance(data, dict):
            return

        mp = data.get("map") or {}
        new_mid = str(mp.get("matchid") or "0")
        stage = mp.get("game_state", "UNKNOWN")

        with self._lock:
            # Смена матча -> очищаем старый состав
            if new_mid not in ("0", "", None) and new_mid != self.match_id:
                self.match_id = new_mid
                self.players_dossiers.clear()
                self.players_meta.clear()
                self.last_opendota_fetch = 0.0

            self.stage = stage

            # Информация о текущем игроке
            pl = data.get("player") or {}
            self_aid_raw = pl.get("accountid")
            if self_aid_raw:
                try:
                    self.self_account_id = int(self_aid_raw)
                    self.self_team = (pl.get("team_name") or "unknown").lower()
                    if self.self_account_id not in self.players_meta:
                        self.players_meta[self.self_account_id] = {
                            "account_id": self.self_account_id,
                            "name": pl.get("name", "You"),
                            "team": self.self_team,
                            "slot": pl.get("player_slot"),
                            "source": "gsi_player",
                        }
                except (TypeError, ValueError, AttributeError) as e:
                    logger.debug("Failed to parse GSI self player: %s", e)

            # Парсинг секции allplayers
            allp = data.get("allplayers")
            if isinstance(allp, dict):
                for team_key, team_dict in allp.items():
                    if not isinstance(team_dict, dict):
                        continue
                    if team_key.startswith("player"):
                        # Формат 2: плоский {"player0": {...}, "player1": {...}}
                        self._ingest_player_dict(team_dict)
                    elif any(k.startswith("player") and isinstance(v, dict) for k, v in team_dict.items()):
                        # Формат 1: {"team2": {"player0": {...}}, "team3": {"player5": {...}}}
                        t_name = "radiant" if team_key in ("team2", "radiant") else (
                            "dire" if team_key in ("team3", "dire") else "unassigned"
                        )
                        for p_info in team_dict.values():
                            if isinstance(p_info, dict):
                                self._ingest_player_dict(p_info, default_team=t_name)

    def _ingest_player_dict(self, p_info, default_team="unassigned"):
        """Регистрирует одного игрока из словаря GSI."""
        aid_raw = p_info.get("accountid") or p_info.get("steamid")
        if not aid_raw:
            return

        aid = None
        try:
            aid_num = int(aid_raw)
            if aid_num > 76561197960265728:
                aid = aid_num - 76561197960265728
            else:
                aid = aid_num
        except (TypeError, ValueError):
            return

        if not aid:
            return

        team = (p_info.get("team_name") or default_team).lower()
        if team not in ("radiant", "dire"):
            pslot = p_info.get("player_slot")
            if pslot is not None:
                try:
                    team = "radiant" if int(pslot) < 5 else "dire"
                except (TypeError, ValueError):
                    pass

        slot = p_info.get("player_slot")
        if slot is None:
            slot = p_info.get("team_slot")

        meta = self.players_meta.get(aid, {})
        meta["account_id"] = aid
        meta["name"] = p_info.get("name") or meta.get("name") or f"Player_{aid}"
        meta["team"] = team
        meta["slot"] = slot if slot is not None else meta.get("slot")

        hid = p_info.get("hero_id")
        if hid:
            meta["hero_id"] = hid
            meta["hero_name"] = scout_engine.HEROES_MAP.get(int(hid), str(hid))

        meta["source"] = "gsi_allplayers"
        self.players_meta[aid] = meta

    def _sync_opendota_live(self):
        """Опрашивает OpenDota /api/live для автоматического получения всех 10 игроков матча."""
        if not self.match_id or self.match_id in ("0", ""):
            return

        now = time.time()
        # Опрашиваем не чаще 1 раза в 12 секунд
        if now - self.last_opendota_fetch < 12.0:
            return

        # Если уже есть 10 игроков с командами, часто спамить не нужно
        if (
            len(self.players_meta) >= 10
            and all(p.get("team") in ("radiant", "dire") for p in self.players_meta.values())
            and now - self.last_opendota_fetch < 60.0
        ):
            return

        self.last_opendota_fetch = now

        try:
            req = urllib.request.Request(
                "https://api.opendota.com/api/live",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))

            found = None
            for m in data or []:
                if str(m.get("match_id")) == self.match_id:
                    found = m
                    break

            if not found:
                return

            with self._lock:
                for p in found.get("players") or []:
                    aid = p.get("account_id")
                    if not aid:
                        continue
                    team = "radiant" if p.get("team") == 0 else "dire"
                    hid = p.get("hero_id")
                    name = p.get("name")

                    meta = self.players_meta.get(aid, {})
                    meta["account_id"] = aid
                    meta["team"] = team
                    meta["slot"] = p.get("team_slot")
                    if name:
                        meta["name"] = name
                    if hid:
                        meta["hero_id"] = hid
                        meta["hero_name"] = scout_engine.HEROES_MAP.get(int(hid), str(hid))
                    meta["source"] = "opendota_live"
                    self.players_meta[aid] = meta
        except (
            urllib.error.URLError,
            http.client.HTTPException,
            OSError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            AttributeError,
        ) as e:
            logger.debug("OpenDota /live sync failed: %s", e)

    def _scout_unscouted_players(self):
        """Параллельно сканирует игроков, по которым еще нет досье."""
        to_scout = []
        with self._lock:
            for aid in list(self.players_meta.keys()):
                if aid not in self.players_dossiers:
                    to_scout.append(aid)

        if not to_scout:
            return

        # Параллельный запрос до 5 потоков
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_map = {executor.submit(scout_engine.scout_player, aid): aid for aid in to_scout[:10]}
            for future in concurrent.futures.as_completed(future_map):
                aid = future_map[future]
                try:
                    dossier = future.result()
                    with self._lock:
                        self.players_dossiers[aid] = dossier
                except Exception as e:
                    with self._lock:
                        self.players_dossiers[aid] = {"ok": False, "account_id": aid, "error": str(e)}

    def get_lobby_state(self):
        """Возвращает актуальное состояние лобби со всеми карточками и тактическими вердиктами."""
        with self._lock:
            radiant = []
            dire = []
            unassigned = []

            all_threats = []
            suggested_bans = set()

            for aid, meta in self.players_meta.items():
                dossier = self.players_dossiers.get(aid)
                card = dict(meta)

                is_you = bool(self.self_account_id and aid == self.self_account_id)
                card["is_you"] = is_you

                if dossier and dossier.get("ok"):
                    card["name"] = dossier.get("name") or card.get("name")
                    card["avatar"] = dossier.get("avatar")
                    card["rank_name"] = dossier.get("rank_name", "Unranked")
                    card["recent_summary"] = dossier.get("recent_summary", {})
                    card["recent_heroes"] = dossier.get("recent_heroes", [])
                    card["smurf_verdict"] = dossier.get("smurf_verdict", {})
                    card["scouted"] = True

                    # Анализ угрозы и банов
                    v = card["smurf_verdict"]
                    if v.get("is_smurf_threat"):
                        all_threats.append((card.get("team"), card["name"], v["badge"]))
                    for tip in v.get("tips", []):
                        if "Забанить" in tip or "забанить" in tip:
                            suggested_bans.add(tip)
                else:
                    card["scouted"] = False
                    card["error"] = dossier.get("error") if dossier else "Сканирование в процессе..."

                team = card.get("team")
                if team == "radiant":
                    radiant.append(card)
                elif team == "dire":
                    dire.append(card)
                else:
                    unassigned.append(card)

            # Сортируем команды: сначала самые опасные (смурфы/бустеры)
            def _threat_score(c):
                if not c.get("scouted"):
                    return 0
                return c.get("smurf_verdict", {}).get("score", 0)

            radiant.sort(key=_threat_score, reverse=True)
            dire.sort(key=_threat_score, reverse=True)
            unassigned.sort(key=_threat_score, reverse=True)

            # Подсчет смурфов у врагов
            enemy_team = "dire" if self.self_team == "radiant" else (
                "radiant" if self.self_team == "dire" else None
            )

            enemy_smurfs = 0
            if enemy_team == "dire":
                enemy_smurfs = sum(1 for p in dire if p.get("smurf_verdict", {}).get("is_smurf_threat"))
            elif enemy_team == "radiant":
                enemy_smurfs = sum(1 for p in radiant if p.get("smurf_verdict", {}).get("is_smurf_threat"))
            else:
                enemy_smurfs = sum(1 for p in (radiant + dire + unassigned) if p.get("smurf_verdict", {}).get("is_smurf_threat"))

            return {
                "ok": True,
                "match_id": self.match_id,
                "stage": self.stage,
                "self_account_id": self.self_account_id,
                "self_team": self.self_team,
                "total_players": len(self.players_meta),
                "radiant": radiant,
                "dire": dire,
                "unassigned": unassigned,
                "summary": {
                    "enemy_smurfs_detected": enemy_smurfs,
                    "threat_level": "DANGER" if enemy_smurfs >= 2 else ("WARNING" if enemy_smurfs == 1 else "NORMAL"),
                    "suggested_bans": sorted(suggested_bans),
                    "all_threats": all_threats,
                },
            }

    def fmt_lobby_report(self):
        """Красивый текстовый отчет по лобби для терминала и CLI."""
        st = self.get_lobby_state()
        lines = []
        lines.append("══════════════════════════════════════════════════════════════════════════")
        lines.append(f"🛡️ РАДАР ЛОББИ: СОЮЗНИКИ vs ПРОТИВНИКИ (Матч: {st['match_id']} | Стадия: {st['stage']})")
        lines.append("══════════════════════════════════════════════════════════════════════════")

        s = st.get("summary", {})
        if s.get("enemy_smurfs_detected", 0) > 0:
            lines.append(
                f"🚨 ВНИМАНИЕ: Во вражеской команде обнаружено подозрительных игроков: {s['enemy_smurfs_detected']}!"
            )
        if s.get("suggested_bans"):
            lines.append("💡 РЕКОМЕНДАЦИИ ПО БАНАМ: " + " | ".join(s["suggested_bans"]))

        for t_name, title, emoji in (
            ("radiant", "RADIANT (Свет)", "🟢"),
            ("dire", "DIRE (Тьма)", "🔴"),
            ("unassigned", "НЕРАСПРЕДЕЛЕННЫЕ ИГРОКИ", "⚪"),
        ):
            plist = st.get(t_name, [])
            if not plist:
                continue
            lines.append(f"\n{emoji} {title} ({len(plist)} игроков):")
            lines.append("──────────────────────────────────────────────────────────────────────────")
            for i, p in enumerate(plist, 1):
                is_you = " [ТЫ]" if p.get("is_you") else ""
                v = p.get("smurf_verdict") or {}
                badge = v.get("badge", "⏳ Сканирование")
                r_name = p.get("rank_name", "Rank ?")
                h_picked = f" (Герой: {p.get('hero_name')})" if p.get("hero_name") else ""
                lines.append(
                    f"{i}. {p.get('name', 'Player')} [{r_name}] (ID: {p['account_id']}){is_you}{h_picked} — {badge}"
                )

                summ = p.get("recent_summary")
                if summ:
                    wins = int(summ.get("wins", 0) or 0)
                    losses = int(summ.get("losses", 0) or 0)
                    wr = summ.get("winrate_pct", 0)
                    kda = summ.get("avg_kda", 0)
                    gpm = int(summ.get("avg_gpm", 0) or 0)
                    lines.append(f"   Форма: {wins}W - {losses}L ({wr:.1f}% WR) | KDA: {kda:.2f} | GPM: {gpm}")

                h_chips = []
                for h in p.get("recent_heroes", [])[:3]:
                    fire = "🔥 " if h.get("is_smurf_hero") else ""
                    h_chips.append(f"{fire}{h['hero_name']} ({int(h['games'])} игр, {h['winrate_pct']:.0f}% WR)")
                if h_chips:
                    lines.append("   Пул: " + ", ".join(h_chips))

                if v.get("triggers"):
                    for tr in v["triggers"]:
                        lines.append(f"   ⚠️ {tr}")
                if v.get("tips"):
                    for tp in v["tips"]:
                        lines.append(f"   💡 Совет: {tp}")

        lines.append("══════════════════════════════════════════════════════════════════════════")
        return "\n".join(lines)


# Глобальный синглтон-менеджер
_MANAGER = None
_INIT_LOCK = threading.Lock()


def get_scout_manager():
    global _MANAGER
    with _INIT_LOCK:
        if _MANAGER is None:
            _MANAGER = AutoScoutManager()
            _MANAGER.start_background_sniffer()
        return _MANAGER
