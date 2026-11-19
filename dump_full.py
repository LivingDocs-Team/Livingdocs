from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    # Ghi lại lỗi console & page error
    page.on("console", lambda m: print("CONSOLE:", m.type, m.text))
    page.on("pageerror", lambda e: print("PAGE ERROR:", e))
    page.on("requestfailed", lambda r: print("REQ FAIL:", r.url, r.failure))

    page.goto("http://localhost:3000/", wait_until="networkidle")
    page.wait_for_timeout(3000)

    print("=== FINAL URL ===")
    print(page.url)
    print("=== PAGE TITLE ===")
    print(repr(page.title()))
    print("=== BODY TEXT (full) ===")
    print(repr(page.inner_text("body")))
    print("=== BODY HTML (first 2000 chars) ===")
    print(page.content()[:2000])
    print("=== ALL ELEMENTS COUNT ===")
    print("a:", len(page.query_selector_all("a")))
    print("input:", len(page.query_selector_all("input")))
    print("button:", len(page.query_selector_all("button")))
    print("form:", len(page.query_selector_all("form")))
    print("div:", len(page.query_selector_all("div")))

    browser.close()
