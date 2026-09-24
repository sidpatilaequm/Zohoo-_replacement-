# Two ways to try this

## `invoicing-standalone.html` — open it in a browser

One file, no install, nothing to run. Double-click it. Everything is held in memory
for the session; use **Export backup** under Templates and Import to keep anything.

Sign in as any seeded user, for example `alok@aequm.in` — passwords are not checked
in this build, and it says so on the sign-in screen.

Use it to see the screens and try the flows. It is not a place to keep real data.

**What the single file cannot do**, and why:

- **Import a filled-in template.** A browser page has nowhere to put the rows and no
  transaction to roll back if one of them fails, so importing here would risk leaving
  the data half-loaded. The templates download and are identical to the stack's, so a
  file prepared here loads into the stack unchanged.
- **Keep data between sessions**, send mail, or enforce access. Those need a server.

## The stack — React, FastAPI, MySQL

```bash
docker compose up --build     #  http://localhost:8080
```

Then **Create an account → Set up a new organisation**. You become its administrator,
and the shared designation and bank lists are seeded on first sign-up.

Suggested order for a first run:

1. **Company Information** — set the business type. Trading reveals Ordering and Inventory.
2. **Masters → HSN and SAC** — add the codes you use with their rates.
3. **Masters → Materials** — the rates fill in from the code you pick.
4. **Masters → Customers and Vendors** — PAN, MSME, bank and contact people.
5. **Setup → Templates and Import** — download a template, fill it, use **Check only** first.
6. Raise a purchase order, receive it short, and watch the discrepancy hold the vendor invoice.
7. **Insight → Registers** and **GST Returns** — enter what you filed in 3B and compare.

Run the tests with `cd backend && python3 -m pytest tests -q`.

## Print-outs and extraction

`tests/test_print_extract.py` renders every document in both layouts and checks the
bytes are a PDF, reads the invoice PDF back with pdfplumber to confirm the document
number and the layout-specific labels (HSN/Ship to vs SAC/Service details), and checks
tenant isolation on the print routes. For extraction it builds a supplier invoice PDF
with reportlab, uploads it, and asserts the vendor (by GSTIN), purchase order, dates,
line and total are read and matched — then records the proposal to prove it round-trips.
Unknown vendors and POs must produce warnings, wrong file types 422, and a user without
the `vinv` permission 403. OCR and the model are not exercised in tests.

## Cancellation and GST filing

`tests/test_cancel_gstr.py` cancels an invoice that has a part receipt with TDS and
checks the GST totals fall by exactly the invoice's tax, the invoice disappears from
GSTR-3B, the GST register and receivables, a contra receipt of −amount/−TDS appears,
stock is restored, table 13 counts one cancelled document, and a second cancel or a
proforma cancel is refused. The cancelled print carries the reason; `as=PRO` prints a
tax invoice in the proforma layout. The GSTR-1 portal JSON is checked field by field
(ctin, inum, idt, val, itm_det, hsn, doc_issue) and the workbook sheet by sheet. A
portal-style GSTR-3B JSON is uploaded and A − B must show the deliberate ₹500 gap.

## v2.3

`tests/test_edit_descr2.py` edits a customer (name, address, contacts), a vendor and a
material through PUT and checks code clashes are refused; records an invoice with Subject,
instructions and Description 2 on two lines, checks the master is untouched, the line
descriptions are "material + Description 2" in the API and in the PDF, and the totals block
reads Sub Total 20,000.00 / IGST18 (18%) 3,600.00 / 23,600.00; checks Description 2 on a PO
prints and copies to the vendor invoice; checks the organisation's bank line prints under
Terms & Conditions; and checks a services company can invoice with zero stock and that
neither an invoice nor a vendor invoice changes stock. The three original stock tests now
run against a trading company.
