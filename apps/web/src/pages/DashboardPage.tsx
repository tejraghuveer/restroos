import { Loader2, Plus } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useAuth } from "@/auth/AuthContext";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";
import type { RestaurantOut, SubscriptionOut, TenantOut } from "@/lib/types";
import { formatDate } from "@/lib/utils";

export function DashboardPage() {
  const { me, hasPermission } = useAuth();
  const [tenant, setTenant] = useState<TenantOut | null>(null);
  const [subscription, setSubscription] = useState<SubscriptionOut | null>(null);
  const [restaurants, setRestaurants] = useState<RestaurantOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [city, setCity] = useState("");
  const [gstin, setGstin] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const canManageBranches = hasPermission("branch:manage") && me?.context.tenant_wide;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [tenantData, subscriptionData, restaurantData] = await Promise.all([
        api.get<TenantOut>("/tenant"),
        api.get<SubscriptionOut>("/billing/subscription"),
        api.get<RestaurantOut[]>("/restaurants"),
      ]);
      setTenant(tenantData);
      setSubscription(subscriptionData);
      setRestaurants(restaurantData);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load the dashboard");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function onCreateBranch(event: FormEvent) {
    event.preventDefault();
    setCreateError(null);
    setCreating(true);
    try {
      await api.post<RestaurantOut>("/restaurants", {
        name: name.trim(),
        city: city.trim() || undefined,
        gstin: gstin.trim() || undefined,
      });
      setName("");
      setCity("");
      setGstin("");
      await load();
    } catch (err) {
      setCreateError(err instanceof ApiError ? err.message : "Could not create the branch");
    } finally {
      setCreating(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading workspace…
      </div>
    );
  }

  if (error) return <Alert tone="error">{error}</Alert>;

  const maxRestaurants = subscription?.limits.max_restaurants;
  const maxStaff = subscription?.limits.max_staff;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          Signed in as {me?.user.email} · {me?.context.role}
          {me?.context.restaurant_name ? ` at ${me.context.restaurant_name}` : ""}
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardDescription>Business</CardDescription>
            <CardTitle>{tenant?.name}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Slug</span>
              <span>{tenant?.slug}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Status</span>
              <Badge variant="success" className="capitalize">
                {tenant?.status}
              </Badge>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Currency</span>
              <span>{tenant?.currency}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Timezone</span>
              <span>{tenant?.timezone}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardDescription>Plan</CardDescription>
            <CardTitle>{subscription?.plan_name}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Status</span>
              <Badge variant="secondary" className="capitalize">
                {subscription?.status}
              </Badge>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Branches used</span>
              <span>
                {restaurants.length} / {String(maxRestaurants ?? "∞")}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Staff limit</span>
              <span>{String(maxStaff ?? "∞")}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Since</span>
              <span>{formatDate(subscription?.current_period_start)}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardDescription>Your access</CardDescription>
            <CardTitle className="capitalize">{me?.context.role}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Scope</span>
              <span>{me?.context.tenant_wide ? "All branches" : "Single branch"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Permissions</span>
              <span>{me?.context.permissions.length}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Businesses</span>
              <span>{me?.available_contexts.length}</span>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Branches</CardTitle>
          <CardDescription>Each branch has its own staff assignments and operations.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="divide-y rounded-md border">
            {restaurants.map((restaurant) => (
              <div
                key={restaurant.id}
                className="flex flex-wrap items-center justify-between gap-2 p-3"
              >
                <div>
                  <div className="font-medium">{restaurant.name}</div>
                  <div className="text-xs text-muted-foreground">
                    {[restaurant.city, restaurant.state].filter(Boolean).join(", ") ||
                      "No address yet"}
                    {restaurant.gstin ? ` · GSTIN ${restaurant.gstin}` : ""}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {restaurant.id === me?.context.restaurant_id && (
                    <Badge variant="outline">Current</Badge>
                  )}
                  <Badge
                    variant={restaurant.status === "active" ? "success" : "destructive"}
                    className="capitalize"
                  >
                    {restaurant.status}
                  </Badge>
                </div>
              </div>
            ))}
          </div>

          {canManageBranches && (
            <form className="space-y-3 rounded-md border bg-muted/30 p-4" onSubmit={onCreateBranch}>
              <div className="text-sm font-medium">Add a branch</div>
              {createError && <Alert tone="error">{createError}</Alert>}
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="space-y-2">
                  <Label htmlFor="branchName">Branch name</Label>
                  <Input
                    id="branchName"
                    required
                    minLength={2}
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    placeholder="Koramangala"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="branchCity">City</Label>
                  <Input
                    id="branchCity"
                    value={city}
                    onChange={(event) => setCity(event.target.value)}
                    placeholder="Bengaluru"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="branchGstin">GSTIN (optional)</Label>
                  <Input
                    id="branchGstin"
                    value={gstin}
                    minLength={15}
                    maxLength={15}
                    onChange={(event) => setGstin(event.target.value.toUpperCase())}
                    placeholder="29ABCDE1234F1Z5"
                  />
                </div>
              </div>
              <Button type="submit" disabled={creating}>
                {creating ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Plus className="h-4 w-4" />
                )}
                Create branch
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
