"""Run every scenario through the DEPLOYED storefront with a real browser and save screenshots.

    python -m pip install playwright && python -m playwright install chromium   # one-time, dev only
    python scripts/capture_ui.py

Uses the same UI a person would (Shop -> Add -> Cart -> Checkout -> Place order -> tracker) for
normal, payment declined, payment glitch, out of stock, the duplicate test and poison. Saves desktop
(1440 px) and mobile (360 px) screenshots to docs/evidence/ui/ and writes docs/evidence/ui/README.md
with the orderId created for each scenario.
"""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

from tf_outputs import load_outputs

OUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "ui"
TERMINAL_TITLES = re.compile(r"Order completed|Order failed|Stuck in the dead-letter queue")
CUSTOMER = ("Asha Rao", "asha.rao@example.com")
DESKTOP = {"width": 1440, "height": 900}
MOBILE = {"width": 360, "height": 780}


def shot(page: Page, name: str, full_page: bool = True) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(OUT_DIR / f"{name}.png"), full_page=full_page)
    print(f"  saved {name}.png")


def add_to_cart(page: Page, base: str, product: str) -> None:
    page.goto(base + "/")
    page.get_by_role("button", name=f"Add {product} to cart").click()


def fill_checkout(page: Page, base: str, scenario: str) -> None:
    page.goto(base + "/checkout")
    page.locator("#name").fill(CUSTOMER[0])
    page.locator("#email").fill(CUSTOMER[1])
    page.locator("#scenario").select_option(label=scenario)


def place_order(page: Page) -> str:
    page.get_by_role("button", name="Place order").click()
    page.wait_for_url(re.compile(r"/orders/ORD-\d{8}-[0-9a-f]{8}$"), timeout=15_000)
    return page.url.rsplit("/", 1)[-1]


def wait_terminal(page: Page, timeout_s: int = 90) -> str:
    title = page.get_by_role("heading", level=1)
    expect(title).to_have_text(TERMINAL_TITLES, timeout=timeout_s * 1000)
    page.wait_for_timeout(600)  # let the last feed row finish its fade-in
    return title.inner_text()


