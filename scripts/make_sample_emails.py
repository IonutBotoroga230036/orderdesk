"""Generate the sample .eml files in data/sample/emails (including a PDF order attachment).

Run once: python scripts/make_sample_emails.py   (needs the dev extra: reportlab)
"""

import io
import json
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "sample"
TZ = timezone(timedelta(hours=2))  # Dutch summer time

EMAILS = [
    dict(file="01-de-linde.eml", sender="Marieke van der Linde <inkoop@delinde.nl>", subject="Bestelling donderdag",
         time=(9, 26), body="Goedemorgen,\n\nGraag voor donderdag het volgende leveren:\n\n240 lavendel blauw 19\n60 Annabelle 5 liter\n500 buxus 15\n120 Rozanne\n\nAlvast bedankt!\nGroet,\nMarieke van der Linde\nTuincentrum De Linde\nTel. 013 555 0192",
         expected=[("LAV-HID-P19", 240), ("HYD-ANN-C5", 60), ("BUX-SEM-P15", 500), ("GER-ROZ-P13", 120)]),
    dict(file="02-brightwell.eml", sender="Gareth Hollis <orders@brightwellgc.co.uk>", subject="Repeat order + olives",
         time=(9, 10), body="Hi team,\n\nCould we repeat last week's order, but double the Salvias and drop the roses this time? Also add 10 olive trees, the big ones if you have them.\n\nDelivery Tuesday the 20th if possible.\n\nCheers,\nGareth Hollis\nBrightwell Garden Centre",
         expected=[("SAL-CAR-P13", 300), ("NEP-WAL-P13", 100), ("PEN-HAM-P17", 80), ("OLE-EUR-C10", 10)]),
    dict(file="03-hoffmann.eml", sender="Julia Weber <einkauf@gc-hoffmann.de>", subject="Bestellung Nr. 4471",
         time=(8, 31), body="Sehr geehrte Damen und Herren,\n\nanbei unsere Bestellung Nr. 4471. Liefertermin bitte KW 43.\n\nMit freundlichen Grüßen\nJulia Weber\nEinkauf, Gartencenter Hoffmann",
         pdf=[("Art.-Nr.", "Bezeichnung", "Menge"), ("H-20931", "Hortensie Annabelle 5L", "80"),
              ("H-20977", "Kirschlorbeer Novita 5L", "150"), ("H-21004", "Rose Bonica 3L", "60"),
              ("H-21015", "Fächerahorn rot 7L", "12")],
         expected=[("HYD-ANN-C5", 80), ("PRU-LAU-C5", 150), ("ROS-BON-C3", 60), ("ACE-PAL-C7", 12)]),
    dict(file="04-groen-in-de-stad.eml", sender="Sven Bakker <sven@groenindestad.nl>", subject="grassen",
         time=(8, 5), body="hoi!\n\nkunnen jullie morgen nog 3 karren grassen sturen? zelfde mix als vorige keer.\nen 25 olijfjes als die er zijn :)\n\ngr Sven",
         expected=[("PEN-HAM-P17", 180), ("CAL-KAR-P17", 180), ("OLE-EUR-C10", 25)]),
    dict(file="05-les-saules.eml", sender="Claire Dubois <achats@lessaules.be>", subject="Commande pour vendredi",
         time=(7, 42), body="Bonjour,\n\nPour une livraison vendredi, merci de nous préparer :\n200 Photinia Red Robin 3L\n100 Heuchera Palace Purple\n50 laurier\n\nCordialement,\nClaire Dubois\nJardinerie Les Saules",
         expected=[("PHO-RED-C3", 200), ("HEU-PAL-P13", 100), ("PRU-LAU-C5", 50)]),
]


def make_pdf(rows) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    table = Table(rows, colWidths=[90, 260, 60])
    table.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                               ("LINEBELOW", (0, 0), (-1, 0), 1, colors.black),
                               ("ALIGN", (2, 0), (2, -1), "RIGHT")]))
    doc.build([Paragraph("Gartencenter Hoffmann, Bestellung Nr. 4471", styles["Heading2"]),
               Paragraph("Liefertermin: KW 43", styles["Normal"]), Spacer(1, 12), table])
    return buf.getvalue()


def main():
    (OUT / "emails").mkdir(parents=True, exist_ok=True)
    truth = {"description": "Correct orders for the sample emails, as a person would enter them.", "emails": []}
    for e in EMAILS:
        msg = EmailMessage()
        msg["From"] = e["sender"]
        msg["To"] = "GreenLine Orders <orders@greenlineplants.nl>"
        msg["Subject"] = e["subject"]
        msg["Date"] = format_datetime(datetime(2026, 10, 12, *e["time"], tzinfo=TZ))
        msg["Message-ID"] = f"<{e['file'][:-4]}@sample.tickwell>"
        msg.set_content(e["body"])
        if "pdf" in e:
            msg.add_attachment(make_pdf(e["pdf"]), maintype="application", subtype="pdf", filename="Bestellung_4471.pdf")
        (OUT / "emails" / e["file"]).write_bytes(bytes(msg))
        truth["emails"].append({"message_id": msg["Message-ID"],
                                "expected": [{"product_code": c, "quantity": q} for c, q in e["expected"]]})
    (OUT / "ground_truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    print(f"Wrote {len(EMAILS)} emails and ground_truth.json to {OUT}")


if __name__ == "__main__":
    main()
