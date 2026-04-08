from urllib.parse import quote


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


# ================= TEST =================

if __name__ == "__main__":
    print(parse_input("тяга рулевая mercedes w203"))
    print(build_url("mercedes", "w203", "тяга рулевая"))

import requests
from bs4 import BeautifulSoup


def parse_list(url):
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")

        items = []

        cards = soup.select(".product-item")[:5]

        for card in cards:
            title_el = card.select_one(".product-title")
            price_el = card.select_one(".product-price")
            link_el = card.select_one("a")

            if not title_el or not link_el:
                continue

            title = title_el.text.strip()
            price = price_el.text.strip() if price_el else "—"
            link = "https://podkapot.com.ua" + link_el.get("href")

            items.append({
                "title": title,
                "price": price,
                "link": link
            })

        return items

    except Exception as e:
        print("parse_list error:", e)
        return []
