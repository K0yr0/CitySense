/** Report screen (M3): form, photo, location, sign-in notice and the status card after sending. */
import { plural } from '@/lib/i18n';

const en = {
  // form
  heading: 'Spotted a problem?',
  intro:
    'Describe it briefly; we work out the topic and the responsible office. A photo and your location ' +
    'help confirm the problem faster.',
  sessionExpired: 'Your session has expired. Sign in again; what you wrote will stay here.',
  textLabel: 'What did you see?',
  placeholder: 'What did you see? e.g. deep pothole in front of Marszałkowska 10',
  textA11y: 'Problem description',
  minChars: (n: number) => plural(n, { one: 'Write at least {n} character.', other: 'Write at least {n} characters.' }),
  tooShort: (n: number) =>
    plural(n, {
      one: 'Please describe the problem in at least {n} character.',
      other: 'Please describe the problem in at least {n} characters.',
    }),
  sendFailed: (detail: string) => `Couldn't send. ${detail}`,
  sessionLoading: 'Loading your session…',
  send: 'Send',
  signInToSend: 'Sign in to send',
  sendHint: 'Sends the report to the city',
  signInHint: 'Opens the sign-in screen',
  // sign-in notice
  signInTitle: 'Sign in to send a report',
  signInBody:
    'Looking at the map is free. Your reports are linked to your account, so your trust score grows ' +
    'and fake reports get filtered out.',
  // photo
  photoLabel: 'Photo (optional)',
  photoA11y: 'Attached photo',
  photoAdded: 'Photo added.',
  removePhoto: 'Remove photo',
  takePhoto: 'Take photo',
  pickPhoto: 'Choose from gallery',
  cameraDenied: 'Camera access was not granted. You can allow it in Settings or choose a photo from the gallery.',
  cameraFailed: (msg: string) => `Couldn't open the camera: ${msg}`,
  galleryFailed: (msg: string) => `Couldn't open the gallery: ${msg}`,
  // location
  locationLabel: 'Add location',
  locationA11y: 'Add my location to the report',
  locationOff: "Your location won't be added. If you write the address in the text, the city can still find it.",
  locationAdded: 'Your location is added',
  locationAddedAccuracy: (meters: number) => `Your location is added (±${meters} m)`,
  locationDenied: 'No location permission. Allow it to add your location to the report, or write the address in the text.',
  locationFailed: (err: string) => `Couldn't get your location: ${err}`,
  locating: 'Getting your location…',
  refresh: 'Refresh',
  allow: 'Allow',
  lowAccuracy: 'Low accuracy. Tapping “Refresh” in an open area can improve it.',
  // result card
  thanks: 'Thank you!',
  received: 'Your report has been received.',
  departmentPending: 'Finding the responsible office',
  yourPhoto: 'Your photo',
  factConfidence: 'Confidence',
  factCity: 'City',
  factReporters: 'Reported by',
  factAddress: 'Address',
  othersReported: (n: number) =>
    plural(n, { one: '{n} other person reported this', other: '{n} other people reported this' }),
  firstReporter: "You're the first to report this",
  notMatched:
    "Not linked to a known problem yet. It will appear on the map as others report it or sensors confirm it.",
  viewProblem: 'View problem',
  newReport: 'New report',
};

