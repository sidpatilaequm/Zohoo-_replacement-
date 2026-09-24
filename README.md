# Aequm billing — React, Python, MySQL

Multi-tenant invoicing, purchasing and GST returns.

```
frontend/   React 18 + Vite + React Router   — the browser client
backend/    FastAPI + SQLAlchemy             — validation, tax and stock engines, auth
db/         MySQL 8                          — constraints, unique keys scoped per tenant
```

Invoicing, purchasing, GST returns, and for a trading business the full
order-to-stock cycle: sales order, delivery, goods issue, goods receipt,
discrepancy release, physical counting and a stock report.

## Trying it without installing anything

`invoicing-standalone.html` is a single self-contained file. Open it in a browser and
it runs with seeded data and no server, no database and no build step. It covers
the same ground as the stack — masters, invoicing, purchasing, inventory,
ordering, registers and the GST screens — and is the quickest way to see the
shape of the thing.

It holds everything in memory, so a refresh starts over. Use **Export backup** on
Templates and Import to keep a copy. It is a demonstration, not the product: the
stack below is what stores data properly.

Sign in as `alok@aequm.in` (any password — the demo does not check them, and says
so on screen).


## Version 4.1 changes

Three points raised against the tax invoice print-out, checked against the code
and covered by `tests/test_v41_print.py`.

**Item & Description.** The line prints the material description and the
invoice line's *Description 2* together, in that order, separated by a space
(`Microsoft office Basic plan Annual subscription ...`), with the material code
on the line beneath. A line saved without a Description 2 prints the master
description alone. This is decided at print time from what is on the invoice
line, so an invoice that shows only the master description was saved without a
Description 2 on that line. The CSV importers for customer invoices, estimates,
purchase orders and vendor invoices now carry an optional **Description 2**
column; files made from the v4 templates, which do not have it, still load.

**Payment Made and Balance Due.** Saving an invoice records no receipt. A new
tax invoice prints `Payment Made (-) 0.00` and `Balance Due` equal to the
total. The Payment Made figure is the sum of receipts recorded against that
invoice on the Receipts screen, and nothing else, so an invoice printing a
Payment Made equal to its total has a receipt on file for it. A test now pins
this down: nil before a receipt, reduced by exactly the receipt after.

**Place of supply.** This is unchanged, deliberately. Under GST the place of
supply is where the recipient is, not where the supplier is: Aequm in
Karnataka billing a customer in Delhi is an inter-state supply with place of
supply Delhi (07) and IGST charged, which is what the invoice in question
shows. Printing Karnataka against it would contradict the IGST on the same
document and misfile the invoice in GSTR-1. The New Invoice screen still lets
the place of supply be overridden for a specific document (a service actually
performed in Karnataka, say), and when it is set to Karnataka the tax switches
to CGST and SGST as it must.

## Version 4 changes

**The Reports link was broken, and this is why.** Two of the three endpoints the
Reports screen calls were guarded by the `gstr` permission instead of `reports`,
so any group holding Reports but not GST Returns — the seeded **Sales** group is
exactly that — saw the menu item, clicked it and got an error. `returns/periods`
had the same shape of problem, and now accepts any of `gstr`, `registers` or
`reports` through a new `need_any()` dependency: a period list is wanted by
three screens, and tying it to one meant a group that could open a screen could
not load it.

**Place of supply.** The field was editable, but selecting a GST registration
overwrote it, so an override was lost the moment anything else on the header was
touched. It now defaults from the billing address, shows plainly when it has been
set by hand, offers a one-click way back to the default, records `pos_manual` on
the invoice, and refuses a state code that does not exist.

**Several addresses per party.** A customer or vendor can hold any number of
addresses, each with its own state and its own GSTIN, because a party with
premises in two states holds a separate registration for each. The invoice picks
which to bill and which to deliver to, and the billing address chosen drives the
default place of supply. An address already used on a document cannot be deleted,
only deactivated, so old documents still print correctly.

