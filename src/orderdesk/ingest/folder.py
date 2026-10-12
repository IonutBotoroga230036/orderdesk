from collections.abc import Iterator
from pathlib import Path


class FolderSource:
    """Reads .eml files from a folder. Duplicates are skipped later by Message-ID."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)

    def fetch(self) -> Iterator[bytes]:
        if not self.folder.exists():
            raise FileNotFoundError(f"Inbox folder not found: {self.folder}")
        for path in sorted(self.folder.glob("*.eml")):
            yield path.read_bytes()
