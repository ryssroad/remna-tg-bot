# Техническое задание: Тестовое окружение для Best2Pay интеграции

## Цель
Создать полноценное тестовое окружение для проверки всего платежного пайплайна Best2Pay без использования реальных денег и без риска для продакшн-системы.

---

## Архитектура

### Компоненты
1. **Тестовая панель Remnawave** - отдельный инстанс для тестовых пользователей
2. **Тестовый Telegram бот** - клон продакшн бота с тестовыми настройками
3. **Тестовый стенд Best2Pay** - `test.best2pay.net`
4. **Тестовая база данных** - изолированная от продакшена

### Конфигурация окружения

```bash
# .env для тестового бота
BOT_TOKEN=<TEST_BOT_TOKEN>
ADMIN_IDS=<YOUR_TELEGRAM_ID>

# PostgreSQL (отдельная БД или схема)
POSTGRES_DB=test_bot_db
POSTGRES_HOST=localhost  # или отдельный контейнер

# Test Panel API
PANEL_API_URL=https://test-panel.example.com/api
PANEL_API_KEY=<TEST_PANEL_API_KEY>

# Best2Pay Test Environment
BEST2PAY_SECTOR_ID=8365
BEST2PAY_PASSWORD=I3ssq1q:UiM2ozdvb
BEST2PAY_API_URL=https://test.best2pay.net/webapi/
BEST2PAY_ENABLED=True

# Webhook (ngrok или временный домен)
WEBHOOK_BASE_URL=https://test-webhook.example.com

# Остальные провайдеры - выключены
YOOKASSA_ENABLED=False
STARS_ENABLED=False
TRIBUTE_ENABLED=False
CRYPTOPAY_ENABLED=False
```

---

## Функциональные требования

### 1. Админское меню тестирования

Добавить в админ-панель новый раздел "🧪 Тестирование Best2Pay"

#### Структура меню:

```
/admin
  └─ 🧪 Тестирование Best2Pay
       ├─ 1️⃣ Создать тестового пользователя
       ├─ 2️⃣ Создать тестовый платеж
       ├─ 3️⃣ Сформировать ссылку на оплату
       ├─ 4️⃣ Симулировать успешную оплату
       ├─ 5️⃣ Симулировать неуспешную оплату
       ├─ 6️⃣ Проверить статус подписки
       ├─ 7️⃣ Очистить тестовые данные
       └─ ℹ️ Показать текущий тест-кейс
```

---

## Детальное описание функций

### 1️⃣ Создать тестового пользователя

**Что делает:**
1. Генерирует случайный username: `test_user_<timestamp>`
2. Создает пользователя в тестовой панели через API
3. Создает запись в локальной БД бота (таблица `users`)
4. Сохраняет UUID пользователя из панели

**API панели:**
```http
POST /api/users
Authorization: Bearer <PANEL_API_KEY>
Content-Type: application/json

{
  "username": "test_user_1700000000",
  "telegramId": null,
  "email": "test@example.com",
  "subscriptionDurationDays": 0,
  "trafficLimitBytes": 10737418240,  // 10GB
  "subscriptionTrafficStrategy": "NO_RESET",
  "squadUuids": ["<DEFAULT_SQUAD_UUID>"],
  "tags": ["test_user"]
}
```

**Response:**
```json
{
  "uuid": "d50941b5-504e-448d-9c40-32c9b21c6722",
  "shortUuid": "abc123",
  "username": "test_user_1700000000",
  "subscriptionDurationDays": 0,
  "expiresAt": null,
  "trafficLimitBytes": 10737418240,
  "trafficUsedBytes": 0,
  "isActive": false,
  "tags": ["test_user"]
}
```

**Вывод боту:**
```
✅ Тестовый пользователь создан!

Username: test_user_1700000000
UUID: d50941b5-504e-448d-9c40-32c9b21c6722
Short UUID: abc123
Telegram ID: <YOUR_ID>
Статус: Не активирован (нет подписки)

📋 Скопируйте UUID для следующих шагов
```

**Сохранение в контекст:**
- FSM State: `TestingState.user_created`
- FSM Data: `{"test_user_uuid": "...", "test_username": "...", "test_telegram_id": ...}`

---

### 2️⃣ Создать тестовый платеж

