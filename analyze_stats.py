import json
from collections import Counter
import datetime

def load_stats(file_path="stats.json"):
    """Загружает данные из stats.json."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Ошибка загрузки файла: {e}")
        return {"visits": []}

def analyze_visits(stats):
    """Анализирует посещения с упором на уникальные IP и разделение по часам."""
    visits = stats["visits"]
    total_visits = len(visits)
    unique_ips = len(set(v["ip"] for v in visits))
    referrers = Counter(v["referrer"] for v in visits)
    pages = Counter(v["page"] for v in visits)

    # Разделение посещений по часам
    hourly_visits = {i: 0 for i in range(24)}  # Инициализация для всех часов
    hourly_unique_ips = {i: set() for i in range(24)}  # Уникальные IP по часам

    for visit in visits:
        try:
            visit_time = datetime.datetime.strptime(visit["timestamp"], "%Y-%m-%d %H:%M:%S")
            hour = visit_time.hour
            hourly_visits[hour] += 1
            hourly_unique_ips[hour].add(visit["ip"])
        except ValueError as e:
            print(f"Ошибка формата времени в записи {visit}: {e}")

    print(f"Всего посещений: {total_visits}")
    print(f"Уникальных IP: {unique_ips}")
    print("\nПосещения по источникам:")
    for ref, count in referrers.most_common():
        print(f"  {ref}: {count} ({count/total_visits*100:.1f}%)")
    print("\nПосещения по страницам:")
    for page, count in pages.most_common():
        print(f"  {page}: {count} ({count/total_visits*100:.1f}%)")

    # Вывод посещений по часам
    print("\nПосещения по часам (местное время):")
    for hour in range(24):
        visits_count = hourly_visits[hour]
        unique_ip_count = len(hourly_unique_ips[hour])
        percentage = (visits_count / total_visits * 100) if total_visits > 0 else 0
        print(f"  {hour:02d}:00 - {hour:02d}:59: {visits_count} посещений ({percentage:.1f}%), уникальных IP: {unique_ip_count}")

def main():
    stats = load_stats()
    print("Анализ статистики сайта для оценки рекламы в TikTok")
    print("=" * 50)
    analyze_visits(stats)

if __name__ == "__main__":
    main()