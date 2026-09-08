-- =====================================================================
--  Aequm billing — MySQL 8.0, multi-tenant
--  Every business row carries tenant_id and every unique key is scoped
--  to it, so two organisations can each have a customer C001 and an
--  invoice INV/001 without colliding.
-- =====================================================================
CREATE DATABASE IF NOT EXISTS aequm_billing
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE aequm_billing;

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS gstr3b_uploads, party_contacts, hsn_codes, banks, designations,
  delivery_picks, delivery_lines, deliveries, so_lines, sales_orders,
  physical_counts, discrepancies, stock_ledger, material_attributes, attribute_values,
  attributes, payments, vendor_invoice_lines, vendor_invoices, po_lines,
  purchase_orders, invoice_lines, invoices, materials, vendor_gstins, vendors,
  customer_gstins, customers, user_roles, group_perms, user_groups, users,
  tenants, states, uoms;
SET FOREIGN_KEY_CHECKS = 1;

CREATE TABLE states (code CHAR(2) PRIMARY KEY, name VARCHAR(60) NOT NULL UNIQUE) ENGINE=InnoDB;
CREATE TABLE uoms   (code VARCHAR(6) PRIMARY KEY, name VARCHAR(40) NOT NULL) ENGINE=InnoDB;

CREATE TABLE tenants (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(160) NOT NULL,
  gstin CHAR(15) NULL UNIQUE,
  pan CHAR(10) NULL,
  addr VARCHAR(255) NULL, city VARCHAR(80) NULL,
  state_code CHAR(2) NOT NULL, pin CHAR(6) NULL,
  company_type ENUM('TRADING','NONTRADING') NOT NULL DEFAULT 'NONTRADING',
  logo MEDIUMTEXT NULL,
  inv_prefix VARCHAR(24) NOT NULL DEFAULT 'INV/', inv_seq INT NOT NULL DEFAULT 1,
  po_prefix  VARCHAR(24) NOT NULL DEFAULT 'PO/',  po_seq  INT NOT NULL DEFAULT 1,
  bank VARCHAR(255) NULL,
  smtp_from_name VARCHAR(120) NULL, smtp_from_email VARCHAR(160) NULL,
  smtp_reply_to VARCHAR(160) NULL,  smtp_bcc VARCHAR(160) NULL,
  smtp_host VARCHAR(160) NULL,      smtp_port SMALLINT UNSIGNED NULL,
  smtp_encryption ENUM('STARTTLS','SSL','NONE') NULL,
  smtp_username VARCHAR(160) NULL,  smtp_password VARCHAR(255) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_t_state FOREIGN KEY (state_code) REFERENCES states(code),
  CONSTRAINT t_gstin_st CHECK (gstin IS NULL OR LEFT(gstin,2) = state_code)
) ENGINE=InnoDB;

CREATE TABLE users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  email VARCHAR(160) NOT NULL UNIQUE,
  pwd_hash VARCHAR(255) NOT NULL,
  status ENUM('ACTIVE','PENDING','DISABLED') NOT NULL DEFAULT 'PENDING',
  requested_tenant INT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_u_req FOREIGN KEY (requested_tenant) REFERENCES tenants(id) ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE user_groups (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id INT NOT NULL,
  name VARCHAR(80) NOT NULL,
  CONSTRAINT fk_g_t FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
  UNIQUE KEY uq_g (tenant_id, name)
) ENGINE=InnoDB;

