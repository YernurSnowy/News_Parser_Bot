import asyncio, logging, datetime
from dateutil import parser
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import (Message, CallbackQuery, 
                           InlineKeyboardMarkup, InlineKeyboardButton, 
                           ReplyKeyboardMarkup, KeyboardButton)

import requests
import fake_useragent
from bs4 import BeautifulSoup

import psycopg2

from config import TOKEN, POSTGRESQL_URI

# Устанавливаем соединение с базой данных PostgreSQL
connection = psycopg2.connect(POSTGRESQL_URI)
cursor = connection.cursor()

# Асинхронная функция для добавления пользователя в базу данных
async def add_user(user_id, user_name):
    try:
        # Проверяем, существует ли пользователь
        cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        existing_user = cursor.fetchone()

        # Если пользователь не существует, вставляем его в базу данных
        if not existing_user:
            cursor.execute("INSERT INTO users (user_id, user_name, notifications) VALUES (%s, %s, FALSE)", (user_id, user_name))
            connection.commit()
    except psycopg2.Error as e:
        print("Ошибка при добавлении пользователя в базу данных:", e)

# Асинхронная функция для установки статуса уведомлений "True"
async def update_notifications_to_true(user_id):
    try:
        cursor.execute("UPDATE users SET notifications = TRUE WHERE user_id = %s", (user_id,))
        connection.commit()
    except psycopg2.Error as e:
        print("Ошибка при установке статуса уведомлений 'True':", e)

# Асинхронная функция для установки статуса уведомлений "False"
async def update_notifications_to_false(user_id):
    try:
        cursor.execute("UPDATE users SET notifications = FALSE WHERE user_id = %s", (user_id,))
        connection.commit()
    except psycopg2.Error as e:
        print("Ошибка при установке статуса уведомлений 'False':", e)

# Создание экземпляров бота и диспетчера
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Обработчик команды /start
@dp.message(CommandStart())
async def cmd_start(message: Message):
    # Добавляем пользователя в базу данных при старте чата с ботом
    await add_user(message.from_user.id, message.from_user.username)
    # Отправляем приветственное сообщение и клавиатуру
    await message.answer(f"Привет, {message.from_user.first_name}!\n"
                         "Данный бот предназначен для просмотра новостей.\n"
                         "Кнопка '📋 Новости' позволит приступить к просмотру новостей.\n"
                         "Кнопка '🔔 Уведомления' позволит настроить получение уведомлений.",
                         reply_markup=get_main_keyboard())

# Функция для формирования основной клавиатуры
def get_main_keyboard():
    main = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text='📋 Новости'), KeyboardButton(text='🔔 Уведомления')]
    ],
    resize_keyboard=True,
    input_field_placeholder='Выберите пункт меню.')
    return main

# Обработчик команды "Уведомления"
@dp.message(F.text == '🔔 Уведомления')
async def get_notification(message: Message):
    await message.answer('Вы хотите получать уведомления при выходе новостей?',
                         reply_markup=get_notification_keyboard())

# Функция для формирования клавиатуры запроса подписки на уведомления
def get_notification_keyboard():
    notification = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='✅ Да', callback_data='subscribe'), InlineKeyboardButton(text='❌ Нет', callback_data='unsubscribe')]
    ]) 
    return notification

# Обработчик подписки на уведомления
@dp.callback_query(F.data == 'subscribe')
async def subscribe(callback: CallbackQuery):
    await callback.answer('')
    await update_notifications_to_true(callback.from_user.id)
    await callback.message.edit_text('✅ Теперь вы будете получать уведомления!')

# Обработчик отписки от уведомлений
@dp.callback_query(F.data == 'unsubscribe')
async def subscribe(callback: CallbackQuery):
    await callback.answer('')
    await update_notifications_to_false(callback.from_user.id)
    await callback.message.edit_text('❌ Теперь вы не будете получать уведомления!')


# Функция для парсинга содержимого новости на сайте Informburo
def parse_informburo_article_content(article_url):
    url = article_url
    header = {'user-agent': fake_useragent.UserAgent().random}
    response = requests.get(url, headers=header).text

    soup = BeautifulSoup(response, 'lxml')
    content_block = soup.find('div', class_='article')
    paragraphs = content_block.find_all('p')
    
    # Собираем содержимое параграфов в строку
    content = ''.join(paragraph.text for paragraph in paragraphs)
    
    # Ограничиваем длину содержимого до 600 символов
    content = content[:600] + '...'
    
    return content

