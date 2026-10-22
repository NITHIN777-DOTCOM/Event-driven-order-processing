/**
 * The shopper's identity (contact details remembered in localStorage) and their DemoPay wallet.
 * The header shows the balance; checkout, the tracker and the wallet page call refresh() after a payment.
 */
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { getWallet } from "./api";
import { storage } from "./format";
import type { Wallet } from "./types";

export interface Contact {
  name: string;
  email: string;
  address: string;
}

const CONTACT_KEY = "order-saga.contact";
export const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const REFRESH_MS = 15_000;

function loadContact(): Contact {
  try {
    const saved = JSON.parse(storage.get(CONTACT_KEY) ?? "{}");
    return { name: String(saved.name ?? ""), email: String(saved.email ?? ""), address: String(saved.address ?? "") };
  } catch {
    return { name: "", email: "", address: "" };
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
  const [contact, setContact] = useState<Contact>(loadContact);
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const email = contact.email.trim();

  const refresh = useCallback(async () => {
    if (!EMAIL_PATTERN.test(email)) {
      setWallet(null);
      return;
    }
    try {
      setWallet(await getWallet(email));
    } catch {
      /* keep the last known balance; the wallet page shows errors explicitly */
    }
  }, [email]);

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