CREATE TABLE group_perms (
  group_id INT NOT NULL, perm VARCHAR(32) NOT NULL,
  PRIMARY KEY (group_id, perm),
  CONSTRAINT fk_gp FOREIGN KEY (group_id) REFERENCES user_groups(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE user_roles (
  user_id INT NOT NULL, tenant_id INT NOT NULL, group_id INT NOT NULL,
  PRIMARY KEY (user_id, tenant_id),
  CONSTRAINT fk_ur_u FOREIGN KEY (user_id)   REFERENCES users(id)       ON DELETE CASCADE,
  CONSTRAINT fk_ur_t FOREIGN KEY (tenant_id) REFERENCES tenants(id)     ON DELETE CASCADE,
  CONSTRAINT fk_ur_g FOREIGN KEY (group_id)  REFERENCES user_groups(id)
) ENGINE=InnoDB;

CREATE TABLE customers (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id INT NOT NULL, code VARCHAR(20) NOT NULL, name VARCHAR(160) NOT NULL,
  party_type ENUM('B2B','B2C') NOT NULL DEFAULT 'B2B',
  bill_addr VARCHAR(255) NOT NULL, bill_city VARCHAR(80) NOT NULL,
  bill_state CHAR(2) NOT NULL, bill_pin CHAR(6) NULL,
  ship_same BOOLEAN NOT NULL DEFAULT TRUE,
  ship_addr VARCHAR(255) NULL, ship_city VARCHAR(80) NULL,
  ship_state CHAR(2) NULL, ship_pin CHAR(6) NULL,
  pan CHAR(10) NULL,
  msme_registered BOOLEAN NOT NULL DEFAULT FALSE,
  msme_number VARCHAR(30) NULL,
  bank_name VARCHAR(120) NULL,
  bank_ifsc CHAR(11) NULL,
  bank_account VARCHAR(30) NULL,
  email VARCHAR(160) NULL,
  CONSTRAINT fk_c_t  FOREIGN KEY (tenant_id)  REFERENCES tenants(id) ON DELETE CASCADE,
  CONSTRAINT fk_c_bs FOREIGN KEY (bill_state) REFERENCES states(code),
  CONSTRAINT fk_c_ss FOREIGN KEY (ship_state) REFERENCES states(code),
  CONSTRAINT c_ship_ok CHECK (ship_same = TRUE OR (ship_addr IS NOT NULL AND ship_state IS NOT NULL)),
  UNIQUE KEY uq_c (tenant_id, code)
) ENGINE=InnoDB;

CREATE TABLE customer_gstins (
  id INT AUTO_INCREMENT PRIMARY KEY, customer_id INT NOT NULL,
  gstin CHAR(15) NOT NULL UNIQUE, state_code CHAR(2) NOT NULL,
  label VARCHAR(80) NULL, is_default BOOLEAN NOT NULL DEFAULT FALSE,
  CONSTRAINT fk_cg   FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
  CONSTRAINT fk_cg_s FOREIGN KEY (state_code)  REFERENCES states(code),
  CONSTRAINT cg_match CHECK (LEFT(gstin,2) = state_code AND CHAR_LENGTH(gstin) = 15)
) ENGINE=InnoDB;

CREATE TABLE vendors (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id INT NOT NULL, code VARCHAR(20) NOT NULL, name VARCHAR(160) NOT NULL,
  party_type ENUM('B2B','B2C') NOT NULL DEFAULT 'B2B',
  addr VARCHAR(255) NOT NULL, city VARCHAR(80) NOT NULL,
  state_code CHAR(2) NOT NULL, pin CHAR(6) NULL, email VARCHAR(160) NULL,
  CONSTRAINT fk_v_t FOREIGN KEY (tenant_id)  REFERENCES tenants(id) ON DELETE CASCADE,
  CONSTRAINT fk_v_s FOREIGN KEY (state_code) REFERENCES states(code),
  UNIQUE KEY uq_v (tenant_id, code)
) ENGINE=InnoDB;

CREATE TABLE vendor_gstins (
  id INT AUTO_INCREMENT PRIMARY KEY, vendor_id INT NOT NULL,
  gstin CHAR(15) NOT NULL UNIQUE, state_code CHAR(2) NOT NULL,
  label VARCHAR(80) NULL, is_default BOOLEAN NOT NULL DEFAULT FALSE,
  CONSTRAINT fk_vg   FOREIGN KEY (vendor_id)  REFERENCES vendors(id) ON DELETE CASCADE,
  CONSTRAINT fk_vg_s FOREIGN KEY (state_code) REFERENCES states(code),
  CONSTRAINT vg_match CHECK (LEFT(gstin,2) = state_code AND CHAR_LENGTH(gstin) = 15)
) ENGINE=InnoDB;

CREATE TABLE materials (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id INT NOT NULL, code VARCHAR(30) NOT NULL, descr VARCHAR(200) NOT NULL,
  price DECIMAL(14,2) NOT NULL, cost DECIMAL(14,2) NOT NULL DEFAULT 0,
  hsn VARCHAR(8) NOT NULL, stock_qty DECIMAL(14,3) NOT NULL DEFAULT 0,
  uom VARCHAR(6) NOT NULL,
  batch_managed BOOLEAN NOT NULL DEFAULT FALSE,
  shelf_life_days INT NOT NULL DEFAULT 0,
  sgst_pct DECIMAL(5,2) NOT NULL, cgst_pct DECIMAL(5,2) NOT NULL, igst_pct DECIMAL(5,2) NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  CONSTRAINT fk_m_t   FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
  CONSTRAINT fk_m_uom FOREIGN KEY (uom)       REFERENCES uoms(code),
  CONSTRAINT m_split CHECK (ABS(sgst_pct + cgst_pct - igst_pct) < 0.005),
  CONSTRAINT m_pos   CHECK (price >= 0 AND cost >= 0),
  CONSTRAINT m_shelf CHECK (shelf_life_days >= 0),
  UNIQUE KEY uq_m (tenant_id, code)
) ENGINE=InnoDB;

CREATE TABLE invoices (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id INT NOT NULL, doc_no VARCHAR(40) NOT NULL,
  doc_type ENUM('TAX','PRO') NOT NULL DEFAULT 'TAX',
  doc_date DATE NOT NULL, due_date DATE NULL,
  customer_id INT NOT NULL, gstin CHAR(15) NULL, pos_state CHAR(2) NOT NULL,
  po_no VARCHAR(60) NULL, po_date DATE NULL,
  reverse_chg ENUM('Y','N') NOT NULL DEFAULT 'N',
  converted_from VARCHAR(40) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_i_t FOREIGN KEY (tenant_id)   REFERENCES tenants(id) ON DELETE CASCADE,
  CONSTRAINT fk_i_c FOREIGN KEY (customer_id) REFERENCES customers(id),
  CONSTRAINT fk_i_p FOREIGN KEY (pos_state)   REFERENCES states(code),
  CONSTRAINT i_po_order  CHECK (po_date  IS NULL OR po_date  <= doc_date),
  CONSTRAINT i_due_order CHECK (due_date IS NULL OR due_date >= doc_date),
  UNIQUE KEY uq_i (tenant_id, doc_no)
) ENGINE=InnoDB;
CREATE INDEX ix_i_date ON invoices(tenant_id, doc_date);

CREATE TABLE invoice_lines (
  id INT AUTO_INCREMENT PRIMARY KEY,
  invoice_id INT NOT NULL, line_no SMALLINT NOT NULL, material_id INT NOT NULL,
  qty DECIMAL(14,3) NOT NULL, price DECIMAL(14,2) NOT NULL,
  CONSTRAINT fk_il_i FOREIGN KEY (invoice_id)  REFERENCES invoices(id) ON DELETE CASCADE,
  CONSTRAINT fk_il_m FOREIGN KEY (material_id) REFERENCES materials(id),
  CONSTRAINT il_pos CHECK (qty > 0 AND price > 0),
  UNIQUE KEY uq_il (invoice_id, line_no)
) ENGINE=InnoDB;

CREATE TABLE purchase_orders (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id INT NOT NULL, doc_no VARCHAR(40) NOT NULL,
  doc_date DATE NOT NULL, req_date DATE NULL,
  vendor_id INT NOT NULL, gstin CHAR(15) NULL,
  bill_addr TEXT NOT NULL, ship_same BOOLEAN NOT NULL DEFAULT TRUE, ship_addr TEXT NOT NULL,
  status ENUM('OPEN','INVOICED','CANCELLED') NOT NULL DEFAULT 'OPEN',
  CONSTRAINT fk_po_t FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
  CONSTRAINT fk_po_v FOREIGN KEY (vendor_id) REFERENCES vendors(id),
  CONSTRAINT po_req CHECK (req_date IS NULL OR req_date >= doc_date),
  UNIQUE KEY uq_po (tenant_id, doc_no)
) ENGINE=InnoDB;

CREATE TABLE po_lines (
  id INT AUTO_INCREMENT PRIMARY KEY,
  po_id INT NOT NULL, line_no SMALLINT NOT NULL, material_id INT NOT NULL,
  qty DECIMAL(14,3) NOT NULL, price DECIMAL(14,2) NOT NULL,
  CONSTRAINT fk_pl_p FOREIGN KEY (po_id)       REFERENCES purchase_orders(id) ON DELETE CASCADE,
  CONSTRAINT fk_pl_m FOREIGN KEY (material_id) REFERENCES materials(id),
  CONSTRAINT pl_pos CHECK (qty > 0 AND price > 0),
  UNIQUE KEY uq_pl (po_id, line_no)
) ENGINE=InnoDB;

CREATE TABLE vendor_invoices (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id INT NOT NULL, doc_no VARCHAR(40) NOT NULL,
  doc_date DATE NOT NULL, due_date DATE NULL,
  vendor_id INT NOT NULL, gstin CHAR(15) NULL, po_id INT NULL,
  CONSTRAINT fk_vi_t FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
  CONSTRAINT fk_vi_v FOREIGN KEY (vendor_id) REFERENCES vendors(id),
  CONSTRAINT fk_vi_p FOREIGN KEY (po_id)     REFERENCES purchase_orders(id),
  CONSTRAINT vi_due CHECK (due_date IS NULL OR due_date >= doc_date),
  UNIQUE KEY uq_vi (tenant_id, vendor_id, doc_no)
) ENGINE=InnoDB;

CREATE TABLE vendor_invoice_lines (
  id INT AUTO_INCREMENT PRIMARY KEY,
  vinv_id INT NOT NULL, line_no SMALLINT NOT NULL, material_id INT NOT NULL,
  qty DECIMAL(14,3) NOT NULL, price DECIMAL(14,2) NOT NULL,
  CONSTRAINT fk_vil_v FOREIGN KEY (vinv_id)     REFERENCES vendor_invoices(id) ON DELETE CASCADE,
  CONSTRAINT fk_vil_m FOREIGN KEY (material_id) REFERENCES materials(id),
  CONSTRAINT vil_pos CHECK (qty > 0 AND price > 0),
  UNIQUE KEY uq_vil (vinv_id, line_no)
) ENGINE=InnoDB;

CREATE TABLE payments (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id INT NOT NULL,
  pay_type ENUM('REC','PAY') NOT NULL, pay_date DATE NOT NULL,
  invoice_id INT NULL, vinv_id INT NULL,
  amount DECIMAL(14,2) NOT NULL, tds DECIMAL(14,2) NOT NULL DEFAULT 0,
  mode ENUM('NEFT','RTGS','IMPS','UPI','Cheque','Cash','Adjustment') NOT NULL,
  bank_ref VARCHAR(60) NULL, bank_acct VARCHAR(80) NULL, narration VARCHAR(200) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_p_t  FOREIGN KEY (tenant_id)  REFERENCES tenants(id) ON DELETE CASCADE,
  CONSTRAINT fk_p_i  FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
  CONSTRAINT fk_p_vi FOREIGN KEY (vinv_id)    REFERENCES vendor_invoices(id) ON DELETE CASCADE,
  CONSTRAINT p_pos  CHECK (amount > 0 AND tds >= 0),
  CONSTRAINT p_side CHECK (
    (pay_type='REC' AND invoice_id IS NOT NULL AND vinv_id    IS NULL) OR
    (pay_type='PAY' AND vinv_id    IS NOT NULL AND invoice_id IS NULL))
) ENGINE=InnoDB;
CREATE INDEX ix_p_inv  ON payments(invoice_id);
CREATE INDEX ix_p_vinv ON payments(vinv_id);

-- ==================================================================
--  Attributes. Definitions are global on purpose: a material master
--  has the same shape in every organisation, only the values differ.
-- ==================================================================
CREATE TABLE attributes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(30) NOT NULL UNIQUE,
  name VARCHAR(120) NOT NULL,
  attr_type ENUM('LIST','MULTI','TEXT','NUM','DATE') NOT NULL
) ENGINE=InnoDB;

CREATE TABLE attribute_values (
  id INT AUTO_INCREMENT PRIMARY KEY,
  attribute_id INT NOT NULL,
  value VARCHAR(160) NOT NULL,
  CONSTRAINT fk_av FOREIGN KEY (attribute_id) REFERENCES attributes(id) ON DELETE CASCADE,
  UNIQUE KEY uq_av (attribute_id, value)
) ENGINE=InnoDB;

CREATE TABLE material_attributes (
  material_id INT NOT NULL,
  attribute_id INT NOT NULL,
  value VARCHAR(400) NOT NULL,
  PRIMARY KEY (material_id, attribute_id),
  CONSTRAINT fk_ma_m FOREIGN KEY (material_id)  REFERENCES materials(id)  ON DELETE CASCADE,
  CONSTRAINT fk_ma_a FOREIGN KEY (attribute_id) REFERENCES attributes(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ==================================================================
--  Stock. One append-only ledger: positive rows bring stock in,
--  negative rows take it out. Balance is always the sum, so a
--  movement can never be lost by editing a running total.
-- ==================================================================
CREATE TABLE stock_ledger (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id   INT NOT NULL,
  move_date   DATE NOT NULL,
  source      ENUM('GRN','GI','PI') NOT NULL,
  doc_no      VARCHAR(40) NOT NULL,
  material_id INT NOT NULL,
  stock_type  ENUM('NORMAL','RESERVED','DAMAGED','CONSIGNMENT') NOT NULL DEFAULT 'NORMAL',
  batch       VARCHAR(40) NULL,
  mfg_date    DATE NULL,
  exp_date    DATE NULL,
  qty         DECIMAL(14,3) NOT NULL,     -- signed
  po_id       INT NULL,
  so_id       INT NULL,
  party       VARCHAR(160) NULL,
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_sl_t FOREIGN KEY (tenant_id)   REFERENCES tenants(id)   ON DELETE CASCADE,
  CONSTRAINT fk_sl_m FOREIGN KEY (material_id) REFERENCES materials(id),
  CONSTRAINT sl_qty CHECK (qty <> 0),
  CONSTRAINT sl_exp CHECK (exp_date IS NULL OR mfg_date IS NULL OR exp_date >= mfg_date)
) ENGINE=InnoDB;
CREATE INDEX ix_sl_mat ON stock_ledger(tenant_id, material_id, batch, stock_type);
CREATE INDEX ix_sl_date ON stock_ledger(tenant_id, move_date);

CREATE TABLE discrepancies (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id   INT NOT NULL,
  grn_no      VARCHAR(40) NOT NULL,
  grn_date    DATE NOT NULL,
  po_id       INT NOT NULL,
  material_id INT NOT NULL,
  ordered_qty  DECIMAL(14,3) NOT NULL,
  received_qty DECIMAL(14,3) NOT NULL,
  status      ENUM('HELD','RELEASED') NOT NULL DEFAULT 'HELD',
  released_on DATE NULL,
  released_by VARCHAR(120) NULL,
  CONSTRAINT fk_d_t FOREIGN KEY (tenant_id)   REFERENCES tenants(id) ON DELETE CASCADE,
  CONSTRAINT fk_d_p FOREIGN KEY (po_id)       REFERENCES purchase_orders(id),
  CONSTRAINT fk_d_m FOREIGN KEY (material_id) REFERENCES materials(id),
  CONSTRAINT d_diff CHECK (ordered_qty <> received_qty)
) ENGINE=InnoDB;

CREATE TABLE physical_counts (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id   INT NOT NULL,
  doc_no      VARCHAR(40) NOT NULL,
  count_date  DATE NOT NULL,
  counted_by  VARCHAR(120) NULL,
  reason      VARCHAR(200) NULL,
  material_id INT NOT NULL,
  batch       VARCHAR(40) NULL,
  stock_type  ENUM('NORMAL','RESERVED','DAMAGED','CONSIGNMENT') NOT NULL,
  book_qty    DECIMAL(14,3) NOT NULL,
  counted_qty DECIMAL(14,3) NOT NULL,
  diff_qty    DECIMAL(14,3) NOT NULL,
  CONSTRAINT fk_pc_t FOREIGN KEY (tenant_id)   REFERENCES tenants(id) ON DELETE CASCADE,
  CONSTRAINT fk_pc_m FOREIGN KEY (material_id) REFERENCES materials(id),
  CONSTRAINT pc_diff CHECK (diff_qty = counted_qty - book_qty AND diff_qty <> 0)
) ENGINE=InnoDB;

-- ==================================================================
--  Ordering: sales order, delivery, goods issue.
-- ==================================================================
CREATE TABLE sales_orders (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id   INT NOT NULL,
  doc_no      VARCHAR(40) NOT NULL,
  doc_date    DATE NOT NULL,
  req_date    DATE NULL,
  customer_id INT NOT NULL,
  cust_ref    VARCHAR(60) NULL,
  CONSTRAINT fk_so_t FOREIGN KEY (tenant_id)   REFERENCES tenants(id) ON DELETE CASCADE,
  CONSTRAINT fk_so_c FOREIGN KEY (customer_id) REFERENCES customers(id),
  CONSTRAINT so_req CHECK (req_date IS NULL OR req_date >= doc_date),
  UNIQUE KEY uq_so (tenant_id, doc_no)
) ENGINE=InnoDB;

CREATE TABLE so_lines (
  id INT AUTO_INCREMENT PRIMARY KEY,
  so_id INT NOT NULL, line_no SMALLINT NOT NULL, material_id INT NOT NULL,
  qty DECIMAL(14,3) NOT NULL, price DECIMAL(14,2) NOT NULL,
  CONSTRAINT fk_sol_s FOREIGN KEY (so_id)       REFERENCES sales_orders(id) ON DELETE CASCADE,
  CONSTRAINT fk_sol_m FOREIGN KEY (material_id) REFERENCES materials(id),
  CONSTRAINT sol_pos CHECK (qty > 0 AND price > 0),
  UNIQUE KEY uq_sol (so_id, line_no)
) ENGINE=InnoDB;

CREATE TABLE deliveries (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id INT NOT NULL,
  doc_no    VARCHAR(40) NOT NULL,
  doc_date  DATE NOT NULL,
  so_id     INT NOT NULL,
  ship_to   VARCHAR(400) NULL,
  CONSTRAINT fk_dl_t FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
  CONSTRAINT fk_dl_s FOREIGN KEY (so_id)     REFERENCES sales_orders(id),
  UNIQUE KEY uq_dl (tenant_id, doc_no)
) ENGINE=InnoDB;

CREATE TABLE delivery_lines (
  id INT AUTO_INCREMENT PRIMARY KEY,
  delivery_id INT NOT NULL, material_id INT NOT NULL,
  batch VARCHAR(40) NULL,
  stock_type ENUM('NORMAL','RESERVED','DAMAGED','CONSIGNMENT') NOT NULL DEFAULT 'NORMAL',
  exp_date DATE NULL,
  qty DECIMAL(14,3) NOT NULL,
  CONSTRAINT fk_dll_d FOREIGN KEY (delivery_id) REFERENCES deliveries(id) ON DELETE CASCADE,
  CONSTRAINT fk_dll_m FOREIGN KEY (material_id) REFERENCES materials(id),
  CONSTRAINT dll_pos CHECK (qty > 0)
) ENGINE=InnoDB;

-- Stock on hand per material, batch and stock type: the sum of the ledger.
CREATE OR REPLACE VIEW v_stock_on_hand AS
SELECT tenant_id, material_id, COALESCE(batch,'') AS batch, stock_type,
       MAX(exp_date) AS exp_date, SUM(qty) AS qty
FROM stock_ledger
GROUP BY tenant_id, material_id, COALESCE(batch,''), stock_type
HAVING SUM(qty) <> 0;

-- ============================================================
-- Shared masters / GST / party contacts
-- ============================================================

CREATE TABLE designations (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(80) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE banks (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(120) NOT NULL UNIQUE,
    short_code VARCHAR(12) NULL
) ENGINE=InnoDB;

CREATE TABLE hsn_codes (
    id INT PRIMARY KEY AUTO_INCREMENT,
    tenant_id INT NOT NULL,
    code VARCHAR(8) NOT NULL,
    descr VARCHAR(200) NOT NULL,
    kind ENUM('HSN','SAC') NOT NULL DEFAULT 'HSN',
    sgst_pct DECIMAL(5,2) NOT NULL,
    cgst_pct DECIMAL(5,2) NOT NULL,
    igst_pct DECIMAL(5,2) NOT NULL,
    cess_pct DECIMAL(5,2) NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT uq_h UNIQUE (tenant_id, code),
    CONSTRAINT fk_hsn_tenant
        FOREIGN KEY (tenant_id) REFERENCES tenants(id)
        ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE party_contacts (
    id INT PRIMARY KEY AUTO_INCREMENT,
    tenant_id INT NOT NULL,
    party_kind ENUM('CUSTOMER','VENDOR') NOT NULL,
    party_id INT NOT NULL,
    first_name VARCHAR(60) NOT NULL,
    middle_name VARCHAR(60) NULL,
    last_name VARCHAR(60) NULL,
    designation_id INT NULL,
    phone VARCHAR(20) NULL,
    email VARCHAR(160) NULL,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT fk_party_contact_tenant
        FOREIGN KEY (tenant_id) REFERENCES tenants(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_party_contact_designation
        FOREIGN KEY (designation_id) REFERENCES designations(id)
) ENGINE=InnoDB;

CREATE TABLE gstr3b_uploads (
    id INT PRIMARY KEY AUTO_INCREMENT,
    tenant_id INT NOT NULL,
    period VARCHAR(7) NOT NULL,
    uploaded_by VARCHAR(120) NULL,
    out_taxable DECIMAL(16,2) NOT NULL DEFAULT 0,
    out_igst DECIMAL(16,2) NOT NULL DEFAULT 0,
    out_cgst DECIMAL(16,2) NOT NULL DEFAULT 0,
    out_sgst DECIMAL(16,2) NOT NULL DEFAULT 0,
    itc_igst DECIMAL(16,2) NOT NULL DEFAULT 0,
    itc_cgst DECIMAL(16,2) NOT NULL DEFAULT 0,
    itc_sgst DECIMAL(16,2) NOT NULL DEFAULT 0,
    CONSTRAINT uq_g3 UNIQUE (tenant_id, period),
    CONSTRAINT fk_gstr3b_tenant
        FOREIGN KEY (tenant_id) REFERENCES tenants(id)
        ON DELETE CASCADE
) ENGINE=InnoDB;

