import asyncio
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin


async def is_valid_image(url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=3, follow_redirects=True) as client:
            r = await client.head(url)
        return r.status_code == 200 and "image" in r.headers.get("content-type", "")
    except Exception:
        return False


async def extract_logo(url: str):
    try:
        async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
            r = await client.get(url)

        soup = BeautifulSoup(r.text, "html.parser")

        # 1. og:image
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            logo = og["content"]
            if await is_valid_image(logo):
                return logo

        # 2. favicon
        icon = soup.find("link", rel=lambda x: x and "icon" in x.lower())
        if icon and icon.get("href"):
            logo = urljoin(url, icon["href"])
            if await is_valid_image(logo):
                return logo

        # 3. img logo
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if "logo" in src.lower():
                logo = urljoin(url, src)
                if await is_valid_image(logo):
                    return logo

    except Exception as e:
        print("ERROR:", e)

    return None


async def main():
    urls = [
        "https://tesla-sklad.com.ua",
        "https://motorparts.com.ua",
        "https://tn-group.com.ua",
        "https://razborka-odessa.com.ua",
    ]

    for url in urls:
        print("\n=== TEST:", url)

        logo = await extract_logo(url)

        if logo:
            print("✅ LOGO:", logo)
        else:
            print("❌ NOT FOUND")


if __name__ == "__main__":
    asyncio.run(main())
