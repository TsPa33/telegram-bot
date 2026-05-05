from bot.database.repositories.admin_repo import (
create_verification_request,
approve_seller,
reject_seller,
get_verification_requests
)

# ================= SUBMIT =================

async def submit_verification(seller: dict, photo_id: str) -> int:
if seller.get("is_verified"):
raise ValueError("ALREADY_VERIFIED")

```
request_id = await create_verification_request(
    seller_id=seller["id"],
    photo_id=photo_id
)

return request_id
```

# ================= APPROVE =================

async def approve_verification(request_id: int) -> int | None:
telegram_id = await approve_seller(request_id)

```
return telegram_id
```

# ================= REJECT =================

async def reject_verification(request_id: int) -> int | None:
telegram_id = await reject_seller(request_id)

```
return telegram_id
```

# ================= GET =================

async def get_pending_verifications():
return await get_verification_requests()
