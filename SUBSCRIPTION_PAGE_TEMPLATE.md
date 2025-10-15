# Шаблон страницы подписки из remnawave-telegram-sub-mini-app

Этот документ содержит структуру и компоненты из мини-приложения подписки для интеграции в личный кабинет.

## 📋 Структура компонентов

### 1. **SubscriptionInfoWidget** - Информация о подписке
Основной виджет с информацией о пользователе (аккордеон):

**Отображает:**
- Имя пользователя
- Статус подписки (ACTIVE/INACTIVE) с иконкой
- Дата истечения подписки (или ∞ для бессрочных)
- Использованный трафик / Лимит трафика

**Визуальные элементы:**
- Цветовая индикация статуса:
  - 🟢 Зеленый (teal) - активна, более 3 дней
  - 🟠 Оранжевый - истекает (0-3 дня)
  - 🔴 Красный - неактивна
- Иконки для каждого параметра (User, Check/X, Calendar, ArrowsUpDown)
- Адаптивная сетка (1-2 колонки в зависимости от экрана)

**Компонент:** `src/components/SubscriptionInfoWidget/SubscriptionInfoWidget.tsx`

---

### 2. **InstallationGuideWidget** - Инструкция по установке
Виджет с пошаговыми инструкциями по установке приложений:

**Функционал:**
- Автоопределение ОС пользователя
- Переключение между платформами (dropdown selector):
  - Android, iOS
  - Windows, macOS, Linux
  - Android TV, Apple TV
- Поддержка нескольких языков (en, ru, fa, zh)
- Динамическая загрузка конфигурации приложений из `app-config.json`

**Отображает:**
1. **Шаг 1:** Установка приложения
   - Кнопки для скачивания из конфига
   - Название приложения
