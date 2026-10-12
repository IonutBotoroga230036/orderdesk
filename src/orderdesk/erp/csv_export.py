"""Writes one CSV per order. Almost every ERP can import CSV, so this is the safe first go-live."""

import csv
from datetime import UTC, datetime
from pathlib import Path

from .base import OrderPayload


class CSVExporter:
    def __init__(self, export_dir: Path):
        self.export_dir = Path(export_dir)

    def create_order(self, order: OrderPayload) -> str:
        self.export_dir.mkdir(parents=True, exist_ok=True)
        reference = f"SO-{datetime.now(UTC):%Y%m%d}-{order.draft_id:05d}"
        path = self.export_dir / f"{reference}.csv"
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(["order_ref", "customer_id", "customer_name", "delivery_date", "your_ref",
                        "line", "product_code", "description", "quantity", "unit_price"])
            for i, line in enumerate(order.lines, 1):
                w.writerow([reference, order.customer_id, order.customer_name,
                            order.delivery_date.isoformat() if order.delivery_date else "", order.reference,
                            i, line.code, line.description, line.quantity, f"{line.unit_price:.2f}"])
        return reference
