"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Crown, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ApiError, checkPremiumPassword } from "@/lib/api";
import { cn } from "@/lib/utils";

// Premium mode (user request, 2026-10-25): one password unlocks every
// premium feature for the rest of the browser session. The password is
// checked server-side by every premium endpoint (never shipped in the
// bundle) -- this only remembers it, after the server has accepted it, so
// each feature can send it along.
const PASSWORD_KEY = "premium-password";
// Where the Roster Optimizer kept it before premium mode existed.
const LEGACY_PASSWORD_KEY = "roster-optimizer-password";

// Shown in the unlocked dialog -- add new premium features here.
export const PREMIUM_FEATURES = [
  "Roster optimizer: the best free-agent swaps for your team",
  "Win probability by category for manual roster swaps",
  "Trade Hub: each team's win probability before and after a trade",
  "Trade Hub: recommend a trade for your team",
];

function readStored(): string | null {
  try {
    const pw = sessionStorage.getItem(PASSWORD_KEY) ?? sessionStorage.getItem(LEGACY_PASSWORD_KEY);
    return pw || null;
  } catch {
    return null;
  }
}

function store(password: string | null) {
  try {
    sessionStorage.removeItem(LEGACY_PASSWORD_KEY);
    if (password) sessionStorage.setItem(PASSWORD_KEY, password);
    else sessionStorage.removeItem(PASSWORD_KEY);
  } catch {}
}

interface PremiumState {
  unlocked: boolean;
  // The accepted password, for premium API calls; null while locked.
  password: string | null;
  // Opens the premium dialog. If locked, `onUnlocked` runs right after a
  // successful login (e.g. continue into the feature that was clicked); if
  // already unlocked it runs immediately and no dialog opens.
  requireUnlock: (onUnlocked?: () => void) => void;
  // Opens the dialog in whatever state premium is in (nav button).
  openDialog: () => void;
  // Ends premium for this session -- also what features call when the
  // server rejects the stored password (it was changed).
  lock: () => void;
}

const PremiumContext = createContext<PremiumState | null>(null);

export function PremiumProvider({ children }: { children: ReactNode }) {
  const [password, setPassword] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const pending = useRef<(() => void) | null>(null);

  // sessionStorage isn't available during server render -- read it after
  // mount so server and first client render match (premium shows locked
  // for that first frame).
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPassword(readStored());
  }, []);

  const requireUnlock = useCallback(
    (onUnlocked?: () => void) => {
      if (password) {
        onUnlocked?.();
        return;
      }
      pending.current = onUnlocked ?? null;
      setOpen(true);
    },
    [password],
  );

  const openDialog = useCallback(() => {
    pending.current = null;
    setOpen(true);
  }, []);

  const lock = useCallback(() => {
    store(null);
    setPassword(null);
  }, []);

  function onUnlocked(pw: string) {
    store(pw);
    setPassword(pw);
    setOpen(false);
    const next = pending.current;
    pending.current = null;
    // After the dialog's close has rendered, so a feature dialog opened by
    // `next` doesn't fight this one for focus.
    if (next) setTimeout(next, 0);
  }

  return (
    <PremiumContext.Provider value={{ unlocked: password != null, password, requireUnlock, openDialog, lock }}>
      {children}
      <Dialog
        open={open}
        onOpenChange={(o) => {
          setOpen(o);
          if (!o) pending.current = null;
        }}
      >
        <DialogContent className="sm:max-w-md">
          {open && (password ? <UnlockedPanel onLock={() => { lock(); setOpen(false); }} /> : <LoginPanel onUnlocked={onUnlocked} />)}
        </DialogContent>
      </Dialog>
    </PremiumContext.Provider>
  );
}

export function usePremium(): PremiumState {
  const ctx = useContext(PremiumContext);
  if (!ctx) throw new Error("usePremium must be used within PremiumProvider");
  return ctx;
}

function PremiumTitle({ children }: { children: ReactNode }) {
  return (
    <DialogTitle className="flex items-center gap-2 font-display text-2xl font-bold text-gold [font-variation-settings:'opsz'_36]">
      <Crown className="size-5" aria-hidden />
      {children}
    </DialogTitle>
  );
}

function LoginPanel({ onUnlocked }: { onUnlocked: (password: string) => void }) {
  const [value, setValue] = useState("");
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!value) return;
    setChecking(true);
    setError(null);
    try {
      await checkPremiumPassword(value);
      onUnlocked(value);
    } catch (err) {
      setValue("");
      if (err instanceof ApiError && err.status === 401) setError("That password didn't work.");
      else if (err instanceof ApiError && err.status === 503) setError("Premium mode isn't set up on the server.");
      else setError("Couldn't reach the server. Try again in a moment.");
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <DialogHeader>
        <PremiumTitle>Premium mode</PremiumTitle>
        <DialogDescription>Enter the premium password to unlock every premium feature for this session.</DialogDescription>
      </DialogHeader>
      <FeatureList />
      <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1.5">
          <span className="label">Password</span>
          <span className="relative">
            <Lock className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <input
              type="password"
              value={value}
              onChange={(e) => {
                setValue(e.target.value);
                setError(null);
              }}
              autoFocus
              autoComplete="current-password"
              className="h-8 w-52 rounded-md border border-input bg-background pr-3 pl-8 text-sm outline-none focus-visible:border-ring"
            />
          </span>
        </label>
        <Button type="submit" size="sm" disabled={checking || !value}>
          {checking ? "Checking…" : "Unlock premium"}
        </Button>
      </form>
      {error && <p className="text-sm text-loss">{error}</p>}
    </div>
  );
}

function UnlockedPanel({ onLock }: { onLock: () => void }) {
  return (
    <div className="flex flex-col gap-4">
      <DialogHeader>
        <PremiumTitle>Premium is on</PremiumTitle>
        <DialogDescription>Every premium feature is unlocked until you close this browser tab.</DialogDescription>
      </DialogHeader>
      <FeatureList />
      <div>
        <Button type="button" variant="outline" size="sm" onClick={onLock}>
          Lock premium
        </Button>
      </div>
    </div>
  );
}

function FeatureList() {
  return (
    <ul className="flex flex-col gap-1.5 text-sm">
      {PREMIUM_FEATURES.map((f) => (
        <li key={f} className="flex items-start gap-2">
          <Crown className="mt-0.5 size-3.5 shrink-0 text-gold" aria-hidden />
          {f}
        </li>
      ))}
    </ul>
  );
}

/**
 * The nav's Premium entry: gold text, a crown that fills in once premium is
 * unlocked. `variant` matches the surrounding nav (desktop folder tabs vs
 * the mobile drawer's rows).
 */
export function PremiumNavButton({ variant, onClick }: { variant: "tab" | "drawer"; onClick?: () => void }) {
  const { unlocked, openDialog } = usePremium();
  return (
    <button
      type="button"
      onClick={() => {
        onClick?.();
        openDialog();
      }}
      aria-label={unlocked ? "Premium mode (on)" : "Premium mode"}
      className={cn(
        "flex items-center gap-1.5 font-semibold text-gold transition-colors hover:bg-gold/10",
        variant === "tab"
          ? "shrink-0 rounded-t-md px-4 py-2.5 text-sm"
          : "w-full rounded-md px-3 py-2.5 text-base",
      )}
    >
      <Crown className={cn(variant === "tab" ? "size-3.5" : "size-4", unlocked && "fill-current")} aria-hidden />
      Premium
    </button>
  );
}