**Что делает:**
1. Проверяет, что тестовый пользователь создан (есть в FSM)
2. Предлагает выбрать период подписки (1, 3, 6, 12 месяцев)
3. Создает запись в таблице `payments` в БД
4. Регистрирует заказ в Best2Pay через `webapi/Register`

**Inline кнопки:**
```
Выберите период подписки:
[1 месяц - 300₽] [3 месяца - 850₽]
[6 месяцев - 1600₽] [12 месяцев - 3000₽]
```

**После выбора периода:**

**БД запись:**
```sql
INSERT INTO payments (
  user_id,
  amount,
  currency,
  status,
  subscription_duration_months,
  provider,
  description
) VALUES (
  <TEST_USER_ID>,
  300.00,
  'RUB',
  'pending_best2pay',
  1,
  'best2pay',
  'Техподдержка'
) RETURNING payment_id;
```

**API Best2Pay:**
```http
POST https://test.best2pay.net/webapi/Register

sector=8365
amount=30000  # в копейках
currency=643  # RUB
reference=<PAYMENT_ID>
description=Техподдержка
url=https://test-webhook.example.com/webhook/best2pay/success
fail_url=https://test-webhook.example.com/webhook/best2pay/fail
signature=<CALCULATED_SIGNATURE>
```

**Response:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<order>
  <id>2804372329</id>
  <state>REGISTERED</state>
</order>
```

**Обновление БД:**
```sql
UPDATE payments
SET best2pay_order_id = '2804372329'
WHERE payment_id = <PAYMENT_ID>;
```

**Вывод боту:**
```
✅ Тестовый платеж создан!

Payment ID (БД): 123
Best2Pay Order ID: 2804372329
Сумма: 300.00 RUB (30000 копеек)
Период: 1 месяц
Статус: pending_best2pay

🔄 Заказ зарегистрирован в Best2Pay
Следующий шаг: Создать ссылку на оплату
```

**FSM обновление:**
- State: `TestingState.payment_created`
- Data: `{..., "test_payment_id": 123, "test_order_id": "2804372329", "test_months": 1, "test_amount": 300}`

---

### 3️⃣ Сформировать ссылку на оплату

**Что делает:**
1. Проверяет наличие order_id в FSM
2. Вызывает Best2Pay API для создания СБП ссылки
3. Генерирует QR-код (опционально)
4. Предоставляет ссылку для оплаты

**API Best2Pay:**
```http
POST https://test.best2pay.net/webapi/PurchaseSBP

sector=8365
order_id=2804372329
payment_method=sbp
signature=<CALCULATED_SIGNATURE>
```

**Response:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<sbp_payment>
  <qrc_id>AS1R000KOMEPGAIE9519CB1Q4PGN6ULN</qrc_id>
  <pay_url>https://test.best2pay.net/sbp/pay/AS1R000KOMEPGAIE9519CB1Q4PGN6ULN</pay_url>
</sbp_payment>
```

**Вывод боту:**
```
✅ Ссылка на оплату создана!

Order ID: 2804372329
QRC ID: AS1R000KOMEPGAIE9519CB1Q4PGN6ULN
Метод: СБП (Faster Payment System)

🔗 Ссылка на оплату:
https://test.best2pay.net/sbp/pay/AS1R000KOMEPGAIE9519CB1Q4PGN6ULN

⚠️ Внимание: На тестовом стенде Best2Pay реальная оплата
через СБП может не работать. Используйте симуляцию (шаг 4)

📲 Можете попробовать открыть ссылку (для теста UX)
```

**FSM обновление:**
- State: `TestingState.payment_url_created`
- Data: `{..., "test_qrc_id": "...", "test_pay_url": "..."}`

---

### 4️⃣ Симулировать успешную оплату

**Что делает:**
1. Использует сервис `test/SBPTestCase` для симуляции платежа
2. Best2Pay отправляет webhook уведомление на наш сервер
3. Бот обрабатывает webhook как реальный платеж
4. Активирует подписку через Panel API
5. Обновляет статус в БД

**API Best2Pay:**
```http
POST https://test.best2pay.net/test/SBPTestCase

sector=8365
case_id=150  # успешная оплата
order_id=2804372329
signature=<CALCULATED_SIGNATURE>
```

**Response:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<SBPTestCase>
  <qrc_id>AS1R000KOMEPGAIE9519CB1Q4PGN6ULN</qrc_id>
  <message>[00150: не запущен] Тестовый сценарий запущен</message>
