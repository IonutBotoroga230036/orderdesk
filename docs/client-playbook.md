# Client playbook

How to take a wholesaler from first call to go-live in about four weeks.

## Week 0: qualify

Ask: "How do orders reach you, and who types them into your system? How many a day?"
Good fit: 30+ email orders a day, one or more people retyping them, an ERP that can import CSV
or has an API. Then show the demo, ideally with an order they type themselves.

## Week 1: data

Request, as CSV exports (formats in `data/templates/`):

- Product list: code, name, pot or unit size, price, stock.
- Customer list: id, name, email domain, language, ERP id.
- Six months of order history: customer, date, product, quantity.
- Any known customer article numbers or nicknames (aliases).
- **200 to 300 past order emails** (exported as .eml) **with the orders that were entered
  for them.** This is the ground truth for the shadow test.

Sign a data processing agreement with the client before receiving any of this. Check the
current data handling terms of the model provider you use and tell the client where data goes.

## Week 2: build and measure

1. `orderdesk init --data client_data`
2. Ingest the historical emails from a folder.
3. Write their ground truth file (same shape as `data/sample/ground_truth.json`).
4. `orderdesk evaluate --truth client_data/ground_truth.json`
5. Fix what fails: add aliases, customer notes (trolley sizes, standing agreements), prompt
   rules for their quirks. Re-run until the numbers hold.

Go-live criteria to agree with the client:

- Lines marked `ok` that are wrong: below 1%. This is the trust number.
- Line recall: above 90%.
- Average review time well under the current manual time per order.

## Week 3: shadow mode

Connect the real mailbox (`ORDERDESK_MAIL_SOURCE=graph`) and run the worker. The order desk
keeps working as before and checks drafts alongside. Track review time and corrections.

## Week 4: go live

Switch approvals on with CSV export into their ERP. Move to the API connector once it is
tested in their sandbox. Monthly fee starts here; it covers hosting, monitoring, model costs
and alias and rule upkeep.

## Monthly check-in (keeps the retainer)

Send a one-page report: orders processed, average review time, hours saved, corrections,
new aliases learned. Pull it from `drafts` and `audit_events`.
