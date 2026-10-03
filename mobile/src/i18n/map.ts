/** Map tab: layer chips, banners, location chip, incident card, web fallback list. */
import { plural } from '@/lib/i18n';

const en = {
  layers: {
    incidents: 'Problems',
    roadColors: 'Road colours',
  },
  zoomInForColors: 'Zoom in to see road colours',
  loadFailed: (error: string) => `Couldn't load map data. ${error}`,
  locateLabel: 'Show my location',
  zoomOutLabel: 'Zoom out',
  /** GPS accuracy chip while following the user. */
  accuracy: (m: number) => `Location ±${m} m`,
  /** Same chip when the GPS is too imprecise for the "problem near you?" question. */
  accuracyTooLow: (m: number, limit: number) =>
    `Location ±${m} m · nearby questions need GPS accurate to ${limit} m`,
  card: {
    status: (label: string, pct: string) => `Status: ${label} (${pct})`,
    repair: (label: string) => `Repair: ${label}`,
    noReports: 'No reports yet',
    reportedBy: (n: number) =>
      plural(n, { one: 'Reported by {n} person', other: 'Reported by {n} people' }),
    openDetails: 'Open problem details',
  },
  /** Yes / No poll on the tapped problem's card (answers within 100 m, GPS accuracy <= 25 m). */
  poll: {
    title: 'Is this problem still there?',
    hint: 'You can answer when you are within 100 m of it.',
    locating: 'Checking your location…',
    tooFar: (m: number) => `You are about ${m} m away. Get within 100 m to answer.`,
    lowAccuracy: (m: number) => `Your location is accurate to ±${m} m; it must be 25 m or better. Try again outdoors.`,
    /** `answer` is already translated ("Yes" / "No"). */
    answered: (answer: string) => `You answered: ${answer}`,
  },
  web: {
    note: 'The map is only shown in the mobile app (Expo Go). On the web, nearby problems are listed instead.',
    empty: 'No open problems in this area.',
  },
};

const pl: typeof en = {
  layers: {
    incidents: 'Problemy',
    roadColors: 'Kolory dróg',
  },
  zoomInForColors: 'Przybliż, aby zobaczyć kolory dróg',
  loadFailed: (error: string) => `Nie udało się wczytać danych mapy. ${error}`,
  locateLabel: 'Pokaż moją lokalizację',
  zoomOutLabel: 'Oddal mapę',
  accuracy: (m: number) => `Lokalizacja ±${m} m`,
  accuracyTooLow: (m: number, limit: number) =>
    `Lokalizacja ±${m} m · pytania o okolicę wymagają GPS z dokładnością do ${limit} m`,
  card: {
    status: (label: string, pct: string) => `Status: ${label} (${pct})`,
    repair: (label: string) => `Naprawa: ${label}`,
    noReports: 'Brak zgłoszeń',
    reportedBy: (n: number) =>
      plural(n, {
        one: 'Zgłosiła {n} osoba',
        few: 'Zgłosiły {n} osoby',
        many: 'Zgłosiło {n} osób',
        other: 'Zgłosiło {n} osoby',
      }),
    openDetails: 'Otwórz szczegóły problemu',
  },
  poll: {
    title: 'Czy ten problem nadal występuje?',
    hint: 'Możesz odpowiedzieć, gdy jesteś w promieniu 100 m.',
    locating: 'Sprawdzam lokalizację…',
    tooFar: (m: number) => `Jesteś ok. ${m} m od problemu. Podejdź bliżej niż 100 m, aby odpowiedzieć.`,
    lowAccuracy: (m: number) => `Dokładność lokalizacji to ±${m} m; potrzeba 25 m lub lepiej. Spróbuj na zewnątrz.`,
    answered: (answer: string) => `Twoja odpowiedź: ${answer}`,
  },
  web: {
    note: 'Mapa jest widoczna tylko w aplikacji mobilnej (Expo Go). W przeglądarce problemy w pobliżu są pokazane jako lista.',
    empty: 'Brak otwartych problemów w tym obszarze.',
  },
};

const uk: typeof en = {
  layers: {
    incidents: 'Проблеми',
    roadColors: 'Кольори доріг',
  },
  zoomInForColors: 'Наблизьте мапу, щоб побачити кольори доріг',
  loadFailed: (error: string) => `Не вдалося завантажити дані мапи. ${error}`,
  locateLabel: 'Показати моє місцезнаходження',
  zoomOutLabel: 'Віддалити мапу',
  accuracy: (m: number) => `Місцезнаходження ±${m} м`,
  accuracyTooLow: (m: number, limit: number) =>
    `Місцезнаходження ±${m} м · для запитань про околиці потрібна точність GPS до ${limit} м`,
  card: {
    status: (label: string, pct: string) => `Статус: ${label} (${pct})`,
    repair: (label: string) => `Ремонт: ${label}`,
    noReports: 'Ще немає повідомлень',
    reportedBy: (n: number) =>
      plural(n, {
        one: 'Повідомила {n} людина',
        few: 'Повідомили {n} людини',
        many: 'Повідомили {n} людей',
        other: 'Повідомили {n} людини',
      }),
    openDetails: 'Відкрити подробиці проблеми',
  },
  poll: {
    title: 'Ця проблема досі є?',
    hint: 'Відповісти можна, коли ви в межах 100 м від неї.',
    locating: 'Перевіряємо ваше місцезнаходження…',
    tooFar: (m: number) => `Ви приблизно за ${m} м. Підійдіть ближче ніж на 100 м, щоб відповісти.`,
    lowAccuracy: (m: number) => `Точність місцезнаходження ±${m} м; потрібно 25 м або краще. Спробуйте надворі.`,
    answered: (answer: string) => `Ваша відповідь: ${answer}`,
  },
  web: {
    note: 'Мапа доступна лише в мобільному застосунку (Expo Go). У браузері проблеми поблизу показано списком.',
    empty: 'У цьому районі немає відкритих проблем.',
  },
};

export const mapText = { en, pl, uk };
