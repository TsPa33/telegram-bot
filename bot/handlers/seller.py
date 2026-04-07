@router.message(SellerStates.waiting_for_model, F.text)
async def seller_model(message: Message, state: FSMContext):

    if not validate_text(message.text):
        await message.answer("Некоректна модель ❗")
        return

    data = await state.get_data()

    user_id = message.from_user.id
    username = message.from_user.username

    brand = normalize(data.get("brand"))
    model = normalize(message.text)

    conn = get_connection()
    cursor = conn.cursor()

    # 🔹 отримати або створити seller
    cursor.execute(
        "SELECT id FROM sellers WHERE telegram_id = %s",
        (user_id,)
    )
    seller = cursor.fetchone()

    if not seller:
        cursor.execute(
            """
            INSERT INTO sellers (telegram_id, username)
            VALUES (%s, %s)
            RETURNING id
            """,
            (user_id, username)
        )
        seller_id = cursor.fetchone()[0]
    else:
        seller_id = seller[0]

    # 🔹 вставка авто (ВИПРАВЛЕНО)
    cursor.execute(
        """
        INSERT INTO seller_cars (seller_id, brand, model)
        VALUES (%s, %s, %s)
        """,
        (seller_id, brand, model)
    )

    conn.commit()

    await message.answer("Авто збережено в БД ✅")

    cursor.close()
    conn.close()

    await state.clear()
