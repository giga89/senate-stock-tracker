import json
import os
import logging

PROGRESS_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'progress.json')
logger = logging.getLogger(__name__)

def update_progress(status, current, total, message):
    try:
        os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
        data = {
            "status": status,
            "current": current,
            "total": total,
            "message": message
        }
        with open(PROGRESS_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        logger.error(f"Failed to update progress: {e}")

def get_progress():
    try:
        if os.path.exists(PROGRESS_FILE):
            with open(PROGRESS_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return None
