# 🚀 Развертывание Remnawave VPN системы с Telegram ботом и Mini App

Полное руководство по развертыванию системы управления VPN подписками с Telegram ботом, Mini App и личным кабинетом.

## 📋 Компоненты системы

1. **Telegram Bot** - управление пользователями и подписками
2. **Mini App** - интерфейс подписок внутри Telegram
3. **Personal Cabinet** - веб-интерфейс управления подписками
4. **PostgreSQL Database** - база данных пользователей и подписок
5. **Nginx** - реверс-прокси и SSL терминация

## 🛠️ Предварительные требования

### Система
- Ubuntu 20.04+ или аналогичный Linux дистрибутив
- Docker и Docker Compose
- Nginx
- Certbot для SSL сертификатов

### Домены
- Основной домен для личного кабинета (например: `lk.tunnl.space`)
- Домен для Mini App (например: `app.tunnl.space`)
- Домен для webhook'ов (например: `wh.tunnl.space`)

### API токены
- Telegram Bot Token от @BotFather
- Remnawave Panel API токен

## 📚 Пошаговая инструкция

### 1. Подготовка сервера

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Установка Docker Compose
sudo apt install docker-compose-plugin -y

# Установка Nginx
sudo apt install nginx -y

# Установка Certbot для SSL
sudo apt install certbot python3-certbot-nginx -y
```

### 2. Создание сети Docker

```bash
# Создание внешней сети для контейнеров
sudo docker network create remnawave-network
```

### 3. Настройка DNS и SSL сертификатов

```bash
# Получение SSL сертификатов для всех доменов
sudo certbot certonly --manual --preferred-challenges dns -d lk.tunnl.space -d app.tunnl.space -d wh.tunnl.space

# Или с помощью acme.sh (если используется)
~/.acme.sh/acme.sh --issue --dns dns_cf -d lk.tunnl.space --ecc
~/.acme.sh/acme.sh --issue --dns dns_cf -d app.tunnl.space --ecc
```

### 4. Развертывание Telegram бота

#### 4.1 Клонирование репозитория бота

```bash
cd /home/ubuntu
git clone https://github.com/machka-pasla/remnawave-tg-shop.git
cd remnawave-tg-shop
```

#### 4.2 Настройка .env файла для бота

```bash
cp .env.example .env
nano .env
```

**Пример конфигурации .env:**

```env
# Telegram Bot Token and Admin IDs
BOT_TOKEN=YOUR_BOT_TOKEN_FROM_BOTFATHER
ADMIN_IDS=YOUR_TELEGRAM_USER_ID

# PostgreSQL Settings
POSTGRES_USER=postgres
POSTGRES_PASSWORD=strong_password_here
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=postgres
POSTGRES_HOST_AUTH_METHOD=trust

# Localization and Display
DEFAULT_LANGUAGE="ru"
DEFAULT_CURRENCY_SYMBOL="RUB"

# External Links
SUPPORT_LINK=https://t.me/your_support_channel
SERVER_STATUS_URL=https://status.yourdomain.com
TERMS_OF_SERVICE_URL=https://yourdomain.com/tos
SUBSCRIPTION_MINI_APP_URL=https://app.tunnl.space

# Remnawave Panel Integration
REMNAWAVE_PANEL_URL=https://panl.tunnl.space
REMNAWAVE_API_TOKEN=your_remnawave_panel_api_token

# Bot Configuration
BOT_USERNAME=tunnlspace_bot
```

#### 4.3 Запуск бота

```bash
# Запуск в фоновом режиме
docker-compose up -d

# Проверка статуса
docker-compose ps
docker-compose logs -f
```

### 5. Развертывание Mini App

#### 5.1 Клонирование репозитория Mini App

```bash
cd /home/ubuntu
git clone https://github.com/maposia/remnawave-telegram-sub-mini-app.git
cd remnawave-telegram-sub-mini-app
```

#### 5.2 Настройка .env файла для Mini App

```bash
cp .env.example .env
nano .env
```

**Пример конфигурации .env для Mini App:**

```env
REMNAWAVE_PANEL_URL=https://panl.tunnl.space
REMNAWAVE_TOKEN=your_remnawave_panel_api_token
BUY_LINK=https://sub.tunnl.space
CRYPTO_LINK=
REDIRECT_LINK=https://app.tunnl.space/redirect.html?redirect_to=
AUTH_API_KEY=
```

#### 5.3 Создание файла redirect.html

```bash
# Создание директории для redirect страницы
sudo mkdir -p /var/www/app-redirect

