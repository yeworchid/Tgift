from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import asyncio

async def fetch_collections():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept-Language": "ru-RU,ru;q=0.9",
        })
        try:
            await page.goto("https://getgems.io/top-gifts", wait_until="networkidle", timeout=30000)
            last_height = await page.evaluate("document.body.scrollHeight")
            while True:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                await page.wait_for_timeout(2000)
                new_height = await page.evaluate("document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height

            content = await page.content()
        except Exception as e:
            print(f"Ошибка загрузки страницы коллекций: {e}")
            await browser.close()
            return []

        await browser.close()

        soup = BeautifulSoup(content, "html.parser")
        collections = []

        rows = soup.select(".TableRow.TopCollectionsRow")
        for row in rows:
            try:
                link = row.select_one(".AppLink.TopCollectionsRow__cell-inner")
                href = link["href"]
                collection_id = href.split("/collection/")[1]
                name = row.select_one(".LibraryCellTitle__label").text.strip()
                image = row.select_one(".TopCollectionsRow__img")["src"]
                collections.append({
                    "id": collection_id,
                    "name": name,
                    "image": image
                })
            except (AttributeError, KeyError, IndexError):
                continue

        return collections