2. **Шаг 2:** Импорт конфигурации
   - Кнопка "Открыть в приложении" с deeplink
   - Поддержка криптоссылок (happ://)
   - Поддержка обычных ссылок подписки

**Компонент:** `src/components/InstallationGuideWidget/InstallationGuideWidget.tsx`

---

### 3. **InfoBlock** - Информационный блок
Переиспользуемый компонент для отображения параметра:

```tsx
<InfoBlock
    color="blue"           // teal, green, red, blue, yellow, orange
    icon={<IconUser />}    // Иконка из @tabler/icons-react
    title="Имя"           // Заголовок
    value="username"      // Значение
/>
```

**Визуально:**
- Цветная иконка слева
- Заголовок сверху (маленький текст)
- Значение снизу (жирный текст)

**Компонент:** `src/components/InfoBlock/InfoBlock.tsx`

---

### 4. **SubscriptionLinkWidget** - QR-код и ссылка подписки
Виджет с QR-кодом и кнопкой копирования ссылки:

**Функционал:**
- Генерация QR-кода из subscription URL
- Кнопка копирования ссылки
- Опциональная ссылка на поддержку

**Компонент:** `src/components/SubQR/SubQR.tsx`

---

## 🎨 UI Framework

Проект использует **Mantine UI** v7 с компонентами:
- `Accordion` - для раскрывающихся блоков
- `SimpleGrid` - для адаптивной сетки
- `ThemeIcon` - для цветных иконок
- `Select` - для выбора платформы
- `Button`, `Text`, `Stack`, `Group` и др.

Иконки: `@tabler/icons-react`

---

## 📦 Конфигурация приложений

Файл: `public/assets/app-config.json`

Структура:
```json
{
  "config": {
    "additionalLocales": ["ru", "fa", "zh"],
    "branding": {
      "name": "Название сервиса",
      "logoUrl": "https://...",
      "supportUrl": "https://..."
    }
  },
  "platforms": {
    "ios": [...],
    "android": [...],
    "windows": [...],
    "macos": [...],
    "linux": [...],
    "androidTV": [...],
    "appleTV": [...]
  }
}
```

Каждое приложение:
```json
{
  "name": "Название приложения",
  "urlScheme": "streisand://",     // или "happ://" для криптоссылок
  "isNeedBase64Encoding": false,
  "installationStep": {
    "buttons": [
      {
        "buttonText": {
          "en": "Download",
          "ru": "Скачать",
          "fa": "...",
          "zh": "..."
        },
        "buttonLink": "https://..."
      }
    ]
  }
}
```

---

## 🔧 API Integration

### Получение информации о пользователе

**Endpoint:** `GET /api/users/by-short-uuid/{shortUuid}`

**Response:**
```typescript
{
  response: {
    user: {
      uuid: string
      username: string
      shortUuid: string
      userStatus: 'ACTIVE' | 'DISABLED' | 'LIMITED' | 'EXPIRED'
      expiresAt: string (ISO date)
      usedTrafficBytes: number
      trafficLimitBytes: number
      trafficUsed: string (formatted, e.g. "1.2 GB")
      trafficLimit: string (formatted, e.g. "10 GB" or "0" for unlimited)
    }
    subscriptionUrl: string (e.g. "https://sub.example.com/...")
    happ: {
      cryptoLink: string (e.g. "happ://crypt3/...")
    }
  }
}
```

### Используется в коде:
```typescript
import { fetchUserByTelegramId } from '@/api/fetchUserByTgId'

const user = await fetchUserByTelegramId(telegramId)
```

---

## 🌐 Интернационализация (i18n)

Используется `next-intl` с переводами в:
- `messages/en.json`
- `messages/ru.json`
- `messages/fa.json`
- `messages/zh.json`

Ключевые переводы:
```json
{
  "subscription-info.widget.active": "Активна",
  "subscription-info.widget.inactive": "Неактивна",
  "subscription-info.widget.name": "Имя",
  "subscription-info.widget.status": "Статус",
  "subscription-info.widget.expires": "Истекает",
  "subscription-info.widget.bandwidth": "Трафик",
  "installation-guide.widget.installation": "Установка",
  "installation-guide.widget.select-device": "Выберите устройство"
}
```

---

## 🎯 Основные утилиты

### 1. Расчет оставшихся дней
```typescript
// utils/utils.ts
export const calculateDaysLeft = (expiresAt: string): number => {
  const now = dayjs()
  const expireDate = dayjs(expiresAt)
  return expireDate.diff(now, 'day')
}
```

### 2. Форматирование даты истечения
```typescript
export const getExpirationTextUtil = (
  expiresAt: string,
  t: Function,
  lang: string
): string => {
  const daysLeft = calculateDaysLeft(expiresAt)

  if (daysLeft > 50 * 365) return t('expires.never')
  if (daysLeft < 0) return t('expires.expired')
  if (daysLeft === 0) return t('expires.today')

  return t('expires.in-days', { days: daysLeft })
}
```

### 3. Открытие deeplink
```typescript
const openDeepLink = (
  urlScheme: string,
  subscriptionUrl: string,
  cryptoLink?: string
) => {
  if (urlScheme.startsWith('happ') && cryptoLink) {
    window.open(cryptoLink, '_blank')
  } else {
    window.open(`${urlScheme}${subscriptionUrl}`, '_blank')
  }
}
```

---

## 📱 Responsive Design

Компоненты адаптивны:
- **Mobile first** подход
- Брейкпоинты Mantine:
  - `xs`: 576px
  - `sm`: 768px
  - `md`: 992px
  - `lg`: 1200px
  - `xl`: 1408px

Пример адаптивной сетки:
```tsx
<SimpleGrid
  cols={{ base: 1, xs: 2, sm: 2 }}
  spacing="xs"
>
  {/* InfoBlocks */}
</SimpleGrid>
```

---

## 🚀 Интеграция в личный кабинет

### Рекомендуемая структура:

```
personal-cabinet/
├── components/
│   ├── SubscriptionCard/          # Карточка подписки (адаптация SubscriptionInfoWidget)
│   │   ├── SubscriptionCard.tsx
│   │   └── InfoBlock.tsx
│   ├── ConnectionGuide/           # Инструкция по подключению (адаптация InstallationGuideWidget)
│   │   ├── ConnectionGuide.tsx
│   │   ├── PlatformSelector.tsx
│   │   └── AppInstallStep.tsx
│   ├── QRCodeBlock/              # QR-код и ссылка
│   │   └── QRCodeBlock.tsx
│   └── PaymentMethods/           # Ваши кнопки оплаты
│       └── PaymentButtons.tsx
├── api/
│   └── subscription.ts           # API для получения данных пользователя
└── config/
    └── apps-config.json         # Конфигурация приложений
```

### Примерная разметка личного кабинета:

```tsx
<Container>
  {/* Заголовок с логотипом */}
  <Header logo={config.branding.logoUrl} name={config.branding.name} />

  {/* Информация о подписке */}
  <SubscriptionCard user={userData} />

  {/* Если подписка истекла - показать способы оплаты */}
  {!isActive && <PaymentMethods />}

  {/* Если подписка активна - показать инструкцию */}
  {isActive && (
    <>
      <QRCodeBlock url={subscriptionUrl} />
      <ConnectionGuide
        appsConfig={appsConfig}
        subscriptionUrl={subscriptionUrl}
        cryptoLink={cryptoLink}
      />
    </>
  )}
</Container>
```

---

## 💡 Ключевые фичи для адаптации:

1. **Автоопределение платформы** - используйте `useOs()` из `@mantine/hooks`
2. **Поддержка криптоссылок** - проверяйте `isCryptoLinkEnabled` и фильтруйте приложения
3. **Многоязычность** - интегрируйте переводы из `messages/`
4. **Конфигурация приложений** - храните в JSON или БД
5. **Цветовая индикация** - используйте цвета для статусов подписки
6. **Responsive layout** - адаптация под мобильные устройства

---

## 📚 Зависимости

```json
{
  "@mantine/core": "^7.x",
  "@mantine/hooks": "^7.x",
  "@tabler/icons-react": "^3.x",
  "next-intl": "^3.x",
  "dayjs": "^1.x",
  "qrcode.react": "^3.x",
  "@telegram-apps/sdk-react": "^1.x"
}
```

---

## 🔗 Полезные ссылки

- Mantine UI: https://mantine.dev/
- Tabler Icons: https://tabler-icons.io/
- Next-intl: https://next-intl-docs.vercel.app/
- Dayjs: https://day.js.org/

---

## 📝 Примечания

- Компоненты используют TypeScript
- Стили: CSS Modules + Mantine's built-in styling
- Формат конфигурации можно адаптировать под ваши нужды
- QR-код генерируется библиотекой `qrcode.react`
- Deeplinks работают через `window.open()`

---

## 🎨 Кастомизация

Для изменения внешнего вида измените:
1. **Цветовую схему** - в Mantine theme provider
2. **Иконки** - замените на свои из Tabler Icons
3. **Брендинг** - в `app-config.json` → `config.branding`
4. **Тексты** - в файлах переводов `messages/*.json`

---

Эта структура позволяет легко интегрировать компоненты подписки в ваш личный кабинет,
сохраняя удобный UX и поддержку всех платформ.