**Several rates per HSN or SAC code.** A rate is not a property of the code — it
comes from the rate notification entry, and one code can sit against more than
one entry. Each code now holds a list of permitted rates with the condition that
earns each, and the invoice line says which applies.

**Choosing the rate does not choose the head.** Whether the tax lands as CGST and
SGST or as IGST still follows the place of supply and is not the user's to pick.
A test pins this: the same 5% rate produces CGST 25.00 intra-state and IGST 50.00
inter-state, with identical total tax.

**Payment terms and the due date.** The customer master carries a credit period
and the wording to print. The invoice due date is the invoice date plus that
period, filled in automatically and overridable by typing. The footer carries the
payment terms with the due date, **Remit To** with the organisation's own bank,
and **Customer Bank Account On File** from the customer master.

One thing worth flagging on that last point: the money normally travels the other
way, so the organisation's own bank is what lets a customer pay. Both are printed,
each labelled, rather than one silently replacing the other.


## Licence seats

A company set is licensed for **two users**, and the auditor occupies one of
them. That is the point of the limit: it caps who can sign in, not who can
change things.

A seat is a *role in a company set*, not a person. Someone holding a role in two
organisations occupies a seat in each, because they can sign in to each.

Every path that could create a seat checks first — adding a user, approving a
join request, or moving someone into the set — and refuses with the count rather
than allowing an unlicensed sign-in. Changing an existing user's group does not
take a new seat. `GET /api/licence` reports the position, and the Users screen
shows it.

## The auditor

A seeded **Auditor** group that can open every screen carrying a document and
change none of them.

**Read-only is enforced at the HTTP verb, not the screen.** A screen permission
grants the screen, not the verb, so without this a group given the Customers
screen in order to *read* customers could also *create* them — which is exactly
what happened the first time, and a test now pins it shut. A group flagged
view-only is refused anything that is not a GET, whatever screens it holds.

### Automatic reconciliation

`GET /api/audit/reconcile?period=YYYY-MM` runs two checks and says plainly
whether anything needs looking at.

**GST** compares three statements of the same month: the invoice register, what
GSTR-1 would carry, and what was actually filed in GSTR-3B. Proforma and
cancelled documents are excluded and counted, because neither carries a
liability. Where no GSTR-3B has been uploaded it says so, rather than quietly
comparing the books against nothing. Differences under a rupee are rounding.

**TDS** compares what was deducted against what the vendor master says should
have been deducted, and flags the cases that carry a legal consequence of their
own — a deduction with no PAN on file, a rate that does not match the section, a
deduction where the master carries no rate at all, or nothing deducted where it
does.

Both are reconciliations of the records held here. Neither is a filing and
neither touches the portal.

One thing worth knowing: GSTR-1 and GSTR-3B are monthly, so the GST half only
means anything against a period. The screen lands on the most recent one and
says so if you switch to all periods.


## Prices with GST in them, or without

A material carries a **price basis**: the price is either before GST or has GST
already in it. The invoice handles both, and an invoice can mix them.

Three ways to decide, in order of precedence:

1. the whole document — *Prices on this invoice are* set to all inclusive or all
   exclusive, which overrides everything on it
2. a single line, where the entry says so explicitly
3. otherwise the flag on the material

**The basis is frozen onto the invoice line.** Repricing a material later cannot
re-interpret an invoice already issued, and a test pins that shut.

### Why the tax is carved out by subtraction

On an inclusive line the customer pays exactly quantity times price, so the tax
is carved out of that figure rather than added to it:

    taxable = gross x 100 / (100 + rate)
    tax     = gross - taxable          <- subtraction, not a second percentage

Deriving both halves independently would leave them disagreeing by a paisa on odd
numbers, and the customer would be billed something other than the price they
were quoted. The intra-state split works the same way: CGST is derived, SGST is
whatever is left, so the two always add back to the carved amount.

Tested on 3 x 333.33, 7 x 99.99, 11 x 45.55 and 2 x 1234.56 — taxable plus tax
equals the gross to the paisa in every case.

