from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import asyncio

async def fetch_ton_rub_rate():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept-Language": "ru-RU,ru;q=0.9",
        })
        url = "https://www.coingecko.com/ru/Криптовалюты/toncoin/rub"
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            content = await page.content()
        except Exception as e:
            print(f"Ошибка загрузки курса TON/RUB: {e}")
            await browser.close()
            return cache.get('ton_rub_rate') or 0  # Возвращаем последний кэшированный курс или 0

        await browser.close()

        soup = BeautifulSoup(content, "html.parser")
        price_elem = soup.select_one('span[data-coin-id="17980"][data-price-target="price"]')
        if price_elem:
            price_text = price_elem.text.strip().replace("₽", "").replace(",", ".").replace("\xa0", "")
            return float(price_text)
        return cache.get('ton_rub_rate') or 0  # Возвращаем последний кэшированный курс или 0