const pl: typeof en = {
  heading: 'Widzisz problem?',
  intro:
    'Opisz go krótko; temat i odpowiedzialną jednostkę ustalimy sami. Zdjęcie i lokalizacja pomagają ' +
    'szybciej potwierdzić problem.',
  sessionExpired: 'Twoja sesja wygasła. Zaloguj się ponownie; twój tekst tu zostanie.',
  textLabel: 'Opisz, co widzisz',
  placeholder: 'Co widzisz? Np. głęboka dziura w jezdni przed Marszałkowską 10',
  textA11y: 'Opis problemu',
  minChars: (n: number) =>
    plural(n, {
      one: 'Napisz co najmniej {n} znak.',
      few: 'Napisz co najmniej {n} znaki.',
      many: 'Napisz co najmniej {n} znaków.',
      other: 'Napisz co najmniej {n} znaku.',
    }),
  tooShort: (n: number) =>
    plural(n, {
      one: 'Opisz problem: potrzeba co najmniej {n} znaku.',
      few: 'Opisz problem: potrzeba co najmniej {n} znaków.',
      many: 'Opisz problem: potrzeba co najmniej {n} znaków.',
      other: 'Opisz problem: potrzeba co najmniej {n} znaku.',
    }),
  sendFailed: (detail: string) => `Nie udało się wysłać. ${detail}`,
  sessionLoading: 'Wczytywanie sesji…',
  send: 'Wyślij',
  signInToSend: 'Zaloguj się, aby wysłać',
  sendHint: 'Wysyła zgłoszenie do miasta',
  signInHint: 'Otwiera ekran logowania',
  signInTitle: 'Zaloguj się, aby wysłać zgłoszenie',
  signInBody:
    'Przeglądanie mapy jest dostępne dla wszystkich. Zgłoszenia są przypisane do twojego konta, dzięki temu ' +
    'rośnie twój poziom zaufania, a fałszywe zgłoszenia są odsiewane.',
  photoLabel: 'Zdjęcie (opcjonalnie)',
  photoA11y: 'Dodane zdjęcie',
  photoAdded: 'Zdjęcie dodane.',
  removePhoto: 'Usuń zdjęcie',
  takePhoto: 'Zrób zdjęcie',
  pickPhoto: 'Wybierz z galerii',
  cameraDenied: 'Nie udzielono dostępu do aparatu. Możesz zezwolić na to w Ustawieniach albo wybrać zdjęcie z galerii.',
  cameraFailed: (msg: string) => `Nie udało się otworzyć aparatu: ${msg}`,
  galleryFailed: (msg: string) => `Nie udało się otworzyć galerii: ${msg}`,
  locationLabel: 'Dołącz lokalizację',
  locationA11y: 'Dołącz moją lokalizację do zgłoszenia',
  locationOff: 'Lokalizacja nie zostanie dołączona. Jeśli wpiszesz adres w treści, miasto i tak trafi na miejsce.',
  locationAdded: 'Dołączono twoją lokalizację',
  locationAddedAccuracy: (meters: number) => `Dołączono twoją lokalizację (±${meters} m)`,
  locationDenied: 'Brak dostępu do lokalizacji. Zezwól, aby dołączyć ją do zgłoszenia, albo wpisz adres w treści.',
  locationFailed: (err: string) => `Nie udało się ustalić lokalizacji: ${err}`,
  locating: 'Ustalanie lokalizacji…',
  refresh: 'Odśwież',
  allow: 'Zezwól',
  lowAccuracy: 'Niska dokładność. Naciśnij „Odśwież” na otwartej przestrzeni, aby ją poprawić.',
  thanks: 'Dziękujemy!',
  received: 'Twoje zgłoszenie zostało przyjęte.',
  departmentPending: 'Ustalamy odpowiedzialną jednostkę',
  yourPhoto: 'Twoje zdjęcie',
  factConfidence: 'Pewność',
  factCity: 'Miasto',
  factReporters: 'Zgłoszenia',
  factAddress: 'Adres',
  othersReported: (n: number) =>
    plural(n, {
      one: 'Zgłosiła to jeszcze {n} osoba',
      few: 'Zgłosiły to jeszcze {n} osoby',
      many: 'Zgłosiło to jeszcze {n} osób',
      other: 'Zgłosiło to jeszcze {n} osoby',
    }),
  firstReporter: 'To pierwsze zgłoszenie tego problemu',
  notMatched:
    'Jeszcze nie powiązano go z żadnym problemem. Pojawi się na mapie, gdy zgłoszą go inni lub potwierdzą go czujniki.',
  viewProblem: 'Zobacz problem',
  newReport: 'Nowe zgłoszenie',
};

