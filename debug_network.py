from playwright.sync_api import sync_playwright

URL = "https://www.amfiindia.com/otherdata/scheme-details"


with sync_playwright() as p:

    browser = p.chromium.launch(
        headless=False,
    )

    page = browser.new_page()

    def log_response(response):

        url = response.url.lower()

        interesting = (
            "scheme" in url
            or "fund" in url
            or "amc" in url
            or "api" in url
        )

        if interesting:

            print(
                response.status,
                response.request.method,
                response.url,
            )

    page.on(
        "response",
        log_response,
    )

    page.goto(
        URL,
        wait_until="networkidle",
        timeout=60000,
    )

    page.wait_for_timeout(10000)

    input(
        "Interact with the AMC dropdown in the browser. "
        "Press Enter here when finished..."
    )

    browser.close()