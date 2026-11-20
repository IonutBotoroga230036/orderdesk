import csv

from fastapi.testclient import TestClient


def client():
    from tickwell.api.app import create_app

    return TestClient(create_app())


def find(emails, subject):
    return next(e for e in emails if e["subject"] == subject)


def test_review_and_approve_flow(env):
    with client() as c:
        emails = c.get("/api/emails").json()
        assert len(emails) == 5
        e = find(emails, "Bestelling donderdag")

        draft = c.post(f"/api/emails/{e['id']}/draft").json()
        assert draft["customer_id"] == "C1023" and not draft["blocking_issues"]

        c.get(f"/api/emails/{e['id']}")  # opening the email starts the review timer
        approved = c.post(f"/api/drafts/{draft['id']}/approve").json()
        assert approved["erp_reference"].startswith("SO-")

        rows = list(csv.DictReader((env / "exports" / f"{approved['erp_reference']}.csv").open(), delimiter=";"))
        assert {r["product_code"] for r in rows} == {"LAV-HID-P19", "HYD-ANN-C5", "BUX-SEM-P15", "GER-ROZ-P13"}

        stock = {p["code"]: p["stock"] for p in c.get("/api/products").json()}
        assert stock["LAV-HID-P19"] == 1200 - 240
        assert c.get("/api/stats").json()["approved"] == 1
        assert c.post(f"/api/drafts/{draft['id']}/approve").status_code == 409


def test_cannot_approve_until_lines_checked_and_learns_aliases(env):
    with client() as c:
        e = find(c.get("/api/emails").json(), "Bestellung Nr. 4471")
        d = c.post(f"/api/emails/{e['id']}/draft").json()
        assert c.post(f"/api/drafts/{d['id']}/approve").status_code == 400

        for line in d["lines"]:
            if line["needs_review"] and line["product_code"]:
                d = c.patch(f"/api/drafts/{d['id']}/lines/{line['id']}", json={"resolved": True}).json()
        maple = next(line for line in d["lines"] if "Fächerahorn" in line["source_text"])
        d = c.patch(f"/api/drafts/{d['id']}/lines/{maple['id']}", json={"product_code": "ACE-PAL-C7"}).json()
        assert not d["blocking_issues"]
        assert c.post(f"/api/drafts/{d['id']}/approve").status_code == 200

    from sqlalchemy import select

    from tickwell.db import new_session
    from tickwell.models import CustomerAlias

    s = new_session()
    learned = s.scalars(select(CustomerAlias).where(CustomerAlias.source == "learned")).all()
    assert any(a.product_code == "ACE-PAL-C7" and a.customer_id == "C1102" for a in learned)
    s.close()


def test_basic_auth(env, monkeypatch):
    monkeypatch.setenv("TICKWELL_UI_USER", "desk")
    monkeypatch.setenv("TICKWELL_UI_PASSWORD", "secret")
    from tickwell.config import get_settings

    get_settings.cache_clear()
    with client() as c:
        assert c.get("/api/emails").status_code == 401
        assert c.get("/api/emails", auth=("desk", "secret")).status_code == 200
        assert c.get("/api/health").status_code == 200