**The head still follows the place of supply.** Choosing a pricing basis does not
choose between CGST/SGST and IGST, and neither does choosing a rate. An inclusive
line of 1,180 gives CGST 90 and SGST 90 intra-state, or IGST 180 inter-state, with
the same 1,000 taxable and the same 1,180 total.

**GSTR-1 reports the taxable value, not the gross**, whichever way the price was
quoted, because that is what the return asks for.

On the printed invoice an inclusive line shows the value *before* tax in the Rate
and Amount columns, so quantity times rate equals the amount on its own row.
Printing the quoted figure there would break the arithmetic of the row. The line
is marked and a note under the terms explains the carve-out.

## Running it

### Docker

```bash
docker compose up --build
```

MySQL initialises from `db/`, the API listens on 8000, the UI is served on
<http://localhost:8080>. Open it and choose **Create an account → Set up a new
organisation**; you become its administrator.

### Without Docker

```bash
# 1. database
mysql -u root -p < db/01_schema.sql
mysql -u root -p < db/02_seed.sql

# 2. API
cd backend
python3 -m pip install -r requirements.txt
export DATABASE_URL='mysql+pymysql://aequm:change-me@localhost:3306/aequm_billing?charset=utf8mb4'
export SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_hex(32))')"
uvicorn app.main:app --reload --port 8000

# 3. UI, in another terminal
cd frontend
npm install
npm run dev          # http://localhost:5173, proxies /api to :8000
```

API documentation is at <http://localhost:8000/docs>.

## Tests

```bash
cd backend && python3 -m pytest tests -q
```

80 tests against SQLite, so no database server is needed to run them. They cover
the tax engine directly and the API end to end, including the tenant isolation
guarantees below.

## Multi-tenancy

Every business table carries `tenant_id`, and every unique key is scoped to it —
two organisations can each have a customer `C001` and an invoice `INV/001`
without colliding.

**The tenant comes from the signed token, never from the request body.** A client
can ask for a different organisation by sending a different `X-Tenant-Id`, and the
API checks that the user actually holds a role there before doing anything. Four
tests cover this:

- two organisations may reuse the same codes
- one organisation's list endpoints never return another's rows
- passing another organisation's row id is rejected, not silently accepted
- a user sending a tenant id they lack gets 403

`Ctx.scope()` and `Ctx.get()` in `backend/app/deps.py` are the only ways the
routers reach data; both add the tenant filter, so a new endpoint inherits the
isolation rather than having to remember it.

## Access control

A group is a named set of menu permissions, held per organisation. A user gets one
group in each organisation they belong to, so the same person can be an
administrator in one and read-only in another.

**The API enforces it.** `Depends(need("vpay"))` on a route means the server
refuses the request with 403 when the group lacks that permission. Hiding the menu
in the sidebar is a convenience on top, not the control itself. An administrator
cannot edit their own group to remove the Users menu, and cannot remove their own
access to the organisation they are signed in to.

Sign-up has two paths: create a new organisation and become its administrator, or
ask to join an existing one. A join request lands as `PENDING` and cannot sign in
until an administrator there assigns a group.

Passwords are PBKDF2-HMAC-SHA256 with 240,000 iterations and a per-user salt.
Sessions are HMAC-signed bearer tokens with an expiry. Both are written out in
`backend/app/security.py` using only the standard library, so there is nothing
hidden to audit.

## Business type

Each organisation is either **trading** or **non-trading**, set under Company
Information.

**Non-trading** — IT products and services. The **Ordering** and **Inventory**
menus are hidden and the matching endpoints return 409, because there is no
physical stock to move. Everything else works unchanged, and materials still
carry a quantity so licences and service units can be counted.

**Trading** — buys and sells physical goods. Stock comes in through a purchase
order and goods receipt, and goes out through a sales order, delivery and goods
issue.

## PDF print-outs

