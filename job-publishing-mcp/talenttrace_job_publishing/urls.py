"""Local validation only; never fetch or resolve an application URL."""
import ipaddress
import re
import unicodedata
from urllib.parse import unquote, urlsplit


def validate_application_url(value: str) -> str:
    try:
        if not isinstance(value, str) or not 1 <= len(value) <= 2048:
            raise ValueError
        decoded = unquote(value)
        if any(c.isspace() or c in "<>\\" or unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in value):
            raise ValueError
        if any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in decoded):
            raise ValueError
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username is not None or parsed.password is not None or "#" in value or parsed.port not in {None, 443}:
            raise ValueError
        host = parsed.hostname.encode("idna").decode("ascii")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if "." not in host or host.lower() == "localhost" or host.lower().endswith((".localhost", ".local")):
                raise ValueError
            if len(host) > 253 or not re.search(r"[a-zA-Z]", host.rsplit(".", 1)[-1]):
                raise ValueError
            if any(not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label) for label in host.split(".")):
                raise ValueError
        else:
            if not address.is_global:
                raise ValueError
    except (ValueError, UnicodeError):
        raise ValueError("Application URL must be a bounded public HTTPS URL without credentials, fragments or unsafe characters.") from None
    return value
