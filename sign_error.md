# Best2Pay Invalid Signature - Детальный анализ

## 📋 Описание проблемы

При интеграции платежного шлюза Best2Pay (webapi/Register) возникает ошибка **109 "Invalid signature"**.

**Параметры из кабинета Best2Pay:**
- Номер сектора: `22436`
- Сектор для запросов к API: `fccdeb67-cc87-47f8-83c4-3fcddcbf765b`
- Пароль для подписи: `X5e87TgD`

**Тестовый запрос:**
- sector: `22436`
- amount: `15000` (копеек, т.е. 150 рублей)
- currency: `643` (RUB)
- password: `X5e87TgD`

**Результат:**
```xml
<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<error>
    <description>Invalid signature</description>
    <code>109</code>
</error>
```

---

## 📖 Алгоритм формирования подписи (из документации Best2Pay)

### Официальное описание:

**Приложение №2: Алгоритм формирования цифровой подписи**

1. **Формируется строка** из значений заданных параметров для каждого вида Запросов/ответов и в конце добавляется пароль ТСП для цифровой подписи.

2. **Полученная строка преобразуется в хэш** алгоритмом SHA256. Например, с использованием функции `CryptoJS.SHA256(str).toString()` библиотеки crypto-js.min.js. При вычислении SHA256 для правильного кодирования русских символов, необходимо использовать только кодировку **UTF-8**.

3. **Полученное значение хеша кодируется** алгоритмом Base64 (**кодируется не его битовое представление, а его шестнадцатеричное строковое представление в нижнем регистре**) в итоговую цифровую подпись signature. Например, с использованием функции `Base64.encode(sha256)` jquery.base64.js.

### Для webapi/Register:

**Формула подписи:**
```
str = sector + amount + currency + password
```

---

## 🧪 Эталонный пример из документации Best2Pay

### Исходные данные:
```
sector = 1
amount = 100
currency = 643
email = info@mail.ru
phone = 8911111111111
reference = 1s23d333d333
description = Оплата товара ноутбук ASUS X55A
password = test
```

### Вычисление:
```
str = sector + amount + currency + password
str = "1100643test"
```

### Результат:
```
sha256 = f665bf26a3d24e00b5646c829ea07cef67ed7a2af5eb1fbc258720c651136fee
signature = ZjY2NWJmMjZhM2QyNGUwMGI1NjQ2YzgyOWVhMDdjZWY2N2VkN2EyYWY1ZWIxZmJjMjU4NzIwYzY1MTEzNmZlZQ==
```

### Ответ (успешный):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<order>
    <id>561</id>
    <state>REGISTERED</state>
    <date>2014.07.10 15:07:45</date>
    <amount>100</amount>
    <currency>643</currency>
    <email>info@mail.ru</email>
    <phone>8911111111111</phone>
    <reference>1s23d333d333</reference>
    <description>Оплата товара ноутбук ASUS X55A</description>
    <signature>ZTBiMjk0NzBiMTcxYjUxMmQ2MzVjNTE5M2FiODNkZTk3N2FiZTFkMmQwNmY5YmEwZDdjYmYxODJmODMxMjdlYg==</signature>
</order>
```

---

## 💻 Наша реализация (Python)

### Код генерации подписи:

```python
import hashlib
import base64

def generate_signature(sector, amount, currency, password):
    """
    Генерация подписи по алгоритму Best2Pay

    Args:
        sector: Номер сектора (строка)
        amount: Сумма в копейках (int)
        currency: Код валюты (строка)
        password: Пароль для подписи (строка)

    Returns:
        str: Base64 подпись
    """
    # Шаг 1: Формируем строку
    signature_string = f"{sector}{amount}{currency}{password}"

    # Шаг 2: Вычисляем SHA256 (UTF-8 кодировка)
    sha256_hash = hashlib.sha256(signature_string.encode('utf-8')).hexdigest().lower()

    # Шаг 3: Base64 кодирование HEX-строки (не битового представления!)
    signature = base64.b64encode(sha256_hash.encode('utf-8')).decode('utf-8')

    return signature
```

### Использование:

```python
signature = generate_signature(
    sector="22436",
    amount=15000,      # 150 рублей = 15000 копеек
    currency="643",     # RUB
    password="X5e87TgD"
)
```

---

## ✅ Проверка алгоритма на эталонном примере

### Тест с примером из документации:

```python
# Входные данные из документации
sector = "1"
amount = "100"
currency = "643"
password = "test"

# Вычисление
str_value = f"{sector}{amount}{currency}{password}"
# Результат: "1100643test"

