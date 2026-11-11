export type Role =
  | "owner"
  | "manager"
  | "cashier"
  | "waiter"
  | "kitchen"
  | "inventory"
  | "viewer";

export type MembershipStatus = "invited" | "active" | "suspended" | "removed";

export interface ContextOut {
  tenant_id: string;
  tenant_name: string;
  tenant_slug: string;
  restaurant_id: string | null;
  restaurant_name: string | null;
  role: Role;
  tenant_wide: boolean;
  permissions: string[];
}

export interface ContextOption {
  membership_id: string;
  tenant_id: string;
  tenant_name: string;
  tenant_slug: string;
  restaurant_id: string | null;
  role: Role;
}

export interface UserOut {
  id: string;
  email: string;
  full_name: string;
  is_platform_admin: boolean;
}

export interface SessionOut {
  access_token: string;
  token_type: string;
  expires_in: number;
  context: ContextOut;
  available_contexts: ContextOption[];
}

export interface MeOut {
  user: UserOut;
  context: ContextOut;
  available_contexts: ContextOption[];
}

export interface TenantOut {
  id: string;
  name: string;
  slug: string;
  status: string;
  currency: string;
  timezone: string;
  created_at: string;
}

export interface RestaurantOut {
  id: string;
  name: string;
  slug: string;
  status: string;
  address_line1: string | null;
  address_line2: string | null;
  city: string | null;
  state: string | null;
  postal_code: string | null;
  country: string;
  timezone: string;
  currency: string;
  gstin: string | null;
  tax_inclusive: boolean;
  service_charge_bp: number;
  created_at: string;
}

export interface SubscriptionOut {
  plan_code: string;
  plan_name: string;
  status: string;
  price_cents: number;
  currency: string;
  limits: Record<string, number | string | boolean | null>;
  current_period_start: string;
  current_period_end: string | null;
}

export interface MembershipOut {
  id: string;
  tenant_id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: Role;
  status: MembershipStatus;
  restaurant_id: string | null;
  restaurant_name: string | null;
  created_at: string;
}

export interface InvitationOut {
  id: string;
  email: string;
  role: Role;
  restaurant_id: string | null;
  restaurant_name: string | null;
  status: "pending" | "expired";
  expires_at: string;
  created_at: string;
}

export interface InvitationCreatedOut {
  id: string;
  email: string;
  role: Role;
  restaurant_id: string | null;
  expires_at: string;
  invite_token: string;
}

export interface RegisterPayload {
  email: string;
  password: string;
  full_name: string;
  business_name?: string;
  restaurant_name?: string;
  timezone?: string;
  invitation_token?: string;
}

export interface SwitchTarget {
  membership_id?: string;
  restaurant_id?: string;
}
