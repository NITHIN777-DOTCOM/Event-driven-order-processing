/**
 * Sign-in with Amazon Cognito managed login: OpenID Connect, authorization code flow + PKCE.
 *
 * Library: oidc-client-ts (protocol) + react-oidc-context (React hooks), not AWS Amplify. The app only
 * needs "redirect to the login page, swap the code for tokens, refresh them, sign out": a standard OIDC
 * client does exactly that against Cognito's standard endpoints (discovered from the issuer URL), adds
 * about 19 kB gzipped (measured: the app bundle went from 70.7 to 90.1 kB) instead of Amplify's
 * much larger one, and isn't tied to AWS.
 *
 * Flow:
 *   1. a protected page calls signIn() -> browser goes to the managed login page with a PKCE challenge
 *   2. Cognito redirects back to /auth/callback?code=...  -> the library swaps code + verifier for tokens
 *   3. tokens live in sessionStorage (the library default); the access/ID tokens last 60 min and are
 *      renewed in the background with the refresh token (rotated on every use, 7-day session)
 *
 * Token storage trade-off: sessionStorage is readable by any script on this origin, so an XSS bug could
 * steal the tokens. Mitigations here: no third-party scripts, React escapes all rendered data, 60-minute
 * tokens, refresh-token rotation, and sessionStorage (gone when the tab closes) rather than localStorage.
 * Not done yet: a Content-Security-Policy header. The stronger alternative is a backend-for-frontend that
 * keeps the tokens in an HttpOnly cookie, at the cost of a server component this serverless demo doesn't have.
 */
import { UserManager, WebStorageStateStore, type User } from "oidc-client-ts";
import { useEffect, type ReactNode } from "react";
import { AuthProvider as OidcProvider, useAuth } from "react-oidc-context";
import { useLocation, useNavigate } from "react-router-dom";

export interface AuthConfig {
  authority: string; // https://cognito-idp.<region>.amazonaws.com/<pool id> (the token issuer)
  userPoolId: string;
  clientId: string; // the public "spa" app client (no secret)
  domain: string; // managed login base URL, used for Cognito's logout endpoint
}

export const CALLBACK_PATH = "/auth/callback";
let manager: UserManager | null = null;
let logoutDomain = "";

/** Build the OIDC client from /config.json. Called once at startup, before anything renders. */
export function initAuth(config: AuthConfig): void {
  const origin = window.location.origin;
  logoutDomain = config.domain.replace(/\/$/, "");
  manager = new UserManager({
    authority: config.authority,
    client_id: config.clientId,
    redirect_uri: `${origin}${CALLBACK_PATH}`,
    post_logout_redirect_uri: `${origin}/`,
    response_type: "code", // + PKCE, which oidc-client-ts always adds for the code flow
    scope: "openid email profile",
    userStore: new WebStorageStateStore({ store: window.sessionStorage }),
    automaticSilentRenew: true, // uses the refresh token shortly before the access token expires
  });
}

/**
 * The ID token to send as "Authorization" on API calls, or undefined when signed out.
 * The API needs the user's id (sub) AND verified email; Cognito puts the email only in the ID token,
 * so that is the one sent (API Gateway's JWT authorizer accepts it: aud = this app client).
 */
export async function getIdToken(): Promise<string | undefined> {
  const user = await manager?.getUser();
  return user && !user.expired ? user.id_token : undefined;
}

/** Wraps the app: provides useAuth() and handles the redirect back from Cognito. */
export function AuthProvider({ children }: { children: ReactNode }) {
  if (!manager) throw new Error("initAuth() must run before <AuthProvider> renders");
  return (
    <OidcProvider
      userManager={manager}
      // Remove ?code=&state= from the address bar once the tokens are in; <AuthCallback> then navigates on.
      onSigninCallback={() => window.history.replaceState({}, document.title, window.location.pathname)}
    >
      {children}
    </OidcProvider>
  );
}

/** Where to come back to after signing in, carried through Cognito in the OIDC `state`. */
interface ReturnState {
  returnTo?: string;
}

