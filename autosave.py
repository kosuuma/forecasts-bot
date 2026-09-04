"""
Автосохранение проекта в GitHub — как save point в игре.

Следит за папкой проекта и при любом изменении файла (кроме игнорируемых)
автоматически делает git commit + push.

Запуск:
    python autosave.py

Останов: Ctrl+C
"""
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    print("Нужна библиотека watchdog. Установи: pip install watchdog")
    sys.exit(1)

# Папка проекта — по умолчанию та, где лежит сам скрипт
PROJECT_DIR = Path(__file__).resolve().parent

# Что игнорировать (кроме того, что уже в .gitignore)
IGNORE_DIRS = {".git", "__pycache__", "venv", ".venv", "node_modules"}
IGNORE_SUFFIXES = {".pyc", ".log", ".db", ".db-journal"}
IGNORE_NAMES = {".env"}

# Минимальный интервал между коммитами (секунды) — чтобы не спамить
# коммитами при массовом сохранении/копировании файлов
DEBOUNCE_SECONDS = 5


def should_ignore(path: Path) -> bool:
    parts = set(path.parts)
    if parts & IGNORE_DIRS:
        return True
    if path.suffix in IGNORE_SUFFIXES:
        return True
    if path.name in IGNORE_NAMES:
        return True
    return False


def run_git(*args) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=PROJECT_DIR, capture_output=True, text=True
    )


def has_changes() -> bool:
    result = run_git("status", "--porcelain")
    return bool(result.stdout.strip())


def commit_and_push():
    if not has_changes():
        return

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    run_git("add", "-A")
    commit_result = run_git("commit", "-m", f"Автосохранение: {timestamp}")
    if commit_result.returncode != 0:
        print(f"[{timestamp}] Нечего коммитить или ошибка: {commit_result.stderr.strip()}")
        return

    push_result = run_git("push")
    if push_result.returncode == 0:
        print(f"[{timestamp}] ✅ Сохранено и запушено в GitHub")
    else:
        print(f"[{timestamp}] ⚠️ Коммит создан, но push не удался: {push_result.stderr.strip()}")


class ChangeHandler(FileSystemEventHandler):
    def __init__(self):
        self._last_trigger = 0.0

    def _on_any_change(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        try:
            rel_path = path.relative_to(PROJECT_DIR)
        except ValueError:
            rel_path = path
        if should_ignore(rel_path):
            return

        now = time.time()
        self._last_trigger = now
        # Debounce: ждём немного, вдруг будет ещё серия изменений подряд
        time.sleep(DEBOUNCE_SECONDS)
        if self._last_trigger == now:  # никто не перебил ожидание новым событием
            commit_and_push()

    def on_modified(self, event):
        self._on_any_change(event)

    def on_created(self, event):
        self._on_any_change(event)

    def on_deleted(self, event):
        self._on_any_change(event)

    def on_moved(self, event):
        self._on_any_change(event)


def main():
    if not (PROJECT_DIR / ".git").exists():
        print(f"Ошибка: {PROJECT_DIR} — не git-репозиторий. Сначала сделай git init / клонируй репозиторий.")
        sys.exit(1)

    print(f"👀 Слежу за изменениями в: {PROJECT_DIR}")
    print("Автосохранение включено. Останов: Ctrl+C\n")

    event_handler = ChangeHandler()
    observer = Observer()
    observer.schedule(event_handler, str(PROJECT_DIR), recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nОстановлено.")
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
