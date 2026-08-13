import logging
import os
import sys


def _log_directory():
    configured = os.environ.get("PHISHGUARD_LOG_DIR")
    if configured:
        return configured
    try:
        directory = os.path.join(os.getcwd(), "logs")
        os.makedirs(directory, exist_ok=True)
        return directory
    except OSError:
        return None


def _build_logger():
    logger = logging.getLogger("networksecurity")
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    directory = _log_directory()
    if directory is not None:
        try:
            file_handler = logging.FileHandler(os.path.join(directory, "networksecurity.log"))
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except OSError:
            pass

    return logger


logging = _build_logger()