export interface Session {
  isLoading: boolean;
  isSignedIn: boolean;
  user: User | null | undefined;
  email: string;
  name: string;
  signIn: (returnTo?: string) => Promise<void>;
  signOut: () => Promise<void>;
}

/** The signed-in user (or not) plus sign-in / sign-up / sign-out actions. */
export function useSession(): Session {
  const auth = useAuth();
  const here = () => window.location.pathname + window.location.search;
  const profile = auth.user?.profile;
  return {
    isLoading: auth.isLoading,
    isSignedIn: auth.isAuthenticated,
    user: auth.user,
    email: String(profile?.email ?? ""),
    name: String(profile?.name ?? ""),
    // The managed login page also has "Create an account" (self-sign-up + email code), same flow.
    signIn: (returnTo = here()) => auth.signinRedirect({ state: { returnTo } satisfies ReturnState }),
    signOut: async () => {
      // Revoke the refresh token at Cognito, forget the tokens locally, then end the managed login
      // session cookie. Cognito's logout endpoint is not the standard OIDC end_session one: it takes
      // client_id + logout_uri (which must be one of the app client's logout URLs).
      await auth.revokeTokens(["refresh_token"]).catch(() => undefined);
      await auth.removeUser();
      const params = new URLSearchParams({ client_id: manager!.settings.client_id, logout_uri: `${window.location.origin}/` });
      window.location.assign(`${logoutDomain}/logout?${params}`);
    },
  };
}

/** Pages that need an account (checkout, wallet, orders): send signed-out visitors to Cognito and back. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const session = useSession();
  const location = useLocation();
  const auth = useAuth();

  useEffect(() => {
    if (!session.isLoading && !session.isSignedIn && !auth.activeNavigator && !auth.error) {
      session.signIn(location.pathname + location.search);
    }
  }, [session.isLoading, session.isSignedIn, auth.activeNavigator, auth.error]); // eslint-disable-line react-hooks/exhaustive-deps

  if (auth.error) return <AuthErrorMessage message={auth.error.message} />;
  if (!session.isSignedIn) return <p className="py-10 text-muted">Redirecting to sign in…</p>;
  return <>{children}</>;
}

/** /auth/callback: the library has swapped the code for tokens; go back to where the user started. */
export function AuthCallback() {
  const auth = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    // A sign-up started from a bookmarked managed-login link (not from this app) comes back with a code but
    // without this app's PKCE state. The user now has a Cognito session cookie, so one normal sign-in
    // redirect bounces straight back with a valid code.
    if (auth.error && /state/i.test(auth.error.message) && !sessionStorage.getItem("order-saga.auth-retry")) {
      sessionStorage.setItem("order-saga.auth-retry", "1");
      void auth.signinRedirect({ state: { returnTo: "/" } satisfies ReturnState });
      return;
    }
    if (auth.isAuthenticated) {
      sessionStorage.removeItem("order-saga.auth-retry");
      const returnTo = (auth.user?.state as ReturnState | undefined)?.returnTo;
      // Only same-site paths: never redirect to another origin taken from the URL.
      navigate(returnTo && returnTo.startsWith("/") && !returnTo.startsWith("//") ? returnTo : "/", { replace: true });
    }
  }, [auth.isAuthenticated, auth.user, auth.error, navigate]); // eslint-disable-line react-hooks/exhaustive-deps

  if (auth.error) return <AuthErrorMessage message={auth.error.message} />;
  return <p className="py-10 text-muted">Signing you in…</p>;
}

function AuthErrorMessage({ message }: { message: string }) {
  const auth = useAuth();
  return (
    <div className="py-10">
      <h1 className="text-[28px] font-semibold">Sign-in didn't work</h1>
      <p className="mt-2 text-muted">{message}</p>
      <button type="button" className="btn-primary mt-6" onClick={() => auth.signinRedirect({ state: { returnTo: "/" } })}>
        Try again
      </button>
    </div>
  );
}