# Асинхронная функция для парсинга новостей с сайта Informburo
async def parse_news_informburo():
    url = 'https://informburo.kz/novosti'
    header = {'user-agent': fake_useragent.UserAgent().random}
    response = requests.get(url, headers=header).text

    soup = BeautifulSoup(response, 'lxml')

    # Список, в который будут добавляться данные о новых статьях
    new_articles_data = []

    # Проходим по всем блокам с новостями на сайте
    for block in soup.find_all('li', class_='uk-grid uk-grid-small uk-margin-remove-top'):
        article_block = block.find('div', class_='uk-width-expand')
        photo_block = block.find('div', class_='uk-width-auto')
        article_photo = photo_block.find('img')['data-src']
        article_title = article_block.find('a').contents[0].strip()
        article_time = article_block.find('time', class_='article-time').text.strip()
        article_url = article_block.find('a')['href']
        article_content = parse_informburo_article_content(article_url)
        # Проверяем наличие хэштега
        try:
            article_mark = article_block.find('span', class_='article-mark').text.strip()
        except AttributeError:
            article_mark = '#отсутствует'

        # Проверяем, есть ли уже такой title в базе данных
        cursor.execute("SELECT id FROM informburo_news WHERE title = %s", (article_title,))
        result = cursor.fetchone()
        if not result:
            # Создаем запись о статье в базе данных
            cursor.execute("INSERT INTO informburo_news (title, photo, time, mark, link, content) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                        (article_title, 'https://informburo.kz' + article_photo, article_time, article_mark, article_url, article_content))
            # Получаем ID новой записи
            new_article_id = cursor.fetchone()[0]

            # Создаем словарь с данными о текущей статье
            article_info = {
                'ID': new_article_id,
                'Title': article_title,
                'Photo': 'https://informburo.kz' + article_photo,
                'Time': article_time,
                'Mark': article_mark,
                'Link': article_url,
                'Content': article_content
            }
            # Добавляем информацию о новой статье в список новых статей
            new_articles_data.append(article_info)

    # Если есть новые статьи, отправляем уведомления пользователям, которые подписаны на уведомления
    if new_articles_data:
        # Отправка уведомлений пользователям, которые подписаны на уведомления
        cursor.execute("SELECT user_id FROM users WHERE notifications = TRUE")
        users = cursor.fetchall()
        for user_id in users:
            for article_info in new_articles_data:
                links = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text='Читать', url=article_info['Link'])]
                ])
                await bot.send_photo(user_id[0],
                                    photo=article_info['Photo'],
                                    caption=f'🔔 Новая публикация!\n📋 Заголовок: {article_info["Title"]}\n🕰 Время публикации: {article_info["Time"]}\n{article_info["Mark"]}\nСайт: informburo.kz',
                                    reply_markup=links)

    # Фиксируем изменения в базе данных
    connection.commit()



# Функция для парсинга содержимого новости на сайте Nur
def parse_nur_article_content(article_url):
    url = article_url
    header = {'user-agent': fake_useragent.UserAgent().random}
    response = requests.get(url, headers=header).text

    soup = BeautifulSoup(response, 'lxml')
    content_block = soup.find('div', class_='formatted-body__content--wrapper')
    paragraphs = content_block.find_all('p', class_='align-left formatted-body__paragraph')
    
    # Собираем содержимое параграфов в строку
    content = ''.join(paragraph.text for paragraph in paragraphs)
    
    # Ограничиваем длину содержимого до 600 символов
    content = content[:600] + '...'
    
    return content

def parse_nur_article_photo(article_url):
    url = article_url
    header = {'user-agent': fake_useragent.UserAgent().random}
    response = requests.get(url, headers=header).text

    soup = BeautifulSoup(response, 'lxml')
    photo_block = soup.find('picture')
    photo = photo_block.find('img')['src']

    return photo