</SBPTestCase>
```

**После этого Best2Pay отправит webhook:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<operation>
  <order_id>2804372329</order_id>
  <order_state>COMPLETED</order_state>
  <reference>123</reference>
  <id>99999999</id>
  <date>2025.11.18 12:00:00</date>
  <type>PURCHASE_BY_QR</type>
  <state>APPROVED</state>
  <amount>30000</amount>
  <currency>643</currency>
  <signature>...</signature>
</operation>
```

**Обработка webhook:**
1. Проверка подписи
2. Обновление статуса платежа: `pending_best2pay` → `succeeded`
3. Вызов Panel API для активации подписки
4. Отправка уведомления пользователю

**Panel API (активация подписки):**
```http
POST /api/subscriptions

{
  "userUuid": "d50941b5-504e-448d-9c40-32c9b21c6722",
  "durationDays": 30,
  "trafficLimitBytes": 0,
  "subscriptionTrafficStrategy": "NO_RESET"
}
```

**Вывод боту:**
```
✅ Успешная оплата симулирована!

🔔 Webhook получен и обработан
💳 Платеж #123: pending_best2pay → succeeded
👤 Пользователь: test_user_1700000000
📅 Подписка активирована на 30 дней
📊 Трафик: безлимитный

✉️ Уведомление отправлено пользователю
```

---

### 5️⃣ Симулировать неуспешную оплату

**Аналогично шагу 4, но:**
- `case_id=151` (неуспешная оплата)
- Webhook содержит `state=DECLINED`
- Статус остается `pending_best2pay` или меняется на `failed`
- Подписка НЕ активируется
- Пользователь получает уведомление об ошибке

**Вывод боту:**
```
⚠️ Неуспешная оплата симулирована

🔔 Webhook получен и обработан
💳 Платеж #123: pending_best2pay → failed
👤 Пользователь: test_user_1700000000
❌ Подписка НЕ активирована
Причина: Операция отклонена (тест-кейс 151)

✉️ Уведомление об ошибке отправлено пользователю
```

---

### 6️⃣ Проверить статус подписки

**Что делает:**
1. Запрашивает данные пользователя из Panel API
2. Проверяет статус в локальной БД
3. Показывает детальную информацию

**Panel API:**
```http
GET /api/users/{uuid}
Authorization: Bearer <PANEL_API_KEY>
```

**Response:**
```json
{
  "uuid": "d50941b5-504e-448d-9c40-32c9b21c6722",
  "username": "test_user_1700000000",
  "subscriptionDurationDays": 30,
  "expiresAt": "2025-12-18T12:00:00Z",
  "isActive": true,
  "trafficLimitBytes": 0,
  "trafficUsedBytes": 1048576,
  "tags": ["test_user"]
}
```

**Локальная БД:**
```sql
SELECT * FROM users WHERE panel_uuid = 'd50941b5-504e-448d-9c40-32c9b21c6722';
SELECT * FROM payments WHERE user_id = <USER_ID> ORDER BY created_at DESC LIMIT 5;
```

**Вывод боту:**
```
📊 Статус тестового пользователя

👤 Пользователь
Username: test_user_1700000000
UUID: d50941b5-504e-448d-9c40-32c9b21c6722
Telegram ID: <YOUR_ID>

📅 Подписка
Статус: ✅ Активна
Истекает: 2025-12-18 12:00:00 UTC
Осталось дней: 30

📊 Трафик
Лимит: Безлимит
Использовано: 1.00 MB
Осталось: ∞

💳 Последние платежи
1. #123 - succeeded - 300 RUB - 2025-11-18 (Best2Pay)

🔗 Подключение
[Получить конфигурацию]
```

---

### 7️⃣ Очистить тестовые данные

**Что делает:**
1. Удаляет тестового пользователя из Panel API
2. Удаляет записи из локальной БД (users, payments)
3. Очищает FSM state
4. Подтверждает очистку

**Confirmation dialog:**
```
⚠️ Вы уверены?

Будут удалены:
• Тестовый пользователь в панели
• Записи в БД (users, payments)
• FSM данные текущего тест-кейса

[✅ Да, удалить] [❌ Отмена]
```

**Panel API:**
```http
DELETE /api/users/{uuid}
Authorization: Bearer <PANEL_API_KEY>
```

