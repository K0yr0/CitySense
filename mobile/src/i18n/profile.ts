/** Profile tab, sign-in screen, Google sign-in button and language picker. */
import { plural } from '@/lib/i18n';

const en = {
  // shared by profile and sign-in
  trustCarryOver: 'The trust score you earn before signing in carries over to your account.',
  server: (url: string) => `Server: ${url}`,

  // profile tab
  signedOutTitle: "You're not signed in",
  signedOutBody:
    "You don't need to sign in to look at the map. Sign in to report problems, answer questions " +
    'about your area and follow your reports.',
  defaultName: 'CityEcho user',
  loadFailed: "Couldn't load your details.",
  myReports: 'My reports',
  noReports: (tab: string) => `No reports yet. When you see a problem, send it from the “${tab}” tab.`,

  // trust card
  trustTitle: 'Your trust score',
  trustA11y: (pct: string) => `Trust score ${pct}`,
  trustHint: 'Your score goes up as your answers turn out right; the higher it is, the more your answers count.',
  stats: {
    correct: (n: number) => plural(n, { one: 'correct answer', other: 'correct answers' }),
    incorrect: (n: number) => plural(n, { one: 'wrong answer', other: 'wrong answers' }),
    reports: (n: number) => plural(n, { one: 'report', other: 'reports' }),
    answers: (n: number) => plural(n, { one: 'answer', other: 'answers' }),
  },

  // report row
  underReview: 'Under review',

  // sign-in screen
  signInTitle: 'Sign in to CityEcho',
  signInIntro: 'Looking at the map is free. Sign in to report problems and answer questions about your area.',
  alreadySignedIn: (email: string) => `You're already signed in as ${email}`,
  google: 'Google',
  googleButton: 'Sign in with Google',
  googleNoResponse: "Google didn't respond. Try again.",
  googleNotOnServer: "Google sign-in isn't set up on the server (GOOGLE_CLIENT_IDS).",
  googleNotVerified: "Couldn't verify your Google account. Try again.",
  googleExpoGo: "Google sign-in doesn't work in Expo Go; it needs a development build.",
  googleNotConfigured: (envVar: string) => `Google sign-in isn't set up (mobile/.env: ${envVar}).`,
  googleNoIdToken: "Couldn't get the Google ID token.",
  googleFailed: 'Google sign-in failed.',
  demoTitle: 'Demo sign-in',
  demoBody: 'For testing and presentations only: sign in with just an email, without Google.',
  demoButton: 'Demo sign-in',
  emailPlaceholder: 'you@example.com',
  emailLabel: 'Email',
  invalidEmail: 'Enter a valid email address.',
  demoDisabled: 'Demo sign-in is disabled on this server (needs AUTH_DEV_LOGIN=1).',
  privacy: 'Only your email and name are stored; no location history is kept.',
};

const pl: typeof en = {
  trustCarryOver: 'Poziom zaufania zdobyty przed zalogowaniem przejdzie na twoje konto.',
  server: (url: string) => `Serwer: ${url}`,

  signedOutTitle: 'Nie zalogowano',
  signedOutBody:
    'Do przeglądania mapy nie musisz się logować. Zaloguj się, aby zgłaszać problemy, odpowiadać ' +
    'na pytania o okolicę i śledzić swoje zgłoszenia.',
  defaultName: 'Użytkownik CityEcho',
  loadFailed: 'Nie udało się pobrać twoich danych.',
  myReports: 'Moje zgłoszenia',
  noReports: (tab: string) =>
    `Nie masz jeszcze zgłoszeń. Gdy zobaczysz problem, wyślij go w zakładce „${tab}”.`,

  trustTitle: 'Twój poziom zaufania',
  trustA11y: (pct: string) => `Poziom zaufania ${pct}`,
  trustHint:
    'Poziom rośnie, gdy twoje odpowiedzi okazują się trafne; im jest wyższy, tym bardziej liczą się twoje odpowiedzi.',
  stats: {
    correct: (n: number) =>
      plural(n, {
        one: 'poprawna odpowiedź',
        few: 'poprawne odpowiedzi',
        many: 'poprawnych odpowiedzi',
        other: 'poprawnej odpowiedzi',
      }),
    incorrect: (n: number) =>
      plural(n, {
        one: 'błędna odpowiedź',
        few: 'błędne odpowiedzi',
        many: 'błędnych odpowiedzi',
        other: 'błędnej odpowiedzi',
      }),
    reports: (n: number) =>
      plural(n, { one: 'zgłoszenie', few: 'zgłoszenia', many: 'zgłoszeń', other: 'zgłoszenia' }),
    answers: (n: number) =>
      plural(n, { one: 'odpowiedź', few: 'odpowiedzi', many: 'odpowiedzi', other: 'odpowiedzi' }),
  },

  underReview: 'W trakcie oceny',

  signInTitle: 'Zaloguj się do CityEcho',
  signInIntro:
    'Mapę możesz przeglądać bez logowania. Zaloguj się, aby zgłaszać problemy i odpowiadać na pytania o okolicę.',
  alreadySignedIn: (email: string) => `Zalogowano już jako ${email}`,
  google: 'Google',
  googleButton: 'Zaloguj się przez Google',
  googleNoResponse: 'Google nie odpowiada. Spróbuj ponownie.',
  googleNotOnServer: 'Logowanie przez Google nie jest skonfigurowane na serwerze (GOOGLE_CLIENT_IDS).',
  googleNotVerified: 'Nie udało się zweryfikować konta Google. Spróbuj ponownie.',
  googleExpoGo: 'Logowanie przez Google nie działa w Expo Go; potrzebna jest wersja deweloperska (development build).',
  googleNotConfigured: (envVar: string) => `Logowanie przez Google nie jest skonfigurowane (mobile/.env: ${envVar}).`,
  googleNoIdToken: 'Nie udało się pobrać tokenu tożsamości Google (ID token).',
  googleFailed: 'Logowanie przez Google nie powiodło się.',
  demoTitle: 'Logowanie demo',
  demoBody: 'Tylko do testów i prezentacji: logowanie samym adresem e-mail, bez Google.',
  demoButton: 'Logowanie demo',
  emailPlaceholder: 'ty@example.pl',
  emailLabel: 'E-mail',
  invalidEmail: 'Wpisz poprawny adres e-mail.',
  demoDisabled: 'Logowanie demo jest wyłączone na tym serwerze (wymaga AUTH_DEV_LOGIN=1).',
  privacy: 'Przechowujemy tylko twój e-mail i imię; nie zapisujemy historii lokalizacji.',
};

