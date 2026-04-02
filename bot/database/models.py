from bot.keyboards.contact import contact_button


@router.message(BuyerStates.waiting_for_model)
async def buyer_model(message: Message, state: FSMContext):
    data = await state.get_data()

    brand = data.get("brand")
    model = message.text

    cursor.execute(
        "SELECT telegram_id, username, brand, model FROM seller_cars WHERE LOWER(brand)=? AND LOWER(model)=?",
        (brand.lower(), model.lower())
    )

    results = cursor.fetchall()

    if not results:
        await message.answer("Нічого не знайдено ❌")
        await state.clear()
        return

    # 🔥 групування продавців
    sellers_dict = {}

    for user_id, username, brand, model in results:
        if user_id not in sellers_dict:
            sellers_dict[user_id] = {
                "username": username,
                "cars": []
            }

        sellers_dict[user_id]["cars"].append(f"{brand} {model}")

    # 🔥 красивий вивід
    for user_id, data in sellers_dict.items():
        username = data["username"]
        cars = data["cars"]

        text = "Продавець:\n"

        if username:
            text += f"@{username}\n\n"
        else:
            text += f"ID: {user_id}\n\n"

        text += "Авто:\n"
        for car in cars:
            text += f"- {car}\n"

        await message.answer(
            text,
            reply_markup=contact_button(username)
        )

    await state.clear()
