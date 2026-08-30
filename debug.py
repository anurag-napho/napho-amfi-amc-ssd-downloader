from playwright.sync_api import sync_playwright

URL = "https://www.amfiindia.com/otherdata/scheme-details"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)

    page = browser.new_page()

    page.goto(
        URL,
        wait_until="domcontentloaded",
        timeout=60000,
    )

    page.wait_for_timeout(3000)

    print("URL:", page.url)

    print("\nINPUTS")
    print("------")

    inputs = page.locator("input")

    print("Count:", inputs.count())

    for i in range(inputs.count()):
        el = inputs.nth(i)

        print(
            i,
            {
                "placeholder": el.get_attribute("placeholder"),
                "name": el.get_attribute("name"),
                "id": el.get_attribute("id"),
                "class": el.get_attribute("class"),
                "type": el.get_attribute("type"),
                "value": el.get_attribute("value"),
            },
        )

    print("\nBUTTONS")
    print("-------")

    buttons = page.locator("button")

    for i in range(buttons.count()):
        button = buttons.nth(i)

        print(
            i,
            button.inner_text(),
            button.get_attribute("class"),
        )

    page.screenshot(
        path="amfi_scheme_details_debug.png",
        full_page=True,
    )

    browser.close()