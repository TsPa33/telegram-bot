import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin


DEFAULT_LOGO = "https://your-cdn.com/default_logo.png"  # заміни на свою заглушку


async def _is_valid_image(url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=3, follow_redirects=True) as client:
            r = await client.head(url)

        ct = r.headers.get("content-type", "")

        # відсікаємо svg/favicon
        if "svg" in ct:
            return False
        if "icon" in url.lower():
            return False

        return r.status_code == 200 and "image" in ct
    except Exception:
        return False


async def extract_logo(url: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
            r = await client.get(url)

        soup = BeautifulSoup(r.text, "html.parser")

        # 1. og:image
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            logo = og["content"]
            if await _is_valid_image(logo):
                return logo

        # 2. favicon
        icon = soup.find("link", rel=lambda x: x and "icon" in x.lower())
        if icon and icon.get("href"):
            logo = urljoin(url, icon["href"])
            if await _is_valid_image(logo):
                return logo

        # 3. img з "logo"
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if "logo" in src.lower():
                logo = urljoin(url, src)
                if await _is_valid_image(logo):
                    return logo

    except Exception:
        return None

    return None


async def get_logo(url: str) -> str:
    logo = await extract_logo(url)
    return logo or DEFAULT_LOGO
