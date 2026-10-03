/** Short incident view (app/incident/[id].tsx and components/incident/). */
import { plural } from '@/lib/i18n';

const en = {
  notFoundTitle: "We couldn't find this problem",
  notFoundBody: 'It may have been removed, or the link may be wrong.',
  loadFailedTitle: "Couldn't load this problem",
  unknownError: 'Something went wrong.',
  refreshFailed: (error: string) => `Couldn't update: ${error}`,
  reportedBy: (n: number) =>
    plural(n, { one: '{n} person reported this', other: '{n} people reported this' }),
  firstSeen: (when: string) => `First seen: ${when}`,
  lastSeen: (when: string) => `Last: ${when}`,
  youReported: 'You reported this',
  yourAnswer: (answer: string) => `Your answer: ${answer}`,
  sectionConfidence: 'Confidence',
  sectionCity: 'City',
  confidenceA11y: (label: string, pct: string) => `Confidence: ${label}, ${pct}`,
  workA11y: (label: string) => `City status: ${label}`,
  doneTitle: '✓ Fixed. Thank you!',
  doneBody: 'The city has fixed this problem. Thanks for your reports.',
  openInMaps: 'Open in Maps',
};

const pl: typeof en = {
  notFoundTitle: 'Nie znaleziono tego problemu',
  notFoundBody: 'Mógł zostać usunięty albo link jest błędny.',
  loadFailedTitle: 'Nie udało się wczytać problemu',
  unknownError: 'Coś poszło nie tak.',
  refreshFailed: (error: string) => `Nie udało się odświeżyć: ${error}`,
  reportedBy: (n: number) =>
    plural(n, {
      one: '{n} osoba to zgłosiła',
      few: '{n} osoby to zgłosiły',
      many: '{n} osób to zgłosiło',
      other: '{n} osoby to zgłosiły',
    }),
  firstSeen: (when: string) => `Pierwsze zgłoszenie: ${when}`,
  lastSeen: (when: string) => `Ostatnie: ${when}`,
  youReported: 'To Twoje zgłoszenie',
  yourAnswer: (answer: string) => `Twoja odpowiedź: ${answer}`,
  sectionConfidence: 'Pewność',
  sectionCity: 'Miasto',
  confidenceA11y: (label: string, pct: string) => `Pewność: ${label}, ${pct}`,
  workA11y: (label: string) => `Stan prac miasta: ${label}`,
  doneTitle: '✓ Naprawione. Dziękujemy!',
  doneBody: 'Miasto usunęło ten problem. Dziękujemy za Twoje zgłoszenia.',
  openInMaps: 'Otwórz w aplikacji map',
};

const uk: typeof en = {
  notFoundTitle: 'Цю проблему не знайдено',
  notFoundBody: 'Можливо, її видалили або посилання неправильне.',
  loadFailedTitle: 'Не вдалося завантажити проблему',
  unknownError: 'Щось пішло не так.',
  refreshFailed: (error: string) => `Не вдалося оновити: ${error}`,
  reportedBy: (n: number) =>
    plural(n, {
      one: 'Про це повідомила {n} людина',
      few: 'Про це повідомили {n} людини',
      many: 'Про це повідомили {n} людей',
      other: 'Про це повідомили {n} людини',
    }),
  firstSeen: (when: string) => `Уперше: ${when}`,
  lastSeen: (when: string) => `Востаннє: ${when}`,
  youReported: 'Ви повідомили про це',
  yourAnswer: (answer: string) => `Ваша відповідь: ${answer}`,
  sectionConfidence: 'Достовірність',
  sectionCity: 'Місто',
  confidenceA11y: (label: string, pct: string) => `Достовірність: ${label}, ${pct}`,
  workA11y: (label: string) => `Стан робіт міста: ${label}`,
  doneTitle: '✓ Виправлено. Дякуємо!',
  doneBody: 'Місто усунуло цю проблему. Дякуємо за ваші повідомлення.',
  openInMaps: 'Відкрити в застосунку мап',
};

export const incidentText = { en, pl, uk };
