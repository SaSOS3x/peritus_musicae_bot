import sqlite3
import asyncio
from contextlib import contextmanager

class DBManager:
    def __init__(self, db_name='db.db'):
        self.db_name = db_name
        self.conn = None

    async def async_init(self):
        """Асинхронная инициализация БД"""
        with self._get_cursor() as cursor:
            # Создаем таблицу, если не существует
            cursor.execute('''CREATE TABLE IF NOT EXISTS bot_settings
                           (key TEXT PRIMARY KEY, value TEXT)''')
            
            # Читаем и сохраняем токен
            token = await self._read_token_file()
            cursor.execute('INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)',
                          ('bot_token', token))

    @contextmanager
    def _get_cursor(self):
        """Контекстный менеджер для работы с курсором"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        finally:
            conn.close()

    async def _read_token_file(self):
        """Чтение токена из файла"""
        try:
            with open('token.txt', 'r') as f:
                token = f.read().strip()
                if not token:
                    raise ValueError("Token file is empty")
                return token
        except FileNotFoundError:
            print("Error: token.txt file not found")
            raise

    def get_bot_token(self):
        """Получение токена из БД"""
        with self._get_cursor() as cursor:
            cursor.execute('SELECT value FROM bot_settings WHERE key = "bot_token"')
            result = cursor.fetchone()
            if not result:
                raise ValueError("Token not found in database")
            return result[0]

    def cleanup_db(self):
        """Очистка БД"""
        with self._get_cursor() as cursor:
            cursor.execute('DROP TABLE IF EXISTS bot_settings')
        print("Таблица удалена")