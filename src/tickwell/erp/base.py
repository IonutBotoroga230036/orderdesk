from dataclasses import dataclass, field
from datetime import date
from typing import Protocol


class ERPError(RuntimeError):
    pass


@dataclass
class OrderLinePayload:
    code: str
    erp_id: str | None
    description: str
    quantity: int
    unit_price: float


@dataclass
class OrderPayload:
    draft_id: int
    customer_id: str
    customer_name: str
    customer_erp_id: str | None
    delivery_date: date | None
    reference: str
    lines: list[OrderLinePayload] = field(default_factory=list)


class ERPConnector(Protocol):
    def create_order(self, order: OrderPayload) -> str:
        """Create the sales order and return the ERP's order reference."""
        ...


def get_erp(name: str | None = None) -> ERPConnector:
    from ..config import get_settings

    s = get_settings()
    name = name or s.erp
    if name == "csv":
        from .csv_export import CSVExporter

        return CSVExporter(s.export_dir)
    if name == "exact":
        from .exact_online import ExactOnlineConnector

        if not (s.exact_division and s.exact_access_token):
            raise ERPError("Exact Online needs TICKWELL_EXACT_DIVISION and TICKWELL_EXACT_ACCESS_TOKEN.")
        return ExactOnlineConnector(s.exact_base_url, s.exact_division, s.exact_access_token)
    raise ERPError(f"Unknown ERP connector: {name}")
