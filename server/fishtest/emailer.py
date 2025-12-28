import os

import requests

RESEND_API_URL = "https://api.resend.com/emails"
RESEND_TIMEOUT = 10


class EmailSendError(RuntimeError):
    pass


class EmailSender:
    def __init__(
        self,
        api_key=None,
        from_email=None,
        from_name=None,
        session=None,
    ):
        self.api_key = api_key or os.getenv("FISHTEST_RESEND_API_KEY")
        self.from_email = from_email or os.getenv("FISHTEST_RESEND_FROM_EMAIL")
        self.from_name = from_name or os.getenv("FISHTEST_RESEND_FROM_NAME", "Fishtest")
        self.session = session or requests.Session()
        missing_settings = []
        if not self.api_key:
            missing_settings.append("FISHTEST_RESEND_API_KEY")
        if not self.from_email:
            missing_settings.append("FISHTEST_RESEND_FROM_EMAIL")
        if missing_settings:
            print(
                "Email sending is not configured; missing {}.".format(
                    ", ".join(missing_settings)
                ),
                flush=True,
            )

    def _from_field(self):
        if not self.from_email:
            raise EmailSendError("FISHTEST_RESEND_FROM_EMAIL is missing.")
        if self.from_name:
            return f"{self.from_name} <{self.from_email}>"
        return self.from_email

    def send(
        self,
        username,
        to_email,
        subject,
        text,
        html=None,
        reply_to=None,
    ):
        if not self.api_key:
            raise EmailSendError("FISHTEST_RESEND_API_KEY is missing.")
        if not to_email:
            raise EmailSendError("to_email is required.")

        payload = {
            "from": self._from_field(),
            "to": [to_email] if isinstance(to_email, str) else to_email,
            "subject": subject,
            "text": text,
        }
        if html:
            payload["html"] = html
        if reply_to:
            payload["reply_to"] = reply_to

        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            response = self.session.post(
                RESEND_API_URL, json=payload, headers=headers, timeout=RESEND_TIMEOUT
            )
        except Exception as exc:
            raise EmailSendError(f"Failed to reach Resend: {exc}") from exc

        if not response.ok:
            raise EmailSendError(
                f"Resend error {response.status_code}: {response.text}"
            )

        return response.json()