# Асинхронная функция для парсинга новостей с сайта Nur
async def parse_news_nur():
    url = 'https://www.nur.kz/latest/'
    header = {'user-agent': fake_useragent.UserAgent().random}
    response = requests.get(url, headers=header).text

    soup = BeautifulSoup(response, "lxml")

    # Список, в который будут добавляться данные о новых статьях
    new_articles_data = []

    # Проходим по всем блокам с новостями на сайте
    for article in soup.find_all("a", class_="article-preview-category__content"):
        article_category = article.find("span", class_="article-preview-category__text").text.strip()
        article_title = article.find("h2", class_="article-preview-category__subhead").text.strip()
        article_url = f'{article.get("href")}'
        article_date_time = article.find("time").get("datetime")
        article_content = parse_nur_article_content(article_url)
        article_photo = parse_nur_article_photo(article_url)

        # Проверяем, есть ли уже такой title в базе данных
        cursor.execute("SELECT id FROM nur_news WHERE title = %s", (article_title,))
        result = cursor.fetchone()
        if not result:
            # Создаем запись о статье в базе данных
            cursor.execute("INSERT INTO nur_news (title, photo, time, category, link, content) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                           (article_title, article_photo, article_date_time, article_category, article_url, article_content))
            # Получаем ID новой записи
            new_article_id = cursor.fetchone()[0]

            # Parse the time string including timezone information
            time_datetime = parser.parse(article_date_time)

            formatted_date = time_datetime.strftime('%d.%m.%Y %H:%M')

            # Создаем словарь с данными о текущей статье
            article_info = {
                'ID': new_article_id,
                'Title': article_title,
                'Photo': article_photo,
                'Date': formatted_date,
                'Category': article_category,
                'Link': article_url,
                'Content': article_content
            }
            # Добавляем информацию о новой статье в список новых статей
            new_articles_data.append(article_info)

    # Если есть новые статьи, отправляем уведомления пользователям, которые подписаны на уведомления
    if new_articles_data:
        # Отправка уведомлений пользователям, которые подписаны на уведомления
        cursor.execute("SELECT user_id FROM users WHERE notifications = TRUE")
        users = cursor.fetchall()
        for user_id in users:
            for article_info in new_articles_data:
                links = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text='Читать', url=article_info['Link'])]
                ])
                await bot.send_photo(user_id[0],
                                    photo=article_info['Photo'],
                                    caption=f'🔔 Новая публикация!\n📋 Заголовок: {article_info["Title"]}\n🕰 Дата публикации: {article_info["Date"]}\nКатегория: {article_info["Category"]}\nСайт: nur.kz',
                                    reply_markup=links)

    # Фиксируем изменения в базе данных
    connection.commit()



# Асинхронная функция для периодического парсинга новостей
async def parse_news_periodically():
    while True:
        await parse_news_informburo()
        await parse_news_nur()
        await asyncio.sleep(60)




# Асинхронная функция для получения новостей Informburo
async def get_news_informburo(message: types.Message, page_number: int = 1):
    # Определение количества новостей на одной странице
    items_per_page = 5  
    start_index = (page_number - 1) * items_per_page
    
    # Получение новостей из базы данных
    cursor.execute("SELECT id, title, photo, time, mark, link FROM informburo_news ORDER BY id ASC OFFSET %s LIMIT %s", (start_index, items_per_page))
    news = cursor.fetchall()

    # Отправка новостей текущей страницы пользователю
    for article_info in news:
        links = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='Раскрыть', callback_data=f'open_content_informburo_{article_info[0]}')],
            [InlineKeyboardButton(text='Читать', url=article_info[5])]
        ])

        await message.answer_photo(
            photo=article_info[2],
            caption=f'📋 Заголовок: {article_info[1]}\n🕰 Время публикации: {article_info[3]}\n{article_info[4]}',
            reply_markup=links
        )

    # Определение количества страниц и создание клавиатуры пагинации
    cursor.execute("SELECT COUNT(*) FROM informburo_news")
    total_news_count = cursor.fetchone()[0]
    total_pages = total_news_count // items_per_page + (1 if total_news_count % items_per_page > 0 else 0)
    pagination_buttons = []
    if page_number > 1:
        pagination_buttons.append(InlineKeyboardButton(text='◀️', callback_data=f"informburo_page_{page_number - 1}"))
    pagination_buttons.append(InlineKeyboardButton(text=f'{page_number}/{total_pages}', callback_data="current_page"))
    if page_number < total_pages:
        pagination_buttons.append(InlineKeyboardButton(text='▶️', callback_data=f"informburo_page_{page_number + 1}"))
    pagination_keyboard = InlineKeyboardMarkup(inline_keyboard=[pagination_buttons])

    # Отправка клавиатуры пагинации
    await message.answer("Выберите страницу:", reply_markup=pagination_keyboard)

