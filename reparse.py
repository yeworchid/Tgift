import os
import asyncio
import json
import aiohttp
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from collections_parser import fetch_collections

# Константы
SERVER_URL = os.environ.get("SERVER_URL", "http://127.0.0.1:8000/api/upload-data/")
MAX_NFTS_PER_COLLECTION = 139  # Ограничение на 130 NFT
JSON_FILE = 'parsed_data.json'  # Файл с данными

async def fetch_nfts_for_sale(collection_id, limit=MAX_NFTS_PER_COLLECTION):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        })
        url = f"https://getgems.io/collection/{collection_id}?filter=%7B%22saleType%22%3A%22fix_price%22%7D&sort=price-asc"
        print(f"Начинаем повторный парсинг коллекции {collection_id}")
        try:
            await page.goto(url, wait_until="networkidle")
        except Exception as e:
            print(f"Ошибка загрузки страницы для {collection_id}: {e}")
            await browser.close()
            return []

        nfts = []

        while len(nfts) < limit:
            content = await page.content()
            soup = BeautifulSoup(content, "html.parser")
            nft_cards = soup.select(".NftItemContainer.NftItemContainer--surface-none")
            print(f"Найдено карточек на странице: {len(nft_cards)}")

            for card in nft_cards:
                try:
                    if card.select_one(".NftItemPrice__ton"):
                        continue
                    name = card.select_one(".NftItemNameContent__name").text.strip()
                    price_elem = card.select_one(".NftItemPrice .CryptoPrice__amount")
                    price = price_elem.text.strip().replace("\u2009", "") + " TON"
                    image = card.select_one(".LibraryImg.LibraryMedia--fill-container")["src"]

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
                    
                    if not any(n["name"] == nft["name"] for n in nfts):
                        nfts.append(nft)
                except (AttributeError, KeyError):
                    continue

            if len(nfts) >= limit:
                print(f"Достигнут лимит {limit} для {collection_id}")
                break

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

def load_json():
    """Загружаем текущие данные из JSON."""
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Ошибка загрузки {JSON_FILE}: {e}. Используем пустые данные.")
        return {"ton_rub_rate": 290.0, "collections": [], "nfts": {}}

def save_to_json(data):
    """Сохраняем данные в JSON."""
    try:
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"Данные сохранены в {JSON_FILE}")
    except Exception as e:
        print(f"Ошибка при сохранении данных в {JSON_FILE}: {e}")

async def reparse_missing_collections():
    # Загружаем текущие данные
    data = load_json()
    print(f"Загружено коллекций из JSON: {len(data['collections'])}, NFT записей: {len(data['nfts'])}")

    # Получаем актуальный список коллекций
    try:
        all_collections = await fetch_collections()
        if not all_collections:
            print("Не удалось получить коллекции. Завершаем.")
            return
        print(f"Получено актуальных коллекций: {len(all_collections)}")
    except Exception as e:
        print(f"Ошибка при получении коллекций: {e}")
        return

    # Определяем коллекции для повторного парсинга
    collection_ids = {col["id"] for col in all_collections if col.get("id")}
    missing_or_empty = {
        col_id for col_id in collection_ids
        if col_id not in data["nfts"] or len(data["nfts"][col_id]) == 0
    }
    if not missing_or_empty:
        print("Все коллекции уже спарсены и имеют NFT. Завершаем.")
        return

    print(f"Найдено коллекций для повторного парсинга: {len(missing_or_empty)}")
    total_missing = len(missing_or_empty)
    parsed_count = 0

    # Обновляем список коллекций в данных, если есть новые
    data["collections"] = all_collections
    save_to_json(data)

    # Парсим недостающие или пустые коллекции
    for collection_id in missing_or_empty:
        try:
            nft_list = await fetch_nfts_for_sale(collection_id)
            data["nfts"][collection_id] = nft_list
        except Exception as e:
            print(f"Ошибка при повторном парсинге NFT для {collection_id}: {e}")
            data["nfts"][collection_id] = []

        parsed_count += 1
        print(f"Прогресс: спарсено {parsed_count} из {total_missing} недостающих коллекций")
        save_to_json(data)

if __name__ == "__main__":
    asyncio.run(reparse_missing_collections())