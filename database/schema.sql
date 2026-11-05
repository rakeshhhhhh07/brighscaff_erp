-- BRIGHT SCAFF: TiDB-compatible structure-only schema
-- Generated from the supplied working local MySQL 8.0 dump.
-- No INSERT statements or existing data are included.
-- Safe for existing tables: CREATE TABLE IF NOT EXISTS does not drop or overwrite them.
-- IMPORTANT: This creates missing tables only; it does not add missing columns to tables
-- that already exist. Compare existing table definitions separately if needed.

USE `bright_scaff`;

-- Table: app_users
CREATE TABLE IF NOT EXISTS `app_users` (
`id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `username` varchar(80) COLLATE utf8mb4_unicode_ci NOT NULL,
  `full_name` varchar(180) COLLATE utf8mb4_unicode_ci NOT NULL,
  `email` varchar(180) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `password_hash` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `role` enum('ADMIN','MANAGER','STAFF') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'STAFF',
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `must_change_password` tinyint(1) NOT NULL DEFAULT '0',
  `last_login_at` datetime DEFAULT NULL,
  `created_by` bigint unsigned DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`),
  KEY `idx_app_users_active` (`is_active`),
  KEY `fk_app_users_creator` (`created_by`),
  CONSTRAINT `fk_app_users_creator` FOREIGN KEY (`created_by`) REFERENCES `app_users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: customers
CREATE TABLE IF NOT EXISTS `customers` (
`id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `customer_code` varchar(40) COLLATE utf8mb4_unicode_ci NOT NULL,
  `customer_name` varchar(180) COLLATE utf8mb4_unicode_ci NOT NULL,
  `contact_person` varchar(180) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `phone` varchar(40) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `email` varchar(180) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `billing_address` text COLLATE utf8mb4_unicode_ci,
  `site_address` text COLLATE utf8mb4_unicode_ci,
  `tax_number` varchar(80) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `opening_balance` decimal(14,2) NOT NULL DEFAULT '0.00',
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `company` varchar(180) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `main_mobile` varchar(40) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `mobile_2` varchar(40) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `mobile_3` varchar(40) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `office_address` text COLLATE utf8mb4_unicode_ci,
  `office_email` varchar(180) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `residential_address` text COLLATE utf8mb4_unicode_ci,
  `gst_number` varchar(80) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `guarantor_relationship` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `guarantor_name` varchar(180) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `guarantor_contact` varchar(40) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `guarantor_address` text COLLATE utf8mb4_unicode_ci,
  PRIMARY KEY (`id`),
  UNIQUE KEY `customer_code` (`customer_code`),
  KEY `idx_customers_name` (`customer_name`),
  KEY `idx_customers_phone` (`phone`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: items
CREATE TABLE IF NOT EXISTS `items` (
`id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `item_code` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `item_name` varchar(180) COLLATE utf8mb4_unicode_ci NOT NULL,
  `category` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `unit` varchar(30) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'Nos',
  `total_stock` int unsigned NOT NULL DEFAULT '0',
  `initial_daily_rate` decimal(12,2) NOT NULL DEFAULT '0.00',
  `post_30_day_daily_rate` decimal(12,2) NOT NULL DEFAULT '0.00',
  `has_monthly_minimum` tinyint(1) NOT NULL DEFAULT '1',
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `item_code` (`item_code`),
  KEY `idx_items_name` (`item_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: customer_sites
CREATE TABLE IF NOT EXISTS `customer_sites` (
`id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `customer_id` bigint unsigned NOT NULL,
  `site_name` varchar(180) COLLATE utf8mb4_unicode_ci NOT NULL,
  `address` text COLLATE utf8mb4_unicode_ci,
  `is_active` tinyint(1) NOT NULL DEFAULT '1',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `fk_sites_customer` (`customer_id`),
  CONSTRAINT `fk_sites_customer` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: invoices
CREATE TABLE IF NOT EXISTS `invoices` (
`id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `invoice_number` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `customer_id` bigint unsigned NOT NULL,
  `invoice_date` date NOT NULL,
  `period_start` date DEFAULT NULL,
  `period_end` date DEFAULT NULL,
  `subtotal` decimal(14,2) NOT NULL DEFAULT '0.00',
  `tax_amount` decimal(14,2) NOT NULL DEFAULT '0.00',
  `total_amount` decimal(14,2) NOT NULL DEFAULT '0.00',
  `status` enum('DRAFT','ISSUED','VOID') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'DRAFT',
  `notes` text COLLATE utf8mb4_unicode_ci,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `invoice_number` (`invoice_number`),
  KEY `fk_invoices_customer` (`customer_id`),
  CONSTRAINT `fk_invoices_customer` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: rental_orders
CREATE TABLE IF NOT EXISTS `rental_orders` (
`id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `rental_number` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `customer_id` bigint unsigned NOT NULL,
  `site_id` bigint unsigned DEFAULT NULL,
  `issue_date` date NOT NULL,
  `status` enum('OPEN','PARTIALLY_RETURNED','CLOSED','CANCELLED') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'OPEN',
  `notes` text COLLATE utf8mb4_unicode_ci,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `apply_gst` tinyint(1) NOT NULL DEFAULT '0',
  `gst_rate` decimal(5,2) NOT NULL DEFAULT '18.00',
  `advance_paid` decimal(14,2) NOT NULL DEFAULT '0.00',
  `vehicle_rent_amount` decimal(14,2) NOT NULL DEFAULT '0.00',
  `vehicle_rent_stage` enum('DELIVERY','RETURN','BOTH') COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `vehicle_type` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `vehicle_number` varchar(40) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `vehicle_paid_status` enum('UNPAID','PARTIAL','PAID') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'UNPAID',
  `vehicle_payment_method` varchar(60) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `site_name` varchar(180) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `discount_allowed` tinyint(1) NOT NULL DEFAULT '0',
  `discount_type` enum('PERCENT','FIXED') COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `discount_value` decimal(14,2) NOT NULL DEFAULT '0.00',
  PRIMARY KEY (`id`),
  UNIQUE KEY `rental_number` (`rental_number`),
  KEY `fk_rentals_site` (`site_id`),
  KEY `idx_rentals_customer_status` (`customer_id`,`status`),
  CONSTRAINT `fk_rentals_customer` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`),
  CONSTRAINT `fk_rentals_site` FOREIGN KEY (`site_id`) REFERENCES `customer_sites` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: rental_order_items
CREATE TABLE IF NOT EXISTS `rental_order_items` (
`id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `rental_order_id` bigint unsigned NOT NULL,
  `item_id` bigint unsigned NOT NULL,
  `quantity_issued` int unsigned NOT NULL,
  `initial_daily_rate` decimal(12,2) NOT NULL,
  `post_30_day_daily_rate` decimal(12,2) NOT NULL,
  `is_daily_rental` tinyint(1) NOT NULL DEFAULT '0',
  `issue_date` date NOT NULL,
  `notes` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `fk_order_items_order` (`rental_order_id`),
  KEY `fk_order_items_item` (`item_id`),
  CONSTRAINT `fk_order_items_item` FOREIGN KEY (`item_id`) REFERENCES `items` (`id`),
  CONSTRAINT `fk_order_items_order` FOREIGN KEY (`rental_order_id`) REFERENCES `rental_orders` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: inventory_movements
CREATE TABLE IF NOT EXISTS `inventory_movements` (
`id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `item_id` bigint unsigned NOT NULL,
  `movement_type` enum('OPENING','PURCHASE','ISSUE','RETURN','DAMAGE','LOSS','ADJUSTMENT') COLLATE utf8mb4_unicode_ci NOT NULL,
  `quantity` int NOT NULL,
  `reference_type` varchar(40) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `reference_id` bigint unsigned DEFAULT NULL,
  `movement_date` date NOT NULL,
  `notes` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_movements_item_date` (`item_id`,`movement_date`),
  CONSTRAINT `fk_movements_item` FOREIGN KEY (`item_id`) REFERENCES `items` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: invoice_lines
CREATE TABLE IF NOT EXISTS `invoice_lines` (
`id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `invoice_id` bigint unsigned NOT NULL,
  `description` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `quantity` decimal(12,2) NOT NULL DEFAULT '1.00',
  `rate` decimal(12,2) NOT NULL DEFAULT '0.00',
  `amount` decimal(14,2) NOT NULL DEFAULT '0.00',
  `rental_order_item_id` bigint unsigned DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_invoice_lines_invoice` (`invoice_id`),
  KEY `fk_invoice_lines_order_item` (`rental_order_item_id`),
  CONSTRAINT `fk_invoice_lines_invoice` FOREIGN KEY (`invoice_id`) REFERENCES `invoices` (`id`),
  CONSTRAINT `fk_invoice_lines_order_item` FOREIGN KEY (`rental_order_item_id`) REFERENCES `rental_order_items` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: ledger_entries
CREATE TABLE IF NOT EXISTS `ledger_entries` (
`id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `customer_id` bigint unsigned NOT NULL,
  `transaction_date` date NOT NULL,
  `reference_number` varchar(60) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `transaction_type` enum('OPENING_BALANCE','RENT','OTHER_CHARGE','RECEIPT','CREDIT_NOTE','ADJUSTMENT') COLLATE utf8mb4_unicode_ci NOT NULL,
  `particulars` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `debit` decimal(14,2) NOT NULL DEFAULT '0.00',
  `credit` decimal(14,2) NOT NULL DEFAULT '0.00',
  `source_type` varchar(40) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `source_id` bigint unsigned DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_ledger_customer_date` (`customer_id`,`transaction_date`,`id`),
  CONSTRAINT `fk_ledger_customer` FOREIGN KEY (`customer_id`) REFERENCES `customers` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: rental_charges
CREATE TABLE IF NOT EXISTS `rental_charges` (
`id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `rental_order_item_id` bigint unsigned NOT NULL,
  `period_start` date NOT NULL,
  `period_end` date NOT NULL,
  `charge_type` enum('MINIMUM_30_DAY','EXTRA_DAILY','ADJUSTMENT','OTHER') COLLATE utf8mb4_unicode_ci NOT NULL,
  `quantity` int unsigned NOT NULL,
  `rate` decimal(12,2) NOT NULL,
  `amount` decimal(14,2) NOT NULL,
  `calculation_notes` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `fk_charges_order_item` (`rental_order_item_id`),
  CONSTRAINT `fk_charges_order_item` FOREIGN KEY (`rental_order_item_id`) REFERENCES `rental_order_items` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: rental_returns
CREATE TABLE IF NOT EXISTS `rental_returns` (
`id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `return_number` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `rental_order_id` bigint unsigned NOT NULL,
  `return_date` date NOT NULL,
  `notes` text COLLATE utf8mb4_unicode_ci,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `return_number` (`return_number`),
  KEY `fk_returns_order` (`rental_order_id`),
  CONSTRAINT `fk_returns_order` FOREIGN KEY (`rental_order_id`) REFERENCES `rental_orders` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: rental_payments
CREATE TABLE IF NOT EXISTS `rental_payments` (
`id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `rental_order_id` bigint unsigned NOT NULL,
  `payment_date` date NOT NULL,
  `amount` decimal(14,2) NOT NULL,
  `payment_method` varchar(60) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `payment_type` enum('ADVANCE','RETURN_PAYMENT','OTHER') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'OTHER',
  `reference_number` varchar(60) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `notes` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_rental_payments_order_date` (`rental_order_id`,`payment_date`),
  CONSTRAINT `fk_rental_payments_order` FOREIGN KEY (`rental_order_id`) REFERENCES `rental_orders` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: rental_return_adjustments
CREATE TABLE IF NOT EXISTS `rental_return_adjustments` (
`id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `rental_return_id` bigint unsigned NOT NULL,
  `rental_order_id` bigint unsigned NOT NULL,
  `vehicle_rent_amount` decimal(14,2) NOT NULL DEFAULT '0.00',
  `vehicle_type` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `vehicle_number` varchar(40) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `discount_type` enum('PERCENT','FIXED') COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `discount_value` decimal(14,2) NOT NULL DEFAULT '0.00',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_return_adjustment_return` (`rental_return_id`),
  KEY `fk_return_adj_order` (`rental_order_id`),
  CONSTRAINT `fk_return_adj_order` FOREIGN KEY (`rental_order_id`) REFERENCES `rental_orders` (`id`),
  CONSTRAINT `fk_return_adj_return` FOREIGN KEY (`rental_return_id`) REFERENCES `rental_returns` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: rental_return_audit
CREATE TABLE IF NOT EXISTS `rental_return_audit` (
`id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `return_item_id` bigint unsigned NOT NULL,
  `rental_return_id` bigint unsigned NOT NULL,
  `action_type` enum('EDIT','DELETE') COLLATE utf8mb4_unicode_ci NOT NULL,
  `old_return_number` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `old_return_date` date NOT NULL,
  `old_rental_order_item_id` bigint unsigned NOT NULL,
  `old_quantity_returned` int unsigned NOT NULL,
  `old_item_condition` enum('GOOD','DAMAGED','MISSING') COLLATE utf8mb4_unicode_ci NOT NULL,
  `old_notes` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `reason` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL,
  `changed_by` varchar(120) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'system-user',
  `changed_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_return_audit_item` (`return_item_id`,`changed_at`),
  KEY `idx_return_audit_header` (`rental_return_id`,`changed_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: rental_return_items
CREATE TABLE IF NOT EXISTS `rental_return_items` (
`id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `rental_return_id` bigint unsigned NOT NULL,
  `rental_order_item_id` bigint unsigned NOT NULL,
  `quantity_returned` int unsigned NOT NULL,
  `item_condition` enum('GOOD','DAMAGED','MISSING') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'GOOD',
  `notes` varchar(500) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `fk_return_items_return` (`rental_return_id`),
  KEY `fk_return_items_order_item` (`rental_order_item_id`),
  CONSTRAINT `fk_return_items_order_item` FOREIGN KEY (`rental_order_item_id`) REFERENCES `rental_order_items` (`id`),
  CONSTRAINT `fk_return_items_return` FOREIGN KEY (`rental_return_id`) REFERENCES `rental_returns` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: user_login_audit
CREATE TABLE IF NOT EXISTS `user_login_audit` (
`id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `user_id` bigint unsigned DEFAULT NULL,
  `username` varchar(80) COLLATE utf8mb4_unicode_ci NOT NULL,
  `event_type` enum('LOGIN','LOGOUT','LOGIN_FAILED','PASSWORD_CHANGED') COLLATE utf8mb4_unicode_ci NOT NULL,
  `success` tinyint(1) NOT NULL DEFAULT '1',
  `ip_address` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `user_agent` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `detail` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_login_audit_user` (`user_id`,`created_at`),
  KEY `idx_login_audit_username` (`username`,`created_at`),
  CONSTRAINT `fk_login_audit_user` FOREIGN KEY (`user_id`) REFERENCES `app_users` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