Purchase orders, customer invoices (tax and proforma) and customer receipt vouchers
print as A4 PDFs from the **Purchase orders**, **Invoices** and **Receipts** screens —
**View** opens the PDF in a new tab, **PDF** downloads it. The figures come from the
same tax engine as the screen, so the print never disagrees with what was shown.

Every print has two layouts, chosen with the **Print layout** picker on the page:

| | Trading | Non-trading |
|---|---|---|
| Line columns | HSN · Qty · UoM | SAC · Units · Per |
| Header | Required-by date | Service start / period |
| Party blocks | Bill to **and** Deliver / Ship to | Bill to and Service details |
| Terms | goods, delivery, transport, returns | services, licences, SLA, TDS |

The default follows the organisation's company type (Company Information), and the
other layout is always available, so a services company can still print a goods
invoice for the odd hardware sale. The API is
`GET /api/print/{purchase-orders|invoices|receipts}/{id}.pdf?variant=TRADING|NONTRADING`
with `disposition=inline` to open in the browser; permissions are the same as for
viewing the document.

## Reading vendor invoices

On **Vendor invoices**, upload the supplier's invoice as a PDF or image and the form is
filled from it: invoice number and dates, the vendor (matched by GSTIN, then by name),
the purchase order (by number), and the line items (by material code, then by HSN
and description). Each match carries a confidence; anything uncertain is highlighted
and listed under *Check before recording*. Nothing is written until **Record** is pressed,
and a vendor invoice may now be recorded without a purchase order.

Reading happens in three layers, each optional:

1. **PDF text layer** — always available.
2. **OCR** for scanned PDFs and images — `tesseract-ocr` is installed in the API
   container; without it, image uploads are refused with a clear message.
3. **Model reading** — set `ANTHROPIC_API_KEY` (and optionally `EXTRACT_MODEL`) in
   `docker-compose.yml` or the environment and the text is also sent to Claude for a
   structured reading; its answer fills gaps and is preferred when its lines reconcile
   better with the printed total. The screen shows which layers are active.

`POST /api/vendor-invoices/extract` (multipart `file`) returns the proposal;
`GET /api/vendor-invoices/extract/capabilities` reports what the container can read.

## v2.3 — masters editing, Description 2, invoice layout, services companies

- **Edit customers, vendors and materials** — an *Edit* button on each list row loads the
  record into the form; *Update* saves it (`PUT /api/customers/{id}`, `/api/vendors/{id}`,
  `/api/materials/{id}`). Registrations and contact people are replaced as a set; invoices
  keep their own copy of the GSTIN, so editing a customer never changes a filed document.
- **Description 2** on every line of a customer invoice, purchase order and vendor invoice.
  It is stored on the document line only — the material master is untouched — and every
  print-out shows *Description + Description 2* (e.g. "Microsoft office basic plan migration").
  A vendor invoice copied from a PO inherits the PO's Description 2.
- **Invoice print-out** now follows the organisation's standard layout: masthead and GSTIN
  left, TAX INVOICE right; #, Invoice Date, Terms (Due on Receipt / Net N days), Due Date,
  Place of Supply; Bill To / Ship To with GSTIN; **Subject**; item grid with HSN/SAC, Qty,
  Rate, a tax column group (IGST, or CGST + SGST) and Amount; Sub Total, IGST18 (18%), Total,
  Payment Made (−), Balance Due; Total In Words; **Notes**; Terms & Conditions with the bank
  line; Authorized Signature.
- **Specific instructions** — a text box on the invoice form, saved with the invoice and
  printed as *Notes*. Subject is printed under the party blocks.
- **Company information → Bank details** are now three fields (Bank name, IFSC, Account
  number, validated) and print under Terms & Conditions as
  "Aequm India Private Limited, SBI Account No: 38600386525 IFSC Code: SBIN0040807".
- **Non-trading (services) company**: the material master has no stock quantity, batch or
  shelf-life fields; customer invoices and vendor invoices neither check nor move stock.
  A trading company keeps all of that. The switch is *Company type* on Company information.

Upgrading an existing database: run `db/04_descr2_bank_instructions.sql`.

## Cancelling an invoice

