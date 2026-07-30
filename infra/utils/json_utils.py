import json
import os
import tempfile
import logging

log = logging.getLogger("tiffany-bot")

def atomic_json_dump(data, filepath, ensure_ascii=False, indent=None):
    """
    Writes JSON data to a temporary file and atomically replaces the target file.
    This prevents file corruption if the process crashes during writing.
    """
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
        log.error(f"Failed to atomically write JSON to {filepath}: {e}")
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
