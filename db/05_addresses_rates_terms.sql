-- =====================================================================
--  Version 4 additions
--    party_addresses  one party, many addresses, chosen per document
--    hsn_rates        one HSN or SAC code, several permitted rates
--    payment terms    on the customer, driving the invoice due date
--    invoice          remembers the address and rate actually chosen
-- =====================================================================
USE aequm_billing;

-- ---------------------------------------------------------- addresses
CREATE TABLE IF NOT EXISTS party_addresses (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id  INT NOT NULL,
  party_kind ENUM('CUSTOMER','VENDOR') NOT NULL,
  party_id   INT NOT NULL,
  label      VARCHAR(80)  NOT NULL,
  addr_type  ENUM('BILLING','SHIPPING','BOTH') NOT NULL DEFAULT 'BOTH',
  gstin      CHAR(15)     NULL,
  addr       VARCHAR(255) NOT NULL,
  city       VARCHAR(80)  NOT NULL,
  state_code CHAR(2)      NOT NULL,
  pin        CHAR(6)      NULL,
  contact    VARCHAR(120) NULL,
  phone      VARCHAR(20)  NULL,
  is_default BOOLEAN      NOT NULL DEFAULT FALSE,
  active     BOOLEAN      NOT NULL DEFAULT TRUE,
  CONSTRAINT fk_pa_t FOREIGN KEY (tenant_id)  REFERENCES tenants(id) ON DELETE CASCADE,
  CONSTRAINT fk_pa_s FOREIGN KEY (state_code) REFERENCES states(code),
  CONSTRAINT pa_gstin CHECK (gstin IS NULL OR
    (CHAR_LENGTH(gstin) = 15 AND LEFT(gstin,2) = state_code)),
  UNIQUE KEY uq_pa (tenant_id, party_kind, party_id, label)
) ENGINE=InnoDB;
CREATE INDEX ix_pa_party ON party_addresses(tenant_id, party_kind, party_id);

-- ------------------------------------------------------------- rates
-- One code can carry several permitted rates. The rate is not a property
-- of the code; it comes from the rate notification entry, and one code can
-- sit against more than one entry.
CREATE TABLE IF NOT EXISTS hsn_rates (
  id INT AUTO_INCREMENT PRIMARY KEY,
  hsn_id     INT NOT NULL,
  label      VARCHAR(120) NOT NULL,
  sgst_pct   DECIMAL(5,2) NOT NULL,
  cgst_pct   DECIMAL(5,2) NOT NULL,
  igst_pct   DECIMAL(5,2) NOT NULL,
  cess_pct   DECIMAL(5,2) NOT NULL DEFAULT 0,
  condition_note VARCHAR(255) NULL,
  is_default BOOLEAN NOT NULL DEFAULT FALSE,
  active     BOOLEAN NOT NULL DEFAULT TRUE,
  CONSTRAINT fk_hr FOREIGN KEY (hsn_id) REFERENCES hsn_codes(id) ON DELETE CASCADE,
  CONSTRAINT hr_split CHECK (ABS(sgst_pct + cgst_pct - igst_pct) < 0.005),
  UNIQUE KEY uq_hr (hsn_id, label)
) ENGINE=InnoDB;

-- ----------------------------------------------------- payment terms
ALTER TABLE customers
  ADD COLUMN payment_term_days INT NOT NULL DEFAULT 0,
  ADD COLUMN payment_terms VARCHAR(120) NULL;
ALTER TABLE vendors
  ADD COLUMN payment_term_days INT NOT NULL DEFAULT 0,
  ADD COLUMN payment_terms VARCHAR(120) NULL;

-- ------------------------------- what the document actually chose
ALTER TABLE invoices
  ADD COLUMN bill_addr_id INT NULL,
  ADD COLUMN ship_addr_id INT NULL,
  ADD COLUMN pos_manual BOOLEAN NOT NULL DEFAULT FALSE,
  ADD CONSTRAINT fk_i_ba FOREIGN KEY (bill_addr_id) REFERENCES party_addresses(id),
  ADD CONSTRAINT fk_i_sa FOREIGN KEY (ship_addr_id) REFERENCES party_addresses(id);

ALTER TABLE invoice_lines
  ADD COLUMN sgst_pct DECIMAL(5,2) NULL,
  ADD COLUMN cgst_pct DECIMAL(5,2) NULL,
  ADD COLUMN igst_pct DECIMAL(5,2) NULL,
  ADD COLUMN rate_label VARCHAR(120) NULL;

ALTER TABLE purchase_orders
  ADD COLUMN ship_addr_id INT NULL,
  ADD CONSTRAINT fk_po_sa FOREIGN KEY (ship_addr_id) REFERENCES party_addresses(id);