sha256_value = hashlib.sha256(str_value.encode('utf-8')).hexdigest().lower()
# Результат: f665bf26a3d24e00b5646c829ea07cef67ed7a2af5eb1fbc258720c651136fee

signature_value = base64.b64encode(sha256_value.encode('utf-8')).decode('utf-8')
# Результат: ZjY2NWJmMjZhM2QyNGUwMGI1NjQ2YzgyOWVhMDdjZWY2N2VkN2EyYWY1ZWIxZmJjMjU4NzIwYzY1MTEzNmZlZQ==
```

### Сравнение:

| Параметр | Ожидается (из документации) | Получено | Результат |
|----------|----------------------------|----------|-----------|
| Строка | `1100643test` | `1100643test` | ✅ СОВПАДАЕТ |
| SHA256 | `f665bf26a3d24e00b5646c829ea07cef67ed7a2af5eb1fbc258720c651136fee` | `f665bf26a3d24e00b5646c829ea07cef67ed7a2af5eb1fbc258720c651136fee` | ✅ СОВПАДАЕТ |
| Signature | `ZjY2NWJmMjZhM2QyNGUwMGI1NjQ2YzgyOWVhMDdjZWY2N2VkN2EyYWY1ZWIxZmJjMjU4NzIwYzY1MTEzNmZlZQ==` | `ZjY2NWJmMjZhM2QyNGUwMGI1NjQ2YzgyOWVhMDdjZWY2N2VkN2EyYWY1ZWIxZmJjMjU4NzIwYzY1MTEzNmZlZQ==` | ✅ СОВПАДАЕТ |

**Вывод:** ✅✅✅ **АЛГОРИТМ РАБОТАЕТ ПРАВИЛЬНО!**

---

## 🔬 Применение к нашим реальным данным

### Входные параметры:
```
sector = "22436"
amount = "15000"  (150 рублей в копейках)
currency = "643"
password = "X5e87TgD"
```

### Вычисление:

**Шаг 1: Формирование строки**
```
str = "2243615000643X5e87TgD"
```

Детальная информация:
- Длина: 21 символ
- UTF-8 bytes (hex): `323234333631353030303634335835653837546744`
- Посимвольно:
  ```
  [0] '2' = 50 (0x32)
  [1] '2' = 50 (0x32)
  [2] '4' = 52 (0x34)
  [3] '3' = 51 (0x33)
  [4] '6' = 54 (0x36)
  [5] '1' = 49 (0x31)
  [6] '5' = 53 (0x35)
  [7] '0' = 48 (0x30)
  [8] '0' = 48 (0x30)
  [9] '0' = 48 (0x30)
  [10] '6' = 54 (0x36)
  [11] '4' = 52 (0x34)
  [12] '3' = 51 (0x33)
  [13] 'X' = 88 (0x58)
  [14] '5' = 53 (0x35)
  [15] 'e' = 101 (0x65)
  [16] '8' = 56 (0x38)
  [17] '7' = 55 (0x37)
  [18] 'T' = 84 (0x54)
  [19] 'g' = 103 (0x67)
  [20] 'D' = 68 (0x44)
  ```

**Шаг 2: SHA256**
```
sha256 = dac0f6a096635fb77389ea915f58906536bcddeee7f9d1cc6da70aca2e00bcf1
```

**Шаг 3: Base64**
```
signature = ZGFjMGY2YTA5NjYzNWZiNzczODllYTkxNWY1ODkwNjUzNmJjZGRlZWU3ZjlkMWNjNmRhNzBhY2EyZTAwYmNmMQ==
```

### Тестовый запрос к API:

**Payload:**
```json
{
  "sector": "22436",
  "amount": 15000,
  "currency": "643",
  "description": "Test payment",
  "reference": "test_123",
  "signature": "ZGFjMGY2YTA5NjYzNWZiNzczODllYTkxNWY1ODkwNjUzNmJjZGRlZWU3ZjlkMWNjNmRhNzBhY2EyZTAwYmNmMQ=="
}
```

**Ответ от Best2Pay:**
```xml
<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<error>
    <description>Invalid signature</description>
    <code>109</code>
