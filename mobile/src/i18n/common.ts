/** Words used across many screens: buttons, tabs, screen titles, time, distances, language picker. */
import { plural } from '@/lib/i18n';

const en = {
  yes: 'Yes',
  no: 'No',
  retry: 'Try again',
  cancel: 'Cancel',
  close: 'Close',
  delete: 'Delete',
  save: 'Save',
  back: 'Go back',
  loading: 'Loading…',
  signIn: 'Sign in',
  signOut: 'Sign out',
  details: 'Details',
  unknownAddress: 'Address unknown',
  responsible: (department: string) => `Responsible: ${department}`,
  otherDepartment: 'the relevant office',
  tabs: { map: 'Map', report: 'Report', routes: 'My routes', profile: 'Profile' },
  titles: { incident: 'Problem', route: 'Route', newRoute: 'Add route', signIn: 'Sign in' },
  time: {
    justNow: 'just now',
    minutesAgo: (n: number) => plural(n, { one: '{n} min ago', other: '{n} min ago' }),
    hoursAgo: (n: number) => plural(n, { one: '{n} h ago', other: '{n} h ago' }),
    daysAgo: (n: number) => plural(n, { one: '{n} day ago', other: '{n} days ago' }),
  },
  units: { m: 'm', km: 'km' },
  language: 'Language',
  locationDenied: 'Location permission was not granted.',
  backend: {
    title: 'Server connection',
    connected: '● Connected',
    unreachable: "● Can't reach the server",
    liveTrams: (n: number) => plural(n, { one: '{n} tram live right now.', other: '{n} trams live right now.' }),
    noLiveData: 'Live tram data is unavailable right now.',
    help:
      'Is the backend running? On a phone, EXPO_PUBLIC_API_URL must be your computer’s LAN IP ' +
      '(e.g. http://192.168.1.20:8000) and both must be on the same Wi-Fi.',
    serverUnreachable: (url: string) => `Can't reach the server: ${url}`,
  },
};

const pl: typeof en = {
  yes: 'Tak',
  no: 'Nie',
  retry: 'Spróbuj ponownie',
  cancel: 'Anuluj',
  close: 'Zamknij',
  delete: 'Usuń',
  save: 'Zapisz',
  back: 'Wróć',
  loading: 'Ładowanie…',
  signIn: 'Zaloguj się',
  signOut: 'Wyloguj się',
  details: 'Szczegóły',
  unknownAddress: 'Adres nieznany',
  responsible: (department: string) => `Odpowiada: ${department}`,
  otherDepartment: 'właściwa jednostka',
  tabs: { map: 'Mapa', report: 'Zgłoś', routes: 'Moje trasy', profile: 'Profil' },
  titles: { incident: 'Problem', route: 'Trasa', newRoute: 'Dodaj trasę', signIn: 'Logowanie' },
  time: {
    justNow: 'przed chwilą',
    minutesAgo: (n: number) => plural(n, { one: '{n} min temu', other: '{n} min temu' }),
    hoursAgo: (n: number) => plural(n, { one: '{n} godz. temu', other: '{n} godz. temu' }),
    daysAgo: (n: number) => plural(n, { one: '{n} dzień temu', few: '{n} dni temu', many: '{n} dni temu', other: '{n} dnia temu' }),
  },
  units: { m: 'm', km: 'km' },
  language: 'Język',
  locationDenied: 'Nie udzielono dostępu do lokalizacji.',
  backend: {
    title: 'Połączenie z serwerem',
    connected: '● Połączono',
    unreachable: '● Brak połączenia z serwerem',
    liveTrams: (n: number) =>
      plural(n, {
        one: 'Teraz na trasie: {n} tramwaj.',
        few: 'Teraz na trasie: {n} tramwaje.',
        many: 'Teraz na trasie: {n} tramwajów.',
        other: 'Teraz na trasie: {n} tramwaju.',
      }),
    noLiveData: 'Dane o tramwajach na żywo są teraz niedostępne.',
    help:
      'Czy backend działa? Na telefonie EXPO_PUBLIC_API_URL musi być adresem IP komputera w sieci lokalnej ' +
      '(np. http://192.168.1.20:8000), a oba urządzenia muszą być w tej samej sieci Wi-Fi.',
    serverUnreachable: (url: string) => `Brak połączenia z serwerem: ${url}`,
  },
};

const uk: typeof en = {
  yes: 'Так',
  no: 'Ні',
  retry: 'Спробувати ще раз',
  cancel: 'Скасувати',
  close: 'Закрити',
  delete: 'Видалити',
  save: 'Зберегти',
  back: 'Назад',
  loading: 'Завантаження…',
  signIn: 'Увійти',
  signOut: 'Вийти',
  details: 'Докладніше',
  unknownAddress: 'Адреса невідома',
  responsible: (department: string) => `Відповідальний: ${department}`,
  otherDepartment: 'відповідна служба',
  tabs: { map: 'Мапа', report: 'Повідомити', routes: 'Мої маршрути', profile: 'Профіль' },
  titles: { incident: 'Проблема', route: 'Маршрут', newRoute: 'Додати маршрут', signIn: 'Вхід' },
  time: {
    justNow: 'щойно',
    minutesAgo: (n: number) => plural(n, { one: '{n} хв тому', other: '{n} хв тому' }),
    hoursAgo: (n: number) => plural(n, { one: '{n} год тому', other: '{n} год тому' }),
    daysAgo: (n: number) => plural(n, { one: '{n} день тому', few: '{n} дні тому', many: '{n} днів тому', other: '{n} дня тому' }),
  },
  units: { m: 'м', km: 'км' },
  language: 'Мова',
  locationDenied: 'Доступ до геолокації не надано.',
  backend: {
    title: 'Зʼєднання з сервером',
    connected: '● Підключено',
    unreachable: '● Немає звʼязку з сервером',
    liveTrams: (n: number) =>
      plural(n, {
        one: 'Зараз на лінії {n} трамвай.',
        few: 'Зараз на лінії {n} трамваї.',
        many: 'Зараз на лінії {n} трамваїв.',
        other: 'Зараз на лінії {n} трамвая.',
      }),
    noLiveData: 'Дані про трамваї наживо зараз недоступні.',
    help:
      'Чи працює бекенд? На телефоні EXPO_PUBLIC_API_URL має бути локальною IP-адресою компʼютера ' +
      '(напр. http://192.168.1.20:8000), і обидва пристрої мають бути в одній мережі Wi-Fi.',
    serverUnreachable: (url: string) => `Немає звʼязку з сервером: ${url}`,
  },
};

export const commonText = { en, pl, uk };
