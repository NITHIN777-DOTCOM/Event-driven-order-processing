"""Run every scenario through the DEPLOYED storefront with a real browser and save screenshots.

    python -m pip install playwright && python -m playwright install chromium   # one-time, dev only
    python scripts/capture_ui.py

A person's path, end to end: browse -> sign in (Cognito managed login, as test user A) -> product
page -> cart -> checkout (name, delivery, test scenario) -> payment (DemoPay "Pay ₹X") -> live tracker. Scenarios: normal, payment glitch,
payment declined, a REAL low-balance decline (the balance is set to ₹1,000 on the wallet page),
the duplicate test, poison, and a late payment (DemoPay confirms after the 120 s timeout: the tracker shows
"Awaiting payment confirmation", then the failure and the automatic refund). After each order, the DemoPay ledger is checked through the API.
Checkout holds (step 2.2): every checkout must show the 10-minute countdown, the normal order must consume its hold,
and a separate browser context with Playwright's fake clock jumps past the 10 minutes to capture "Your hold expired".
Per-item fulfillment (step 2.3): a 2-item order whose last item is found damaged after payment must end "Order
partially fulfilled" with that item "Cancelled — refunded ₹X", and the wallet must show exactly one partial CREDIT.
Cancellation (step 2.4): a "Slow warehouse" order is cancelled from the tracker once it is paid (Cancel -> confirm ->
"Order cancelled", "Cancelled — refunded ₹X"), and the wallet must show exactly one CREDIT of the total, "order cancelled".
Desktop (1440 px) and mobile (360 px) screenshots and docs/evidence/ui/README.md are written.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

from auth_tokens import auth_header, credentials
from tf_outputs import load_outputs

OUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "ui"
TERMINAL_TITLES = re.compile(r"Order completed|Order partially fulfilled|Order failed|Order cancelled|Stuck in the dead-letter queue")
NAME = "Asha Rao"
USER = "a"  # Cognito test user (create_test_users.py); the wallet and orders are this account's
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
            headers={"Content-Type": "application/json", **auth_header(USER)},
        )
        with urllib.request.urlopen(request, timeout=15) as resp:
            return json.loads(resp.read())

    def debits(self, order_id: str) -> int:
        txns = self.api_json("GET", "/wallet")["transactions"]
        return sum(1 for t in txns if t.get("orderId") == order_id and t["type"] == "DEBIT")

    def credits(self, order_id: str) -> list[dict]:
        txns = self.api_json("GET", "/wallet")["transactions"]
        return [t for t in txns if t.get("orderId") == order_id and t["type"] == "CREDIT"]

    def balance(self) -> float:
        return self.api_json("GET", "/wallet")["balance"]

    def sign_in(self, page: Page, shot_name: str | None = None) -> None:
        """Header "Sign in" -> Cognito managed login -> back on the storefront, signed in.
        The password is typed into the page only; it is never printed or saved in a screenshot."""
        page.goto(self.base + "/")
        page.get_by_role("button", name=re.compile(r"Sign in")).click()
        page.wait_for_url(re.compile(r"amazoncognito\.com"), timeout=20_000)
        creds = credentials(USER)
        username = page.locator('input[name="username"]:visible, input[type="email"]:visible').first
        expect(username).to_be_visible(timeout=15_000)
        if shot_name:
            self.shot(page, shot_name, full_page=False)  # empty form: no credentials in the image
        username.fill(creds["email"])
        password = page.locator('input[type="password"]:visible').first
        if not password.is_visible():  # two-step page: email first, then "Next"
            page.get_by_role("button", name=re.compile(r"^(Next|Continue)$")).click()
        expect(password).to_be_visible(timeout=15_000)
        password.fill(creds["password"])
        del creds
        page.get_by_role("button", name=re.compile(r"^(Sign in|Continue|Next)$")).click()
        page.wait_for_url(re.compile("^" + re.escape(self.base)), timeout=20_000)
        expect(page.get_by_role("button", name=re.compile(r"Sign out"))).to_be_visible(timeout=20_000)

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
        expect(page.get_by_test_id("hold-countdown")).to_have_text(re.compile(r"^(10:00|9:[0-5]\d)$"))  # cart held for 10 min
        page.locator("#name").fill(NAME)
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
        self.api_json("POST", "/wallet/reset", {})  # start from ₹10,00,000

        # Signed out, the shop still works; the header offers "Sign in".
        page.goto(base + "/")
        expect(page.get_by_role("button", name=re.compile(r"Sign in"))).to_be_visible()
        self.sign_in(page, shot_name="desktop-00-managed-login")
        page.goto(base + "/")
        expect(page.get_by_role("button", name=re.compile(r"^Add .* to cart$"))).to_have_count(16)
        page.wait_for_load_state("networkidle")
        self.shot(page, "desktop-01-shop")

        # Poison first: it needs ~3 minutes of SQS retries before it reaches the DLQ.
        self.add_from_listing(page, "Slim Wireless Mouse")
        poison_id, poison_started = self.checkout(page, "Poison message (to DLQ)"), time.monotonic()
        page.wait_for_timeout(23_000)  # past 20 s, so the SQS-retrying hint row shows
        self.shot(page, "desktop-12-tracker-poison-retrying")

        # Late payment (step 2.1), also placed early: the saga waits for DemoPay's webhook, times out at 120 s,
        # and the payment that arrives at ~150 s is refunded automatically. Net charge 0.
        self.add_from_listing(page, "Dynamic Podcast Microphone")
        late_id = self.checkout(page, "Late payment (auto-refund)")
        expect(page.get_by_text("Awaiting payment confirmation").first).to_be_visible(timeout=20_000)
        self.shot(page, "desktop-07a-tracker-awaiting-payment")

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
        reserved = next(h["detail"] for h in self.api_json("GET", f"/orders/{order_id}")["statusHistory"] if h["status"] == "RESERVED")
        consumed = "from checkout hold" in reserved
        self.record("Normal", order_id, f"{result}; balance {before:,.0f} -> {self.balance():,.0f}; hold consumed: {consumed}", 1)
        self.results[-1]["ok"] &= consumed

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

        # 3b) Item damaged after payment: the mouse ships, the laptop stand (the last line) is refunded.
        self.add_from_listing(page, "Slim Wireless Mouse")
        self.add_from_listing(page, "Aluminium Laptop Stand")
        order_id = self.checkout(page, "Item damaged (partial refund)")
        result = self.wait_terminal(page)
        expect(page.get_by_text("Delivered", exact=True)).to_be_visible()
        expect(page.get_by_text(re.compile(r"^Cancelled — refunded ₹[\d,]+$"))).to_be_visible()
        self.shot(page, "desktop-10b-tracker-partially-fulfilled")
        credits = self.credits(order_id)
        line_amount = next(i["lineAmount"] for i in self.api_json("GET", f"/orders/{order_id}")["items"] if i["lineId"] == "L2")
        self.record("Item damaged (partial refund)", order_id, f"{result}; CREDITs {[c['amount'] for c in credits]} (L2 = {line_amount})", 1)
        self.results[-1]["ok"] &= result == "Order partially fulfilled" and [c["amount"] for c in credits] == [line_amount]
        page.goto(base + "/wallet")
        credit_row = page.locator("tbody tr", has_text=order_id).filter(has_text="Refund").first
        expect(credit_row).to_contain_text(re.compile(r"Refund for .* line L2"))  # the ledger note says which item
        self.shot(page, "desktop-10c-wallet-partial-credit")

        # 3c) Step 2.4: cancel after payment, while the warehouse waits 10 s before it starts.
        self.add_from_listing(page, "Felt and Leather Desk Mat")
        order_id = self.checkout(page, "Slow warehouse (cancel after payment)")
        cancel_button = page.get_by_test_id("cancel-order")
        expect(cancel_button).to_be_visible(timeout=20_000)
        # Cancel once the tracker itself shows the payment (its 1.5 s poll can lag the API), to show the full refund.
        expect(page.get_by_text(re.compile(r"^Paid ₹[\d,]+ with DemoPay$"))).to_be_visible(timeout=20_000)
        self.shot(page, "desktop-10d-tracker-cancel-button")
        cancel_button.click()
        expect(page.get_by_test_id("confirm-cancel")).to_be_visible()
        self.shot(page, "desktop-10e-tracker-cancel-confirm")
        page.get_by_test_id("confirm-cancel").click()
        result = self.wait_terminal(page)
        summary = page.get_by_test_id("cancelled-summary")
        expect(summary).to_have_text(re.compile(r"^Cancelled — refunded ₹[\d,]+$"))
        self.shot(page, "desktop-10f-tracker-cancelled")
        total = self.api_json("GET", f"/orders/{order_id}")["totalAmount"]
        credits = self.credits(order_id)
        self.record("Cancel after payment", order_id, f"{result}; {summary.inner_text()}; CREDITs {[c['amount'] for c in credits]}", 1)
        self.results[-1]["ok"] &= result == "Order cancelled" and [c["amount"] for c in credits] == [total]
        page.goto(base + "/wallet")
        credit_row = page.locator("tbody tr", has_text=order_id).filter(has_text="Refund").first
        expect(credit_row).to_contain_text("order cancelled")
        self.shot(page, "desktop-10g-wallet-cancel-refund")

        # 4) REAL decline: set the wallet to ₹1,000 in the UI, then buy a ₹5,999 microphone.
        page.goto(base + "/wallet")
        page.locator("#custom-balance").fill("1000")
        page.get_by_role("button", name="Set", exact=True).click()
        expect(page.get_by_text("₹1,000", exact=True).first).to_be_visible()
        self.add_from_listing(page, "USB Condenser Microphone")
        page.goto(base + "/checkout")
        page.locator("#name").fill(NAME)
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

        # 6) Back to the late payment: FAILED at the 120 s timeout, then the refund row once DemoPay's late
        # callback arrives (the tracker stops polling at FAILED, so reload until the refund shows).
        page.goto(f"{base}/orders/{late_id}")
        result = self.wait_terminal(page, 200)
        for _ in range(30):
            if page.get_by_text(re.compile(r"refunded", re.I)).count():
                break
            page.wait_for_timeout(5_000)
            page.reload()
            self.wait_terminal(page, 30)
        refunded = page.get_by_text(re.compile(r"refunded", re.I)).count() > 0
        self.record("Late payment (auto-refund)", late_id, f"{result}; refund row shown: {refunded}", 1)
        self.shot(page, "desktop-07b-tracker-late-payment-refunded")

        # 7) Back to the poison order: wait until its third failed delivery dead-letters it.
        page.goto(f"{base}/orders/{poison_id}")
        remaining = max(30, 300 - int(time.monotonic() - poison_started))
        self.record("Poison message (to DLQ)", poison_id, self.wait_terminal(page, remaining), 0)
        self.shot(page, "desktop-17-tracker-poison-dead-lettered")

    def hold_expiry(self, page: Page) -> None:
        """Own browser context with a fake clock: jump 10 min ahead to show the expired-hold state, then "Hold again"."""
        page.clock.install()
        self.sign_in(page)
        self.add_from_listing(page, "Slim Wireless Mouse")
        page.goto(self.base + "/checkout")
        expect(page.get_by_test_id("hold-countdown")).to_be_visible()
        hold_id = self.api_json("GET", "/holds/current")["hold"]["holdId"]
        page.clock.fast_forward("09:01")
        expect(page.get_by_test_id("hold-countdown")).to_have_text(re.compile(r"^0:5\d$"))
        self.shot(page, "desktop-07c-checkout-hold-last-minute", full_page=False)
        page.clock.fast_forward("01:05")
        expect(page.get_by_text("Your hold expired.")).to_be_visible()
        self.shot(page, "desktop-07d-checkout-hold-expired", full_page=False)
        page.get_by_role("button", name="Hold again").click()
        expect(page.get_by_test_id("hold-countdown")).to_be_visible()
        again = self.api_json("GET", "/holds/current")["hold"]["holdId"]
        page.goto(self.base + "/cart")  # leaving checkout releases the hold
        page.get_by_role("button", name="Remove").click()
        page.wait_for_timeout(1500)
        released = self.api_json("GET", "/holds/current")["hold"] is None
        self.results.append({
            "scenario": "Checkout hold: expired, held again, released on leaving", "orderId": "-",
            "result": f"{hold_id} -> {again}; released: {released}", "debits": 0, "ok": released and again != hold_id, "expected": 0,
        })
        print(f"hold expiry UI: {hold_id} -> {again}, released on leaving: {released}")

    def busy_retry(self, page: Page) -> None:
        """Step 3.2: the API answers 503 "busy" (a product row stayed contended). Playwright fakes two 503s on POST /holds
        and one on POST /orders; the storefront must show "busy, retrying…", retry with backoff, and end with exactly one
        order (the same Idempotency-Key on every try) and one DEBIT."""
        origin = self.base
        faked = {"holds": 2, "orders": 1}
        sent_keys: list[str] = []

        def busy_then_real(route, request) -> None:
            path = request.url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
            if request.method == "POST" and path in faked:
                if path == "orders":
                    sent_keys.append(request.headers.get("idempotency-key", ""))
                if faked[path] > 0:
                    faked[path] -= 1
                    route.fulfill(
                        status=503,
                        content_type="application/json",
                        headers={"Access-Control-Allow-Origin": origin, "Access-Control-Expose-Headers": "retry-after", "Retry-After": "1"},
                        body=json.dumps({"error": "RACE busy: the product is contended, retry shortly"}),
                    )
                    return
            route.continue_()

        page.route(f"{self.api}/**", busy_then_real)
        self.sign_in(page)
        self.add_from_listing(page, "Slim Wireless Mouse")
        page.goto(self.base + "/checkout")
        expect(page.get_by_test_id("hold-banner")).to_contain_text("The store is busy, retrying")
        self.shot(page, "desktop-07e-checkout-hold-busy-retrying", full_page=False)
        expect(page.get_by_test_id("hold-countdown")).to_be_visible(timeout=15000)  # held after the retries
        page.locator("#name").fill(NAME)
        page.get_by_role("button", name="Continue to payment").click()
        pay = page.get_by_role("button", name=re.compile(r"^Pay ₹"))
        expect(page.get_by_text(re.compile(r"^₹[\d,]+$")).first).to_be_visible()  # wallet balance loaded
        pay.click()
        expect(page.get_by_test_id("busy-retry")).to_contain_text("The store is busy, retrying")
        self.shot(page, "desktop-07f-checkout-order-busy-retrying", full_page=False)
        page.wait_for_url(re.compile(r"/orders/ORD-\d{8}-[0-9a-f]{8}$"), timeout=20_000)
        order_id = page.url.rsplit("/", 1)[-1]
        result = self.wait_terminal(page)
        one_key = len(sent_keys) == 2 and len(set(sent_keys)) == 1
        print(f"busy retry UI: hold retried {2 - faked['holds']}x, order retried with one key: {one_key} ({len(sent_keys)} POSTs)")
        self.record("Busy 503 -> retried (hold x2, order x1)", order_id, result if one_key else f"{result} (keys {sent_keys})", 1)
        self.results[-1]["ok"] = self.results[-1]["ok"] and one_key and faked == {"holds": 0, "orders": 0}

    def mobile(self, phone: Page) -> None:
        base = self.base
        self.sign_in(phone)
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
    sys.stdout.reconfigure(encoding="utf-8")  # results print "₹"; a Windows console or redirect defaults to cp1252
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
        held = browser.new_context(viewport=DESKTOP).new_page()
        held.on("console", lambda msg: msg.type == "error" and run.console_errors.append(msg.text))
        run.hold_expiry(held)
        busy = browser.new_context(viewport=DESKTOP).new_page()
        # The faked 503s log "Failed to load resource" by design; every other console error still counts.
        busy.on("console", lambda msg: msg.type == "error" and "status of 503" not in msg.text and run.console_errors.append(msg.text))
        run.busy_retry(busy)
        phone = browser.new_context(viewport=MOBILE, device_scale_factor=2, is_mobile=True, has_touch=True).new_page()
        phone.on("console", lambda msg: msg.type == "error" and run.console_errors.append(msg.text))
        run.mobile(phone)
        browser.close()

    write_index(run)
    for r in run.results:
        print(f"{r['scenario']:<30} {r['orderId']}  {r['result']}  DEBITs={r['debits']} {'OK' if r['ok'] else 'MISMATCH'}")


if __name__ == "__main__":
    main()
