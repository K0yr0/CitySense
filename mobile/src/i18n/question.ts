/**
 * The 25 m "do you see it?" question card (components/question, hooks/use-nearby-question).
 * Yes / No buttons use commonText (c.yes, c.no).
 */

const en = {
  /** The question, worded for the incident type. */
  ask: {
    road_damage: 'Is there a pothole here?',
    tram_track: 'Is there a track defect here?',
    streetlight: 'Is this streetlight out?',
    /** Any other type; `label` is typeLabel(type). */
    other: (label: string) => `Is this problem here? (${label})`,
  },
  closeA11y: 'Dismiss',
  yesA11y: 'Yes, I see it',
  noA11y: "No, I don't see it",
  notNow: 'Not now',
  /** `pct` is already formatted, e.g. "80%". */
  thanksTrust: (pct: string) => `Thanks! Your trust score: ${pct}`,
  thanks: 'Thanks! Your answer was saved.',
  /** Answer refused by the server (403 / 409 / 422 / 404): the question closes. */
  tooFar: 'You are no longer within 25 m, so the question was closed.',
  noLongerValid: 'This question no longer applies (already answered or the problem was fixed).',
  lowAccuracy: 'Your location is not accurate enough (over 25 m), so the question was closed.',
  gone: 'This problem no longer exists.',
  sessionExpired: 'Your session has expired. Sign in again to answer.',
  noFix: "Couldn't get your location. Please try again.",
  sendFailed: "Couldn't send your answer. Check your connection and try again.",
};

const pl: typeof en = {
  ask: {
    road_damage: 'Czy jest tu dziura w jezdni?',
    tram_track: 'Czy jest tu usterka torowiska?',
    streetlight: 'Czy ta latarnia nie świeci?',
    other: (label: string) => `Czy ten problem tu jest? (${label})`,
  },
  closeA11y: 'Zamknij',
  yesA11y: 'Tak, widzę',
  noA11y: 'Nie, nie widzę',
  notNow: 'Nie teraz',
  thanksTrust: (pct: string) => `Dzięki! Twój poziom zaufania: ${pct}`,
  thanks: 'Dzięki! Twoja odpowiedź została zapisana.',
  tooFar: 'Nie jesteś już w promieniu 25 m, więc pytanie zostało zamknięte.',
  noLongerValid: 'To pytanie jest już nieaktualne (już na nie odpowiedziano albo problem usunięto).',
  lowAccuracy: 'Twoja lokalizacja jest zbyt niedokładna (ponad 25 m), więc pytanie zostało zamknięte.',
  gone: 'Ten problem już nie istnieje.',
  sessionExpired: 'Twoja sesja wygasła. Zaloguj się ponownie, aby odpowiedzieć.',
  noFix: 'Nie udało się ustalić twojej lokalizacji. Spróbuj ponownie.',
  sendFailed: 'Nie udało się wysłać odpowiedzi. Sprawdź połączenie i spróbuj ponownie.',
};

const uk: typeof en = {
  ask: {
    road_damage: 'Тут є вибоїна?',
    tram_track: 'Тут є дефект колії?',
    streetlight: 'Цей ліхтар не світить?',
    other: (label: string) => `Ця проблема тут є? (${label})`,
  },
  closeA11y: 'Закрити',
  yesA11y: 'Так, бачу',
  noA11y: 'Ні, не бачу',
  notNow: 'Не зараз',
  thanksTrust: (pct: string) => `Дякуємо! Ваш рівень довіри: ${pct}`,
  thanks: 'Дякуємо! Вашу відповідь збережено.',
  tooFar: 'Ви вже не в радіусі 25 м, тому запитання закрито.',
  noLongerValid: 'Це запитання вже неактуальне (на нього вже відповіли або проблему усунуто).',
  lowAccuracy: 'Недостатня точність геолокації (понад 25 м), тому запитання закрито.',
  gone: 'Цієї проблеми більше немає.',
  sessionExpired: 'Ваш сеанс завершився. Увійдіть знову, щоб відповісти.',
  noFix: 'Не вдалося визначити ваше місцезнаходження. Спробуйте ще раз.',
  sendFailed: 'Не вдалося надіслати відповідь. Перевірте зʼєднання та спробуйте ще раз.',
};

export const questionText = { en, pl, uk };
