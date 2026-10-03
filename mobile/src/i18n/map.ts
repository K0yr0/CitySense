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
  /** GPS accuracy chip while following the user. */
  accuracy: (m: number) => `Location ±${m} m`,
  /** Same chip when the GPS is too imprecise for the "problem near you?" question. */
  accuracyTooLow: (m: number, limit: number) =>
    `Location ±${m} m · nearby questions need GPS accurate to ${limit} m`,
  card: {
    status: (label: string, pct: string) => `Status: ${label} (${pct})`,
    repair: (label: string) => `Repair: ${label}`,
    reportedBy: (n: number) =>
      plural(n, { one: 'Reported by {n} person', other: 'Reported by {n} people' }),
    openDetails: 'Open problem details',
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
  accuracy: (m: number) => `Lokalizacja ±${m} m`,
  accuracyTooLow: (m: number, limit: number) =>
    `Lokalizacja ±${m} m · pytania o okolicę wymagają GPS z dokładnością do ${limit} m`,
  card: {
    status: (label: string, pct: string) => `Status: ${label} (${pct})`,
    repair: (label: string) => `Naprawa: ${label}`,
    reportedBy: (n: number) =>
      plural(n, {
        one: 'Zgłosiła {n} osoba',
        few: 'Zgłosiły {n} osoby',
        many: 'Zgłosiło {n} osób',
        other: 'Zgłosiło {n} osoby',
      }),
    openDetails: 'Otwórz szczegóły problemu',
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
  accuracy: (m: number) => `Місцезнаходження ±${m} м`,
  accuracyTooLow: (m: number, limit: number) =>
    `Місцезнаходження ±${m} м · для запитань про околиці потрібна точність GPS до ${limit} м`,
  card: {
    status: (label: string, pct: string) => `Статус: ${label} (${pct})`,
    repair: (label: string) => `Ремонт: ${label}`,
    reportedBy: (n: number) =>
      plural(n, {
        one: 'Повідомила {n} людина',
        few: 'Повідомили {n} людини',
        many: 'Повідомили {n} людей',
        other: 'Повідомили {n} людини',
      }),
    openDetails: 'Відкрити подробиці проблеми',
  },
  web: {
    note: 'Мапа доступна лише в мобільному застосунку (Expo Go). У браузері проблеми поблизу показано списком.',
    empty: 'У цьому районі немає відкритих проблем.',
  },
};

export const mapText = { en, pl, uk };
