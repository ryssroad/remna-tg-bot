# 🚀 Интеграция компонентов подписки в личный кабинет

## 📍 Расположение файлов

### Документация:
- `SUBSCRIPTION_PAGE_TEMPLATE.md` - Полное описание шаблона и архитектуры
- `subscription-template-components/` - Извлечённые React-компоненты

### Исходное приложение:
- `~/remnawave-telegram-sub-mini-app/` - Полное Next.js приложение (работающий контейнер)

---

## 🎯 Что извлечено

### ✅ React-компоненты (готовы к использованию):

1. **SubscriptionInfoWidget** - Карточка с информацией о подписке
   - Показывает: имя, статус, дату истечения, трафик
   - Адаптивный аккордеон с цветовой индикацией

2. **InstallationGuideWidget** - Пошаговая инструкция по подключению
   - Автоопределение ОС пользователя
   - Поддержка всех платформ (iOS, Android, Windows, macOS, Linux, TV)
   - Кнопки для скачивания приложений
   - Deeplinks для автоматического импорта

3. **InfoBlock** - Переиспользуемый информационный блок
   - Иконка + заголовок + значение
   - Настраиваемый цвет

4. **SubQR** - QR-код и копирование ссылки подписки
   - Генерация QR из subscription URL
   - Кнопка копирования

5. **utils.ts** - Утилиты:
   - Расчет оставшихся дней
   - Форматирование дат и трафика

### ✅ Конфигурация:

- `example-app-config.json` - Конфиг приложений для всех платформ
  - Настройки брендирования
  - Список приложений с deeplinks
  - Многоязычные тексты

---

## 🏗️ Архитектура личного кабинета

### Рекомендуемая структура:

```
your-personal-cabinet/
├── pages/
│   └── dashboard.tsx              # Главная страница ЛК
├── components/
│   ├── subscription/
│   │   ├── SubscriptionCard.tsx   # Адаптированный SubscriptionInfoWidget
│   │   ├── ConnectionGuide.tsx    # Адаптированный InstallationGuideWidget
│   │   ├── QRBlock.tsx           # Адаптированный SubQR
│   │   └── InfoBlock.tsx         # Переиспользуемый блок
│   ├── payment/
│   │   ├── PaymentMethods.tsx    # Ваши способы оплаты
│   │   └── PaymentButtons.tsx    # Кнопки FreeKassa, CryptoPay и т.д.
│   └── layout/
│       ├── Header.tsx
│       └── Footer.tsx
├── api/
│   └── subscription.ts           # API для получения данных пользователя
├── config/
│   └── apps.json                # Конфигурация приложений
└── utils/
    └── subscription.ts          # Утилиты (скопированные)
```

---

## 📋 Пошаговая интеграция

### Шаг 1: Установите зависимости

```bash
npm install @mantine/core @mantine/hooks @tabler/icons-react
npm install next-intl dayjs qrcode.react
```

### Шаг 2: Скопируйте компоненты

```bash
cp -r subscription-template-components/* your-project/src/components/
```

### Шаг 3: Настройте API для получения данных пользователя

**Endpoint бота:** `GET /api/users/by-telegram-id/{telegramId}`

Пример интеграции:

```typescript
// api/subscription.ts
export async function getUserSubscription(telegramId: number) {
  const response = await fetch(
    `${process.env.BOT_API_URL}/api/users/by-telegram-id/${telegramId}`,
    {
      headers: {
        'Authorization': `Bearer ${process.env.BOT_API_KEY}`
      }
    }
  )

  if (!response.ok) {
    throw new Error('User not found')
  }

  return await response.json()
}
```

**Ответ API панели:**

```json
{
  "response": {
    "uuid": "...",
    "username": "john_doe_123456",
    "status": "ACTIVE",
    "expireAt": "2025-12-31T23:59:59.000Z",
    "usedTrafficBytes": 1500000000,
    "trafficLimitBytes": 10000000000,
    "subscriptionUrl": "https://sub.example.com/...",
    "happ": {
      "cryptoLink": "happ://crypt3/..."
    }
  }
}
```

### Шаг 4: Создайте главную страницу ЛК