# Создание redirect.html
sudo nano /var/www/app-redirect/index.html
```

**Содержимое redirect.html:**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Redirect</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
</head>
<body>
    <script>
        const urlParams = new URLSearchParams(window.location.search);
        const redirectTo = urlParams.get('redirect_to');

        if (redirectTo && window.Telegram && window.Telegram.WebApp) {
            window.Telegram.WebApp.openTelegramLink(redirectTo);
        } else {
            window.location.href = redirectTo || 'https://t.me/tunnlspace_bot';
        }
    </script>
    <p>Redirecting...</p>
</body>
</html>
```

#### 5.4 Запуск Mini App

```bash
docker-compose up -d

# Проверка статуса
docker-compose ps
docker-compose logs -f
```

### 6. Настройка Nginx

#### 6.1 Конфигурация для Mini App (app.tunnl.space)

```bash
sudo nano /etc/nginx/sites-available/app.tunnl.space.ssl.conf
```

```nginx
server {
    listen 443 ssl http2;
    server_name app.tunnl.space;

    ssl_certificate /home/ubuntu/.acme.sh/app.tunnl.space_ecc/fullchain.cer;
    ssl_certificate_key /home/ubuntu/.acme.sh/app.tunnl.space_ecc/app.tunnl.space.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Redirect page for deep links
    location = /redirect.html {
        alias /var/www/app-redirect/index.html;
        add_header Content-Type "text/html; charset=utf-8";
    }

    location / {
        proxy_pass http://127.0.0.1:3020;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

# HTTP redirect
server {
    listen 80;
    server_name app.tunnl.space;
    return 301 https://$server_name$request_uri;
}
```

#### 6.2 Конфигурация для личного кабинета (lk.tunnl.space)

```bash
sudo nano /etc/nginx/sites-available/lk.tunnl.space.ssl.conf
```

```nginx
server {
    listen 443 ssl http2;
    server_name lk.tunnl.space;

    ssl_certificate /home/ubuntu/.acme.sh/lk.tunnl.space_ecc/fullchain.cer;
    ssl_certificate_key /home/ubuntu/.acme.sh/lk.tunnl.space_ecc/lk.tunnl.space.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (для Next.js hot reload)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

# HTTP redirect to HTTPS
server {
    listen 80;
    server_name lk.tunnl.space;
    return 301 https://$server_name$request_uri;
}
```

#### 6.3 Конфигурация для webhook'ов (wh.tunnl.space)

```bash
sudo nano /etc/nginx/sites-available/wh.tunnl.space
```

```nginx
server {
    listen 80;
    server_name wh.tunnl.space;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

#### 6.4 Активация конфигураций

```bash
# Создание символических ссылок
sudo ln -sf /etc/nginx/sites-available/app.tunnl.space.ssl.conf /etc/nginx/sites-enabled/
sudo ln -sf /etc/nginx/sites-available/lk.tunnl.space.ssl.conf /etc/nginx/sites-enabled/
sudo ln -sf /etc/nginx/sites-available/wh.tunnl.space /etc/nginx/sites-enabled/

# Проверка конфигурации
sudo nginx -t

# Перезапуск Nginx
sudo systemctl reload nginx
```

### 7. Развертывание личного кабинета

#### 7.1 Клонирование репозитория личного кабинета

```bash
cd /home/ubuntu
git clone https://github.com/ryssroad/vpnspace-lk.git saas-starter
cd saas-starter
```

#### 7.2 Установка зависимостей

```bash
# Установка Node.js (если не установлен)
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
source ~/.bashrc
nvm install 18
nvm use 18

# Установка pnpm
npm install -g pnpm

# Установка зависимостей проекта
pnpm install
```

#### 7.3 Настройка .env файла

```bash
cp .env.example .env.local
nano .env.local
```

**Пример конфигурации .env.local:**

```env
# Database
DATABASE_URL=postgresql://postgres:your_password@localhost:5432/postgres

# Auth
AUTH_SECRET=your_very_long_random_secret_key_here

# Telegram Bot
BOT_TOKEN=your_bot_token_from_botfather
NEXT_PUBLIC_BOT_USERNAME=tunnlauth_bot

# Remnawave Panel API
REMNAWAVE_PANEL_URL=https://panl.tunnl.space
REMNAWAVE_API_TOKEN=your_remnawave_panel_api_token

# App URLs
NEXT_PUBLIC_APP_URL=https://lk.tunnl.space
```

#### 7.4 Настройка базы данных

```bash
# Генерация миграций
pnpm db:generate

# Применение миграций
pnpm db:migrate

# Опционально: заполнение тестовыми данными
pnpm db:seed
```

#### 7.5 Сборка и запуск

```bash
# Сборка приложения
pnpm build

# Запуск в production режиме
pnpm start

# Или запуск в development режиме
pnpm dev
```

### 8. Настройка автозапуска с PM2

```bash
# Установка PM2
npm install -g pm2