</error>
```

---

## 🧐 Что было проверено

### ✅ Алгоритм подписи:
- [x] Порядок параметров: `sector + amount + currency + password`
- [x] UTF-8 кодировка при вычислении SHA256
- [x] SHA256 в lowercase (нижний регистр)
- [x] Base64 кодирование HEX-строки (не битового представления)
- [x] Тест на эталонном примере из документации - **УСПЕШНО**

### ✅ Формат данных:
- [x] amount передается как integer в копейках (15000, не 150.0)
- [x] currency = "643" (RUB)
- [x] sector передается как строка "22436"
- [x] password без пробелов в начале/конце

### ✅ Различные варианты:
- [x] Использование UUID вместо числового ID - **ОШИБКА 102**
- [x] Смешанное использование (UUID в запросе, числовой в подписи) - **ОШИБКА 102/109**
- [x] Разные варианты похожих символов в пароле - **ВСЕ ОШИБКА 109**

### ✅ Методы отправки:
- [x] `data=dict` с integer amount
- [x] `data=dict` с string amount
- [x] `FormData`
- [x] Все варианты возвращают **ОШИБКА 109**

---

## 📊 Результаты всех тестов

| Тест | Параметры | Результат |
|------|-----------|-----------|
| Эталонный пример (sector=1, password=test) | По документации | ✅ УСПЕХ |
| Numeric ID + Password | sector=22436, password=X5e87TgD | ❌ Error 109 |
| UUID + Password | sector=fccdeb67-..., password=X5e87TgD | ❌ Error 102 |
| UUID в запросе, Numeric в подписи | Смешанный подход | ❌ Error 102 |
| Numeric в запросе, UUID в подписи | Обратный подход | ❌ Error 109 |
| Варианты пароля (X5e87TgO, X5e87Tg0, etc.) | 11 вариантов | ❌ Все Error 109 |

---

## 🎯 Заключение

### Что точно работает правильно:
1. ✅ Алгоритм формирования подписи реализован **КОРРЕКТНО**
2. ✅ Формат данных соответствует требованиям API
3. ✅ Порядок параметров правильный
4. ✅ Кодировка UTF-8 используется правильно
5. ✅ Base64 кодирование HEX-строки (не битов) работает правильно

### Проблема:
🔴 **Пароль `X5e87TgD` НЕ СОВПАДАЕТ с реальным паролем в системе Best2Pay**

### Доказательства:
1. Алгоритм работает на эталонном примере из документации
2. Все остальные параметры корректны
3. Best2Pay постоянно возвращает ошибку 109 "Invalid signature"
4. Изменение пароля меняет результат, но все варианты неправильные

### Вероятные причины:
- Пароль на скриншоте отображается с ошибкой (похожие символы)
- Пароль был изменен после создания скриншота
- Пароль в кабинете замаскирован и требует раскрытия
- В системе Best2Pay используется другой пароль

---

## ❓ Вопросы для техподдержки Best2Pay

### Письмо в техподдержку:

```
Тема: Ошибка 109 "Invalid signature" при интеграции webapi/Register

Добрый день!

Интегрирую платежный шлюз Best2Pay через API (webapi/Register).

ПРОБЛЕМА:
Получаю ошибку 109 "Invalid signature" при всех попытках регистрации заказа.

НАШИ ПАРАМЕТРЫ:
- Номер сектора: 22436
- Сектор для запросов к API: fccdeb67-cc87-47f8-83c4-3fcddcbf765b
- Пароль из кабинета: X5e87TgD

АЛГОРИТМ ПОДПИСИ:
Реализован строго по документации (Приложение №2):
1. str = sector + amount + currency + password
2. SHA256(str) в UTF-8 кодировке
3. Base64(hex_string) - кодируется HEX-строка, не битовое представление

ПРОВЕРКА:
Алгоритм проверен на эталонном примере из документации:
- sector=1, amount=100, currency=643, password=test
- Ожидаемая подпись: ZjY2NWJmMjZhM2QyNGUwMGI1NjQ2YzgyOWVhMDdjZWY2N2VkN2EyYWY1ZWIxZmJjMjU4NzIwYzY1MTEzNmZlZQ==
- Наша подпись: ZjY2NWJmMjZhM2QyNGUwMGI1NjQ2YzgyOWVhMDdjZWY2N2VkN2EyYWY1ZWIxZmJjMjU4NzIwYzY1MTEzNmZlZQ==
- Результат: ✅ ПОЛНОЕ СОВПАДЕНИЕ

ТЕСТОВЫЙ ЗАПРОС:
POST https://pay.best2pay.net/webapi/Register
{
  "sector": "22436",
  "amount": 15000,
  "currency": "643",
  "description": "Test payment",
  "reference": "test_123",
  "signature": "ZGFjMGY2YTA5NjYzNWZiNzczODllYTkxNWY1ODkwNjUzNmJjZGRlZWU3ZjlkMWNjNmRhNzBhY2EyZTAwYmNmMQ=="
}

