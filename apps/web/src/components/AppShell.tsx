import { Building2, ChefHat, LogOut } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/input";
import { Alert } from "@/components/ui/alert";
import { api, ApiError } from "@/lib/api";
import type { RestaurantOut } from "@/lib/types";
import { cn } from "@/lib/utils";

function navClass({ isActive }: { isActive: boolean }) {
  return cn(
    "rounded-md px-3 py-2 text-sm font-medium transition-colors",
    isActive
      ? "bg-secondary text-secondary-foreground"
      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
  );
}

export function AppShell() {
  const { me, logout, switchContext, hasPermission } = useAuth();
  const [restaurants, setRestaurants] = useState<RestaurantOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [switching, setSwitching] = useState(false);
  const navigate = useNavigate();

  const context = me?.context;
  const canReadBranches = hasPermission("branch:read");

  const loadBranches = useCallback(async () => {
    if (!canReadBranches) {
      setRestaurants([]);
      return;
    }
    try {
      setRestaurants(await api.get<RestaurantOut[]>("/restaurants"));
    } catch {
      setRestaurants([]);
    }
  }, [canReadBranches]);

  useEffect(() => {
    void loadBranches();
  }, [loadBranches, context?.tenant_id, context?.restaurant_id]);

  if (!me || !context) return null;

  const activeMembership = me.available_contexts.find(
    (option) =>
      option.tenant_id === context.tenant_id &&
      option.role === context.role &&
      option.restaurant_id === context.restaurant_id,
  );

  async function onSwitch(target: { membership_id?: string; restaurant_id?: string }) {
    setSwitching(true);
    setError(null);
    try {
      await switchContext(target);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not switch context");
    } finally {
      setSwitching(false);
    }
  }

  async function onLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b bg-card">
        <div className="container flex h-16 items-center gap-4">
          <Link to="/" className="flex items-center gap-2 font-semibold">
            <ChefHat className="h-6 w-6 text-primary" />
            <span>RestroOS</span>
          </Link>

          <nav className="ml-4 hidden items-center gap-1 md:flex">
            <NavLink to="/" end className={navClass}>
              Dashboard
            </NavLink>
            {hasPermission("staff:read") && (
              <NavLink to="/staff" className={navClass}>
                Staff
              </NavLink>
            )}
          </nav>

          <div className="ml-auto flex flex-wrap items-center justify-end gap-2">
            <div className="hidden text-right sm:block">
              <div className="text-sm font-medium">{me.user.full_name}</div>
              <div className="text-xs text-muted-foreground">{me.user.email}</div>
            </div>
            <Badge variant="secondary" className="capitalize">
              {context.role}
            </Badge>
            <Button variant="ghost" size="sm" onClick={onLogout} title="Log out">
              <LogOut className="h-4 w-4" />
              <span className="sr-only">Log out</span>
            </Button>
          </div>
        </div>
      </header>

      <div className="border-b bg-muted/40">
        <div className="container flex flex-wrap items-center gap-3 py-3">
          <div className="flex items-center gap-2 text-sm">
            <Building2 className="h-4 w-4 text-muted-foreground" />
            <span className="font-medium">{context.tenant_name}</span>
            <span className="text-muted-foreground">({context.tenant_slug})</span>
          </div>

          {me.available_contexts.length > 1 && activeMembership && (
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              Business
              <Select
                className="h-8 w-auto"
                value={activeMembership.membership_id}
                disabled={switching}
                onChange={(event) => onSwitch({ membership_id: event.target.value })}
                aria-label="Switch business"
              >
                {me.available_contexts.map((option) => (
                  <option key={option.membership_id} value={option.membership_id}>
                    {option.tenant_name} · {option.role}
                    {option.restaurant_id ? " · branch" : ""}
                  </option>
                ))}
              </Select>
            </label>
          )}

          {restaurants.length > 1 && (
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              Branch
              <Select
                className="h-8 w-auto"
                value={context.restaurant_id ?? ""}
                disabled={switching || !context.tenant_wide}
                onChange={(event) => onSwitch({ restaurant_id: event.target.value })}
                aria-label="Switch branch"
              >
                {restaurants.map((restaurant) => (
                  <option key={restaurant.id} value={restaurant.id}>
                    {restaurant.name}
                  </option>
                ))}
              </Select>
            </label>
          )}

          {!context.tenant_wide && (
            <Badge variant="outline">
              Branch scoped: {context.restaurant_name ?? "assigned branch"}
            </Badge>
          )}
        </div>
        {error && (
          <div className="container pb-3">
            <Alert tone="error">{error}</Alert>
          </div>
        )}
      </div>

      <main className="container py-8">
        <Outlet />
      </main>
    </div>
  );
}
