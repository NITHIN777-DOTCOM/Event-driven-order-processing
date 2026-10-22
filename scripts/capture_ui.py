"""Run every scenario through the DEPLOYED storefront with a real browser and save screenshots.

    python -m pip install playwright && python -m playwright install chromium   # one-time, dev only
    python scripts/capture_ui.py

A person's path, end to end: browse -> product page -> cart -> checkout (contact, delivery, test
scenario) -> payment (DemoPay "Pay ₹X") -> live tracker. Scenarios: normal, payment glitch,
payment declined, a REAL low-balance decline (the balance is set to ₹1,000 on the wallet page),
the duplicate test and poison. After each order, the DemoPay ledger is checked through the API.
Desktop (1440 px) and mobile (360 px) screenshots and docs/evidence/ui/README.md are written.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

from tf_outputs import load_outputs

OUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "ui"
TERMINAL_TITLES = re.compile(r"Order completed|Order failed|Stuck in the dead-letter queue")
NAME, EMAIL = "Asha Rao", "asha.rao@example.com"
DESKTOP = {"width": 1440, "height": 900}
MOBILE = {"width": 360, "height": 780}


class Run:
    def __init__(self, base: str, api: str) -> None:
        self.base, self.api = base, api
        self.results: list[dict] = []
        self.console_errors: list[str] = []

    # ---------------------------------------------------------------- helpers
    def api_json(self, method: str, path: str, body: dict | None = None) -> dict:
        request = urllib.request.Request(
            self.api + path,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=15) as resp:
            return json.loads(resp.read())

    def debits(self, order_id: str) -> int:
        txns = self.api_json("GET", f"/wallet?email={EMAIL}")["transactions"]
        return sum(1 for t in txns if t.get("orderId") == order_id and t["type"] == "DEBIT")

    def balance(self) -> float:
        return self.api_json("GET", f"/wallet?email={EMAIL}")["balance"]

    @staticmethod
    def shot(page: Page, name: str, full_page: bool = True) -> None:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(OUT_DIR / f"{name}.png"), full_page=full_page)
        print(f"  saved {name}.png")

    def add_from_listing(self, page: Page, product: str) -> None:
        page.goto(self.base + "/")
        page.get_by_role("button", name=f"Add {product} to cart").click()

    def checkout(self, page: Page, scenario: str, shot_prefix: str | None = None) -> str:
        """Checkout step 1 (details + scenario) -> step 2 (DemoPay) -> Pay. Returns the orderId."""
        page.goto(self.base + "/checkout")
        page.locator("#name").fill(NAME)
        page.locator("#email").fill(EMAIL)
        page.locator("#scenario").select_option(label=scenario)
        if shot_prefix:
            self.shot(page, f"{shot_prefix}-checkout-details")
        page.get_by_role("button", name="Continue to payment").click()
        pay = page.get_by_role("button", name=re.compile(r"^Pay ₹"))
        expect(pay).to_be_visible()
        expect(page.get_by_text(re.compile(r"^₹[\d,]+$")).first).to_be_visible()  # wallet balance loaded
        if shot_prefix:
            self.shot(page, f"{shot_prefix}-checkout-payment")
        pay.click()
        page.wait_for_url(re.compile(r"/orders/ORD-\d{8}-[0-9a-f]{8}$"), timeout=15_000)
        return page.url.rsplit("/", 1)[-1]

    @staticmethod
    def wait_terminal(page: Page, timeout_s: int = 90) -> str:
        title = page.get_by_role("heading", level=1)
        expect(title).to_have_text(TERMINAL_TITLES, timeout=timeout_s * 1000)
        page.wait_for_timeout(700)  # let the last feed row finish its fade-in
        return title.inner_text()

    def record(self, scenario: str, order_id: str, result: str, debits_expected: int) -> None:
        debits = self.debits(order_id)
        ok = debits == debits_expected
        self.results.append(
            {"scenario": scenario, "orderId": order_id, "result": result, "debits": debits, "ok": ok, "expected": debits_expected}
        )
        print(f"{scenario}: {order_id} -> {result}; DEBITs={debits} (expected {debits_expected}) {'OK' if ok else 'MISMATCH'}")

    # ---------------------------------------------------------------- scenarios
    def desktop(self, page: Page) -> None:
        base = self.base
        self.api_json("POST", "/wallet/reset", {"email": EMAIL})  # start from ₹10,00,000

        page.goto(base + "/")
        expect(page.get_by_role("button", name=re.compile(r"^Add .* to cart$"))).to_have_count(16)
        page.wait_for_load_state("networkidle")
        self.shot(page, "desktop-01-shop")

        # Poison first: it needs ~3 minutes of SQS retries before it reaches the DLQ.
        self.add_from_listing(page, "Slim Wireless Mouse")
        poison_id, poison_started = self.checkout(page, "Poison message (to DLQ)"), time.monotonic()
        page.wait_for_timeout(23_000)  # past 20 s, so the SQS-retrying hint row shows
        self.shot(page, "desktop-12-tracker-poison-retrying")

        # Browse: category, search, product page, cart page.
        page.goto(base + "/c/keyboards")
        expect(page.get_by_text(re.compile(r"1–3 of 3 results"))).to_be_visible()
        self.shot(page, "desktop-02-category-keyboards")
        page.locator("#search-query").fill("mic")
        page.get_by_role("button", name="Search", exact=True).click()
        expect(page.get_by_role("heading", level=1)).to_contain_text("Results for")
        self.shot(page, "desktop-03-search")
        page.goto(base + "/p/MECH-KEYBOARD")
        expect(page.get_by_role("button", name="Add to Cart")).to_be_visible()
        self.shot(page, "desktop-04-product")
        page.get_by_role("button", name="Add to Cart").click()
        expect(page.get_by_role("dialog")).to_be_visible()
        self.shot(page, "desktop-05-cart-drawer", full_page=False)
        page.get_by_role("button", name="Close").click()
        page.goto(base + "/cart")
        self.shot(page, "desktop-06-cart")

        # 1) Normal: balance drops by the total.
        before = self.balance()
        order_id = self.checkout(page, "Normal", shot_prefix="desktop-07")
        result = self.wait_terminal(page)
        self.shot(page, "desktop-08-tracker-completed")
        self.record("Normal", order_id, f"{result}; balance {before:,.0f} -> {self.balance():,.0f}", 1)

        # 2) Payment glitch: retried, debited once.
        self.add_from_listing(page, "Noise-Cancelling Wireless Headphones")
        order_id = self.checkout(page, "Payment glitch (retries)")
        self.record("Payment glitch (retries)", order_id, self.wait_terminal(page), 1)
        self.shot(page, "desktop-09-tracker-payment-glitch")

        # 3) Payment declined (simulated): nothing debited.
        self.add_from_listing(page, "USB-C Hub, 6-in-1")
        order_id = self.checkout(page, "Payment declined")
        self.record("Payment declined", order_id, self.wait_terminal(page), 0)
        self.shot(page, "desktop-10-tracker-payment-declined")

        # 4) REAL decline: set the wallet to ₹1,000 in the UI, then buy a ₹5,999 microphone.
        page.goto(base + "/wallet")
        page.locator("#custom-balance").fill("1000")
        page.get_by_role("button", name="Set", exact=True).click()
        expect(page.get_by_text("₹1,000", exact=True).first).to_be_visible()
        self.add_from_listing(page, "USB Condenser Microphone")
        page.goto(base + "/checkout")
        page.locator("#name").fill(NAME)
        page.locator("#email").fill(EMAIL)
        page.locator("#scenario").select_option(label="Normal")
        page.get_by_role("button", name="Continue to payment").click()
        expect(page.get_by_role("alert")).to_contain_text("Not enough balance")
        self.shot(page, "desktop-11-checkout-insufficient-balance")
        page.get_by_role("button", name=re.compile(r"^Pay ₹")).click()
        page.wait_for_url(re.compile(r"/orders/ORD-"), timeout=15_000)
        order_id = page.url.rsplit("/", 1)[-1]
        self.record("Low balance (real decline)", order_id, self.wait_terminal(page), 0)
        self.shot(page, "desktop-13-tracker-insufficient-balance")
        page.goto(base + "/wallet")
        page.get_by_role("button", name=re.compile(r"Reset demo balance")).click()
        expect(page.get_by_text("₹10,00,000", exact=True).first).to_be_visible()

        # 5) Duplicate test: 3 requests, 1 order, debited once.
        self.add_from_listing(page, "Slim Wireless Mouse")
        page.goto(base + "/checkout")
        page.locator("#name").fill(NAME)
        page.locator("#email").fill(EMAIL)
        page.get_by_role("button", name=re.compile(r"Send same order 3")).click()
        status = page.get_by_role("status").filter(has_text="requests")
        expect(status).to_contain_text("3 requests → 1 order", timeout=20_000)
        duplicate_id = re.search(r"ORD-\d{8}-[0-9a-f]{8}", status.inner_text()).group(0)
        self.shot(page, "desktop-14-checkout-duplicate-test")
        page.goto(f"{base}/orders/{duplicate_id}")
        self.record("Duplicate test (3 requests)", duplicate_id, f"{self.wait_terminal(page)} · 1 order", 1)
        page.goto(base + "/cart")
        page.get_by_role("button", name="Remove").click()  # leave the cart empty

        page.goto(base + "/wallet")
        expect(page.locator("tbody tr").first).to_be_visible()
        self.shot(page, "desktop-15-wallet")
        page.goto(base + "/orders")
        expect(page.locator("tbody tr").first).to_contain_text("ORD-")
        self.shot(page, "desktop-16-orders")

        # 6) Back to the poison order: wait until its third failed delivery dead-letters it.
        page.goto(f"{base}/orders/{poison_id}")
        remaining = max(30, 300 - int(time.monotonic() - poison_started))
        self.record("Poison message (to DLQ)", poison_id, self.wait_terminal(page, remaining), 0)
        self.shot(page, "desktop-17-tracker-poison-dead-lettered")

    def mobile(self, phone: Page) -> None:
        base = self.base
        phone.goto(base + "/")
        expect(phone.get_by_role("button", name=re.compile(r"^Add .* to cart$"))).to_have_count(16)
        phone.wait_for_load_state("networkidle")
        self.shot(phone, "mobile-01-shop", full_page=False)
        phone.goto(base + "/p/ERGO-MOUSE")
        self.shot(phone, "mobile-02-product")
        phone.get_by_role("button", name="Add to Cart").click()
        phone.get_by_role("button", name="Close").click()
        phone.goto(base + "/checkout")
        phone.locator("#name").fill(NAME)
        phone.locator("#email").fill(EMAIL)
        phone.get_by_role("button", name="Continue to payment").click()
        expect(phone.get_by_role("button", name=re.compile(r"^Pay ₹"))).to_be_visible()
        self.shot(phone, "mobile-03-checkout-payment")
        phone.goto(f"{base}/orders/{self.results[0]['orderId']}")
        self.wait_terminal(phone)
        self.shot(phone, "mobile-04-tracker-completed")
        phone.goto(base + "/wallet")
        expect(phone.locator("tbody tr").first).to_be_visible()
        self.shot(phone, "mobile-05-wallet")


def write_index(run: Run) -> None:
    lines = [
        "# Storefront UI evidence (Phase 4.1)",
        "",
        f"Every scenario was run through the deployed storefront ({run.base}) by `scripts/capture_ui.py`",
        "(Playwright + Chromium): browse -> product -> cart -> checkout -> DemoPay payment -> live tracker.",
        "After each order the DemoPay ledger was checked through `GET /wallet`.",
        "",
        "| Scenario | orderId | Tracker result | Wallet DEBITs (expected) |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {r['scenario']} | `{r['orderId']}` | {r['result']} | {r['debits']} ({r['expected']}) {'✓' if r['ok'] else '✗'} |"
        for r in run.results
    ]
    lines += ["", f"Browser console errors during the run: {len(run.console_errors)}", ""]
    lines += [f"- `{e[:200]}`" for e in run.console_errors]
    lines += ["## Screenshots", ""]
    lines += [f"### {p.stem}\n\n![{p.stem}]({p.name})\n" for p in sorted(OUT_DIR.glob("*.png"))]
    (OUT_DIR / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", help="storefront URL (default: terraform output frontend_url)")
    args = parser.parse_args()
    outputs = load_outputs()
    run = Run((args.url or outputs["frontend_url"]).rstrip("/"), outputs["api_url"].rstrip("/"))

    for old in OUT_DIR.glob("*.png"):  # screenshots always reflect the current UI
        old.unlink()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_context(viewport=DESKTOP).new_page()
        page.on("console", lambda msg: msg.type == "error" and run.console_errors.append(msg.text))
        run.desktop(page)
        phone = browser.new_context(viewport=MOBILE, device_scale_factor=2, is_mobile=True, has_touch=True).new_page()
        phone.on("console", lambda msg: msg.type == "error" and run.console_errors.append(msg.text))
        run.mobile(phone)
        browser.close()

    write_index(run)
    for r in run.results:
        print(f"{r['scenario']:<30} {r['orderId']}  {r['result']}  DEBITs={r['debits']} {'OK' if r['ok'] else 'MISMATCH'}")


if __name__ == "__main__":
    main()
