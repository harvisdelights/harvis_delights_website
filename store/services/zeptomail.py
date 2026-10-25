from email.utils import parseaddr
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


def email_configured():
    return bool(settings.ZEPTOMAIL_API_KEY and settings.ZEPTOMAIL_API_URL)


class ZeptoMailBackend(BaseEmailBackend):
    """Send individual messages through ZeptoMail's HTTPS API."""

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        try:
            if not email_configured():
                raise ValueError("ZeptoMail is not configured")
            url = urlsplit(settings.ZEPTOMAIL_API_URL)
            # Use the endpoint displayed by the selected ZeptoMail/CPaaS
            # agent. Accounts in the India data centre use cpaas.zoho.in.
            allowed_hosts = {
                "api.zeptomail.com", "api.zeptomail.in",
                "zeptomail.zoho.com", "zeptomail.zoho.in",
                "cpaas.zoho.com", "cpaas.zoho.in",
            }
            if url.scheme != "https" or url.hostname not in allowed_hosts or url.path != "/v1.1/email" or url.query or url.fragment or url.username or url.password or url.port not in (None, 443):
                raise ValueError("Invalid ZeptoMail API URL")
            key = settings.ZEPTOMAIL_API_KEY
            authorization = key if key.startswith("Zoho-enczapikey ") else f"Zoho-enczapikey {key}"
            sent = 0
            for message in email_messages:
                name, address = parseaddr(message.from_email or settings.DEFAULT_FROM_EMAIL)
                for recipient in message.recipients():
                    payload = {"from": {"address": address, "name": name or "Harvi's Delights"}, "to": [{"email_address": {"address": recipient}}], "subject": message.subject, "textbody": message.body}
                    response = requests.post(settings.ZEPTOMAIL_API_URL, json=payload, headers={"Authorization": authorization, "Accept": "application/json"}, timeout=8, allow_redirects=False)
                    if not 200 <= response.status_code < 300:
                        raise ValueError(f"ZeptoMail rejected the request (HTTP {response.status_code})")
                sent += 1
            return sent
        except (requests.RequestException, ValueError) as exc:
            if self.fail_silently:
                return 0
            # Never propagate a provider response or request headers containing secrets.
            raise RuntimeError("ZeptoMail could not accept the email") from exc
