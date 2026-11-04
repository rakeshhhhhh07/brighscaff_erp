export type NavKey =
  | 'Dashboard'
  | 'Customers'
  | 'Inventory'
  | 'Rentals'
  | 'Billing & Ledgers'
  | 'Reports'
  | 'Settings';
export type Customer = {
  id?: number;
  customer_code: string;
  customer_name: string;
  contact_person?: string;
  phone?: string;
  email?: string;
  billing_address?: string;
  site_address?: string;
  tax_number?: string;
  company?: string;
  main_mobile?: string;
  mobile_2?: string;
  mobile_3?: string;
  office_address?: string;
  office_email?: string;
  residential_address?: string;
  gst_number?: string;
  guarantor_relationship?: string;
  guarantor_name?: string;
  guarantor_contact?: string;
  guarantor_address?: string;
  is_active?: boolean;
  opening_balance?: number;
};
export type Item = {
  id?: number;
  item_code: string;
  item_name: string;
  category?: string;
  unit: string;
  total_stock: number;
  initial_daily_rate: number;
  post_30_day_daily_rate: number;
  has_monthly_minimum: boolean;
  is_active?: boolean;
};
export type Summary = {
  customers: number;
  active_customers: number;
  catalogue_items: number;
  total_stock: number;
  active_rentals: number;
  items_on_rent: number;
  rent_accrued: number;
  outstanding_amount: number;
  customers_owing?: number;
};

/** Live outstanding position for one customer, from /ledgers/balances. */
export type CustomerBalance = {
  customer_id: number;
  customer_code: string;
  customer_name: string;
  opening_balance: number;
  charged_rent: number;
  vehicle_rent: number;
  payments: number;
  balance: number;
  open_orders: number;
  last_activity?: string | null;
};
