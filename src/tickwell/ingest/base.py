from collections.abc import Iterable
from typing import Protocol


class MailSource(Protocol):
    def fetch(self) -> Iterable[bytes]:
        """Yield raw RFC 822 messages that have not been fetched before."""
        ...


def get_mail_source(name: str | None = None) -> MailSource:
    from ..config import get_settings

    s = get_settings()
    name = name or s.mail_source
    if name == "folder":
        from .folder import FolderSource

        return FolderSource(s.inbox_dir)
    if name == "imap":
        from .imap import IMAPSource

        return IMAPSource(s.imap_host, s.imap_user, s.imap_password, s.imap_folder)
    if name == "graph":
        from .graph import GraphSource

        return GraphSource(s.graph_tenant_id, s.graph_client_id, s.graph_client_secret, s.graph_mailbox)
    raise ValueError(f"Unknown mail source: {name}")
