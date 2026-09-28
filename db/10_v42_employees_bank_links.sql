-- =====================================================================
-- Aequm Billing v4.2 — employees and bank statement attachments
--
-- Additive and safe to run more than once: it creates two tables if they
-- are missing and grants one new screen. It does not ALTER, DROP, TRUNCATE
-- or DELETE anything. Take a backup first all the same.
--
--   employees        employee ID, first name, last name, e-mail
--   stmt_txn_links   what a bank transaction was for:
--                      CUST_INV  a customer invoice settled by a credit
--                      VEND_INV  a vendor invoice paid by a debit
--                      EMPLOYEE  salary or an expense paid to an employee
--
-- Card statements need no schema change: the company / personal choice made
-- at upload is written to the existing stmt_txns.allocation column.
-- =====================================================================
USE aequm_billing;

CREATE TABLE IF NOT EXISTS employees (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id INT NOT NULL,
  emp_code VARCHAR(20) NOT NULL,
  first_name VARCHAR(60) NOT NULL,
  last_name VARCHAR(60) NOT NULL,
  email VARCHAR(160) NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_emp_t FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE,
  UNIQUE KEY uq_emp_code (tenant_id, emp_code),
  UNIQUE KEY uq_emp_email (tenant_id, email)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS stmt_txn_links (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tenant_id INT NOT NULL,
  txn_id INT NOT NULL,
  link_type ENUM('CUST_INV','VEND_INV','EMPLOYEE') NOT NULL,
  invoice_id INT NULL,
  vinv_id INT NULL,
  employee_id INT NULL,
  purpose ENUM('SALARY','EXPENSE') NULL,     -- set for EMPLOYEE links only
  amount DECIMAL(14,2) NOT NULL,
  notes VARCHAR(200) NULL,
  linked_by VARCHAR(120) NULL,
  linked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_stl_t FOREIGN KEY (tenant_id)   REFERENCES tenants(id)         ON DELETE CASCADE,
  CONSTRAINT fk_stl_x FOREIGN KEY (txn_id)      REFERENCES stmt_txns(id)       ON DELETE CASCADE,
  CONSTRAINT fk_stl_i FOREIGN KEY (invoice_id)  REFERENCES invoices(id)        ON DELETE CASCADE,
  CONSTRAINT fk_stl_v FOREIGN KEY (vinv_id)     REFERENCES vendor_invoices(id) ON DELETE CASCADE,
  CONSTRAINT fk_stl_e FOREIGN KEY (employee_id) REFERENCES employees(id),
  KEY ix_stl_txn (tenant_id, txn_id),
  KEY ix_stl_inv (tenant_id, invoice_id),
  KEY ix_stl_vinv (tenant_id, vinv_id),
  KEY ix_stl_emp (tenant_id, employee_id)
) ENGINE=InnoDB;

-- The Employees screen goes to groups that already administer the
-- organisation. INSERT IGNORE makes this safe to repeat.
INSERT IGNORE INTO group_perms (group_id, perm)
  SELECT group_id, 'employees' FROM group_perms WHERE perm = 'org';
