import asyncio
import discord
import yt_dlp as youtube_dl

import functools

from discord.ext import commands
from db import DBManager

# Включаем необходимые интенты
intents = discord.Intents.default()
intents.message_content = True  # Для работы с содержимым сообщений

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

@bot.event
async def on_ready():
    print(f"Бот {bot.user} успешно запущен!")

@bot.command(name='voice')
async def voice_control(ctx, action: str = None):
    voice_client = ctx.guild.voice_client
    
    if action == "leave":
        if not voice_client or not voice_client.is_connected():
            await ctx.send("Я не подключен к голосовому каналу!")
            return

        # Проверка прав пользователя
        if not ctx.author.voice:
            await ctx.send("Вы должны быть в голосовом канале!")
            return
            
        await voice_client.disconnect()
        await ctx.send(f"Отключился от канала {voice_client.channel.name}!")
    
    elif action == "join":
        # Проверка, находится ли пользователь в голосовом канале
        if not ctx.author.voice:
            await ctx.send("Сначала зайдите в голосовой канал!")
            return

        channel = ctx.author.voice.channel
        await channel.connect()
        await ctx.send(f"Подключился к {channel}!")
    
    else:
        await ctx.send("Доступные действия: join, leave")

@bot.command(name='join')
async def join(ctx):
    await voice_control(ctx, "join")

@bot.command(name='leave')
async def leave(ctx):
    await voice_control(ctx, "leave")

@bot.command(name='start')
async def start(ctx):
    await ctx.send("""Это бот, для проигрывания звуковой дорожки видео с youtube

Список команд:
!play (url - с ютуба или название песни) - начинает воспроизведение музыки
!voice - выводит список доступных команд для работы с голосовыми каналами
!stop - пауза
!continue - продолжение проигрывания""")

# Логика проигрывания музыки
# Настройки для yt-dlp (извлекаем аудио, игнорируем ошибки)
ytdl_format_options = {
    # Выбираем аудио с максимальным битрейтом
    'format': 'bestaudio/best[abr>192]/best',
    
    # Расширенные параметры для качества
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    
    # Расширенные аудио настройки
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'opus',  # Лучший кодек для Discord
        'preferredquality': '320',  # Максимальный битрейт
    }],
    
    # Дополнительные параметры для YouTube
    'youtube_include_dash_manifest': False,
    'age_limit': 25,
    'socket_timeout': 10,
    'audio_quality': 0,
}

ffmpeg_options = {
    'options': '-vn -b:a 320K -af "loudnorm=I=-16:LRA=11:TP=-1.5"',
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -analyzeduration 0 -hwaccel auto -threads 8',
    # 'before_options': '-re '
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    # @classmethod
    # async def from_url(cls, url, *, loop=None, stream=True):
    #     loop = loop or asyncio.get_event_loop()
    #     data = await loop.run_in_executor(
    #         None, 
    #         functools.partial(
    #             ytdl.extract_info,
    #             url,
    #             download=not stream
    #         )
    #     )

    #     if 'entries' in data:
    #         data = data['entries'][0]

    #     filename = data['url'] if stream else ytdl.prepare_filename(data)
    #     return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)
    
    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(
                None, 
                lambda: ytdl.extract_info(url, download=not stream)
            )
            
            if not data:
                return None
                
            if 'entries' in data:
                data = data['entries'][0]
                
            if stream:
                filename = data['url']
            else:
                filename = ytdl.prepare_filename(data)
                
            return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)
        except Exception as e:
            print(f"YTDL error: {e}")
            return None

@bot.command(name='play')
async def play_command(ctx, *, query):
    try:
        # Проверка подключения
        if not ctx.author.voice:
            await ctx.send("Сначала подключитесь к голосовому каналу!")
            return

        voice_client = ctx.guild.voice_client

        if not voice_client:
            await ctx.author.voice.channel.connect()
            await asyncio.sleep(1)                             # Даем время на инициализацию подключения
            voice_client = ctx.guild.voice_client

        elif voice_client.channel != ctx.author.voice.channel:   # Если бот подключен в другом канале, перемещаемся
            await voice_client.move_to(ctx.author.voice.channel)
            await asyncio.sleep(1)

        # Дополнительная проверка состояния подключения
        if not voice_client or not voice_client.is_connected():
            await ctx.send("Не удалось подключиться к голосовому каналу")
            return
        
        async with ctx.typing():
            # Обработка URL/запроса
            if not query.startswith('http'):
                query = f'ytsearch:{query}'

            player = await YTDLSource.from_url(query, loop=bot.loop, stream=True)
            
            # Проверка источника
            if not player:
                await ctx.send("Не удалось загрузить аудио")
                return
            
            # Проверка готовности клиента перед воспроизведением
            if voice_client.is_playing() or voice_client.is_paused():
                voice_client.stop()

            voice_client.play(
                player, 
                after=lambda e: asyncio.run_coroutine_threadsafe(
                    ctx.send(f"Завершено воспроизведение: {player.title}"), 
                    bot.loop
                )
            )
            
            await ctx.send(f"**Сейчас играет:** {player.title}")

    except Exception as e:
        await ctx.send(f"Ошибка: {str(e)}")
        print(f"Error: {e}")

@bot.command(name='stop')
async def stop(ctx):
    voice_client = ctx.guild.voice_client
    
    if not voice_client or not voice_client.is_playing():
        await ctx.send("Сейчас ничего не играет!")
        return
        
    voice_client.pause()
    await ctx.send("⏸️ Музыка приостановлена")

@bot.command(name='continue')
async def resume(ctx):
    voice_client = ctx.guild.voice_client
    
    if not voice_client or not voice_client.is_paused():
        await ctx.send("Нет приостановленной музыки!")
        return
        
    voice_client.resume()
    await ctx.send("▶️ Воспроизведение продолжено")

async def main():
    # Инициализация БД
    db_manager = DBManager()
    await db_manager.async_init()
    
    # Запуск бота
    try:
        await bot.start(db_manager.get_bot_token())
    except KeyboardInterrupt:
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())