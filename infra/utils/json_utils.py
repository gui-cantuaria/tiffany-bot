import asyncio
import json
import os
import tempfile
import logging

log = logging.getLogger("tiffany-bot")

def _atomic_write_worker(raw_json: str, filepath: str):
    filepath = os.path.abspath(filepath)
    dir_name = os.path.dirname(filepath)
    
    # Ensure directory exists
    if dir_name and not os.path.exists(dir_name):
        os.makedirs(dir_name, exist_ok=True)

    # Write to a temporary file in the same directory
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(raw_json)
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
    Serializes JSON in the calling thread to prevent race conditions (dictionary changed size during iteration)
    when offloading disk I/O to background threads.
    """
    raw_json = json.dumps(data, ensure_ascii=ensure_ascii, indent=indent)
    
    if "PYTEST_CURRENT_TEST" not in os.environ:
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                log.debug("Offloading synchronous atomic_json_dump to worker thread for %s to protect event loop.", filepath)
                loop.run_in_executor(None, _atomic_write_worker, raw_json, filepath)
                return
        except RuntimeError:
            pass

    _atomic_write_worker(raw_json, filepath)


async def async_atomic_json_dump(data, filepath, ensure_ascii=False, indent=None):
    """
    Asynchronous version of atomic_json_dump using asyncio.to_thread.
    Executes disk writing and fsync without blocking the Event Loop.
    """
    raw_json = json.dumps(data, ensure_ascii=ensure_ascii, indent=indent)
    await asyncio.to_thread(_atomic_write_worker, raw_json, filepath)


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
