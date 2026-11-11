import { Loader2, MailPlus, Trash2, UserX } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useAuth } from "@/auth/AuthContext";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";
import type {
  InvitationCreatedOut,
  InvitationOut,
  MembershipOut,
  RestaurantOut,
  Role,
} from "@/lib/types";
import { formatDate } from "@/lib/utils";

const INVITABLE_ROLES: Role[] = ["manager", "cashier", "waiter", "kitchen", "inventory", "viewer"];
const MANAGER_INVITABLE: Role[] = ["cashier", "waiter", "kitchen", "inventory", "viewer"];

function statusVariant(status: string) {
  if (status === "active") return "success" as const;
  if (status === "suspended") return "warning" as const;
  if (status === "pending") return "secondary" as const;
  return "destructive" as const;
}

export function StaffPage() {
  const { me, hasPermission } = useAuth();
  const [members, setMembers] = useState<MembershipOut[]>([]);
  const [invitations, setInvitations] = useState<InvitationOut[]>([]);
  const [restaurants, setRestaurants] = useState<RestaurantOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("cashier");
  const [branch, setBranch] = useState("");
  const [inviting, setInviting] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);

  const canInvite = hasPermission("staff:invite");
  const canManage = hasPermission("staff:manage");
  const tenantWide = me?.context.tenant_wide ?? false;
  const allowedRoles = me?.context.role === "manager" ? MANAGER_INVITABLE : INVITABLE_ROLES;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [memberData, invitationData] = await Promise.all([
        api.get<MembershipOut[]>("/staff"),
        api.get<InvitationOut[]>("/staff/invitations"),
      ]);
      setMembers(memberData);
      setInvitations(invitationData);
      if (tenantWide) {
        setRestaurants(await api.get<RestaurantOut[]>("/restaurants"));
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load staff");
    } finally {
      setLoading(false);
    }
  }, [tenantWide]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onInvite(event: FormEvent) {
    event.preventDefault();
    setInviteError(null);
    setNotice(null);
    setInviting(true);
    try {
      const created = await api.post<InvitationCreatedOut>("/staff/invitations", {
        email: email.trim(),
        role,
        restaurant_id: branch || undefined,
      });
      const link = `${window.location.origin}/accept-invitation?token=${encodeURIComponent(
        created.invite_token,
      )}&email=${encodeURIComponent(created.email)}`;
      setNotice(
        `Invitation ready for ${created.email}. Share this single-use link: ${link}`,
      );
      setEmail("");
      await load();
    } catch (err) {
      setInviteError(err instanceof ApiError ? err.message : "Could not create the invitation");
    } finally {
      setInviting(false);
    }
  }

  async function updateStatus(member: MembershipOut) {
    setError(null);
    setNotice(null);
    try {
      await api.patch<MembershipOut>(`/staff/${member.id}`, {
        status: member.status === "suspended" ? "active" : "suspended",
      });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update the member");
    }
  }

  async function removeMember(member: MembershipOut) {
    if (!window.confirm(`Remove ${member.email} from this business?`)) return;
    setError(null);
    setNotice(null);
    try {
      await api.delete(`/staff/${member.id}`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not remove the member");
    }
  }

  async function revokeInvitation(invitation: InvitationOut) {
    setError(null);
    setNotice(null);
    try {
      await api.delete(`/staff/invitations/${invitation.id}`);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not revoke the invitation");
    }
  }

  if (loading) {
    return (
      <div className="flex items-center text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading team…
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Staff</h1>
        <p className="text-sm text-muted-foreground">
          Manage memberships and invitations for your {tenantWide ? "business" : "branch"}.
        </p>
      </div>

      {error && <Alert tone="error">{error}</Alert>}
      {notice && <Alert tone="success">{notice}</Alert>}

      {canInvite && (
        <Card>
          <CardHeader>
            <CardTitle>Invite a staff member</CardTitle>
            <CardDescription>
              Invitations are single-use, expire in 7 days, and are bound to the email address.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-3" onSubmit={onInvite}>
              {inviteError && <Alert tone="error">{inviteError}</Alert>}
              <div className="grid gap-3 sm:grid-cols-4">
                <div className="space-y-2 sm:col-span-2">
                  <Label htmlFor="inviteEmail">Email</Label>
                  <Input
                    id="inviteEmail"
                    type="email"
                    required
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="staff@example.com"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="inviteRole">Role</Label>
                  <Select
                    id="inviteRole"
                    value={role}
                    onChange={(event) => setRole(event.target.value as Role)}
                  >
                    {allowedRoles.map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="inviteBranch">Branch</Label>
                  <Select
                    id="inviteBranch"
                    value={branch}
                    disabled={!tenantWide}
                    onChange={(event) => setBranch(event.target.value)}
                  >
                    {tenantWide ? (
                      <>
                        <option value="">All branches (tenant-wide)</option>
                        {restaurants.map((restaurant) => (
                          <option key={restaurant.id} value={restaurant.id}>
                            {restaurant.name}
                          </option>
                        ))}
                      </>
                    ) : (
                      <option value="">{me?.context.restaurant_name ?? "Assigned branch"}</option>
                    )}
                  </Select>
                </div>
              </div>
              <Button type="submit" disabled={inviting}>
                {inviting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <MailPlus className="h-4 w-4" />
                )}
                Create invitation
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Team members</CardTitle>
          <CardDescription>{members.length} active or suspended membership(s).</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {members.length === 0 && (
            <p className="text-sm text-muted-foreground">No staff members yet.</p>
          )}
          {members.map((member) => (
            <div
              key={member.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3"
            >
              <div>
                <div className="font-medium">
                  {member.full_name}{" "}
                  {member.user_id === me?.user.id && (
                    <span className="text-xs text-muted-foreground">(you)</span>
                  )}
                </div>
                <div className="text-xs text-muted-foreground">
                  {member.email} · {member.restaurant_name ?? "All branches"}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="capitalize">
                  {member.role}
                </Badge>
                <Badge variant={statusVariant(member.status)} className="capitalize">
                  {member.status}
                </Badge>
                {canManage && member.user_id !== me?.user.id && member.role !== "owner" && (
                  <>
                    <Button variant="outline" size="sm" onClick={() => updateStatus(member)}>
                      <UserX className="h-3.5 w-3.5" />
                      {member.status === "suspended" ? "Reactivate" : "Suspend"}
                    </Button>
                    <Button variant="destructive" size="sm" onClick={() => removeMember(member)}>
                      <Trash2 className="h-3.5 w-3.5" />
                      Remove
                    </Button>
                  </>
                )}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Pending invitations</CardTitle>
          <CardDescription>Unused invitations that have not expired.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {invitations.length === 0 && (
            <p className="text-sm text-muted-foreground">No pending invitations.</p>
          )}
          {invitations.map((invitation) => (
            <div
              key={invitation.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3"
            >
              <div>
                <div className="font-medium">{invitation.email}</div>
                <div className="text-xs text-muted-foreground">
                  {invitation.role} · {invitation.restaurant_name ?? "All branches"} · expires{" "}
                  {formatDate(invitation.expires_at)}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant={statusVariant(invitation.status)} className="capitalize">
                  {invitation.status}
                </Badge>
                {canInvite && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => revokeInvitation(invitation)}
                  >
                    Revoke
                  </Button>
                )}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