const uk: typeof en = {
  trustCarryOver: 'Рівень довіри, здобутий до входу, перейде на ваш обліковий запис.',
  server: (url: string) => `Сервер: ${url}`,

  signedOutTitle: 'Ви не ввійшли',
  signedOutBody:
    'Щоб переглядати мапу, входити не потрібно. Увійдіть, щоб повідомляти про проблеми, відповідати ' +
    'на запитання про вашу околицю та стежити за своїми повідомленнями.',
  defaultName: 'Користувач CityEcho',
  loadFailed: 'Не вдалося завантажити ваші дані.',
  myReports: 'Мої повідомлення',
  noReports: (tab: string) =>
    `У вас ще немає повідомлень. Коли побачите проблему, надішліть її у вкладці «${tab}».`,

  trustTitle: 'Ваш рівень довіри',
  trustA11y: (pct: string) => `Рівень довіри ${pct}`,
  trustHint:
    'Рівень зростає, коли ваші відповіді виявляються правильними; що він вищий, то більше важать ваші відповіді.',
  stats: {
    correct: (n: number) =>
      plural(n, {
        one: 'правильна відповідь',
        few: 'правильні відповіді',
        many: 'правильних відповідей',
        other: 'правильної відповіді',
      }),
    incorrect: (n: number) =>
      plural(n, {
        one: 'хибна відповідь',
        few: 'хибні відповіді',
        many: 'хибних відповідей',
        other: 'хибної відповіді',
      }),
    reports: (n: number) =>
      plural(n, { one: 'повідомлення', few: 'повідомлення', many: 'повідомлень', other: 'повідомлення' }),
    answers: (n: number) =>
      plural(n, { one: 'відповідь', few: 'відповіді', many: 'відповідей', other: 'відповіді' }),
  },

  underReview: 'На розгляді',

  signInTitle: 'Вхід до CityEcho',
  signInIntro:
    'Переглядати мапу можна без входу. Увійдіть, щоб повідомляти про проблеми й відповідати на запитання про вашу околицю.',
  alreadySignedIn: (email: string) => `Ви вже ввійшли як ${email}`,
  google: 'Google',
  googleButton: 'Увійти через Google',
  googleNoResponse: 'Google не відповідає. Спробуйте ще раз.',
  googleNotOnServer: 'Вхід через Google не налаштовано на сервері (GOOGLE_CLIENT_IDS).',
  googleNotVerified: 'Не вдалося перевірити обліковий запис Google. Спробуйте ще раз.',
  googleExpoGo: 'Вхід через Google не працює в Expo Go; потрібна збірка для розробки (development build).',
  googleNotConfigured: (envVar: string) => `Вхід через Google не налаштовано (mobile/.env: ${envVar}).`,
  googleNoIdToken: 'Не вдалося отримати токен Google (ID token).',
  googleFailed: 'Не вдалося увійти через Google.',
  demoTitle: 'Демо-вхід',
  demoBody: 'Лише для тестів і презентацій: вхід лише за електронною поштою, без Google.',
  demoButton: 'Демо-вхід',
  emailPlaceholder: 'name@example.com',
  emailLabel: 'Електронна пошта',
  invalidEmail: 'Введіть правильну адресу електронної пошти.',
  demoDisabled: 'Демо-вхід вимкнено на цьому сервері (потрібно AUTH_DEV_LOGIN=1).',
  privacy: 'Ми зберігаємо лише вашу електронну пошту та імʼя; історію місцезнаходження не зберігаємо.',
};

export const profileText = { en, pl, uk };
