"""Exact Online sales order connector.

SKELETON: written against Exact Online's REST API (salesorder/SalesOrders), but not yet
tested against a live division. Before a client go-live:
  1. Register an app in the Exact App Center and implement the OAuth2 flow + token refresh
     (access tokens are short-lived; store the refresh token securely).
  2. Fill Product.erp_id (Item GUID) and Customer.erp_id (Account GUID) during the data import.
  3. Test in a sandbox division and check rate limits for the client's plan.
"""

import httpx

from .base import ERPError, OrderPayload


class ExactOnlineConnector:
    def __init__(self, base_url: str, division: int, access_token: str, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.division = division
        self.client = client or httpx.Client(timeout=30)
        self.headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json",
                        "Content-Type": "application/json"}

    def create_order(self, order: OrderPayload) -> str:
        if not order.customer_erp_id:
            raise ERPError(f"Customer {order.customer_id} has no Exact Account ID (erp_id).")
        missing = [line.code for line in order.lines if not line.erp_id]
        if missing:
            raise ERPError(f"Products without an Exact Item ID: {', '.join(missing)}")
        body = {
            "OrderedBy": order.customer_erp_id,
            "YourRef": order.reference,
            "Description": f"OrderDesk draft {order.draft_id}",
            "SalesOrderLines": [{"Item": line.erp_id, "Quantity": line.quantity} for line in order.lines],
        }
        if order.delivery_date:
            body["DeliveryDate"] = order.delivery_date.isoformat()
        url = f"{self.base_url}/api/v1/{self.division}/salesorder/SalesOrders"
        resp = self.client.post(url, json=body, headers=self.headers)
        if resp.status_code >= 400:
            raise ERPError(f"Exact Online returned {resp.status_code}: {resp.text[:300]}")
        data = resp.json().get("d", {})
        return str(data.get("OrderNumber") or data.get("OrderID") or "created")
