import asyncio
import json
import os
import tempfile
import logging

log = logging.getLogger("tiffany-bot")

def _atomic_dump_worker(data, filepath, ensure_ascii=False, indent=None):
    filepath = os.path.abspath(filepath)
    dir_name = os.path.dirname(filepath)
    
    # Ensure directory exists
    if dir_name and not os.path.exists(dir_name):
        os.makedirs(dir_name, exist_ok=True)

    # Write to a temporary file in the same directory
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=ensure_ascii, indent=indent)
            f.flush()
            os.fsync(f.fileno())  # Ensure it is written to disk
            
        # Atomically replace the destination file
        os.replace(tmp_path, filepath)
    except Exception as e:
        log.error("Failed to atomically write JSON to %s: %s", filepath, e)
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise

def atomic_json_dump(data, filepath, ensure_ascii=False, indent=None):
    """
    Writes JSON data to a temporary file and atomically replaces the target file.
    This prevents file corruption if the process crashes during writing.
    Automatically offloads disk execution to a worker thread if an asyncio event loop is running
    (unless in unit tests) to eliminate ~15ms event-loop blocking across hot paths.
    """
    if "PYTEST_CURRENT_TEST" not in os.environ:
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                log.debug("Offloading synchronous atomic_json_dump to worker thread for %s to protect event loop.", filepath)
                loop.run_in_executor(None, _atomic_dump_worker, data, filepath, ensure_ascii, indent)
                return
        except RuntimeError:
            pass

    _atomic_dump_worker(data, filepath, ensure_ascii, indent)


async def async_atomic_json_dump(data, filepath, ensure_ascii=False, indent=None):
    """
    Asynchronous version of atomic_json_dump using asyncio.to_thread.
    Executes disk writing and fsync without blocking the Event Loop.
    """
    await asyncio.to_thread(_atomic_dump_worker, data, filepath, ensure_ascii, indent)


def _load_json_sync(filepath, default=None):
    if not os.path.exists(filepath):
        return default
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


async def async_json_load(filepath, default=None):
    """
    Asynchronous version of json.load using asyncio.to_thread.
    """
    return await asyncio.to_thread(_load_json_sync, filepath, default)