**Локальная БД:**
```sql
DELETE FROM payments WHERE user_id = <TEST_USER_ID>;
DELETE FROM users WHERE id = <TEST_USER_ID>;
```

**Вывод боту:**
```
✅ Тестовые данные очищены

Удалено:
• Пользователь test_user_1700000000 из панели
• 1 запись из таблицы users
• 3 записи из таблицы payments
• FSM state сброшен

Можете начать новый тест-кейс
```

---

### ℹ️ Показать текущий тест-кейс

**Что делает:**
- Показывает все данные из FSM state
- Статус прохождения пайплайна
- Быстрые действия для следующих шагов

**Вывод боту:**
```
📋 Текущий тест-кейс

Прогресс: ████████░░ 80% (4/5 шагов)

✅ 1. Пользователь создан
   └─ test_user_1700000000 (UUID: d509...)

✅ 2. Платеж создан
   └─ Payment ID: 123, Order ID: 2804372329

✅ 3. Ссылка сформирована
   └─ QRC ID: AS1R000...

✅ 4. Оплата симулирована
   └─ Status: succeeded

⏸️ 5. Следующий шаг: Проверить статус

[▶️ Продолжить] [🗑️ Очистить] [🔄 Начать заново]
```

---

## Технические детали реализации

### Структура файлов

```
bot/
├── handlers/
│   └── admin/
│       └── test_b2p.py          # Новый файл с тестовым меню
├── keyboards/
│   └── inline/
│       └── test_b2p_keyboards.py  # Клавиатуры для тестирования
├── states/
│   └── test_b2p_states.py       # FSM states для тестирования
└── services/
    └── test_b2p_service.py      # Сервисный слой для тест-кейсов
```

### FSM States

```python
from aiogram.fsm.state import State, StatesGroup

class TestB2PStates(StatesGroup):
    # Основное меню
    main_menu = State()

    # Создание пользователя
    awaiting_user_creation = State()
    user_created = State()

    # Создание платежа
    selecting_subscription_period = State()
    payment_created = State()

    # Ссылка на оплату
    payment_url_created = State()

    # Симуляция оплаты
    payment_simulated = State()

    # Проверка статуса
    checking_status = State()

    # Очистка
    confirming_cleanup = State()
```

### FSM Data Schema

```python
{
    # Пользователь
    "test_user_uuid": "d50941b5-504e-448d-9c40-32c9b21c6722",
    "test_user_short_uuid": "abc123",
    "test_username": "test_user_1700000000",
    "test_telegram_id": 123456789,
    "test_user_db_id": 999,

    # Платеж
    "test_payment_id": 123,
    "test_order_id": "2804372329",
    "test_months": 1,
    "test_amount": 300.00,

    # Best2Pay
    "test_qrc_id": "AS1R000KOMEPGAIE9519CB1Q4PGN6ULN",
    "test_pay_url": "https://test.best2pay.net/sbp/pay/...",

    # Метаданные
    "test_started_at": "2025-11-18T12:00:00Z",
    "test_steps_completed": ["user_created", "payment_created", ...]
}
```

### Клавиатуры

```python
# Главное меню тестирования
def get_test_b2p_main_menu(i18n, lang, state_data):
    builder = InlineKeyboardBuilder()

    # Проверяем, какие шаги уже выполнены
    completed = state_data.get("test_steps_completed", [])

    # Шаг 1
    icon = "✅" if "user_created" in completed else "1️⃣"
    builder.button(text=f"{icon} Создать тестового пользователя",
                   callback_data="test_b2p:create_user")

    # Шаг 2 (доступен только после шага 1)
    if "user_created" in completed:
        icon = "✅" if "payment_created" in completed else "2️⃣"
        builder.button(text=f"{icon} Создать тестовый платеж",
                       callback_data="test_b2p:create_payment")
    else:
        builder.button(text="🔒 Создать тестовый платеж",
                       callback_data="test_b2p:locked")

    # ... и так далее для остальных шагов

    builder.button(text="ℹ️ Текущий тест-кейс",
                   callback_data="test_b2p:show_status")
    builder.button(text="🗑️ Очистить данные",
                   callback_data="test_b2p:cleanup")
    builder.button(text="◀️ Назад в админку",
                   callback_data="admin:main")

    builder.adjust(1)  # По одной кнопке в ряд
    return builder.as_markup()

# Выбор периода подписки
def get_subscription_period_keyboard():
    builder = InlineKeyboardBuilder()

    builder.button(text="1 месяц - 300₽",
                   callback_data="test_b2p:period:1:300")
    builder.button(text="3 месяца - 850₽",
                   callback_data="test_b2p:period:3:850")
    builder.button(text="6 месяцев - 1600₽",
                   callback_data="test_b2p:period:6:1600")
    builder.button(text="12 месяцев - 3000₽",
                   callback_data="test_b2p:period:12:3000")
    builder.button(text="◀️ Назад",
                   callback_data="test_b2p:main")

    builder.adjust(2, 2, 1)
    return builder.as_markup()
```