A tax invoice is cancelled from the **Invoice Register** (Cancel, with a reason). It is
not deleted — a GST document number must not be reused — but:

- it drops out of every GST register, GSTR-1 and GSTR-3B, which reverses the output
  tax it carried, and GSTR-1 table 13 (documents issued) counts it as cancelled;
- stock issued on it comes back;
- every receipt against it, including TDS the customer deducted, is reversed by a
  contra entry dated the day of cancellation that references the original receipt,
  so the settlement position and the TDS receivable return to nil. Reversal entries
  are shown in red on **Customer Payments** and cannot be printed as receipts.

The print-out of a cancelled invoice carries a CANCELLED watermark and the reason.
Proformas are not tax documents and are simply deleted. (`POST /api/invoices/{id}/cancel`.)

The register can also print any invoice **as a proforma** (or a proforma as a tax
invoice) with the *Print as* picker — `?as=PRO|TAX` on the print route.

## GST filing — A, B and A − B

Under **Reports → GST filing** (also on **GST Returns**):

- **A — GSTR-1 register.** Every tax invoice of the period by table (B2B, B2CL, B2CS)
  with totals. Downloads as **Portal JSON** — the GSTR-1 upload schema (`b2b`, `b2cl`,
  `b2cs`, `hsn`, `doc_issue`) accepted by the GST portal and the Returns Offline Tool —
  or as an **Offline tool Excel** workbook with one sheet per table, plus the section CSVs.
- **B — GSTR-3B as filed.** Upload the GSTR-3B JSON downloaded from the portal
  (`sup_details.osup_det` and `itc_elg` are read), a `field,value` CSV, or type the
  figures. Stored per period.
- **A − B.** Outward taxable, IGST, CGST, SGST and input credit head by head with the
  difference. Until a GSTR-3B is uploaded, B is the 3B computed from the books and the
  panel says so. (`GET /api/returns/reconciliation/ab?period=YYYY-MM`.)

Upgrading an existing database: run `db/03_cancel_and_gstr.sql` (docker applies it
automatically on a fresh volume).

## Stock

**The ledger is append-only and signed.** A receipt writes a positive row, a
goods issue a negative one, a count adjustment either. Stock on hand is always
the sum of the ledger, never a stored running total, so a movement cannot be
lost by an edit going wrong. The stock report shows in, out and a running
balance from the same rows.

**Consignment is not ours.** It sits on our premises but belongs to the vendor
until consumed, so it is reported separately and never raises the quantity the
material master says is sellable. Receiving 500 normal and 250 consignment
raises the material by 500, not 750.

**Batch and expiry.** A material can be flagged batch managed, in which case a
receipt requires a batch number. Where the material also carries a shelf life,
entering the manufacturing date fixes expiry at manufacturing date plus shelf
life; the server computes it rather than trusting what the client sends.

**Picking is earliest expiry first**, suggested by the API and overridable line
by line.

## Discrepancy and release

A goods receipt compares total delivered against the quantity ordered **per
order line**, not per receipt line — a delivery split across two batches is
still one line of the order. Where they differ, one discrepancy is raised and
**held**.

While a line is held the vendor can invoice **nothing** on it. Releasing makes
the **received** quantity invoiceable, not the ordered quantity. A later receipt
that makes the order good clears the discrepancy automatically.

There is no approval workflow: anyone with the `disc` permission can release.

## Attributes

Attributes are typed — dropdown, multiple choice, text, numeric or date — and
their **definitions are global on purpose**: a material master has the same
shape in every organisation, only the values differ. Values on a dropdown or
multiple-choice attribute are checked against the permitted list when a material
is saved.

## Party master detail

Customers and vendors both carry **PAN**, an **MSME registered** flag with its Udyam number,
**bank details** as three separate fields (bank name from the shared bank list, IFSC, account
number), and any number of **contact people** — first, middle and last name, designation from
the shared designation list, phone and email, with one marked primary.

