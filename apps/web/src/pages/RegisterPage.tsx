import { Loader2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api";

export function RegisterPage() {
  const { status, register } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const invitationToken = params.get("token") ?? undefined;
  const invitedEmail = params.get("email") ?? "";

  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState(invitedEmail);
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [businessName, setBusinessName] = useState("");
  const [restaurantName, setRestaurantName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  if (status === "authenticated") return <Navigate to="/" replace />;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setFieldErrors({});

    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }
    if (password.length < 10) {
      setError("Password must be at least 10 characters");
      return;
    }

    setSubmitting(true);
    try {
      await register({
        email: email.trim(),
        password,
        full_name: fullName.trim(),
        business_name: businessName.trim() || undefined,
        restaurant_name: restaurantName.trim() || undefined,
        invitation_token: invitationToken,
      });
      navigate("/", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        setFieldErrors(err.fieldErrors());
      } else {
        setError("Unable to create the account right now");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/40 p-6">
      <div className="w-full max-w-lg space-y-4">
        <div className="text-center">
          <h1 className="text-2xl font-semibold">
            {invitationToken ? "Join your team on RestroOS" : "Start your restaurant on RestroOS"}
          </h1>
          <p className="text-sm text-muted-foreground">
            {invitationToken
              ? "Create your account to accept the invitation."
              : "The first account becomes the owner of the business."}
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>{invitationToken ? "Create account" : "Create your business"}</CardTitle>
            <CardDescription>
              {invitationToken
                ? "Your role and branch are set by the invitation."
                : "You can add branches and invite staff after this."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={onSubmit}>
              {error && (
                <Alert tone="error">
                  {error}
                  {Object.keys(fieldErrors).length > 0 && (
                    <ul className="list-inside list-disc text-xs">
                      {Object.entries(fieldErrors).map(([field, message]) => (
                        <li key={field}>
                          {field}: {message}
                        </li>
                      ))}
                    </ul>
                  )}
                </Alert>
              )}

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="fullName">Your name</Label>
                  <Input
                    id="fullName"
                    required
                    minLength={2}
                    autoComplete="name"
                    value={fullName}
                    onChange={(event) => setFullName(event.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="email">Email</Label>
                  <Input
                    id="email"
                    type="email"
                    required
                    autoComplete="email"
                    value={email}
                    readOnly={Boolean(invitedEmail)}
                    onChange={(event) => setEmail(event.target.value)}
                  />
                </div>
              </div>

              {!invitationToken && (
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="businessName">Business name</Label>
                    <Input
                      id="businessName"
                      required
                      minLength={2}
                      placeholder="Spice Route Hospitality"
                      value={businessName}
                      onChange={(event) => setBusinessName(event.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="restaurantName">First branch (optional)</Label>
                    <Input
                      id="restaurantName"
                      placeholder="Indiranagar"
                      value={restaurantName}
                      onChange={(event) => setRestaurantName(event.target.value)}
                    />
                  </div>
                </div>
              )}

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="password">Password</Label>
                  <Input
                    id="password"
                    type="password"
                    required
                    minLength={10}
                    autoComplete="new-password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="confirmPassword">Confirm password</Label>
                  <Input
                    id="confirmPassword"
                    type="password"
                    required
                    minLength={10}
                    autoComplete="new-password"
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                  />
                </div>
              </div>

              <Button type="submit" className="w-full" disabled={submitting}>
                {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
                {invitationToken ? "Create account and join" : "Create business"}
              </Button>
            </form>

            <p className="mt-4 text-sm text-muted-foreground">
              Already registered?{" "}
              <Link className="text-primary underline-offset-4 hover:underline" to="/login">
                Sign in
              </Link>
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