### Сервисный слой

```python
class TestB2PService:
    """Service for Best2Pay testing pipeline"""

    def __init__(self, settings, panel_service, best2pay_service):
        self.settings = settings
        self.panel = panel_service
        self.b2p = best2pay_service

    async def create_test_user(self, telegram_id: int) -> dict:
        """Create test user in panel and local DB"""
        username = f"test_user_{int(time.time())}"

        # Create in panel
        panel_user = await self.panel.create_user({
            "username": username,
            "telegramId": telegram_id,
            "email": f"{username}@test.local",
            "subscriptionDurationDays": 0,
            "trafficLimitBytes": 10737418240,  # 10GB
            "tags": ["test_user", "bot_test"]
        })

        # Create in local DB
        # ... (implementation)

        return {
            "uuid": panel_user["uuid"],
            "username": username,
            "telegram_id": telegram_id
        }

    async def create_test_payment(self, user_id: int, months: int, amount: float) -> dict:
        """Create test payment and register order in Best2Pay"""
        # Create DB record
        # Register in Best2Pay
        # Return payment data
        pass

    async def create_payment_url(self, order_id: str) -> dict:
        """Generate SBP payment URL"""
        return await self.b2p.create_payment_url(order_id, "sbp")

    async def simulate_payment(self, order_id: str, success: bool = True) -> dict:
        """Trigger test case in Best2Pay"""
        case_id = "150" if success else "151"
        return await self.b2p.trigger_test_case(order_id=order_id, case_id=case_id)

    async def check_subscription_status(self, user_uuid: str) -> dict:
        """Get user status from panel and local DB"""
        panel_data = await self.panel.get_user(user_uuid)
        # Get local DB data
        # Combine and return
        pass

    async def cleanup_test_data(self, user_uuid: str, user_db_id: int):
        """Delete test user and related data"""
        # Delete from panel
        await self.panel.delete_user(user_uuid)

        # Delete from local DB
        # ... (implementation)
        pass
```

---

## Безопасность и валидация

### Проверки перед выполнением действий

1. **Только админы:** Все хендлеры должны иметь `IsAdminFilter()`
2. **Только тестовое окружение:** Проверять `BEST2PAY_API_URL` содержит `test.best2pay.net`
3. **Тегирование:** Все тестовые пользователи должны иметь тег `test_user`
4. **Изоляция:** Использовать отдельную БД или schema для тестов

### Валидация FSM данных

```python
def validate_test_state(state_data: dict, required_keys: list) -> bool:
    """Validate that all required keys exist in FSM state"""
    return all(key in state_data for key in required_keys)

# Пример использования:
if not validate_test_state(state_data, ["test_user_uuid", "test_payment_id"]):
    await callback.answer("⚠️ Не все шаги выполнены", show_alert=True)
    return
```

---

## Логирование и мониторинг

### Формат логов

```python
logging.info(
    f"[TEST_B2P] User created: username={username}, "
    f"uuid={uuid}, telegram_id={telegram_id}"
)

logging.info(
    f"[TEST_B2P] Payment created: payment_id={payment_id}, "
    f"order_id={order_id}, amount={amount}, months={months}"
)

logging.info(
    f"[TEST_B2P] Payment simulated: order_id={order_id}, "
    f"case_id={case_id}, success={success}"
)
```

### Уведомления в лог-чат (опционально)

```python
# Отправка в admin log chat
await bot.send_message(
    chat_id=settings.LOG_CHAT_ID,
    text=(
        f"🧪 <b>Test B2P: Успешный тест-кейс</b>\n\n"
        f"Админ: {admin_name}\n"
        f"Пользователь: {username}\n"
        f"Платеж: {amount} RUB за {months} мес.\n"
        f"Статус: ✅ Подписка активирована"
    ),
    parse_mode="HTML"
)
```

