# News Bot

## Project Overview
This Telegram bot is designed to scrape news websites, parse the content, and send news updates to users via Telegram. It integrates with PostgreSQL for data storage, making it a robust solution for handling and storing news items.

## Features
- News scraping and parsing.
- Sending news updates through Telegram.
- Integration with PostgreSQL database.

## Prerequisites
- Python 3.x
- PostgreSQL
- Aiogram, Requests, BeautifulSoup, psycopg2, and fake_useragent Python libraries.

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/YernurSnowy/News_Parser_Bot
   ```
2. Install the required Python packages:
   ```bash
   pip install aiogram requests beautifulsoup4 psycopg2 fake_useragent
   ```
3. Set up a PostgreSQL database and update the `POSTGRESQL_URI` in `config.py` with your database URI.

4. Replace `YOUR TELEGRAM TOKEN` in `config.py` with your actual Telegram bot token.

## Usage
To start the bot, run the following command:
```bash
python news_bot_updated.py
```

## Configuration
The `config.py` file contains settings that need to be updated before you run the bot:
- `TOKEN`: Your Telegram bot token.
- `POSTGRESQL_URI`: Your PostgreSQL connection URI.
