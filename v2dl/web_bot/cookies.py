import json
import logging
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Any

logger = logging.getLogger()


def load_cookies(file_path: str) -> dict[str, str] | dict[str, Any]:
    if not file_path:
        logger.error("File path not exists.")
        return {}

    fp = Path(file_path)
    if not fp.exists():
        logger.error("File not found: %s", file_path)
        return {}
    if not fp.is_file():
        logger.error("Not a valid file: %s", file_path)
        return {}

    try:
        if fp.suffix.lower() == ".json":
            with fp.open("r", encoding="utf-8") as f:
                logger.debug("Reading cookies from JSON file: %s", file_path)
                cookies = json.load(f)
                if not isinstance(cookies, dict):
                    logger.error(
                        "Invalid JSON format. Expected a dictionary in file: %s",
                        file_path,
                    )
                    return {}
                return {str(k): str(v) for k, v in cookies.items()}
        elif fp.suffix.lower() == ".txt":
            logger.debug("Reading cookies from MozillaCookieJar file: %s", file_path)
            cookie_jar = MozillaCookieJar(fp)
            cookie_jar.load(ignore_discard=True, ignore_expires=True)
            return {cookie.name: cookie.value for cookie in cookie_jar}
        else:
            logger.error("Unsupported file type: %s. Supported types: .json, .txt", fp.suffix)
            return {}
    except json.JSONDecodeError as e:
        logger.error("JSON decoding error in file %s: %s", file_path, e)
    except OSError as e:
        logger.error("OS error when accessing file %s: %s", file_path, e)
    except Exception as e:
        logger.error("Unexpected error: %s", e)

    return {}
