"""Load a client's master data from CSV exports (catalog, customers, aliases, order history)."""

import csv
from datetime import date
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from .matching import normalize
from .models import Customer, CustomerAlias, PastOrderLine, Product


def _rows(path: Path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def load_master_data(session: Session, folder: Path, replace: bool = True) -> dict[str, int]:
    folder = Path(folder)
    if replace:
        for model in (PastOrderLine, CustomerAlias, Customer, Product):
            session.execute(delete(model))
    counts = {"products": 0, "customers": 0, "aliases": 0, "past_order_lines": 0}
    for r in _rows(folder / "products.csv"):
        session.add(Product(code=r["code"], name=r["name"], pot=r.get("pot") or None, price=float(r.get("price") or 0),
                            stock=int(r.get("stock") or 0), erp_id=r.get("erp_id") or None))
        counts["products"] += 1
    for r in _rows(folder / "customers.csv"):
        session.add(Customer(id=r["id"], name=r["name"], email_domain=(r.get("email_domain") or "").lower() or None,
                             language=r.get("language") or None, notes=r.get("notes") or None, erp_id=r.get("erp_id") or None))
        counts["customers"] += 1
    session.flush()
    for r in _rows(folder / "aliases.csv"):
        session.add(CustomerAlias(customer_id=r["customer_id"], alias=normalize(r["alias"]), product_code=r["product_code"]))
        counts["aliases"] += 1
    for r in _rows(folder / "past_orders.csv"):
        session.add(PastOrderLine(customer_id=r["customer_id"], order_date=date.fromisoformat(r["order_date"]),
                                  product_code=r["product_code"], quantity=int(r["quantity"])))
        counts["past_order_lines"] += 1
    session.flush()
    return counts