PAN and IFSC are validated rather than merely stored: PAN must be five letters, four digits and
a letter; IFSC must be four letters, a zero and six alphanumerics. Setting the MSME flag without
a registration number is refused, as is an IFSC or account number with no bank chosen.

Designations and banks are **shared across organisations** and seeded on first sign-up.

## HSN and SAC master

Codes are held per organisation with their SGST, CGST, IGST and cess rates. **A material picks
its rates up from the code automatically**; sending different rates is ignored unless the
material sets `use_hsn_rates` to false. The split must reconcile — SGST plus CGST has to equal
IGST — and a code in use on a material cannot be deleted.

## Registers

**Invoice register** — every customer document with its GST split, PAN, MSME status and
settlement position. **GST register** — outward and inward side by side with net payable.
**TDS register** — deductions taken from vendor payments, with the implied rate worked back
from what was entered, and a warning listing any vendor with no PAN on file, since section 206AA
requires a higher rate there. Each downloads as CSV.

## GSTR-3B reconciliation

`POST /api/registers/gstr3b` records what was actually filed for a period, either as JSON or as a
two-column CSV through `/gstr3b/upload-csv`. It is then compared with the books head by head.
Differences within one rupee are treated as rounding; anything larger is flagged. This is what
makes a reconciliation possible — GSTR-1 alone only tells you what the books say, not what
was filed.

## Templates and import

Seven objects can be loaded from CSV: customers, vendors, materials, customer estimates,
customer invoices, vendor estimates and vendor invoices. Each template carries the exact
headings the importer expects plus one worked example row.

**An import is all or nothing.** If any row fails, nothing at all is written, so a part-loaded
file can never leave the books half-changed. `?dry_run=true` checks a file and reports what
would happen without writing. Missing columns are named rather than guessed at.

The importers call the same handlers the API uses, so a typed entry and an imported one go
through identical validation. Customer estimates are stored as proforma invoices and vendor
estimates as purchase orders, since that is what they are.

## Party master

A customer or vendor carries a **PAN**, an **MSME registration** flag with its Udyam
number, **bank details as three separate fields** (bank name from the bank master,
IFSC, account number), and any number of **contact people** — first, middle and
last name, a designation drawn from the designation master, phone and email, with
one marked primary.

A vendor additionally carries a **TDS section and rate**, which the TDS register
uses. A rate without a section is refused, because a deduction with no section
cannot be reported.

Designations and banks are shared across organisations. IFSC is checked for shape
(four letters, a zero, six more) and the MSME flag cannot be set without a number.

## HSN and SAC master

Each organisation maintains its own list of the codes it actually uses, with the
rates behind them. **A material with no rates entered takes them from this
master**; entering rates on the material overrides it. If neither is available the
save is refused with a message naming the missing code, rather than silently
writing a zero-rated material.

The split is checked here too: SGST plus CGST must equal IGST.

## Registers and GST reconciliation

Three registers, each filterable by period and downloadable as CSV:

- **Invoice register** — every document with customer, GSTIN, PAN and values
- **GST register** — outward and inward tax, split by head
- **TDS register** — deductions by vendor, with PAN, MSME status and the rate
  worked back from what was actually paid

GSTR-1 downloads in the offline-tool column layout. **GSTR-3B goes the other
way**: upload what you filed, as CSV or by typing the figures, and the system
compares it head by head against the books. Differences under a rupee are treated
as rounding; anything larger is flagged with the usual causes named.

The comparison is tested both ways — a return that agrees passes clean, and a
CGST figure understated by ₹1,000 is caught and attributed to the right head.

## Master data templates

Seven CSV templates download with the correct headers and import back:
customers, vendors, materials, customer estimates, customer invoices, vendor
estimates and vendor invoices.

## Where the rules live

