@router.message(F.photo)
async def save_banner(message: Message, state: FSMContext):
    current_state = await state.get_state()

    if current_state != "site_banner":
        return

    seller = await get_seller_by_telegram_id(message.from_user.id)
    if not seller:
        return

    site = await get_site_by_seller(seller["id"])
    if not site:
        return

    config = parse_config(site.get("config_draft"))

    config.setdefault("hero", {})
    config["hero"].setdefault("banners", [])

    photo = message.photo[-1].file_id
    config["hero"]["banners"].append(photo)

    await update_site_config(site["id"], config)

    await state.clear()
    await message.answer("Банер додано ✅")
