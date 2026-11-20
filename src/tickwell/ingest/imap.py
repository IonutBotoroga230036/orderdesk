import imaplib
from collections.abc import Iterator


class IMAPSource:
    """Fetches unread messages over IMAP (SSL) and marks them as read."""

    def __init__(self, host: str | None, user: str | None, password: str | None, folder: str = "INBOX"):
        if not (host and user and password):
            raise ValueError("IMAP needs TICKWELL_IMAP_HOST, TICKWELL_IMAP_USER and TICKWELL_IMAP_PASSWORD.")
        self.host, self.user, self.password, self.folder = host, user, password, folder

    def fetch(self) -> Iterator[bytes]:
        with imaplib.IMAP4_SSL(self.host) as conn:
            conn.login(self.user, self.password)
            conn.select(self.folder)
            _, data = conn.search(None, "UNSEEN")
            for num in data[0].split():
                _, msg = conn.fetch(num, "(RFC822)")
                if msg and isinstance(msg[0], tuple):
                    yield msg[0][1]
                    conn.store(num, "+FLAGS", "\\Seen")
