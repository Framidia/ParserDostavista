# Dostavista Orders Parser + Telegram Bot

Сервис для мониторинга доступных заказов Dostavista и отправки уведомлений в Telegram. Поддерживает фильтрацию по цене и расстоянию, а также принятие заказов через кнопку.

## Возможности

- 📋 **Парсинг заказов** — опрос API Dostavista по расписанию
- 🔍 **Фильтрация** — по минимальной цене и максимальному расстоянию
- 📍 **Яндекс.Карты** — ссылка на маршрут между точками заказа
- ⚡ **Принятие заказов** — кнопка для быстрого принятия заказа
- 🔄 **Автообновление сессии** — сохранение новой сессии из заголовков/тела ответа
- 📊 **Логирование** — все события записываются в лог-файл

## Быстрый старт

### 1. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 2. Настройка переменных окружения

Создайте файл `.env` на основе `.env.example`:

```bash
cp .env.example .env
```

Заполните обязательные значения:

| Переменная | Описание |
|------------|----------|
| `DV_DEVICE_ID` | ID устройства (64 hex-символа) |
| `DV_SESSION` | Сессионный токен (32 hex-символа) |
| `TELEGRAM_BOT_TOKEN` | Токен Telegram-бота от [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | ID чата для уведомлений (узнать через [@userinfobot](https://t.me/userinfobot)) |

### 3. Запуск

```bash
python main.py
```

## Конфигурация

### Переменные окружения

#### Dostavista API

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `API_BASE_URL` | `https://robot.dostavista.ru/api/courier/` | Базовый URL API |
| `API_VERSION` | `2.75` | Версия API |
| `API_ENDPOINT` | `available-mixed-list-compact` | Эндпоинт для получения заказов |
| `DV_DEVICE_ID` | — | ID устройства (**обязательно**) |
| `DV_SESSION` | — | Сессионный токен (**обязательно**, если нет `.session_cache`) |
| `USER_AGENT` | `ru-courier-app-main-android/2.125.0.3309` | User-Agent запросов |
| `ACCEPT_ENCODING` | `gzip` | Заголовок Accept-Encoding |

#### Фильтры и опрос

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `POLL_INTERVAL_SECONDS` | `4` | Интервал опроса API (мин. 3 сек) |
| `MIN_PRICE` | `0` | Минимальная цена заказа |
| `MAX_DISTANCE_M` | `999999` | Макс. расстояние до первой точки (в метрах) |
| `HTTP_TIMEOUT_SECONDS` | `10` | Таймаут HTTP-запросов |

#### Telegram

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `TELEGRAM_BOT_TOKEN` | — | Токен бота (**обязательно**) |
| `TELEGRAM_CHAT_ID` | — | ID чата (**обязательно**) |

#### Координаты курьера

Для функции принятия заказов:

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `COURIER_LATITUDE` | — | Широта курьера |
| `COURIER_LONGITUDE` | — | Долгота курьера |

#### Файлы

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `SESSION_CACHE_PATH` | `.session_cache` | Путь к файлу кэша сессии |
| `LOG_PATH` | `parser.log` | Путь к лог-файлу |

## Как это работает

### Сессия

1. При запуске сессия загружается из `.session_cache` (если файл существует)
2. Если файл не найден — используется `DV_SESSION` из `.env`
3. При получении нового `x-dv-session` (из заголовка или тела ответа) он автоматически сохраняется в кэш
4. Если API возвращает `is_successful=false`, отправляется уведомление в Telegram

### Уведомления о заказах

Каждое уведомление содержит:
- Цену заказа
- Название и описание груза
- Адреса подачи и доставки
- Расстояние до первой точки и между точками
- Кнопку **«Принять заказ»**
- Кнопку **«Открыть в Яндекс.Картах»**

### Принятие заказов

При нажатии на кнопку «Принять заказ»:
1. Отправляется POST-запрос на `/take-order` с координатами курьера
2. При успехе — уведомление в Telegram
3. При ошибке — сообщение с причиной отказа

## Развёртывание на сервере

### Systemd (Linux)

Создайте файл `/etc/systemd/system/dostavista-parser.service`:

```ini
[Unit]
Description=Dostavista Orders Parser
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/dostavista-parser
ExecStart=/opt/dostavista-parser/.venv/bin/python /opt/dostavista-parser/main.py
Restart=always
RestartSec=10
EnvironmentFile=/opt/dostavista-parser/.env
User=www-data
Group=www-data

[Install]
WantedBy=multi-user.target
```

Активация и запуск:

```bash
sudo systemctl daemon-reload
sudo systemctl enable dostavista-parser
sudo systemctl start dostavista-parser
sudo systemctl status dostavista-parser
```

### Docker (опционально)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
```

## Структура проекта

```
.
├── main.py              # Точка входа, основная логика
├── config.py            # Загрузка и валидация конфигурации
├── dostavista_client.py # HTTP-клиент для API Dostavista
├── telegram_client.py   # HTTP-клиент для Telegram Bot API
├── storage.py           # Работа с кэшем сессии
├── requirements.txt     # Зависимости Python
├── .env.example         # Шаблон переменных окружения
└── README.md            # Документация
```

## Логирование

События записываются в `parser.log` (по умолчанию) с форматом:

```
YYYY-MM-DD HH:MM:SS [LEVEL] logger: message
```

Уровни логирования:
- `INFO` — запуск, отправка заказов, обновление сессии
- `WARNING` — проблемы с запросами, невалидная сессия
- `ERROR` — непредвиденные ошибки

## Получение сессии (для продвинутых)

Для перехвата `x-dv-session`:

1. Установите [mitmproxy](https://mitmproxy.org/)
2. Настройте прокси на устройстве с приложением Dostavista
3. Запустите перехват трафика
4. Найдите запросы к `robot.dostavista.ru`
5. Скопируйте заголовок `x-dv-session` и `x-dv-device-id`

## Требования

- Python 3.9+
- Библиотеки: `requests`, `python-dotenv`

## Лицензия

MIT

## Предупреждение

Использование данного ПО может нарушать условия использования сервиса Dostavista. Используйте на свой страх и риск.