const uk: typeof en = {
  heading: 'Помітили проблему?',
  intro:
    'Опишіть коротко; тему й відповідальну службу ми визначимо самі. Фото й геолокація допомагають ' +
    'швидше підтвердити проблему.',
  sessionExpired: 'Ваша сесія завершилася. Увійдіть знову; написане залишиться тут.',
  textLabel: 'Що ви побачили?',
  placeholder: 'Що ви побачили? Напр., глибока вибоїна біля вул. Маршалковської, 10',
  textA11y: 'Опис проблеми',
  minChars: (n: number) =>
    plural(n, {
      one: 'Напишіть щонайменше {n} символ.',
      few: 'Напишіть щонайменше {n} символи.',
      many: 'Напишіть щонайменше {n} символів.',
      other: 'Напишіть щонайменше {n} символу.',
    }),
  tooShort: (n: number) =>
    plural(n, {
      one: 'Опишіть проблему: потрібно щонайменше {n} символ.',
      few: 'Опишіть проблему: потрібно щонайменше {n} символи.',
      many: 'Опишіть проблему: потрібно щонайменше {n} символів.',
      other: 'Опишіть проблему: потрібно щонайменше {n} символу.',
    }),
  sendFailed: (detail: string) => `Не вдалося надіслати. ${detail}`,
  sessionLoading: 'Завантаження сесії…',
  send: 'Надіслати',
  signInToSend: 'Увійдіть, щоб надіслати',
  sendHint: 'Надсилає повідомлення місту',
  signInHint: 'Відкриває екран входу',
  signInTitle: 'Увійдіть, щоб надіслати повідомлення',
  signInBody:
    'Переглядати мапу можна без входу. Ваші повідомлення привʼязуються до облікового запису, тож зростає ' +
    'ваш рівень довіри, а фейкові повідомлення відсіюються.',
  photoLabel: 'Фото (необовʼязково)',
  photoA11y: 'Додане фото',
  photoAdded: 'Фото додано.',
  removePhoto: 'Видалити фото',
  takePhoto: 'Зробити фото',
  pickPhoto: 'Вибрати з галереї',
  cameraDenied: 'Доступ до камери не надано. Ви можете дозволити його в Налаштуваннях або вибрати фото з галереї.',
  cameraFailed: (msg: string) => `Не вдалося відкрити камеру: ${msg}`,
  galleryFailed: (msg: string) => `Не вдалося відкрити галерею: ${msg}`,
  locationLabel: 'Додати геолокацію',
  locationA11y: 'Додати мою геолокацію до повідомлення',
  locationOff: 'Геолокацію не буде додано. Якщо ви вкажете адресу в тексті, місто все одно знайде це місце.',
  locationAdded: 'Вашу геолокацію додано',
  locationAddedAccuracy: (meters: number) => `Вашу геолокацію додано (±${meters} м)`,
  locationDenied: 'Немає доступу до геолокації. Дозвольте його, щоб додати її до повідомлення, або вкажіть адресу в тексті.',
  locationFailed: (err: string) => `Не вдалося визначити геолокацію: ${err}`,
  locating: 'Визначаємо геолокацію…',
  refresh: 'Оновити',
  allow: 'Дозволити',
  lowAccuracy: 'Низька точність. Натисніть «Оновити» на відкритому місці, щоб її покращити.',
  thanks: 'Дякуємо!',
  received: 'Ваше повідомлення отримано.',
  departmentPending: 'Визначаємо відповідальну службу',
  yourPhoto: 'Ваше фото',
  factConfidence: 'Достовірність',
  factCity: 'Місто',
  factReporters: 'Повідомили',
  factAddress: 'Адреса',
  othersReported: (n: number) =>
    plural(n, {
      one: 'Про це повідомила ще {n} людина',
      few: 'Про це повідомили ще {n} людини',
      many: 'Про це повідомили ще {n} людей',
      other: 'Про це повідомили ще {n} людини',
    }),
  firstReporter: 'Ви перші повідомили про цю проблему',
  notMatched:
    'Поки що не повʼязано з жодною проблемою. Зʼявиться на мапі, коли про неї повідомлять інші або її підтвердять датчики.',
  viewProblem: 'Переглянути проблему',
  newReport: 'Нове повідомлення',
};

export const reportText = { en, pl, uk };
