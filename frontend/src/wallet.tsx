/**
 * The signed-in shopper's DemoPay wallet, plus their delivery details (name + address, remembered in
 * localStorage). Identity comes from Cognito, never from a form: the wallet belongs to whoever is signed in.
 * The header shows the balance; checkout, the tracker and the wallet page call refresh() after a payment.
 */
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { getWallet } from "./api";
import { useSession } from "./auth";
import { storage } from "./format";
import type { Wallet } from "./types";

/** Delivery details only. The email is the account's (verified by Cognito), so it isn't stored here. */
export interface Contact {
  name: string;
  address: string;
}

const CONTACT_KEY = "order-saga.contact";
const REFRESH_MS = 15_000;

function loadContact(): Contact {
  try {
    const saved = JSON.parse(storage.get(CONTACT_KEY) ?? "{}");
    return { name: String(saved.name ?? ""), address: String(saved.address ?? "") };
  } catch {
    return { name: "", address: "" };
  }
}

interface WalletState {
  contact: Contact;
  saveContact: (contact: Contact) => void;
  wallet: Wallet | null;
  refresh: () => Promise<void>;
  setWallet: (wallet: Wallet) => void;
}

const WalletContext = createContext<WalletState | null>(null);

export function WalletProvider({ children }: { children: ReactNode }) {
  const session = useSession();
  const [contact, setContact] = useState<Contact>(loadContact);
  const [wallet, setWallet] = useState<Wallet | null>(null);
  // Re-fetch when the signed-in user changes (sign-in, sign-out, another account).
  const userId = session.isSignedIn ? String(session.user?.profile.sub ?? "") : "";

  const refresh = useCallback(async () => {
    if (!userId) {
      setWallet(null);
      return;
    }
    try {
      setWallet(await getWallet());
    } catch {
      /* keep the last known balance; the wallet page shows errors explicitly */
    }
  }, [userId]);

  useEffect(() => {
    refresh();
    const id = window.setInterval(refresh, REFRESH_MS);
    return () => window.clearInterval(id);
  }, [refresh]);

  const saveContact = useCallback((next: Contact) => {
    storage.set(CONTACT_KEY, JSON.stringify(next));
    setContact(next);
  }, []);

  return <WalletContext.Provider value={{ contact, saveContact, wallet, refresh, setWallet }}>{children}</WalletContext.Provider>;
}

export function useWallet(): WalletState {
  const value = useContext(WalletContext);
  if (!value) throw new Error("useWallet must be used inside <WalletProvider>");
  return value;
}