```tsx
// pages/dashboard.tsx
import { useState, useEffect } from 'react'
import { Container, Stack } from '@mantine/core'
import { SubscriptionCard } from '@/components/subscription/SubscriptionCard'
import { ConnectionGuide } from '@/components/subscription/ConnectionGuide'
import { PaymentMethods } from '@/components/payment/PaymentMethods'
import { getUserSubscription } from '@/api/subscription'
import appsConfig from '@/config/apps.json'

export default function Dashboard() {
  const [userData, setUserData] = useState(null)
  const [loading, setLoading] = useState(true)

  const telegramId = 123456 // Получите из Telegram WebApp или авторизации

  useEffect(() => {
    const fetchData = async () => {
      try {
        const data = await getUserSubscription(telegramId)
        setUserData(data.response)
      } catch (error) {
        console.error('Failed to fetch user data:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [telegramId])

  if (loading) return <div>Loading...</div>

  const isActive = userData?.status === 'ACTIVE'

  return (
    <Container size="lg" py="xl">
      <Stack gap="xl">
        {/* Информация о подписке */}
        {userData && <SubscriptionCard user={userData} />}

        {/* Если неактивна - показываем способы оплаты */}
        {!isActive && <PaymentMethods />}

        {/* Если активна - показываем инструкцию по подключению */}
        {isActive && (
          <ConnectionGuide
            user={userData}
            appsConfig={appsConfig}
            cryptoLinkEnabled={true}
          />
        )}
      </Stack>
    </Container>
  )
}
```

### Шаг 5: Адаптируйте компоненты под свой проект

#### Пример адаптации SubscriptionCard:

```tsx
// components/subscription/SubscriptionCard.tsx
import { Accordion, SimpleGrid, Stack, Text, ThemeIcon } from '@mantine/core'
import { IconCheck, IconX, IconUser, IconCalendar, IconArrowsUpDown } from '@tabler/icons-react'
import { InfoBlock } from './InfoBlock'
import { calculateDaysLeft, formatDate } from '@/utils/subscription'

interface SubscriptionCardProps {
  user: {
    username: string
    status: 'ACTIVE' | 'DISABLED' | 'LIMITED' | 'EXPIRED'
    expireAt: string
    usedTrafficBytes: number
    trafficLimitBytes: number
  }
}

export function SubscriptionCard({ user }: SubscriptionCardProps) {
  const daysLeft = calculateDaysLeft(user.expireAt)
  const isActive = user.status === 'ACTIVE'

  const getStatusColor = () => {
    if (isActive && daysLeft > 3) return 'teal'
    if (isActive && daysLeft <= 3) return 'orange'
    return 'red'
  }

  return (
    <Accordion variant="separated">
      <Accordion.Item value="subscription">
        <Accordion.Control
          icon={
            <ThemeIcon color={getStatusColor()} size="lg" variant="light">
              {isActive ? <IconCheck size={20} /> : <IconX size={20} />}
            </ThemeIcon>
          }
        >
          <Stack gap={3}>
            <Text fw={500} size="md">{user.username}</Text>
            <Text c="dimmed" size="xs">
              {isActive ? `Истекает через ${daysLeft} дней` : 'Неактивна'}
            </Text>
          </Stack>
        </Accordion.Control>

        <Accordion.Panel>
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xs">
            <InfoBlock
              color="blue"
              icon={<IconUser size={20} />}
              title="Имя пользователя"
              value={user.username}
            />

            <InfoBlock
              color={isActive ? 'green' : 'red'}
              icon={isActive ? <IconCheck size={20} /> : <IconX size={20} />}
              title="Статус"
              value={isActive ? 'Активна' : 'Неактивна'}
            />

            <InfoBlock
              color="red"
              icon={<IconCalendar size={20} />}
              title="Истекает"
              value={formatDate(user.expireAt)}
            />

            <InfoBlock
              color="yellow"
              icon={<IconArrowsUpDown size={20} />}
              title="Трафик"
              value={`${formatBytes(user.usedTrafficBytes)} / ${
                user.trafficLimitBytes === 0 ? '∞' : formatBytes(user.trafficLimitBytes)
              }`}
            />
          </SimpleGrid>
        </Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  )
}
```

### Шаг 6: Добавьте компонент с методами оплаты

```tsx
// components/payment/PaymentMethods.tsx
import { Stack, Title, Button, Group } from '@mantine/core'
import { IconCreditCard, IconCurrencyBitcoin } from '@tabler/icons-react'

export function PaymentMethods() {
  const handlePayment = (method: string) => {
    // Интеграция с вашими платёжными системами
    window.location.href = `/payment/${method}`
  }

  return (
    <Stack gap="md">
      <Title order={3}>Способы оплаты</Title>

      <Group>
        <Button
          leftSection={<IconCreditCard size={20} />}
          onClick={() => handlePayment('freekassa')}
          variant="light"
        >
          FreeKassa
        </Button>

        <Button
          leftSection={<IconCurrencyBitcoin size={20} />}
          onClick={() => handlePayment('cryptopay')}
          variant="light"
        >
          CryptoPay
        </Button>
      </Group>
    </Stack>
  )
}
```

---

## 🔧 Настройка конфигурации приложений

Скопируйте `example-app-config.json` и настройте под свой сервис:

