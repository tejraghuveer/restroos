import { Loader2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "@/auth/AuthContext";
import { Alert } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api";

export function AcceptInvitationPage() {
  const { status, me, acceptInvitation } = useAuth();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get("token") ?? "";
  const invitedEmail = params.get("email") ?? "";
  const [error, setError] = useState<string | null>(null);
  const [accepting, setAccepting] = useState(false);

  const next = `/accept-invitation?${params.toString()}`;

  if (!token) {
    return (
      <div className="flex min-h-screen items-center justify-center p-6">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>Invitation link is incomplete</CardTitle>
            <CardDescription>Ask the business owner for a fresh invitation.</CardDescription>
          </CardHeader>
          <CardContent>
            <Link
              className={buttonVariants({ variant: "outline" })}
              to="/"
            >
              Go to dashboard
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center text-muted-foreground">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Checking your session…
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/40 p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Join the team</CardTitle>
          <CardDescription>
            {invitedEmail
              ? `This invitation was issued to ${invitedEmail}.`
              : "Accept the invitation to add this business to your account."}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {error && <Alert tone="error">{error}</Alert>}

          {status === "anonymous" ? (
            <>
              <Alert tone="info">
                Sign in or create an account with the invited email address first.
              </Alert>
              <div className="flex flex-col gap-2">
                <Link className={buttonVariants()} to={`/login?next=${encodeURIComponent(next)}`}>
                  Sign in
                </Link>
                <Link
                  className={buttonVariants({ variant: "outline" })}
                  to={`/register?token=${encodeURIComponent(token)}${
                    invitedEmail ? `&email=${encodeURIComponent(invitedEmail)}` : ""
                  }`}
                >
                  Create account
                </Link>
              </div>
            </>
          ) : (
            <>
              {invitedEmail && me && invitedEmail.toLowerCase() !== me.user.email && (
                <Alert tone="error">
                  You are signed in as {me.user.email}, but this invitation is for{" "}
                  {invitedEmail}.
                </Alert>
              )}
              <Button
                className="w-full"
                disabled={
                  accepting ||
                  Boolean(invitedEmail && me && invitedEmail.toLowerCase() !== me.user.email)
                }
                onClick={async () => {
                  setError(null);
                  setAccepting(true);
                  try {
                    await acceptInvitation(token);
                    navigate("/", { replace: true });
                  } catch (err) {
                    setError(
                      err instanceof ApiError ? err.message : "Could not accept the invitation",
                    );
                  } finally {
                    setAccepting(false);
                  }
                }}
              >
                {accepting && <Loader2 className="h-4 w-4 animate-spin" />}
                Accept invitation
              </Button>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
