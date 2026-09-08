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