ОТВЕТ:
<?xml version="1.0" encoding="UTF-8"?>
<error>
    <description>Invalid signature</description>
    <code>109</code>
</error>

ВОПРОСЫ:
1. Правильно ли отображается пароль "X5e87TgD" в интерфейсе кабинета?
2. Может ли реальный пароль отличаться от отображаемого?
3. Можете ли проверить/выслать правильный пароль для подписи?
4. Нужны ли дополнительные настройки для доступа к API?
5. Есть ли ограничения по IP-адресам для нашего сектора?

ДЕТАЛИ ДЛЯ ПРОВЕРКИ:
- Строка для подписи: "2243615000643X5e87TgD"
- SHA256: dac0f6a096635fb77389ea915f58906536bcddeee7f9d1cc6da70aca2e00bcf1
- Signature: ZGFjMGY2YTA5NjYzNWZiNzczODllYTkxNWY1ODkwNjUzNmJjZGRlZWU3ZjlkMWNjNmRhNzBhY2EyZTAwYmNmMQ==

Можете ли проверить на своей стороне, правильна ли эта подпись для указанных параметров?

Заранее благодарю за помощь!
```

---

## 🛠️ Следующие шаги

### Вариант 1: Получить правильный пароль из кабинета

1. Открыть личный кабинет Best2Pay
2. Найти раздел "Управление секторами" → Сектор 22436
3. Найти поле "Пароль для подписи"
4. **СКОПИРОВАТЬ** пароль (не переписывать вручную!)
5. Запустить интерактивный тест:
   ```bash
   python3 /home/ubuntu/remnawave-tg-shop/test_with_real_password.py
   ```
6. Вставить скопированный пароль
7. Если тест успешен → обновить `.env`

### Вариант 2: Сгенерировать новый пароль

1. В кабинете Best2Pay найти кнопку "Изменить пароль" или "Сгенерировать"
2. Создать новый пароль
3. Скопировать его
4. Запустить интерактивный тест (см. выше)
5. Обновить `.env`

### Вариант 3: Обратиться в техподдержку

Отправить письмо (текст выше) в техподдержку Best2Pay и дождаться ответа.

---

## 📝 Дополнительная информация

### Успешный заказ из кабинета

На скриншоте из кабинета виден успешно созданный заказ:
- Order ID: 2691171254
- Amount: 100.00 RUB
- Status: REGISTERED
- Date: 2025.10.14 19:23:08

**URL для оплаты:**
```
https://pay.best2pay.net/webapi/Purchase?sector=22436&signature=NWQ2NGY0M0...&id=2691171254
```

Обратите внимание: в URL используется **числовой sector=22436**, не UUID.

### Тестовые скрипты

Созданы следующие скрипты для отладки:

1. **test_with_real_password.py** - Интерактивный тест с вводом пароля
2. **test_exact_example.py** - Воспроизведение примера из документации
3. **test_signature_exact.py** - Детальная проверка алгоритма
4. **test_best2pay_debug.py** - Тест разных методов отправки
5. **test_best2pay_password_variants.py** - Тест вариантов пароля
6. **test_best2pay_mixed.py** - Тест смешанного использования UUID/ID
7. **test_final_request.py** - Финальный тест с проверенной подписью

### Структура кода в проекте

**Файл:** `/home/ubuntu/remnawave-tg-shop/bot/services/best2pay_service.py`

Основные методы:
- `_generate_signature(data: str)` - Генерация подписи
- `register_order()` - Регистрация заказа (webapi/Register)
- `create_payment_url()` - Создание URL для оплаты (webapi/PurchaseSBP)
- `verify_signature()` - Проверка подписи в webhook

**Конфигурация:** `/home/ubuntu/remnawave-tg-shop/.env`
```env
BEST2PAY_SECTOR_ID=22436
BEST2PAY_SECTOR_UUID=fccdeb67-cc87-47f8-83c4-3fcddcbf765b
BEST2PAY_PASSWORD=X5e87TgD
BEST2PAY_ENABLED=True
```

---

## 📚 Ссылки на документацию

- **Документация Best2Pay:** B2P API - Общая v2.18.1.pdf
- **Приложение №2:** Алгоритм формирования цифровой подписи (страница ~456)
- **webapi/Register:** Описание метода регистрации заказа (страница ~13)
- **webapi/PurchaseSBP:** Описание метода оплаты через СБП (страница ~414)

---

**Дата создания:** 2025-10-14
**Последнее обновление:** 2025-10-14
**Статус:** Ожидание правильного пароля от Best2Pay
