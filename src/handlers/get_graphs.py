import os

from aiogram import Router, Bot, F
from aiogram.types import Message, FSInputFile, InputMediaPhoto, CallbackQuery

from src.keyboards.keyboards import get_subscribe_keyboard
from src.services.db import subscriptions_collection

router: Router = Router()


@router.message(F.text == '📊 Мої графіки 📅')
async def get_graphs(message: Message, bot: Bot, callback_query: CallbackQuery = None):
    if callback_query:
        user_id = callback_query.from_user.id
    else:
        user_id = message.from_user.id

    # Get a list of groups the user is subscribed to
    subscriptions = subscriptions_collection.find({"id_telegram": user_id})
    groups = {sub["group_number"] for sub in subscriptions}

    if not groups:
        return await message.reply(
            text="Спочатку Вам потрібно підписатись на групу",
            reply_markup=get_subscribe_keyboard()
        )

    # Filter and sort groups from 1 to 6+
    valid_groups = sorted(group for group in groups if 1 <= int(group.split('.')[0]) <= 6)

    # Get a list of all files for graphs
    file_paths = [f"graphs_images/graph_{group}.png" for group in valid_groups if
                  os.path.isfile(f"graphs_images/graph_{group}.png")]

    # Split into parts of 10 photos in one message
    chunks = [file_paths[i:i + 10] for i in range(0, len(file_paths), 10)]

    for index, chunk in enumerate(chunks):
        # Create a media list with a description only for the first photo (rules of Telegram API)
        media_group = []
        for i, path in enumerate(chunk):
            # Check if the file exists and is not empty
            if os.path.isfile(path) and os.path.getsize(path) > 0:
                # Signature is added only to the first photo of the first chunk
                caption = 'Графіки відключень світла для черг, які ти відстежуєш 💡' if index == 0 and i == 0 else ''
                media_group.append(InputMediaPhoto(media=FSInputFile(path), caption=caption))
            else:
                print(f"File {path} does not exist or is empty. Skipping it.")

        # Send a media group to the user only if the media group is not empty
        if media_group:
            await bot.send_media_group(
                chat_id=message.chat.id,
                media=media_group,
            )
        else:
            await message.reply("Не знайдено валідних файлів для відправки.")

# Todo push all the code into the github, and start creating notifications changes system
# Todo Maybe create two workers instead one
