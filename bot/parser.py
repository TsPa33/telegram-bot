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


# ================= TEST =================

if __name__ == "__main__":
    print(parse_input("тяга рулевая mercedes w203"))
    print(build_url("mercedes", "w203", "тяга рулевая"))


def parse_list(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")

        items = []

        # 🔥 головні блоки оголошень
        cards = soup.select(".product-item")

        for card in cards[:5]:

            title_tag = card.select_one(".product-title")
            price_tag = card.select_one(".price")
            link_tag = card.select_one("a")

            title = title_tag.text.strip() if title_tag else "Без назви"
            price = price_tag.text.strip() if price_tag else "Ціна не вказана"

            link = link_tag.get("href") if link_tag else None

            if link and not link.startswith("http"):
                link = "https://podkapot.com.ua" + link

            items.append({
                "title": title,
                "price": price,
                "link": link
            })

        return items

    except Exception as e:
        print("parse_list error:", e)
        return []

    except Exception as e:
        print("parse_list error:", e)
        return []