# Создание ecosystem.config.js
nano ecosystem.config.js
```

**Содержимое ecosystem.config.js:**

```javascript
module.exports = {
  apps: [
    {
      name: 'tunnl-lk',
      script: 'npm',
      args: 'start',
      cwd: '/home/ubuntu/saas-starter',
      env: {
        NODE_ENV: 'production',
        PORT: 3001
      },
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '1G'
    }
  ]
};
```

```bash
# Запуск с PM2
pm2 start ecosystem.config.js

# Автозапуск при перезагрузке
pm2 startup
pm2 save
```

## 🔧 Настройка Telegram бота

### 1. Создание бота через @BotFather

1. Отправьте `/newbot` в @BotFather
2. Выберите имя и username для бота
3. Получите BOT_TOKEN
4. Настройте команды через `/setcommands`:

```
start - 🚀 Начать работу с ботом
profile - 👤 Мой профиль
subscription - 💎 Управление подпиской
support - 🆘 Техническая поддержка
```

### 2. Настройка Mini App

1. В @BotFather отправьте `/newapp`
2. Выберите вашего бота
3. Укажите название приложения
4. Загрузите иконку (512x512 px)
5. Укажите URL Mini App: `https://app.tunnl.space`
6. Добавьте короткое описание

### 3. Установка webhook

```bash
# Установка webhook для бота
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://wh.tunnl.space/webhook"}'
```

## 🔒 Безопасность

### 1. Firewall настройки

```bash
# Настройка UFW
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 5432/tcp  # PostgreSQL (только для локального доступа)
sudo ufw enable
```

### 2. SSL сертификаты

```bash
# Автообновление сертификатов
echo "0 12 * * * /root/.acme.sh/acme.sh --cron --home /root/.acme.sh > /dev/null" | sudo crontab -
```

### 3. Бэкапы базы данных

```bash
# Создание скрипта бэкапа
sudo nano /usr/local/bin/backup-db.sh
```

```bash
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/home/ubuntu/backups"
mkdir -p $BACKUP_DIR

docker exec remnawave-tg-shop-db pg_dump -U postgres postgres > $BACKUP_DIR/backup_$DATE.sql

# Удаление старых бэкапов (старше 7 дней)
find $BACKUP_DIR -type f -mtime +7 -delete
```

```bash
# Установка прав и добавление в cron
sudo chmod +x /usr/local/bin/backup-db.sh
echo "0 2 * * * /usr/local/bin/backup-db.sh" | crontab -
```

## 🚨 Часто встречающиеся проблемы

### 1. Mini App не загружается
- Проверьте SSL сертификат
- Убедитесь, что контейнер запущен на порту 3020
- Проверьте nginx конфигурацию

### 2. Бот не отвечает
- Проверьте webhook: `curl https://api.telegram.org/bot<TOKEN>/getWebhookInfo`
- Проверьте логи: `docker-compose logs -f`
- Убедитесь, что база данных доступна

### 3. Проблемы с SSL
- Проверьте сертификаты: `sudo certbot certificates`
- Обновите сертификаты: `sudo certbot renew`

### 4. Ошибки авторизации в личном кабинете
- Проверьте настройки Telegram аутентификации
- Убедитесь, что BOT_TOKEN корректный
- Проверьте подключение к базе данных

## 📊 Мониторинг

### 1. Логи системы

```bash
# Логи всех контейнеров
docker-compose logs -f

# Логи конкретного сервиса
docker-compose logs -f remnawave-tg-shop

# Логи Nginx
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log

# Логи личного кабинета (PM2)
pm2 logs tunnl-lk
```

### 2. Проверка статуса

```bash
# Статус контейнеров
docker-compose ps

# Статус PM2 приложений
pm2 status

# Статус Nginx
sudo systemctl status nginx

# Проверка портов
sudo netstat -tulpn | grep -E ':80|:443|:3020|:3001|:5432'
```

## 🎯 Финальные проверки

После развертывания проверьте:

1. ✅ Telegram бот отвечает на команды
2. ✅ Mini App открывается в Telegram
3. ✅ Личный кабинет доступен по HTTPS
4. ✅ SSL сертификаты действительны
5. ✅ База данных работает и создает пользователей
6. ✅ Webhook установлен корректно
7. ✅ Все логи без критических ошибок

## 🔄 Обновления

### Обновление бота

```bash
cd /home/ubuntu/remnawave-tg-shop
docker-compose pull
docker-compose up -d
```

### Обновление Mini App

```bash
cd /home/ubuntu/remnawave-telegram-sub-mini-app
docker-compose pull
docker-compose up -d
```

### Обновление личного кабинета

```bash
cd /home/ubuntu/saas-starter
git pull
pnpm install
pnpm build
pm2 reload tunnl-lk
```

---

**Создано с помощью [Claude Code](https://claude.ai/code)**

*Последнее обновление: $(date +%Y-%m-%d)*