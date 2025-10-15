# Best2Pay (СБП) Integration

## Обзор

Интеграция Best2Pay позволяет принимать платежи через Систему Быстрых Платежей (СБП) с использованием QR-кодов.

## Конфигурация

### 1. Переменные окружения (.env)

```bash
# Best2Pay Payment Gateway Configuration (СБП support)
BEST2PAY_SECTOR_ID=22436                # Номер сектора
BEST2PAY_PASSWORD=X5e87TgD              # Пароль для подписи
BEST2PAY_ENABLED=True                    # Включить/выключить
```

### 2. Настройка webhook URL в кабинете Best2Pay

URL для уведомлений: `https://wh.tunnl.space/202321/best2pay/notify`

**Примечание**: Success URL и Fail URL настраиваются автоматически через API, отдельная настройка в кабинете не требуется.

## Архитектура

### Двухэтапный процесс оплаты

1. **Регистрация заказа** (`webapi/Register`)
   - Создается запись в БД
   - Заказ регистрируется в Best2Pay
   - Получаем `order_id`

2. **Создание ссылки на оплату** (`webapi/PurchaseSBP`)
   - Создается ссылка с QR-кодом СБП
   - Пользователь перенаправляется на страницу оплаты

3. **Webhook уведомление** (XML формат)
   - Best2Pay отправляет XML с результатом платежа
   - Проверяется подпись
   - Активируется подписка

## Алгоритм подписи

Best2Pay использует **SHA256 + Base64** (НЕ MD5!):

1. Конкатенация параметров + пароль
2. Вычисление SHA256 (hex lowercase)
3. Кодирование в Base64

### Примеры подписи

**Для Register:**
```
sector + amount + currency + password
```

**Для PurchaseSBP:**
```
sector + order_id + password
```

**Для webhook (все теги):**
```
order_id + order_state + reference + id + date + type + state + ... + password
```

## Формат webhook уведомлений

Best2Pay отправляет данные в **XML формате**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<operation>
  <order_id>123</order_id>
  <order_state>COMPLETED</order_state>
  <reference>456</reference>
  <id>789</id>
  <date>2024.10.14 12:00:00</date>
  <type>PURCHASE_BY_QR</type>
  <state>APPROVED</state>
  <amount>10000</amount>
  <currency>643</currency>
  <signature>...</signature>
</operation>
```

## Endpoints

### Webhook URLs

- **Notify (уведомления о платежах)**: `/202321/best2pay/notify`
  - Метод: POST
  - Формат: XML
  - Требует проверку подписи

- **Success (успешная оплата)**: `/202321/best2pay/success`
  - Метод: GET/POST
  - Редирект для пользователя

- **Fail (неудачная оплата)**: `/202321/best2pay/fail`
  - Метод: GET/POST
  - Редирект для пользователя

## Файлы интеграции

### Основные файлы

1. **bot/services/best2pay_service.py**
   - Best2PayService класс
   - register_order() - регистрация заказа
   - create_payment_url() - создание ссылки СБП
   - verify_signature() - проверка подписи
   - Webhook handlers

2. **bot/handlers/user/subscription/payments.py**
   - pay_best2pay_callback_handler() - обработчик кнопки оплаты

3. **bot/app/web/web_server.py**
   - Регистрация webhook маршрутов

4. **bot/app/factories/build_services.py**
   - Инициализация сервиса

5. **bot/keyboards/inline/user_keyboards.py**
   - Кнопка "💳 Best2Pay (СБП)"

6. **config/settings.py**
   - Настройки и webhook paths

## Процесс оплаты

### Со стороны пользователя:

1. Пользователь выбирает период подписки
2. Выбирает "Best2Pay (СБП)"
3. Получает ссылку с QR-кодом
4. Сканирует QR-код банковским приложением
5. Подтверждает оплату
6. Автоматически активируется подписка

### Со стороны системы:

1. Создается запись в БД (status: pending_best2pay)
2. Регистрируется заказ в Best2Pay → получаем order_id
3. Создается ссылка на СБП → redirect пользователя
4. Best2Pay отправляет XML webhook → проверяем подпись
5. Активируем подписку → отправляем уведомление
6. Применяем реферальные/промо бонусы (если есть)

## Тестирование

### 1. Проверка конфигурации

```bash
python3 -c "
from bot.services.best2pay_service import Best2PayService
from config.settings import Settings

settings = Settings()
service = Best2PayService(settings)

print(f'Configured: {service.configured}')
print(f'Sector ID: {service.sector_id}')
print(f'API URL: {service.api_url}')
"
```

### 2. Тестовый платеж

1. Перезапустите бот: `docker compose restart`
2. Откройте бота
3. Выберите период подписки
4. Нажмите "Best2Pay (СБП)"
5. Проверьте, что создается ссылка
6. Попробуйте тестовую оплату

### 3. Проверка webhook

Проверьте логи на наличие:
```
Best2Pay notify webhook received XML
Best2Pay notify: order_id=..., state=APPROVED
```

## Troubleshooting

### Ошибка "Invalid signature"

- Проверьте пароль в .env (X5e87TgD)
- Проверьте, что используется SHA256 + Base64, а не MD5
- Убедитесь, что все теги учитываются в правильном порядке

### Ошибка регистрации заказа

- Проверьте SECTOR_ID (должен быть 22436)
- Проверьте доступность API: https://pay.best2pay.net/webapi/
- Проверьте формат подписи для Register

### Webhook не приходит

- Проверьте URL в кабинете Best2Pay: `https://wh.tunnl.space/202321/best2pay/notify`
- Убедитесь, что сервер доступен извне
- Проверьте логи веб-сервера

### Платеж не обрабатывается

- Проверьте статус операции (должен быть APPROVED)
- Проверьте, что reference (payment_db_id) корректный
- Проверьте логи на наличие исключений

## Документация Best2Pay

- Основная документация: B2P+API+-+Общая+v2.18.1-compressed.pdf
- input.md - полная документация API в markdown

## Поддержка

При возникновении проблем проверьте:
1. Логи бота (docker logs)
2. Логи Best2Pay в кабинете
3. Статус платежей в БД (таблица payments)

## Заметки

- СБП = Система Быстрых Платежей (Faster Payment System)
- Комиссия Best2Pay уточняется у банка
- Минимальная сумма платежа: уточните у банка
- Тестовые платежи: уточните возможность у банка