| Rule | Database | API | Client |
|---|---|---|---|
| SGST + CGST must equal IGST | CHECK | Pydantic | live warning |
| GSTIN is 15 chars, state code matches | CHECK | Pydantic | form check |
| B2B needs a GSTIN, B2C must not have one | — | Pydantic | form switches |
| Invoice number unique per tenant | UNIQUE | 409 | — |
| Vendor invoice number unique per vendor, not globally | UNIQUE | 409 | — |
| Quantity and price above zero | CHECK | Pydantic | disabled button |
| PO date not after invoice date | CHECK | Pydantic | disabled button |
| Payment cannot exceed the outstanding | — | service | pre-filled with the balance |
| Receipt settles a customer invoice, payment a vendor invoice | CHECK | Pydantic | separate screens |
| Stock cannot go negative | — | service | line warning |
| IFSC is four letters, a zero, six more | CHECK | Pydantic | field turns red |
| MSME flag requires a registration number | CHECK | Pydantic | field enables |
| TDS rate requires a section | — | Pydantic | refused on save |
| SGST + CGST must equal IGST on an HSN code | CHECK | Pydantic | live warning |
| A material with no rates falls back to the HSN master | — | router | hint names the source |
| Only owned stock types raise the sellable figure | — | inventory | shown per type |
| A batch-managed material needs a batch number | — | inventory | field turns red |
| Expiry is manufacturing date plus shelf life | CHECK on ordering | inventory | field auto-fills |
| Cannot receive more than the order leaves open | — | inventory | disabled button |
| Cannot pick more than a batch holds | — | ordering | max on the input |
| A held discrepancy blocks vendor invoicing | — | inventory | shown on the screen |
| PAN is five letters, four digits, a letter | — | Pydantic | field turns red |
| IFSC is four letters, a zero, six alphanumerics | CHECK on length | Pydantic | field turns red |
| MSME flag needs a registration number | — | Pydantic | field enables |
| SGST + CGST must equal IGST on an HSN code | CHECK | Pydantic | live warning |
| An HSN code in use cannot be deleted | — | masters | button hidden |
| A part-failed import writes nothing | transaction | importer | errors listed |

The database constraints matter most. An API can be bypassed by a script and a
browser by anyone with the console open; a CHECK constraint holds regardless of
how the row arrives.

## The tax engine

`backend/app/tax.py` is the single source of truth, used by invoices, purchase
orders, vendor invoices and both returns.

**Place of supply against the supplier's own state decides the split.** Same state
gives CGST and SGST with IGST nil; a different state gives IGST with CGST and SGST
nil. Never all three.

**Tax is computed and rounded per line, then summed.** Rounding the total instead
produces a figure that disagrees with the line detail printed on the invoice.
There is a test pinning this: three lines of ₹33.33 give CGST of exactly ₹9.00.

An unregistered vendor's supply carries no tax and no input credit, handled by a
single `taxable_supply` flag rather than special cases scattered through callers.

## What this does not do

**It does not move money.** The payment screens record settlement and produce a
bank upload file. Initiating a transfer needs bank credentials and an approval
trail that belong in your banking system, not here.

**It does not send mail yet.** SMTP settings are stored per organisation and the
password is never returned to the browser — `GET /api/org` reports only
`password_set`. The endpoint that actually sends is not written; `POST
/api/org/smtp/check` validates the settings and says so plainly. The Email button
on the invoice register composes a `mailto:` for your own mail client meanwhile.

**Input tax credit comes from vendor invoices recorded here, not from GSTR-2B.**
Blocked credits under section 17(5), reverse charge and reversals are not handled.

**Credit and debit notes, exports, SEZ supplies, advances and amendments** are not
modelled, so the GST returns are a preparation aid rather than a filed return.

**There is no printed-document renderer in the React build.** The API returns
everything a tax invoice needs from `GET /api/invoices/{id}` — both addresses, the
HSN summary, amount in words — but the print layout has not been rebuilt yet.

## Before using it for real

Change `SECRET_KEY` to a long random value. Tokens are signed with it; the value
in `.env.example` is marked as a development default for a reason.

Change the MySQL passwords in `docker-compose.yml`.

Serve it over HTTPS. Tokens are bearer tokens in a header — over plain HTTP anyone
on the path can take one.