# Обработчик раскрытия содержания новостей Informburo
@dp.callback_query(lambda callback: callback.data.startswith('open_content_informburo_'))
async def read_content_informburo(callback: CallbackQuery):
    await callback.answer()
    article_id = int(callback.data.split('_')[-1])  # Получаем ID статьи из callback data
    
    # Получение информации о статье из базы данных
    cursor.execute("SELECT * FROM informburo_news WHERE id = %s", (article_id,))
    article_info = cursor.fetchone()
    if article_info:
        links = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='Скрыть', callback_data=f'close_content_informburo_{article_id}')],
            [InlineKeyboardButton(text='Читать', url=article_info[5])]
        ])
        # Обновляем подпись сообщения с новым содержанием статьи
        await bot.edit_message_caption(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            caption=f'📰Содержание: {article_info[6]}',
            reply_markup=links
        )
    else:
        await bot.send_message(callback.message.chat.id, "Статья не найдена.")

# Обработчик скрытия содержания новостей Informburo
@dp.callback_query(lambda callback: callback.data.startswith('close_content_informburo_'))
async def close_content_informburo(callback: CallbackQuery):
    await callback.answer()
    article_id = int(callback.data.split('_')[-1])  # Получаем ID статьи из callback data
    
    # Получение информации о статье из базы данных
    cursor.execute("SELECT * FROM informburo_news WHERE id = %s", (article_id,))
    article_info = cursor.fetchone()
    if article_info:
        links = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='Раскрыть', callback_data=f'open_content_informburo_{article_id}')],
            [InlineKeyboardButton(text='Читать', url=article_info[5])]
        ])
        # Обновляем подпись сообщения с изначальным видом
        await bot.edit_message_caption(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            caption=f'📋 Заголовок: {article_info[1]}\n🕰 Время публикации: {article_info[3]}\n{article_info[4]}',
            reply_markup=links
        )
    else:
        await bot.send_message(callback.message.chat.id, "Статья не найдена.")







# Асинхронная функция для получения новостей Nur
async def get_news_nur(message: types.Message, page_number: int = 1):
    # Запрос на получение новостей из базы данных
    cursor.execute("SELECT * FROM nur_news")
    news = cursor.fetchall()

    items_per_page = 5  # Устанавливаем количество новостей на одной странице
    total_pages = len(news) // items_per_page + (1 if len(news) % items_per_page > 0 else 0)
    start_index = (page_number - 1) * items_per_page
    end_index = start_index + items_per_page
    paginated_news = news[start_index:end_index]

    for article_info in paginated_news:
        links = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='Раскрыть', callback_data=f'open_content_nur_{article_info[0]}')],
            [InlineKeyboardButton(text='Читать', url=article_info[5])]
        ])

        # Parse the time string including timezone information
        time_datetime = parser.parse(article_info[3])

        formatted_date = time_datetime.strftime('%d.%m.%Y %H:%M')

        await message.answer_photo(
            photo=article_info[2],
            caption=f'📋 Заголовок: {article_info[1]}\n🕰 Дата публикации: {formatted_date}\nКатегория: {article_info[4]}',
            reply_markup=links
        )

    # Добавляем кнопки пагинации
    pagination_buttons = []
    if page_number > 1:
        pagination_buttons.append(InlineKeyboardButton(text='◀️', callback_data=f"nur_page_{page_number - 1}"))
    pagination_buttons.append(InlineKeyboardButton(text=f'{page_number}/{total_pages}', callback_data="current_page"))
    if page_number < total_pages:
        pagination_buttons.append(InlineKeyboardButton(text='▶️', callback_data=f"nur_page_{page_number + 1}"))
    pagination_keyboard = InlineKeyboardMarkup(inline_keyboard=[pagination_buttons])

    await message.answer("Выберите страницу:", reply_markup=pagination_keyboard)

