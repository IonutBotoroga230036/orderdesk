"""Microsoft 365 mailbox via Microsoft Graph (app-only auth).

Setup in the client's Azure portal: register an app, add the application permission
Mail.ReadWrite, grant admin consent, and restrict it to the orders mailbox with an
application access policy. Most Dutch SMEs run Microsoft 365, so this is the main path.
"""

from collections.abc import Iterator

import httpx

GRAPH = "https://graph.microsoft.com/v1.0"


class GraphSource:
    def __init__(self, tenant_id: str | None, client_id: str | None, client_secret: str | None, mailbox: str | None,
                 client: httpx.Client | None = None):
        if not (tenant_id and client_id and client_secret and mailbox):
            raise ValueError("Graph needs tenant id, client id, client secret and mailbox settings.")
        self.tenant_id, self.client_id, self.client_secret, self.mailbox = tenant_id, client_id, client_secret, mailbox
        self.client = client or httpx.Client(timeout=30)

    def _token(self) -> str:
        import msal

        app = msal.ConfidentialClientApplication(
            self.client_id, authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            client_credential=self.client_secret,
        )
        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        if "access_token" not in result:
            raise RuntimeError(f"Graph auth failed: {result.get('error_description', result)}")
        return result["access_token"]

    def fetch(self) -> Iterator[bytes]:
        headers = {"Authorization": f"Bearer {self._token()}"}
        url = f"{GRAPH}/users/{self.mailbox}/mailFolders/inbox/messages"
        params = {"$filter": "isRead eq false", "$top": "25", "$select": "id"}
        resp = self.client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        for item in resp.json().get("value", []):
            mid = item["id"]
            raw = self.client.get(f"{GRAPH}/users/{self.mailbox}/messages/{mid}/$value", headers=headers)
            raw.raise_for_status()
            yield raw.content
            self.client.patch(f"{GRAPH}/users/{self.mailbox}/messages/{mid}", headers=headers, json={"isRead": True})
