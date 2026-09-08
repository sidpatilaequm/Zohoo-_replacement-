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