# Обработчик раскрытия содержания новостей Nur
@dp.callback_query(lambda callback: callback.data.startswith('open_content_nur_'))
async def read_content_nur(callback: CallbackQuery):
    await callback.answer()
    article_id = int(callback.data.split('_')[-1])  # Получаем ID статьи из callback data
    
    # Запрос на получение информации о статье из базы данных
    cursor.execute("SELECT * FROM nur_news WHERE id = %s", (article_id,))
    article_info = cursor.fetchone()
    
    if article_info:
        # Parse the time string including timezone information
        time_datetime = parser.parse(article_info[3])

        formatted_date = time_datetime.strftime('%d.%m.%Y %H:%M')

        links = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='Скрыть', callback_data=f'close_content_nur_{article_id}')],
            [InlineKeyboardButton(text='Читать', url=article_info[5])]
        ])
         # Обновляем подпись сообщения с новым содержанием статьи
        await bot.edit_message_caption(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            caption=f'📰Содержание: {article_info[6]}',
            reply_markup=links
        )
    else:
        await bot.send_message(callback.message.chat.id, "Статья не найдена.")

# Обработчик скрытия содержания новостей Nur
@dp.callback_query(lambda callback: callback.data.startswith('close_content_nur_'))
async def close_content_nur(callback: CallbackQuery):
    await callback.answer()
    article_id = int(callback.data.split('_')[-1])  # Получаем ID статьи из callback data
    
    # Запрос на получение информации о статье из базы данных
    cursor.execute("SELECT * FROM nur_news WHERE id = %s", (article_id,))
    article_info = cursor.fetchone()
    
    if article_info:
        # Parse the time string including timezone information
        time_datetime = parser.parse(article_info[3])

        formatted_date = time_datetime.strftime('%d.%m.%Y %H:%M')

        links = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='Раскрыть', callback_data=f'open_content_nur_{article_id}')],
            [InlineKeyboardButton(text='Читать', url=article_info[5])]
        ])
        # Обновляем подпись сообщения с изначальным видом
        await bot.edit_message_caption(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            caption=f'📋 Заголовок: {article_info[1]}\n🕰 Дата публикации: {formatted_date}\nКатегория: {article_info[4]}',
            reply_markup=links
        )
    else:
        await bot.send_message(callback.message.chat.id, "Статья не найдена.")


# Обработчик нажатия кнопок пагинации для нвостей Informburo
@dp.callback_query(lambda callback_query: callback_query.data.startswith('informburo_page_'))
async def process_informburo_page_selection(callback_query: types.CallbackQuery):
    page_number = int(callback_query.data.split('_')[2])
    await get_news_informburo(callback_query.message, page_number)
    await bot.answer_callback_query(callback_query.id)

# Обработчик нажатия кнопок пагинации для новостей Nur
@dp.callback_query(lambda callback_query: callback_query.data.startswith('nur_page_'))
async def process_nur_page_selection(callback_query: types.CallbackQuery):
    page_number = int(callback_query.data.split('_')[2])
    await get_news_nur(callback_query.message, page_number)
    await bot.answer_callback_query(callback_query.id)


# Обработчик нажатия на кнопку текущей страницы
@dp.callback_query(lambda callback_query: callback_query.data == 'current_page')
async def subscribe(callback: CallbackQuery):
    await callback.answer('')



# Обработчик команды "Новости"
@dp.message(F.text == '📋 Новости')
async def get_notification(message: Message):
    await message.answer('Выберите источник новостей:',
                         reply_markup=get_news_keyboard())
    
def get_news_keyboard():
    news = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='Nur', callback_data='nur_news')],
        [InlineKeyboardButton(text='Informburo', callback_data='informburo_news')]
    ]) 
    return news

# Обработчик нажатия на кнопку для вывода новостей Informburo
@dp.callback_query(F.data == 'informburo_news')
async def informburo_news_button(callback: CallbackQuery):
    await callback.answer('')
    await bot.delete_message(callback.message.chat.id, callback.message.message_id)
    await get_news_informburo(callback.message)

# Обработчик нажатия на кнопку для вывода новостей Nur
@dp.callback_query(F.data == 'nur_news')
async def nur_news_button(callback: CallbackQuery):
    await callback.answer('')
    await bot.delete_message(callback.message.chat.id, callback.message.message_id)
    await get_news_nur(callback.message)







# Основная асинхронная функция
async def main():
    # Запуск асинхронной задачи для периодического парсинга новостей
    asyncio.create_task(parse_news_periodically())
    # Запуск диспетчера для обработки входящих сообщений
    await dp.start_polling(bot)

# Точка входа в программу
if __name__ == '__main__':
    try:
        # Запуск основной асинхронной функции
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Exit')
