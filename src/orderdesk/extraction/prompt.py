from .base import ExtractionContext

SYSTEM = (
    "You are the order-entry engine for a plant wholesaler. You read customer emails and draft "
    "sales orders that a person reviews before anything reaches the ERP. Precision matters more "
    "than coverage: when unsure, say so through the status field instead of guessing silently."
)

RULES = """Rules:
1. One line per catalog product. Match by name, cultivar, pot size (P13, P15, P17, P19 are pot
   diameters in cm; C3, C5, C7, C10 are container litres, so "3L" or "3 liter" means C3), the
   customer's own product names (aliases) and their order history. Customers misspell names and
   write in Dutch, German, French or English.
2. If the email refers to a previous order ("same as last week", "zelfde als vorige keer",
   "wie letztes Mal"), expand it from the customer's most recent order and apply the changes
   they ask for. Products they ask to drop go in "removed", not in "lines".
3. Read the customer notes: they hold standing agreements such as trolley mixes.
4. status "ok" = you are confident. "check" = you made an interpretation a person should confirm
   (vague quantity, assumed size, quantity derived from history, substitution question).
   "unknown" = several products fit or none does: set product_code to null and put candidate
   codes in alternatives.
5. source_text must be copied character for character from the email: the shortest span that
   shows what the customer asked for. Several lines may share one source_text.
6. reason: one plain English sentence of at most 20 words, explaining the match or what to check.
7. Resolve relative dates ("donderdag", "next Tuesday", "KW 43") against the date the email was
   received. Put the original words in delivery_text.
8. Ignore signatures, disclaimers and quoted older emails.
Call the record_order tool exactly once."""


def build_prompt(text: str, ctx: ExtractionContext) -> str:
    catalog = "\n".join(f"{p.code} | {p.name} | {p.pot or '-'} | {p.price:.2f}" for p in ctx.catalog)
    customers = []
    for c in ctx.customers:
        aliases = "; ".join(f'"{a}" = {code}' for a, code in c.aliases.items()) or "none"
        orders = " / ".join(
            f"{d.isoformat()}: " + ", ".join(f"{code} x{q}" for code, q in lines) for d, lines in c.recent_orders
        ) or "none"
        customers.append(f"{c.id} | {c.name} | notes: {c.notes or 'none'} | aliases: {aliases} | recent orders: {orders}")
    sender_line = (
        f"Sender is known customer {ctx.known_customer_id}."
        if ctx.known_customer_id
        else "Sender is not a known address. Identify the customer from the text if possible, else null."
    )
    return f"""Email received on {ctx.today.strftime('%A %d %B %Y')} from {ctx.sender}.
{sender_line}

CATALOG (code | name | pot size | price):
{catalog}

CUSTOMERS (id | name | notes | aliases | recent orders):
{chr(10).join(customers)}

EMAIL TEXT:
\"\"\"
{text}
\"\"\"

{RULES}"""
