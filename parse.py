import os
import asyncio
import json
import aiohttp
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from collections_parser import fetch_collections


SERVER_URL = os.environ.get("SERVER_URL", "http://127.0.0.1:8000/api/upload-data/")
MAX_NFTS_PER_COLLECTION = 139  # Ограничение на 83 NFT
DEFAULT_TON_USDT_RATE = 3.9  # Дефолтный курс
DEFAULT_USDT_RUB_RATE = 84.3
DEFAULT_TON_RUB_RATE = DEFAULT_TON_USDT_RATE * DEFAULT_USDT_RUB_RATE
JSON_FILE = 'parsed_data.json'  # Файл для сохранения

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
                    
                    # Извлекаем ID NFT из ссылки
                    nft_link_elem = card.select_one("a.AppLink")
                    if not nft_link_elem or "href" not in nft_link_elem.attrs:
                        print(f"Ссылка NFT не найдена для {name}, пропускаем")
                        continue
                    nft_link = nft_link_elem["href"]
                    nft_id = nft_link.split('/')[-1]  # Последняя часть URL — ID NFT

                    nft = {"id": nft_id, "name": name, "price": price, "image": image}
                    if not any(n["name"] == nft["name"] for n in nfts):  # Избегаем дубликатов
                        nfts.append(nft)
                        print(f"Добавлен NFT: {name} с ID {nft_id}")
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

def save_to_json(data):
    """Сохраняем данные в JSON файл."""
    try:
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"Данные сохранены в {JSON_FILE}")
    except Exception as e:
        print(f"Ошибка при сохранении данных в {JSON_FILE}: {e}")

async def parse_and_upload():
    # Инициализируем данные с дефолтным курсом
    data = {
        "ton_usdt_rate": DEFAULT_TON_USDT_RATE,
        "usdt_rub_rate": DEFAULT_USDT_RUB_RATE,
        "ton_rub_rate": DEFAULT_TON_RUB_RATE,
        "collections": [],
        "nfts": {}
    }
    print(f"Установлен дефолтный курс TON/USDT: {data['ton_usdt_rate']}")
    print(f"Установлен дефолтный курс USDT/RUB: {data['usdt_rub_rate']}")
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

    # Сохраняем начальные данные
    save_to_json(data)

    # Парсинг NFT для каждой коллекции с прогрессом
    total_collections = len(data["collections"])
    parsed_collections = 0

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

        # Обновляем прогресс
        parsed_collections += 1
        print(f"Прогресс: спарсено {parsed_collections} из {total_collections} коллекций")

        # Сохраняем данные после каждой коллекции
        save_to_json(data)

if __name__ == "__main__":
    asyncio.run(parse_and_upload())