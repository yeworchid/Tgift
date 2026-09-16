import os
import asyncio
import json
import aiohttp
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from collections_parser import fetch_collections


SERVER_URL = os.environ.get("SERVER_URL", "http://127.0.0.1:8000/api/upload-data/")
MAX_NFTS_PER_COLLECTION = 150  # Ограничение на 150 NFT
DEFAULT_TON_RUB_RATE = 290.0  # Дефолтный курс

# Переработанная функция fetch_nfts_for_sale
async def fetch_nfts_for_sale(collection_id, limit=MAX_NFTS_PER_COLLECTION):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        })
        url = f"https://getgems.io/collection/{collection_id}?filter=%7B%22saleType%22%3A%22fix_price%22%7D&sort=price-asc"
        print(f"Начинаем парсинг коллекции {collection_id}")
        await page.goto(url, wait_until="networkidle")

        nfts = []

        while len(nfts) < limit:
            content = await page.content()
            soup = BeautifulSoup(content, "html.parser")
            nft_cards = soup.select(".NftItemContainer.NftItemContainer--surface-none")
            print(f"Найдено карточек на странице: {len(nft_cards)}")

            for card in nft_cards:
                try:
                    if card.select_one(".NftItemPrice__ton"):  # Пропускаем неподходящие элементы
                        continue
                    name = card.select_one(".NftItemNameContent__name").text.strip()
                    price_elem = card.select_one(".NftItemPrice .CryptoPrice__amount")
                    price = price_elem.text.strip().replace("\u2009", "") + " TON"
                    image = card.select_one(".LibraryImg.LibraryMedia--fill-container")["src"]
                    nft = {"name": name, "price": price, "image": image}
                    if not any(n["name"] == nft["name"] for n in nfts):  # Избегаем дубликатов
                        nfts.append(nft)
                except (AttributeError, KeyError):
                    continue

            if len(nfts) >= limit:
                print(f"Достигнут лимит {limit} для {collection_id}")
                break

            # Прокручиваем и проверяем конец страницы
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            await page.wait_for_timeout(2000)
            last_height = await page.evaluate("document.body.scrollHeight")
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            await page.wait_for_timeout(2000)
            new_height = await page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                print(f"Достигнут конец страницы для {collection_id}")
                break

        await browser.close()
        print(f"Собрано NFT для {collection_id}: {len(nfts)}")

        def parse_price(price_str):
            num = price_str.split()[0].replace(",", "")
            return float(num)
        nfts.sort(key=lambda x: parse_price(x["price"]))

        return nfts[:limit]

async def parse_and_upload():
    # Инициализируем данные с дефолтным курсом
    data = {
        "ton_rub_rate": DEFAULT_TON_RUB_RATE,
        "collections": [],
        "nfts": {}
    }
    print(f"Установлен дефолтный курс TON/RUB: {data['ton_rub_rate']}")

    # Парсинг коллекций
    try:
        collections = await fetch_collections()
        if collections:
            data["collections"] = collections
            print(f"Спарсено коллекций: {len(collections)}")
        else:
            print("Коллекции вернулись пустыми")
    except Exception as e:
        print(f"Ошибка при парсинге коллекций: {e}")
        data["collections"] = []

    # Парсинг NFT для каждой коллекции
    for collection in data["collections"]:
        collection_id = collection.get('id')
        if not collection_id:
            print(f"Пропущена коллекция без ID: {collection}")
            continue
        try:
            nft_list = await fetch_nfts_for_sale(collection_id)
            data["nfts"][collection_id] = nft_list
        except Exception as e:
            print(f"Ошибка при парсинге NFT для {collection_id}: {e}")
            data["nfts"][collection_id] = []

    # Сохраняем локально в JSON
    try:
        with open('parsed_data.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print("Данные сохранены в parsed_data.json")
    except Exception as e:
        print(f"Ошибка при сохранении данных в parsed_data.json: {e}")

    # Отправка данных на сервер
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(SERVER_URL, json=data) as response:
                if response.status == 200:
                    print(f"Данные успешно отправлены на сервер: {response.status}")
                else:
                    print(f"Ошибка отправки данных на сервер: {response.status} - {await response.text()}")
    except Exception as e:
        print(f"Ошибка при отправке данных на сервер: {e}")

if __name__ == "__main__":
    asyncio.run(parse_and_upload())