CREATE DATABASE IF NOT EXISTS bright_scaff CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE bright_scaff;
CREATE TABLE IF NOT EXISTS customers (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, customer_code VARCHAR(40) NOT NULL UNIQUE,
 customer_name VARCHAR(180) NOT NULL, contact_person VARCHAR(180), phone VARCHAR(40), email VARCHAR(180),
 billing_address TEXT, site_address TEXT, tax_number VARCHAR(80), opening_balance DECIMAL(14,2) NOT NULL DEFAULT 0,
 is_active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 INDEX idx_customers_name(customer_name), INDEX idx_customers_phone(phone)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS customer_sites (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, customer_id BIGINT UNSIGNED NOT NULL, site_name VARCHAR(180) NOT NULL,
 address TEXT, is_active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT fk_sites_customer FOREIGN KEY(customer_id) REFERENCES customers(id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS items (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, item_code VARCHAR(50) NOT NULL UNIQUE, item_name VARCHAR(180) NOT NULL,
 category VARCHAR(100), unit VARCHAR(30) NOT NULL DEFAULT 'Nos', total_stock INT UNSIGNED NOT NULL DEFAULT 0,
 initial_daily_rate DECIMAL(12,2) NOT NULL DEFAULT 0, post_30_day_daily_rate DECIMAL(12,2) NOT NULL DEFAULT 0,
 has_monthly_minimum BOOLEAN NOT NULL DEFAULT TRUE, is_active BOOLEAN NOT NULL DEFAULT TRUE,
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 INDEX idx_items_name(item_name)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS inventory_movements (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, item_id BIGINT UNSIGNED NOT NULL,
 movement_type ENUM('OPENING','PURCHASE','ISSUE','RETURN','DAMAGE','LOSS','ADJUSTMENT') NOT NULL,
 quantity INT NOT NULL, reference_type VARCHAR(40), reference_id BIGINT UNSIGNED, movement_date DATE NOT NULL,
 notes VARCHAR(500), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT fk_movements_item FOREIGN KEY(item_id) REFERENCES items(id), INDEX idx_movements_item_date(item_id,movement_date)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS rental_orders (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, rental_number VARCHAR(50) NOT NULL UNIQUE,
 customer_id BIGINT UNSIGNED NOT NULL, site_id BIGINT UNSIGNED, issue_date DATE NOT NULL,
 status ENUM('OPEN','PARTIALLY_RETURNED','CLOSED','CANCELLED') NOT NULL DEFAULT 'OPEN', notes TEXT,
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 CONSTRAINT fk_rentals_customer FOREIGN KEY(customer_id) REFERENCES customers(id),
 CONSTRAINT fk_rentals_site FOREIGN KEY(site_id) REFERENCES customer_sites(id), INDEX idx_rentals_customer_status(customer_id,status)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS rental_order_items (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, rental_order_id BIGINT UNSIGNED NOT NULL, item_id BIGINT UNSIGNED NOT NULL,
 quantity_issued INT UNSIGNED NOT NULL, initial_daily_rate DECIMAL(12,2) NOT NULL, post_30_day_daily_rate DECIMAL(12,2) NOT NULL,
 is_daily_rental BOOLEAN NOT NULL DEFAULT FALSE,
 issue_date DATE NOT NULL, notes VARCHAR(500), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT fk_order_items_order FOREIGN KEY(rental_order_id) REFERENCES rental_orders(id),
 CONSTRAINT fk_order_items_item FOREIGN KEY(item_id) REFERENCES items(id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS rental_returns (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, return_number VARCHAR(50) NOT NULL UNIQUE,
 rental_order_id BIGINT UNSIGNED NOT NULL, return_date DATE NOT NULL, notes TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT fk_returns_order FOREIGN KEY(rental_order_id) REFERENCES rental_orders(id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS rental_return_items (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, rental_return_id BIGINT UNSIGNED NOT NULL,
 rental_order_item_id BIGINT UNSIGNED NOT NULL, quantity_returned INT UNSIGNED NOT NULL,
 item_condition ENUM('GOOD','DAMAGED','MISSING') NOT NULL DEFAULT 'GOOD', notes VARCHAR(500),
 CONSTRAINT fk_return_items_return FOREIGN KEY(rental_return_id) REFERENCES rental_returns(id),
 CONSTRAINT fk_return_items_order_item FOREIGN KEY(rental_order_item_id) REFERENCES rental_order_items(id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS rental_charges (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, rental_order_item_id BIGINT UNSIGNED NOT NULL,
 period_start DATE NOT NULL, period_end DATE NOT NULL,
 charge_type ENUM('MINIMUM_30_DAY','EXTRA_DAILY','ADJUSTMENT','OTHER') NOT NULL,
 quantity INT UNSIGNED NOT NULL, rate DECIMAL(12,2) NOT NULL, amount DECIMAL(14,2) NOT NULL,
 calculation_notes VARCHAR(500), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT fk_charges_order_item FOREIGN KEY(rental_order_item_id) REFERENCES rental_order_items(id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS invoices (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, invoice_number VARCHAR(50) NOT NULL UNIQUE,
 customer_id BIGINT UNSIGNED NOT NULL, invoice_date DATE NOT NULL, period_start DATE, period_end DATE,
 subtotal DECIMAL(14,2) NOT NULL DEFAULT 0, tax_amount DECIMAL(14,2) NOT NULL DEFAULT 0,
 total_amount DECIMAL(14,2) NOT NULL DEFAULT 0, status ENUM('DRAFT','ISSUED','VOID') NOT NULL DEFAULT 'DRAFT', notes TEXT,
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, CONSTRAINT fk_invoices_customer FOREIGN KEY(customer_id) REFERENCES customers(id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS invoice_lines (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, invoice_id BIGINT UNSIGNED NOT NULL, description VARCHAR(500) NOT NULL,
 quantity DECIMAL(12,2) NOT NULL DEFAULT 1, rate DECIMAL(12,2) NOT NULL DEFAULT 0, amount DECIMAL(14,2) NOT NULL DEFAULT 0,
 rental_order_item_id BIGINT UNSIGNED, CONSTRAINT fk_invoice_lines_invoice FOREIGN KEY(invoice_id) REFERENCES invoices(id),
 CONSTRAINT fk_invoice_lines_order_item FOREIGN KEY(rental_order_item_id) REFERENCES rental_order_items(id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS ledger_entries (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, customer_id BIGINT UNSIGNED NOT NULL, transaction_date DATE NOT NULL,
 reference_number VARCHAR(60), transaction_type ENUM('OPENING_BALANCE','RENT','OTHER_CHARGE','RECEIPT','CREDIT_NOTE','ADJUSTMENT') NOT NULL,
 particulars VARCHAR(500) NOT NULL, debit DECIMAL(14,2) NOT NULL DEFAULT 0, credit DECIMAL(14,2) NOT NULL DEFAULT 0,
 source_type VARCHAR(40), source_id BIGINT UNSIGNED, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT fk_ledger_customer FOREIGN KEY(customer_id) REFERENCES customers(id), INDEX idx_ledger_customer_date(customer_id,transaction_date,id)
) ENGINE=InnoDB;

USE bright_scaff;

ALTER TABLE rental_orders
    ADD COLUMN apply_gst BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN gst_rate DECIMAL(5,2) NOT NULL DEFAULT 18.00,
    ADD COLUMN advance_paid DECIMAL(14,2) NOT NULL DEFAULT 0.00,
    ADD COLUMN vehicle_rent_amount DECIMAL(14,2) NOT NULL DEFAULT 0.00,
    ADD COLUMN vehicle_rent_stage ENUM('DELIVERY','RETURN','BOTH') NULL,
    ADD COLUMN vehicle_type VARCHAR(100) NULL,
    ADD COLUMN vehicle_number VARCHAR(40) NULL,
    ADD COLUMN vehicle_paid_status ENUM('UNPAID','PARTIAL','PAID')
        NOT NULL DEFAULT 'UNPAID',
    ADD COLUMN vehicle_payment_method VARCHAR(60) NULL;

ALTER TABLE customers
    ADD COLUMN company VARCHAR(180) NULL,
    ADD COLUMN main_mobile VARCHAR(40) NULL,
    ADD COLUMN mobile_2 VARCHAR(40) NULL,
    ADD COLUMN mobile_3 VARCHAR(40) NULL,
    ADD COLUMN office_address TEXT NULL,
    ADD COLUMN office_email VARCHAR(180) NULL,
    ADD COLUMN residential_address TEXT NULL,
    ADD COLUMN gst_number VARCHAR(80) NULL,
    ADD COLUMN guarantor_relationship VARCHAR(100) NULL,
    ADD COLUMN guarantor_name VARCHAR(180) NULL,
    ADD COLUMN guarantor_contact VARCHAR(40) NULL,
    ADD COLUMN guarantor_address TEXT NULL;

CREATE TABLE IF NOT EXISTS rental_payments (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 rental_order_id BIGINT UNSIGNED NOT NULL,
 payment_date DATE NOT NULL,
 amount DECIMAL(14,2) NOT NULL,
 payment_method VARCHAR(60) NULL,
 payment_type ENUM('ADVANCE','RETURN_PAYMENT','OTHER') NOT NULL DEFAULT 'OTHER',
 reference_number VARCHAR(60) NULL,
 notes VARCHAR(500) NULL,
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT fk_rental_payments_order FOREIGN KEY (rental_order_id) REFERENCES rental_orders(id),
 INDEX idx_rental_payments_order_date (rental_order_id,payment_date)
) ENGINE=InnoDB;

-- BRIGHT SCAFF: "Take as daily rental" per delivery line.
-- Run once against the existing bright_scaff database.
USE bright_scaff;


-- Optional: the app now uses ONE daily rate per item (initial_daily_rate).
-- The old "after 30 days" columns are kept for history; align them so nothing diverges.
UPDATE items SET post_30_day_daily_rate = initial_daily_rate;

ALTER TABLE rental_orders
  ADD COLUMN site_name VARCHAR(180) NULL,
  ADD COLUMN discount_allowed BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN discount_type ENUM('PERCENT','FIXED') NULL,
  ADD COLUMN discount_value DECIMAL(14,2) NOT NULL DEFAULT 0.00;

-- One row per return bill: vehicle rent and/or discount added from Return history.
CREATE TABLE IF NOT EXISTS rental_return_adjustments (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  rental_return_id BIGINT UNSIGNED NOT NULL,
  rental_order_id BIGINT UNSIGNED NOT NULL,
  vehicle_rent_amount DECIMAL(14,2) NOT NULL DEFAULT 0.00,
  vehicle_type VARCHAR(100) NULL,
  vehicle_number VARCHAR(40) NULL,
  discount_type ENUM('PERCENT','FIXED') NULL,
  discount_value DECIMAL(14,2) NOT NULL DEFAULT 0.00,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_return_adjustment_return (rental_return_id),
  CONSTRAINT fk_return_adj_return FOREIGN KEY (rental_return_id) REFERENCES rental_returns(id),
  CONSTRAINT fk_return_adj_order FOREIGN KEY (rental_order_id) REFERENCES rental_orders(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS rental_return_audit (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 return_item_id BIGINT UNSIGNED NOT NULL,
 rental_return_id BIGINT UNSIGNED NOT NULL,
 action_type ENUM('EDIT','DELETE') NOT NULL,
 old_return_number VARCHAR(50) NOT NULL,
 old_return_date DATE NOT NULL,
 old_rental_order_item_id BIGINT UNSIGNED NOT NULL,
 old_quantity_returned INT UNSIGNED NOT NULL,
 old_item_condition ENUM('GOOD','DAMAGED','MISSING') NOT NULL,
 old_notes VARCHAR(500), reason VARCHAR(500) NOT NULL,
 changed_by VARCHAR(120) NOT NULL DEFAULT 'system-user',
 changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 INDEX idx_return_audit_item(return_item_id, changed_at),
 INDEX idx_return_audit_header(rental_return_id, changed_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS app_users (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(80) NOT NULL UNIQUE,
  full_name VARCHAR(180) NOT NULL,
  email VARCHAR(180),
  -- PBKDF2-SHA256 hash produced by werkzeug.security.generate_password_hash.
  -- Never store a plaintext password here.
  password_hash VARCHAR(255) NOT NULL,
  role ENUM('ADMIN','MANAGER','STAFF') NOT NULL DEFAULT 'STAFF',
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  -- Forces a password change on first login for accounts created by an admin.
  must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
  last_login_at DATETIME NULL,
  created_by BIGINT UNSIGNED NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_app_users_active(is_active),
  CONSTRAINT fk_app_users_creator FOREIGN KEY(created_by) REFERENCES app_users(id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------------
-- Login audit trail
--
-- success = 0 rows are kept deliberately: repeated failures for one username
-- or IP are the signal you want when investigating an account lockout.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_login_audit (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT UNSIGNED NULL,
  -- Recorded even when no account matches, so unknown-user attempts are visible.
  username VARCHAR(80) NOT NULL,
  event_type ENUM('LOGIN','LOGOUT','LOGIN_FAILED','PASSWORD_CHANGED') NOT NULL,
  success BOOLEAN NOT NULL DEFAULT TRUE,
  ip_address VARCHAR(64),
  user_agent VARCHAR(255),
  detail VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_login_audit_user(user_id, created_at),
  INDEX idx_login_audit_username(username, created_at),
  CONSTRAINT fk_login_audit_user FOREIGN KEY(user_id) REFERENCES app_users(id)
) ENGINE=InnoDB;