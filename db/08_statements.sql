-- v2.4: bank and director-card statements.
--   stmt_accounts  one bank account or one director's card
--   stmt_uploads   one statement file loaded against an account and month
--   stmt_txns      every transaction found in the file. A fingerprint keeps
--                  the same row from being saved twice when a statement is
--                  uploaded again, so nothing is lost and nothing doubles.
-- Card debits carry an allocation: COMPANY (a business expense the company
-- owes the director for), PERSONAL (the director's own spend), or
-- UNALLOCATED until someone decides. Bank rows and card credits are NA.
USE aequm_billing;

CREATE TABLE stmt_accounts (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id INT NOT NULL,
  kind ENUM('BANK','CARD') NOT NULL,
  label VARCHAR(120) NOT NULL,          -- "HDFC Current A/c", "RBL Platinum Plus"
  holder VARCHAR(120) NULL,             -- director's name for a card
  number_hint VARCHAR(30) NULL,         -- last digits only, never the full number
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_sa_t FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
  UNIQUE KEY uq_sa (tenant_id, kind, label)
) ENGINE=InnoDB;

CREATE TABLE stmt_uploads (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id INT NOT NULL,
  account_id INT NOT NULL,
  period CHAR(7) NOT NULL,              -- YYYY-MM the statement belongs to
  filename VARCHAR(200) NOT NULL,
  uploaded_by VARCHAR(120) NULL,
  txns_found INT NOT NULL DEFAULT 0,
  txns_new INT NOT NULL DEFAULT 0,      -- found minus already-saved duplicates
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_su_t FOREIGN KEY (tenant_id)  REFERENCES tenants(id)       ON DELETE CASCADE,
  CONSTRAINT fk_su_a FOREIGN KEY (account_id) REFERENCES stmt_accounts(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE stmt_txns (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id INT NOT NULL,
  account_id INT NOT NULL,
  upload_id INT NOT NULL,
  txn_date DATE NOT NULL,
  descr VARCHAR(240) NOT NULL,
  debit  DECIMAL(14,2) NOT NULL DEFAULT 0,
  credit DECIMAL(14,2) NOT NULL DEFAULT 0,
  fingerprint CHAR(40) NOT NULL,        -- sha1(date|descr|debit|credit) for dedupe
  allocation ENUM('NA','UNALLOCATED','COMPANY','PERSONAL') NOT NULL DEFAULT 'NA',
  category VARCHAR(60) NULL,            -- expense head when allocated to COMPANY
  notes VARCHAR(200) NULL,
  allocated_by VARCHAR(120) NULL,
  allocated_at TIMESTAMP NULL,
  CONSTRAINT fk_st_t FOREIGN KEY (tenant_id)  REFERENCES tenants(id)       ON DELETE CASCADE,
  CONSTRAINT fk_st_a FOREIGN KEY (account_id) REFERENCES stmt_accounts(id) ON DELETE CASCADE,
  CONSTRAINT fk_st_u FOREIGN KEY (upload_id)  REFERENCES stmt_uploads(id)  ON DELETE CASCADE,
  UNIQUE KEY uq_st (tenant_id, account_id, fingerprint),
  KEY ix_st_date (tenant_id, account_id, txn_date)
) ENGINE=InnoDB;

-- Groups that hold the Setup permission are the administrators of their
-- organisation; give them the two new screens so somebody can reach them
-- and hand access on. Everyone else is granted from Users and Access.
INSERT IGNORE INTO group_perms (group_id, perm)
  SELECT group_id, 'bankstmt' FROM group_perms WHERE perm = 'org';
INSERT IGNORE INTO group_perms (group_id, perm)
  SELECT group_id, 'cardstmt' FROM group_perms WHERE perm = 'org';
