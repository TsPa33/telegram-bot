from urllib.parse import quote
import requests
from bs4 import BeautifulSoup


# ================= INPUT =================

def parse_input(text: str):
    words = text.lower().split()

    if len(words) < 3:
        return None, None, text

    brand = words[-2]
    model = words[-1]
    detail = " ".join(words[:-2])

    return brand, model, detail


# ================= URL =================

def build_url(brand, model, detail):
    query = f"{detail} {brand} {model}"
    return f"https://podkapot.com.ua/search?query={quote(query)}"


# ================= PARSE LIST =================

def parse_list(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")

        items = []

        cards = soup.select(".goods-item")

        for card in cards[:5]:
            title_el = card.select_one(".goods-title a")
            price_el = card.select_one(".goods-price")

            if not title_el:
                continue

            title = title_el.text.strip()

            href = title_el.get("href")
            link = f"https://podkapot.com.ua{href}" if href else None

            price = price_el.text.strip() if price_el else "Нема ціни"

            items.append({
                "title": title,
                "price": price,
                "link": link
            })

        return items

    except Exception as e:
        print("parse_list error:", e)
        return []


# ================= TEST =================

if __name__ == "__main__":
    print("TEST parse_input:")
    print(parse_input("тяга рулевая mercedes w203"))

    print("\nTEST build_url:")
    url = build_url("mercedes", "w203", "тяга рулевая")
    print(url)

    print("\nTEST parse_list:")
    results = parse_list(url)

    for item in results:
        print(item)