---

## План внедрения

### Этап 1: Подготовка инфраструктуры
- [ ] Поднять тестовый сервер
- [ ] Развернуть тестовую панель Remnawave
- [ ] Создать тестового бота в BotFather
- [ ] Настроить тестовую БД
- [ ] Получить тестовые креды Best2Pay (если еще нет)
- [ ] Настроить webhook URL (ngrok или временный домен)

### Этап 2: Разработка кода
- [ ] Создать FSM states (`test_b2p_states.py`)
- [ ] Создать клавиатуры (`test_b2p_keyboards.py`)
- [ ] Создать сервисный слой (`test_b2p_service.py`)
- [ ] Создать хендлеры (`test_b2p.py`)
- [ ] Зарегистрировать роутер в admin router aggregate
- [ ] Добавить локализацию (ru/en)

### Этап 3: Тестирование
- [ ] Пройти полный пайплайн успешной оплаты
- [ ] Пройти полный пайплайн неуспешной оплаты
- [ ] Проверить edge cases (дубли, ошибки API, и т.д.)
- [ ] Проверить очистку данных
- [ ] Проверить работу на мобильном устройстве

### Этап 4: Документация
- [ ] Создать руководство пользователя
- [ ] Задокументировать API вызовы
- [ ] Добавить примеры и скриншоты

---

## Зависимости

### Python пакеты
```txt
aiogram>=3.0.0
aiohttp>=3.8.0
sqlalchemy>=2.0.0
pydantic>=2.0.0
```

### Внешние сервисы
- Remnawave Panel API
- Best2Pay Test API
- PostgreSQL database
- Telegram Bot API

---

## Дополнительные фичи (опционально)

### 1. История тест-кейсов
Сохранять все тест-кейсы в отдельную таблицу `test_cases`:

```sql
CREATE TABLE test_cases (
    id SERIAL PRIMARY KEY,
    admin_id BIGINT NOT NULL,
    test_user_uuid VARCHAR(255),
    test_username VARCHAR(255),
    payment_id INTEGER,
    order_id VARCHAR(255),
    amount DECIMAL(10, 2),
    months INTEGER,
    status VARCHAR(50),  -- success, failed, incomplete
    steps_completed TEXT[],
    created_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);
```

### 2. Массовое тестирование
Запуск N тест-кейсов параллельно для нагрузочного тестирования

### 3. Экспорт результатов
Генерация отчета в CSV/JSON с результатами всех тестов

### 4. Webhook inspector
Показывать сырые данные вебхука для отладки:
```
📨 Последний вебхук Best2Pay:

Время: 2025-11-18 12:00:05
Метод: POST
Path: /webhook/best2pay/notify
IP: 185.xxx.xxx.xxx

Body (XML):
<?xml version="1.0"?>
<operation>
  <order_id>2804372329</order_id>
  ...
</operation>

Подпись: ✅ Валидна
Обработка: ✅ Успешна (200ms)
```

---

## Итоговый чеклист запуска

### Перед началом работы:
- [ ] Все компоненты развернуты
- [ ] .env настроен правильно
- [ ] Webhook доступен извне
- [ ] Админ ID прописан
- [ ] Тестовые креды Best2Pay получены и проверены

### Проверка работоспособности:
```bash
# 1. Проверить подключение к панели
curl -H "Authorization: Bearer <API_KEY>" \
  https://test-panel.example.com/api/users

# 2. Проверить подключение к Best2Pay
curl -X POST https://test.best2pay.net/webapi/Register \
  -d "sector=8365&..."

# 3. Проверить webhook доступность
curl https://test-webhook.example.com/webhook/best2pay/notify

# 4. Проверить БД
psql -U postgres -d test_bot_db -c "SELECT COUNT(*) FROM users;"
```

---

## Контакты и поддержка

При возникновении проблем:
1. Проверить логи бота: `docker compose logs -f remnawave-tg-shop`
2. Проверить логи панели
3. Проверить документацию Best2Pay
4. Создать issue в репозитории

---

**Версия:** 1.0
**Дата:** 2025-11-18
**Автор:** AI Assistant
**Статус:** Готово к реализации