```json
{
  "config": {
    "additionalLocales": ["ru"],
    "branding": {
      "name": "Ваш VPN",
      "logoUrl": "https://your-domain.com/logo.png",
      "supportUrl": "https://t.me/your_support"
    }
  },
  "platforms": {
    "ios": [
      {
        "name": "Streisand",
        "urlScheme": "streisand://",
        "installationStep": {
          "buttons": [
            {
              "buttonText": {
                "ru": "Скачать из App Store",
                "en": "Download from App Store"
              },
              "buttonLink": "https://apps.apple.com/..."
            }
          ]
        }
      }
    ],
    "android": [...],
    "windows": [...],
    "macos": [...],
    "linux": [...]
  }
}
```

---

## 🎨 Кастомизация дизайна

### Настройка Mantine Theme:

```tsx
// _app.tsx или layout.tsx
import { MantineProvider, createTheme } from '@mantine/core'

const theme = createTheme({
  primaryColor: 'blue',
  colors: {
    // Ваши цвета
  },
  fontFamily: 'Inter, sans-serif'
})

function App({ Component, pageProps }) {
  return (
    <MantineProvider theme={theme}>
      <Component {...pageProps} />
    </MantineProvider>
  )
}
```

### Изменение цветов статусов:

В `SubscriptionCard.tsx` измените:
- `teal` → ваш цвет активной подписки
- `orange` → ваш цвет истекающей подписки
- `red` → ваш цвет неактивной подписки

---

## 🌐 Локализация

Создайте файлы переводов:

```json
// locales/ru.json
{
  "subscription": {
    "active": "Активна",
    "inactive": "Неактивна",
    "name": "Имя пользователя",
    "status": "Статус",
    "expires": "Истекает",
    "traffic": "Трафик",
    "expiresIn": "Истекает через {days} дней",
    "expiresNever": "Бессрочно"
  },
  "installation": {
    "title": "Установка",
    "selectDevice": "Выберите устройство",
    "step1": "Установите приложение",
    "step2": "Импортируйте конфигурацию"
  }
}
```

---

## 📱 Адаптация для Telegram WebApp

Если вы создаёте Telegram Mini App:

```tsx
import { useInitData } from '@telegram-apps/sdk-react'

function Dashboard() {
  const initData = useInitData()
  const telegramId = initData?.user?.id

  // Используйте telegramId для получения данных
}
```

---

## 🔗 API Endpoints

### Для получения данных пользователя:

**Из бота:**
- `GET /api/users/by-telegram-id/{telegramId}` - получить пользователя по Telegram ID

**Из панели:**
- `GET /api/users/by-telegram-id/{telegramId}` - получить пользователя
- `GET /api/users/{uuid}` - получить по UUID
- `GET /api/users/by-short-uuid/{shortUuid}` - получить по Short UUID

---

## ✅ Checklist интеграции

- [ ] Установлены зависимости (@mantine/core, @tabler/icons-react, dayjs)
- [ ] Скопированы компоненты в проект
- [ ] Настроен API для получения данных пользователя
- [ ] Создана главная страница ЛК
- [ ] Адаптированы компоненты под ваш дизайн
- [ ] Добавлены способы оплаты
- [ ] Настроен конфиг приложений (apps.json)
- [ ] Добавлены переводы (если нужна многоязычность)
- [ ] Протестировано на мобильных устройствах
- [ ] Проверены deeplinks для всех платформ

---

## 🐛 Troubleshooting

### Проблема: Компоненты не отображаются

**Решение:**
1. Проверьте, что MantineProvider настроен в корне приложения
2. Импортируйте стили Mantine: `import '@mantine/core/styles.css'`

### Проблема: Deeplinks не работают

**Решение:**
1. Проверьте формат urlScheme в конфиге приложений
2. Убедитесь, что приложение поддерживает этот URL scheme
3. На iOS deeplinks могут требовать Universal Links

### Проблема: Ошибки TypeScript

**Решение:**
Создайте файл типов:

```typescript
// types/subscription.ts
export interface User {
  username: string
  status: 'ACTIVE' | 'DISABLED' | 'LIMITED' | 'EXPIRED'
  expireAt: string
  usedTrafficBytes: number
  trafficLimitBytes: number
}

export interface SubscriptionData {
  response: {
    user: User
    subscriptionUrl: string
    happ?: {
      cryptoLink: string
    }
  }
}
```

---

## 📚 Дополнительные ресурсы

- [SUBSCRIPTION_PAGE_TEMPLATE.md](./SUBSCRIPTION_PAGE_TEMPLATE.md) - Полная документация
- [subscription-template-components/README.md](./subscription-template-components/README.md) - Документация компонентов
- [Mantine Documentation](https://mantine.dev)
- [Tabler Icons](https://tabler-icons.io)

---

## 🎯 Следующие шаги

1. **Создайте прототип страницы** с SubscriptionCard
2. **Добавьте способы оплаты** (FreeKassa, CryptoPay)
3. **Интегрируйте ConnectionGuide** для активных подписок
4. **Протестируйте на разных устройствах**
5. **Добавьте аналитику** (опционально)

Удачи с интеграцией! 🚀
