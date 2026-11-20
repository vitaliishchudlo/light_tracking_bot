# Docker Setup для Svitlo Bot

Цей документ описує як запустити бота з MongoDB використовуючи Docker Compose.

## Вимоги

- Docker
- Docker Compose

## Налаштування

1. **Створіть файл `.env` в корені проекту:**

```env
BOT_TOKEN=your_bot_token_here
```

2. **MongoDB URL автоматично налаштовується для Docker**

   - Для Docker: `mongodb://mongodb:27017/` (використовується ім'я сервісу)
   - Для локального запуску: `mongodb://localhost:27017/`

## Запуск

### Запуск всіх сервісів (MongoDB + Bot)

```bash
docker-compose up -d
```

### Перегляд логів

```bash
# Всі сервіси
docker-compose logs -f

# Тільки бот
docker-compose logs -f bot-app

# Тільки MongoDB
docker-compose logs -f mongodb
```

### Зупинка

```bash
docker-compose down
```

### Зупинка з видаленням даних

```bash
docker-compose down -v
```

## Перебудова після змін в коді

```bash
docker-compose up -d --build
```

## Структура сервісів

- **mongodb**: MongoDB 7.0 на порту 27017
- **bot-app**: Telegram бот для відстеження відключень світла

## Volumes

- `./data/mongodb` (папка в проєкті) - файли бази даних. Її можна просто скопіювати для резервної копії (краще при зупиненому `mongodb`, або через `mongodump`)
- `mongodb_config` (Docker volume) - конфігурація

## Доступ до MongoDB

Якщо потрібен доступ до MongoDB з хоста:

```bash
# Використовуючи mongosh
mongosh mongodb://localhost:27017/

# Або через Docker
docker exec -it svitlo-mongodb mongosh
```

## Troubleshooting

### Бот не підключається до MongoDB

Перевірте що MongoDB запустився:
```bash
docker-compose ps
docker-compose logs mongodb
```

Перевірте що бот чекає на MongoDB (healthcheck):
```bash
docker-compose logs bot-app | grep -i mongo
```

### Перебудова з нуля

```bash
docker-compose down -v
docker-compose build --no-cache
docker-compose up -d
```

### Перевірка статусу сервісів

```bash
# Статус всіх контейнерів
docker-compose ps

# Перевірка healthcheck MongoDB
docker inspect svitlo-mongodb | grep -A 10 Health
```

## Важливі нотатки

1. **Створіть `.env` файл** з `BOT_TOKEN` перед запуском
2. **MongoDB URL** автоматично налаштовується:
   - Docker: `mongodb://mongodb:27017/` (ім'я сервісу)
   - Локально: `mongodb://localhost:27017/` (дефолт)
3. **Дані зберігаються** в папці `data/mongodb`, тому не втрачаються при перезапуску (і `docker-compose down -v` їх не видаляє)
4. **Бот чекає** на готовність MongoDB через `depends_on` з `service_healthy`
