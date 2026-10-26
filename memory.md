# dota2-mcp — Memory & Knowledge Base

Документ постоянной памяти проекта: архитектура, ключевые решения и история исправленных ошибок.

## 1. О проекте и стек
- **Название**: dota2-mcp (VAC-Safe Live Analytics, In-Game WPF Overlay & FastMCP Hub)
- **Стек**: Python 3.12+, .NET 9 WPF (C# 13), FastMCP, Win32 Named Pipes IPC, Source 2 GSI, SAPI5/WinMM
- **Основная цель**: Полноценный локальный ассистент Dota 2 с нулевой стоимостью токенов (0-token standing cost), работающий строго через официальный GSI и консольные логи без инжекта в память игры (100% VAC-Safe).

## 2. Архитектурные компоненты
1. **Source 2 GSI Server (`gsi_server.py`)**: Прием пакетов телеметрии от Dota 2 по HTTP на порту 3000.
2. **Win32 Named Pipe Server (`pipe_server.py`)**: Канал `\\.\pipe\DotaOverlayPipe` для передачи телеметрии в WPF-оверлей с задержкой <1 мс.
3. **C# .NET 9 WPF Overlay (`DotaOverlay.Wpf`)**: Прозрачный клик-сквозной оверлей поверх экрана (`WS_EX_TRANSPARENT`), хоткей F8, адаптирован под 2560x1080 Ultrawide.
4. **Live HUD 2.0 Web Dashboard (`live_board.py`)**: Дашборд на `http://127.0.0.1:8081`.
5. **Post-Game Analyzer (`postgame_analyzer.py`)**: Generative UI HTML-карточки разбора матча.
6. **FastMCP Server (`server.py`, `dota_tools_*.py`)**: 14 инструментов MCP для взаимодействия с AI-агентами.
7. **Offline Voice Coach (`voice_coach.py`)**: Автономный голосовой тренер на SAPI5 pyttsx3 и WinMM MCI:
   - Предупреждения за 15 сек до спавна Bounty (каждые 4 мин) и Wisdom (7:00, 14:00...)
   - Напоминание стаков нейтральных лагерей на XX:45–XX:53
   - Оповещение об открытии тиров нейтралок (T1: 7m, T2: 17m, T3: 27m, T4: 37m, T5: 60m)
   - Таймер Рошана с отслеживанием окна 8–11 минут
   - Дедупликация событий, rate limiting, настройка громкости и скорости речи.

## 3. Архитектурные решения (ADR)
| Дата | Решение | Контекст / Почему так |
|---|---|---|
| 2026-10-25 | Win32 Named Pipes вместо HTTP-поллинга | Сократило задержку обновления оверлея с 1000 мс до <1 мс, устранило нагрузку на CPU |
| 2026-10-25 | Fallback на HTTP при сбое пайпа | Гарантирует надежность работы оверлея, если Python-сервер перезапускается |
| 2026-10-25 | Generative UI в `postgame_analyzer.py` | Визуализация статистики матча (KDA, урон, рекомендации тренера, закуп) в формате UI-карточек |
| 2026-10-26 | Офлайн TTS на `pyttsx3` (SAPI5) + `VoiceWorker` | Нулевая стоимость, 100% приватность, нет задержек сети. Выделенный поток с COM `CoInitialize` исключает блокировки HTTP/GSI серверов |
| 2026-10-26 | Обработка пакета GSI до отправки HTTP 200 | Вызов `process_gsi_packet` до `self._send(200)` гарантирует синхронное обновление состояния без race conditions в тестах и клиентах |

## 4. База знаний ошибок и фиксов (Post-mortem)
- **Координаты Ultrawide**: На разрешении 2560x1080 оверлей смещался. Зафиксированы точные координаты: `X=1560, Y=38, Width=980, Height=65`.
- **C# .NET 9 Async Correctness**: В `DotaStateService.cs` обязательно использовать `sealed class`, `ConfigureAwait(false)` и строгую передачу `CancellationToken`.
- **Named Pipe Buffer**: Неблокирующая отправка UTF-8 JSON lines для исключения зависаний при отключении клиента.
- **SAPI5 COM threading в Python**: Вызовы SAPI5 через pyttsx3 в потоках требуют вызова `pythoncom.CoInitialize()` в начале потока воркера и `pythoncom.CoUninitialize()` при завершении.