def run(base: str) -> list[dict]:
    results: list[dict] = []
    console_errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        desktop = browser.new_context(viewport=DESKTOP)
        page = desktop.new_page()
        page.on("console", lambda msg: msg.type == "error" and console_errors.append(msg.text))

        page.goto(base + "/")
        expect(page.get_by_role("button", name=re.compile(r"^Add "))).to_have_count(5)
        page.wait_for_load_state("networkidle")
        shot(page, "desktop-01-shop")

        # Poison first: it needs ~3 minutes of SQS retries before it reaches the DLQ.
        add_to_cart(page, base, "Wireless Mouse")
        fill_checkout(page, base, "Poison message (to DLQ)")
        poison_id, poison_started = place_order(page), time.monotonic()
        print(f"poison order {poison_id}")
        page.wait_for_timeout(23_000)  # past the 20 s mark, so the SQS-retrying hint row shows
        shot(page, "desktop-07-tracker-poison-retrying")

        scenarios = [
            ("Normal", "Mechanical Keyboard", "desktop-04-tracker-completed"),
            ("Payment declined", "USB-C Hub", "desktop-05-tracker-payment-declined"),
            ("Payment glitch (retries)", "Noise-Cancelling Headphones", "desktop-06-tracker-payment-glitch"),
            ("Out of stock", "27-inch 4K Monitor", "desktop-08-tracker-out-of-stock"),
        ]
        for index, (scenario, product, name) in enumerate(scenarios):
            add_to_cart(page, base, product)
            if index == 0:
                page.get_by_role("button", name=re.compile(r"^Open cart")).click()
                expect(page.get_by_role("dialog")).to_be_visible()
                shot(page, "desktop-02-cart-drawer", full_page=False)
                page.get_by_role("button", name="Close").click()
            fill_checkout(page, base, scenario)
            if index == 0:
                shot(page, "desktop-03-checkout")
            order_id = place_order(page)
            title = wait_terminal(page)
            shot(page, name)
            results.append({"scenario": scenario, "orderId": order_id, "result": title})
            print(f"{scenario}: {order_id} -> {title}")

        # Duplicate test: the same order sent 3 times with one Idempotency-Key.
        add_to_cart(page, base, "Wireless Mouse")
        fill_checkout(page, base, "Normal")
        page.get_by_role("button", name=re.compile(r"Send same order 3")).click()
        status = page.get_by_role("status").filter(has_text="requests")
        expect(status).to_contain_text("3 requests → 1 order", timeout=20_000)
        duplicate_id = re.search(r"ORD-\d{8}-[0-9a-f]{8}", status.inner_text()).group(0)
        shot(page, "desktop-09-checkout-duplicate-test")
        page.goto(f"{base}/orders/{duplicate_id}")
        results.append({"scenario": "Duplicate test (3 requests)", "orderId": duplicate_id, "result": f"{wait_terminal(page)} · 1 order"})
        print(f"duplicate: {duplicate_id}")

        page.goto(base + "/orders")
        expect(page.locator("tbody tr").first).to_contain_text("ORD-")
        shot(page, "desktop-10-orders")

        # Back to the poison order: wait until the third failed delivery dead-letters it.
        page.goto(f"{base}/orders/{poison_id}")
        remaining = max(30, 300 - int(time.monotonic() - poison_started))
        results.append({"scenario": "Poison message (to DLQ)", "orderId": poison_id, "result": wait_terminal(page, remaining)})
        shot(page, "desktop-11-tracker-poison-dead-lettered")

        # Mobile (360 px): the same pages, reusing the orders created above.
        mobile = browser.new_context(viewport=MOBILE, device_scale_factor=2, is_mobile=True, has_touch=True)
        phone = mobile.new_page()
        phone.on("console", lambda msg: msg.type == "error" and console_errors.append(msg.text))
        phone.goto(base + "/")
        expect(phone.get_by_role("button", name=re.compile(r"^Add "))).to_have_count(5)
        phone.wait_for_load_state("networkidle")
        shot(phone, "mobile-01-shop")
        add_to_cart(phone, base, "Mechanical Keyboard")
        fill_checkout(phone, base, "Normal")
        shot(phone, "mobile-02-checkout")
        for name, order_id in (("mobile-03-tracker-completed", results[0]["orderId"]), ("mobile-04-tracker-payment-declined", results[1]["orderId"])):
            phone.goto(f"{base}/orders/{order_id}")
            wait_terminal(phone)
            shot(phone, name)
        phone.goto(base + "/orders")
        expect(phone.locator("tbody tr").first).to_contain_text("ORD-")
        shot(phone, "mobile-05-orders")
        browser.close()

    write_index(base, results, console_errors)
    return results


def write_index(base: str, results: list[dict], console_errors: list[str]) -> None:
    lines = [
        "# Storefront UI evidence (Phase 4)",
        "",
        f"Every scenario was run through the deployed storefront ({base}) by `scripts/capture_ui.py`",
        "(Playwright + Chromium): Shop -> Add -> Cart -> Checkout -> Place order -> live tracker.",
        "",
        "| Scenario | orderId | Tracker result |",
        "|---|---|---|",
    ]
    lines += [f"| {r['scenario']} | `{r['orderId']}` | {r['result']} |" for r in results]
    lines += ["", f"Browser console errors during the run: {len(console_errors)}", ""]
    lines += [f"- `{e[:200]}`" for e in console_errors]
    lines += ["## Screenshots", ""]
    lines += [f"### {p.stem}\n\n![{p.stem}]({p.name})\n" for p in sorted(OUT_DIR.glob("*.png"))]
    (OUT_DIR / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", help="storefront URL (default: terraform output frontend_url)")
    args = parser.parse_args()
    base = (args.url or load_outputs()["frontend_url"]).rstrip("/")
    for result in run(base):
        print(f"{result['scenario']:<30} {result['orderId']}  {result['result']}")


if __name__ == "__main__":
    main()
