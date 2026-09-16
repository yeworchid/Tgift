from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.core.cache import cache
from django.utils import timezone
from django.middleware.csrf import get_token
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
import json
import os
from datetime import timedelta
import requests
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key
import logging
import aiohttp
from bs4 import BeautifulSoup
import datetime # Замените 'import datetime' на это

# Добавляем перед get_wata_public_key
SCRAPINGBEE_API_KEY = settings.BEE_KEY

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

WATA_API_URL = settings.WATA_API_URL
WATA_API_KEY = settings.WATA_API_KEY
WATA_TERMINAL_ID = settings.WATA_TERMINAL_ID
WATA_HEADERS = {"Authorization": f"Bearer {WATA_API_KEY}"}

def get_stats_data():
    """Читает данные статистики из stats.json."""
    try:
        with open(os.path.join(settings.BASE_DIR, 'stats.json'), 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {"visits": [], "purchases": [], "referrals": {}}

def save_stats_data(data):
    """Сохраняет данные статистики в stats.json."""
    try:
        with open(os.path.join(settings.BASE_DIR, 'stats.json'), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        logger.info("Статистика успешно сохранена в stats.json")
    except Exception as e:
        logger.error(f"Ошибка сохранения stats.json: {e}")

async def send_telegram_notification(message):
    token = settings.BOT_TOKEN
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": settings.CHAT_ID,
        "text": message
    }
    async with aiohttp.ClientSession() as session:
        await session.post(url, json=payload)

async def fetch_nft_status(collection_id, nft_id):
    """Проверяет статус NFT на GetGems через ScrapingBee."""
    url = f"https://getgems.io/collection/{collection_id}/{nft_id}"
    scrapingbee_url = f"https://app.scrapingbee.com/api/v1/?api_key={SCRAPINGBEE_API_KEY}&url={url}&render_js=true&wait=5000"
    
    logger.info(f"Запрос к ScrapingBee: {scrapingbee_url}")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(scrapingbee_url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                logger.info(f"ScrapingBee статус: {response.status}")
                if response.status != 200:
                    logger.error(f"ScrapingBee ошибка: статус {response.status}, тело: {await response.text()}")
                    return "Неизвестный статус"
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                status_element = soup.find("div", class_="LibraryBadge__text")
                if status_element:
                    status_text = status_element.text.upper()
                    logger.info(f"Статус на GetGems: '{status_text}' для {url}")
                    if "НЕ ПРОДАЁТСЯ" in status_text or "NOT FOR SALE" in status_text:
                        return "Подарок не продаётся"
                    elif "НА ПРОДАЖЕ" in status_text or "FOR SALE" in status_text or "НА АУКЦИОНЕ" in status_text or "UP FOR AUCTION" in status_text:
                        return "Подарок в продаже"
                    else:
                        logger.warning(f"Неизвестный текст статуса: '{status_text}'")
                        return "Неизвестный статус"
                else:
                    logger.error(f"Элемент LibraryBadge__text не найден. HTML: {html[:1000]}...")
                    return "Неизвестный статус"
        except Exception as e:
            logger.error(f"Ошибка ScrapingBee: {str(e)}")
            return "Неизвестный статус"

def get_wata_public_key():
    logger.info("Попытка получения публичного ключа WATA")
    public_key = cache.get('wata_public_key')
    if not public_key:
        try:
            response = requests.get(f"{WATA_API_URL}/public-key", headers=WATA_HEADERS)
            logger.info(f"Запрос к /public-key: статус {response.status_code}")
            if response.status_code == 200:
                public_key = response.text.encode('utf-8')
                cache.set('wata_public_key', public_key, timeout=86400)
                logger.info("Публичный ключ WATA успешно получен и закеширован")
            else:
                logger.error(f"Ошибка получения ключа: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"Исключение при получении ключа: {e}")
    return public_key

def get_json_data():
    logger.info("Чтение parsed_data.json")
    try:
        with open(os.path.join(settings.BASE_DIR, 'parsed_data.json'), 'r', encoding='utf-8') as f:
            data = json.load(f)
            logger.info("parsed_data.json успешно прочитан")
            return data
    except Exception as e:
        logger.error(f"Ошибка чтения parsed_data.json: {e}")
        return {"ton_rub_rate": 300.0, "collections": [], "nfts": {}}

def save_json_data(data):
    logger.info("Сохранение данных в parsed_data.json")
    try:
        with open(os.path.join(settings.BASE_DIR, 'parsed_data.json'), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        logger.info("Данные успешно сохранены в parsed_data.json")
    except Exception as e:
        logger.error(f"Ошибка сохранения parsed_data.json: {e}")

def index(request):
    referrer = request.GET.get('ref')
    client_ip = request.META.get('REMOTE_ADDR', 'unknown')
    user_agent = request.META.get('HTTP_USER_AGENT', 'unknown')
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Записываем посещение в статистику
    stats_data = get_stats_data()
    visit_data = {
        "timestamp": timestamp,
        "ip": client_ip,
        "referrer": referrer if referrer else "direct",
        "user_agent": user_agent,
        "page": "index"
    }
    stats_data["visits"].append(visit_data)

    # Обрабатываем реферальные ссылки
    if referrer and client_ip:
        referrals_data = get_referrals_data()
        if referrer in referrals_data:
            ip_already_assigned = False
            for ref, ref_data in referrals_data.items():
                if client_ip in ref_data["ips"]:
                    ip_already_assigned = True
                    logger.info(f"IP {client_ip} уже привязан к рефке {ref}, игнорируем {referrer}")
                    break
            if not ip_already_assigned:
                referrals_data[referrer]["ips"].append(client_ip)
                stats_data["referrals"].setdefault(referrer, {"visits": 0, "purchases": 0})
                stats_data["referrals"][referrer]["visits"] += 1
                save_referrals_data(referrals_data)
                logger.info(f"IP {client_ip} привязан к рефке {referrer} (первый реф-код)")
        else:
            logger.warning(f"Недопустимая рефка: {referrer}")
    
    save_stats_data(stats_data)

    csrf_token = get_token(request)
    return render(request, 'index.html', {
        'csrf_token': csrf_token,
        'max_gift_price': settings.MAX_GIFT_PRICE
    })

@csrf_exempt
async def upload_data(request):
    logger.info(f"Запрос на загрузку данных: {request.method}")
    if request.method != 'POST':
        logger.warning("Метод не POST")
        return JsonResponse({'error': 'Метод не поддерживается'}, status=405)

    try:
        data = json.loads(request.body.decode('utf-8'))
        logger.info(f"Получены данные: {data}")
        ton_rub_rate = data.get('ton_rub_rate')
        collections = data.get('collections', [])
        nfts = data.get('nfts', {})

        if ton_rub_rate:
            cache.set('ton_rub_rate', ton_rub_rate, timeout=86400)
            cache.set('last_rate_update', timezone.now(), timeout=86400)
            logger.info(f"Курс TON/RUB обновлен: {ton_rub_rate}")

        json_data = {
            "ton_rub_rate": ton_rub_rate or 290.0,
            "collections": collections,
            "nfts": nfts
        }
        save_json_data(json_data)
        return JsonResponse({'status': 'success'})
    except Exception as e:
        logger.error(f"Ошибка при загрузке данных: {e}")
        return JsonResponse({'error': str(e)}, status=400)

async def get_collections(request):
    logger.info(f"Запрос коллекций: {request.path}")
    client_ip = request.META.get('REMOTE_ADDR', 'unknown')
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Записываем просмотр коллекций
    stats_data = get_stats_data()
    stats_data["visits"].append({
        "timestamp": timestamp,
        "ip": client_ip,
        "referrer": request.GET.get('ref', 'direct'),
        "user_agent": request.META.get('HTTP_USER_AGENT', 'unknown'),
        "page": "collections"
    })
    save_stats_data(stats_data)

    data = get_json_data()
    collections = []
    nfts_data = data.get("nfts", {})
    
    ton_rub_rate = cache.get('ton_rub_rate') or data.get("ton_rub_rate", 290.0)
    last_rate_update = cache.get('last_rate_update')
    MIN_RATE = 100.0
    MAX_CACHE_AGE = 86400

    labels_map = {
        "EQCWh1lPltyTwCWxCXm4umL5tPZoXR8kTIcT-pd0JqoadLHo": ["hit"],  # Diamond Rings
        "EQDumy3bnZYzV4bSWMSSZkmXqx50XuH5d9RlX_yEi2FNlivk": ["for_her"],  # Eternal Roses
        "EQDJsN9OJBhKGZoWZWtkEpzkCfIu16Z9UzTWbYjeLpuHdT5f": ["for_her"],  # Perfume Bottles
        "EQACcQpR2fmdeENWdE2YGQWHVxSTyA8Zq4_k7rk_IaxCRXNe": ["for_him"],  # Vintage Cigars
        "EQADvJxMxCHA7fRlYjoceBORf7RwKs0rzjVaKepQACMnZzG7": ["for_him"],  # Top Hats
        "EQCDBbQYbv3n91TwywBRD9YrJNuNVmbD3Sprpq6hWIDHVu4p": ["spring"],  # Sakura Flowers
        "EQB4x3sT1DVdODzay3H-4VJIdOooS5-kTgyKcYMZWogPOsiq": ["spring"],  # Berry Boxes
        "EQDTro-ogJbS7o-OBD6bt2NysPt7SnGm5zfuRXGB1nE_rbGa": ["spring"]   # Kissed Frogs
    }

    if (not last_rate_update or 
        (timezone.now() - last_rate_update) > timedelta(minutes=10) or 
        (timezone.now() - last_rate_update) > timedelta(seconds=MAX_CACHE_AGE)):
        if not cache.get('rate_updating'):
            cache.set('rate_updating', True, timeout=60)
            try:
                ton_rub_rate = data.get("ton_rub_rate", 290.0)
                logger.info(f"Курс TON/RUB взят из JSON: {ton_rub_rate}")
            finally:
                cache.delete('rate_updating')

    if not ton_rub_rate or ton_rub_rate < MIN_RATE:
        ton_rub_rate = 50.0
        logger.warning(f"Используется дефолтный курс TON/RUB: {ton_rub_rate}")

    # Добавляем "Купить звёзды" в начало с лейблом "best_deal"
    collections.append({
        "id": "buy-stars",
        "name": "Купить звёзды",
        "image": "data:image/svg+xml,%3Csvg%20height%3D%2220%22%20viewBox%3D%220%200%2020%2020%22%20width%3D%2220%22%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20xmlns%3Axlink%3D%22http%3A%2F%2Fwww.w3.org%2F1999%2Fxlink%22%3E%3Cdefs%3E%3Cpath%20id%3D%22a%22%20d%3D%22m6.02%204.99%202.21-4.42c.25-.51.86-.72%201.37-.46.2.1.36.27.46.47l2.08%204.26c.17.34.5.58.88.63l4.36.52c.59.08%201.02.62.95%201.22-.03.24-.14.47-.32.65l-3.45%203.42c-.14.13-.2.33-.18.53l.57%204.61c.09.66-.38%201.27-1.03%201.35-.25.03-.5-.02-.72-.14l-3.64-2c-.26-.14-.58-.15-.85-.01l-3.77%201.95c-.53.27-1.18.06-1.45-.48-.11-.20-.14-.43-.11-.65l.3-2.12c.15-1.04.79-1.93%201.71-2.41l4.19-2.15c.11-.06.15-.20.1-.31-.05-.09-.14-.14-.24-.12l-5.12.74c-.78.11-1.58-.11-2.19-.62l-1.71-1.4c-.49-.40-.56-1.12-.17-1.62.19-.22.45-.37.74-.41l4.38-.57c.28-.03.52-.21.65-.46z%22%2F%3E%3ClinearGradient%20id%3D%22b%22%20x1%3D%2225%25%22%20x2%3D%2274.92%25%22%20y1%3D%22.825%25%22%20y2%3D%22107.86%25%22%3E%3Cstop%20offset%3D%220%22%20stop-color%3D%22%23ffd951%22%2F%3E%3Cstop%20offset%3D%221%22%20stop-color%3D%22%23ffb222%22%2F%3E%3C%2FlinearGradient%3E%3ClinearGradient%20id%3D%22c%22%20x1%3D%2250%25%22%20x2%3D%2250%25%22%20y1%3D%220%25%22%20y2%3D%2299.8%25%22%3E%3Cstop%20offset%3D%220%22%20stop-color%3D%22%23e58f0d%22%2F%3E%3Cstop%20offset%3D%22.9996%22%20stop-color%3D%22%23eb7915%22%2F%3E%3C%2FlinearGradient%3E%3Cfilter%20id%3D%22d%22%20height%3D%22110.6%25%22%20width%3D%22110.3%25%22%20x%3D%22-5.2%25%22%20y%3D%22-5.3%25%22%3E%3CfeOffset%20dx%3D%221%22%20dy%3D%221%22%20in%3D%22SourceAlpha%22%20result%3D%22shadowOffsetInner1%22%2F%3E%3CfeComposite%20in%3D%22shadowOffsetInner1%22%20in2%3D%22SourceAlpha%22%20k2%3D%22-1%22%20k3%3D%221%22%20operator%3D%22arithmetic%22%20result%3D%22shadowInnerInner1%22%2F%3E%3CfeColorMatrix%20in%3D%22shadowInnerInner1%22%20type%3D%22matrix%22%20values%3D%220%200%200%200%201%200%200%200%200%201%200%200%200%200%201%200%200%200%200.657%200%22%2F%3E%3C%2Ffilter%3E%3C%2Fdefs%3E%3Cg%20fill%3D%22none%22%20fill-rule%3D%22evenodd%22%20transform%3D%22translate%281.389%201.389%29%22%3E%3Cuse%20fill%3D%22url%28%23b%29%22%20fill-rule%3D%22evenodd%22%20xlink%3Ahref%3D%22%23a%22%2F%3E%3Cuse%20fill%3D%22%23000%22%20filter%3D%22url%28%23d%29%22%20xlink%3Ahref%3D%22%23a%22%2F%3E%3Cuse%20stroke%3D%22url%28%23c%29%22%20stroke-width%3D%22.89%22%20xlink%3Ahref%3D%22%23a%22%2F%3E%3C%2Fg%3E%3C%2Fsvg%3E",
        "min_price": "от 79 ₽",
        "min_price_rub": 79,
        "labels": ["best_deal"]
    })

    for col in data.get("collections", []):
        collection_nfts = nfts_data.get(col["id"], [])
        min_price = None
        if collection_nfts:
            available_nfts = [nft for nft in collection_nfts if not nft.get("sold", False)]
            if available_nfts:
                min_price_ton = min(float(nft["price"].replace(' TON', '').replace(',', '')) 
                                 for nft in available_nfts)
                min_price_rub = (min_price_ton * settings.MARGIN + 0.2) * ton_rub_rate + 30
                min_price = f"от {min_price_rub:.0f} ₽"
        
        collections.append({
            "id": col["id"],
            "name": col["name"],
            "image": col["image"],
            "min_price": min_price or "Нет в наличии",
            "min_price_rub": min_price_rub if min_price else float('inf'),
            "labels": labels_map.get(col["id"], [])
        })
    
    # Определяем приоритеты для лейблов
    label_priority = {
        "best_deal": 0,  # Звезды
        "hit": 1,        # Хит
        "spring": 2,     # Весна
        "for_her": 3,    # Для неё
        "for_him": 4     # Для него
    }

    # Сортировка: сначала по приоритету лейбла, затем по цене внутри групп
    collections.sort(key=lambda x: (
        label_priority.get(x["labels"][0], 5) if x["labels"] else 5,  # Приоритет лейбла или 5 для "остального"
        x["min_price_rub"]  # Сортировка по цене внутри групп
    ))

    logger.info(f"Возвращено {len(collections)} коллекций, отсортированных: звезды, хит, весна, для неё, для него, остальное по цене")
    return JsonResponse({'collections': [{k: v for k, v in col.items() if k != 'min_price_rub'} for col in collections]})

async def get_nfts(request, collection_id):
    logger.info(f"Запрос NFT для коллекции: {collection_id}")
    data = get_json_data()
    nfts = data.get("nfts", {}).get(collection_id, [])

    formatted_nfts = [
        {
            "name": nft["name"],
            "price": float(nft["price"].replace(' TON', '').replace(',', '')),
            "image": nft["image"],
            "sold": nft.get("sold", False)
        } for nft in nfts
    ]

    ton_rub_rate = cache.get('ton_rub_rate') or data.get("ton_rub_rate", 290.0)
    last_rate_update = cache.get('last_rate_update')
    MIN_RATE = 100.0
    MAX_CACHE_AGE = 86400

    if (not last_rate_update or 
        (timezone.now() - last_rate_update) > timedelta(minutes=10) or 
        (timezone.now() - last_rate_update) > timedelta(seconds=MAX_CACHE_AGE)):
        if not cache.get('rate_updating'):
            cache.set('rate_updating', True, timeout=60)
            try:
                ton_rub_rate = data.get("ton_rub_rate", 290.0)
                logger.info(f"Курс TON/RUB взят из JSON: {ton_rub_rate}")
            finally:
                cache.delete('rate_updating')

    if not ton_rub_rate or ton_rub_rate < MIN_RATE:
        ton_rub_rate = 50.0
        logger.warning(f"Используется дефолтный курс TON/RUB: {ton_rub_rate}")

    if formatted_nfts:
        for nft in formatted_nfts:
            ton_price = float(nft['price'])
            rub_price = ((ton_price * settings.MARGIN) + 0.2) * ton_rub_rate + 30
            nft['price'] = f"{rub_price:.0f} ₽"
    logger.info(f"Возвращено {len(formatted_nfts)} NFT для коллекции {collection_id}")
    return JsonResponse({'nfts': formatted_nfts})

async def create_payment(request):
    logger.info(f"Запрос создания платежа: {request.method}")
    if request.method != 'POST':
        logger.warning("Метод не POST")
        return JsonResponse({'error': 'Метод не поддерживается'}, status=405)

    username = request.POST.get('username')
    buyer_username = request.POST.get('buyer_username')
    price = request.POST.get('price')
    gift_name = request.POST.get('gift_name')
    collection_id = request.POST.get('collection_id')
    stars_count = request.POST.get('stars_count')
    logger.info(f"Получены данные: username={username}, buyer_username={buyer_username}, price={price}, gift_name={gift_name}, collection_id={collection_id}, stars_count={stars_count}")

    if not all([username, buyer_username, price]):
        logger.error("Недостаточно данных для создания платежа")
        return JsonResponse({'error': 'Недостаточно данных'}, status=400)

    try:
        price_float = float(price.replace(' ₽', ''))
        logger.info(f"Цена преобразована: {price_float} ₽")
    except ValueError:
        logger.error(f"Неверный формат цены: {price}")
        return JsonResponse({'error': 'Неверный формат цены'}, status=400)

    client_ip = request.META.get('REMOTE_ADDR', 'unknown')
    ip_key = f"payment_attempts_{client_ip}"
    attempts = cache.get(ip_key, 0)
    logger.info(f"IP {client_ip}: попыток {attempts}")
    if attempts >= 5:
        logger.warning(f"IP {client_ip} превысил лимит в 5 попыток")
        return JsonResponse({'error': 'Превышен лимит покупок. Попробуйте позже.'}, status=429)
    cache.set(ip_key, attempts + 1, timeout=3600)
    logger.info(f"IP {client_ip}: обновлено попыток до {attempts + 1}")

    data = get_json_data()
    ton_rub_rate = cache.get('ton_rub_rate') or data.get("ton_rub_rate", 290.0)

    if collection_id == "buy-stars":
        if not stars_count:
            logger.error("Не указано количество звёзд")
            return JsonResponse({'error': 'Укажите количество звёзд'}, status=400)
        try:
            stars = int(stars_count)
            if stars < 50 or stars > 2000:
                logger.error(f"Количество звёзд {stars} вне диапазона 50-2000")
                return JsonResponse({'error': 'Количество звёзд должно быть от 50 до 2000'}, status=400)
            expected_price = stars * 1.59
            if abs(price_float - expected_price) > 0.01:
                logger.warning(f"Цена звёзд изменилась: ожидалось {expected_price} ₽, получено {price_float} ₽")
                return JsonResponse({
                    'error': f'Цена изменилась на {expected_price:.2f} ₽',
                    'action': 'price_changed',
                    'new_price': f"{expected_price:.2f} ₽"
                }, status=400)
        except ValueError:
            logger.error(f"Неверный формат количества звёзд: {stars_count}")
            return JsonResponse({'error': 'Неверное количество звёзд'}, status=400)
    else:
        nfts = data.get("nfts", {}).get(collection_id, [])
        logger.info(f"Найдено {len(nfts)} NFT в коллекции {collection_id}")

        nft_found = None
        for nft in nfts:
            if nft["name"] == gift_name:
                nft_found = nft
                break

        if not nft_found:
            logger.error(f"Товар '{gift_name}' не найден в коллекции {collection_id}")
            return JsonResponse({'error': 'Товар больше не доступен', 'action': 'remove'}, status=400)

        if nft_found.get("sold", False):
            logger.warning(f"Товар '{gift_name}' уже продан (по данным JSON)")
            return JsonResponse({'error': 'Товар уже продан', 'action': 'sold'}, status=400)

        # Добавляем проверку статуса на GetGems
        nft_id = nft_found.get("id")  # Предполагаем, что id присутствует в данных NFT
        logger.info(f"Проверка NFT с id: {nft_id}")
        status = await fetch_nft_status(collection_id, nft_id)
        logger.info(f"Статус NFT '{gift_name}' на GetGems: {status}")
        
        if status == "Подарок не продаётся":
            logger.warning(f"Товар '{gift_name}' недоступен на GetGems: {status}")
            nft_found["sold"] = True
            save_json_data(data)
            return JsonResponse({'error': 'Товар больше не доступен', 'action': 'sold'}, status=400)
        elif status == "Неизвестный статус":
            logger.warning(f"Не удалось проверить статус NFT '{gift_name}' на GetGems. Продолжаем с локальными данными.")

        current_ton_price = float(nft_found["price"].replace(' TON', '').replace(',', ''))
        current_rub_price = ((current_ton_price * settings.MARGIN) + 0.2) * ton_rub_rate + 30
        if abs(current_rub_price - price_float) > 1:
            logger.warning(f"Цена товара '{gift_name}' изменилась: было {price_float} ₽, стало {current_rub_price:.0f} ₽")
            return JsonResponse({
                'error': f'Цена товара изменилась с {price_float} ₽ на {current_rub_price:.0f} ₽',
                'action': 'price_changed',
                'new_price': f"{current_rub_price:.0f} ₽"
            }, status=400)

        for nft in data["nfts"][collection_id]:
            if nft["name"] == gift_name and "sold" not in nft:
                nft["sold"] = True
                save_json_data(data)
                logger.info(f"Товар '{gift_name}' помечен как проданный при создании платежа")
                break

    # Проверяем рефку по IP (только первый реф-код учитывается)
    referrals_data = get_referrals_data()
    referrer = None
    for ref, ref_data in referrals_data.items():
        if client_ip in ref_data["ips"]:
            referrer = ref
            logger.info(f"IP {client_ip} связан с рефкой {referrer} (первый реф-код)")
            break

    payment_data = {
        "terminalPublicId": WATA_TERMINAL_ID,
        "amount": price_float,
        "currency": "RUB",
        "description": f"Покупка {stars_count} звёзд для {username}" if collection_id == "buy-stars" else f"Подарок '{gift_name}' для {username} (от {buyer_username})",
        "returnUrl": f"{settings.SITE_URL.rstrip('/')}/",
        "failUrl": f"{settings.SITE_URL.rstrip('/')}/fail/"
    }
    logger.info(f"Отправка запроса к WATA: {payment_data}")
    try:
        response = requests.post(f"{WATA_API_URL}/links", headers=WATA_HEADERS, json=payment_data)
        logger.info(f"Ответ от WATA: статус {response.status_code}, тело {response.text}")
        
        if response.status_code == 200:
            message = f"Создана новая ссылка на оплату!" + f"\nПокупка {stars_count} звёзд для {username}" if collection_id == "buy-stars" else f"Подарок '{gift_name}' для {username} (от {buyer_username})\n"
            await send_telegram_notification(message)
            result = response.json()
            confirmation_url = result["url"]
            payment_id = result["id"]
            
            # Добавляем транзакцию в referrals.json, если есть рефка
            if referrer:
                referrals_data[referrer]["transactions"].append(payment_id)
                save_referrals_data(referrals_data)
                logger.info(f"Транзакция {payment_id} добавлена к рефке {referrer}")
            else:
                logger.info(f"Транзакция {payment_id} создана без рефки")

            logger.info(f"Создан платеж: {payment_id}, URL: {confirmation_url}")
            return JsonResponse({'confirmation_url': confirmation_url, 'payment_id': payment_id})
        else:
            logger.error(f"Ошибка создания платежа WATA: {response.status_code} - {response.text}")
            return JsonResponse({'error': 'Ошибка создания платежа'}, status=500)
    except Exception as e:
        logger.error(f"Исключение при запросе к WATA: {e}")
        return JsonResponse({'error': 'Ошибка сервера'}, status=500)

# Функции для работы с referrals.json
def get_referrals_data():
    logger.info("Чтение referrals.json")
    try:
        with open(os.path.join(settings.BASE_DIR, 'referrals.json'), 'r', encoding='utf-8') as f:
            data = json.load(f)
            logger.info("referrals.json успешно прочитан")
            return data
    except Exception as e:
        logger.error(f"Ошибка чтения referrals.json: {e}")
        return {}

def save_referrals_data(data):
    logger.info("Сохранение данных в referrals.json")
    try:
        with open(os.path.join(settings.BASE_DIR, 'referrals.json'), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        logger.info("Данные успешно сохранены в referrals.json")
    except Exception as e:
        logger.error(f"Ошибка сохранения referrals.json: {e}")

# Функции для работы с referrals.json (добавь их в код, если еще не добавил)
def get_referrals_data():
    logger.info("Чтение referrals.json")
    try:
        with open(os.path.join(settings.BASE_DIR, 'referrals.json'), 'r', encoding='utf-8') as f:
            data = json.load(f)
            logger.info("referrals.json успешно прочитан")
            return data
    except Exception as e:
        logger.error(f"Ошибка чтения referrals.json: {e}")
        return {}

def save_referrals_data(data):
    logger.info("Сохранение данных в referrals.json")
    try:
        with open(os.path.join(settings.BASE_DIR, 'referrals.json'), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        logger.info("Данные успешно сохранены в referrals.json")
    except Exception as e:
        logger.error(f"Ошибка сохранения referrals.json: {e}")

@csrf_exempt
async def payment_result(request):
    logger.info(f"Webhook запрос: {request.method}")
    if request.method != 'POST':
        logger.warning("Метод не POST")
        return JsonResponse({'error': 'Метод не поддерживается'}, status=405)

    signature = request.headers.get('X-Signature')
    logger.info(f"Получена подпись: {signature}")
    if not signature:
        logger.error("Отсутствует подпись в запросе Webhook")
        return JsonResponse({'error': 'Отсутствует подпись'}, status=400)

    body = request.body
    logger.info(f"Тело запроса: {body}")
    public_key_pem = get_wata_public_key()
    if not public_key_pem:
        logger.error("Не удалось получить публичный ключ WATA")
        return JsonResponse({'error': 'Ошибка сервера'}, status=500)

    try:
        public_key = load_pem_public_key(public_key_pem)
        public_key.verify(
            bytes.fromhex(signature),
            body,
            padding.PKCS1v15(),
            hashes.SHA512()
        )
        logger.info("Подпись Webhook успешно проверена")
    except Exception as e:
        logger.error(f"Неверная подпись Webhook: {e}")
        return JsonResponse({'error': 'Неверная подпись'}, status=400)

    data = json.loads(body.decode('utf-8'))
    transaction_uuid = data.get('transactionUuid')
    status = data.get('status')
    logger.info(f"Получено уведомление Webhook: UUID={transaction_uuid}, Status={status}")

    logger.info("Перенаправление на главную страницу")
    return redirect('/')

def details(request):
    logger.info(f"Запрос страницы деталей: {request.path}")
    return render(request, 'details.html')

def get_referrals_data():
    logger.info("Чтение referrals.json")
    try:
        with open(os.path.join(settings.BASE_DIR, 'referrals.json'), 'r', encoding='utf-8') as f:
            data = json.load(f)
            logger.info("referrals.json успешно прочитан")
            return data
    except Exception as e:
        logger.error(f"Ошибка чтения referrals.json: {e}")
        return {}  # Пустой словарь, если файла нет или он сломан

def save_referrals_data(data):
    logger.info("Сохранение данных в referrals.json")
    try:
        with open(os.path.join(settings.BASE_DIR, 'referrals.json'), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        logger.info("Данные успешно сохранены в referrals.json")
    except Exception as e:
        logger.error(f"Ошибка сохранения referrals.json: {e}")

# Обновленная вьюха для страницы отзывов
def reviews(request):
    client_ip = request.META.get('REMOTE_ADDR', 'unknown')
    reviews_data = get_reviews_data()

    if request.method == 'POST':
        username = request.POST.get('username')
        review_text = request.POST.get('review_text')
        
        if username and review_text:
            # Проверяем, оставлял ли этот IP отзыв
            ip_has_review = any(review.get('ip') == client_ip for review in reviews_data)
            if ip_has_review:
                logger.info(f"IP {client_ip} уже оставил отзыв, отклоняем новый")
                return render(request, 'reviews.html', {
                    'reviews': reviews_data,
                    'error_message': 'Вы уже оставили отзыв. Один IP — один отзыв.'
                })
            
            # Добавляем новый отзыв
            new_review = {
                "username": username,
                "text": review_text,
                "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "ip": client_ip
            }
            reviews_data.insert(0, new_review)  # Новый отзыв в начало
            save_reviews_data(reviews_data)
            logger.info(f"Добавлен новый отзыв от {username} с IP {client_ip}")
            return redirect('reviews')

    # Сортируем отзывы по убыванию даты
    sorted_reviews = sorted(reviews_data, key=lambda x: x['date'], reverse=True)
    return render(request, 'reviews.html', {'reviews': sorted_reviews})

def get_reviews_data():
    try:
        with open(os.path.join(settings.BASE_DIR, 'reviews.json'), 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []

def save_reviews_data(data):
    try:
        with open(os.path.join(settings.BASE_DIR, 'reviews.json'), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Ошибка сохранения reviews.json: {e}")