/** Favourite routes (M5): the list, adding a route, one route's road quality and warnings. */
import { plural } from '@/lib/i18n';

const en = {
  // errors
  sessionExpired: 'Your session has expired. Please sign in again.',
  notFound: 'This route was not found. It may have been deleted.',
  tooManyRoutes: "You've reached the maximum number of saved routes. Delete one first.",
  invalidRoute: "The route details aren't valid. Start and end must be different.",
  loadFailed: (error: string) => `Couldn't load your routes: ${error}`,
  deleteFailed: "Couldn't delete",
  refreshFailed: "Couldn't refresh",

  // delete
  deleteRoute: 'Delete route',
  deleteConfirm: (name: string) => `Delete the route "${name}"?`,
  deleteConfirmUnnamed: 'Delete this route?',
  deleteA11y: (name: string) => `Delete route ${name}`,

  // list
  addRoute: '+ Add route',
  emptyTitle: "You haven't saved any routes yet",
  emptyText:
    'Add a trip you make often (e.g. Home → Work) or a bus or tram line you ride. You see the road ' +
    "quality along it in colours and get a warning when there's bad road or a reported problem ahead.",
  deleteHint: 'Press and hold a route or tap the trash icon to delete it.',

  // card
  cardHint: 'Opens the route. Press and hold to delete it.',
  computingShort: 'Checking road quality…',
  qualityFailed: "Couldn't get road quality",
  warningCount: (n: number) => plural(n, { one: '{n} warning', other: '{n} warnings' }),
  noWarningsShort: 'No warnings',

  // describing a route
  startToEnd: 'Start → end',
  tramLine: (line: string) => `Tram ${line}`,
  busLine: (line: string) => `Bus ${line}`,
  tramLineGeneric: 'Tram line',
  busLineGeneric: 'Bus line',
  lineGeneric: 'Line',

  // sign-in gate
  gateTitle: 'Your favourite routes',
  gateText:
    'Save your way to work or the bus or tram line you ride. We show the road quality along it in ' +
    "colours and warn you when there's bad road or a reported problem ahead.",
  gateNeedSignIn: 'Routes are saved to your account, so you need to sign in.',

  // new route
  kindPoints: 'Start → end',
  kindLine: 'Bus or tram line',
  nameLabel: 'Route name',
  defaultPointsName: 'Home → Work',
  startAndEnd: 'Start and end',
  tooClose: 'Start and end are too close to each other.',
  vehicle: 'Vehicle',
  modeTram: 'Tram',
  modeBus: 'Bus',
  line: 'Line',
  linesFailed: "Couldn't load the list of lines. You can type the line number below.",
  noTramLines: 'No tram lines have been measured yet. You can type the line number below.',
  noBusLines: 'No bus lines have been measured yet. You can type the line number below.',
  linePlaceholder: (example: string) => `Line number, e.g. ${example}`,
  lineHint: "Road quality is worked out from the roads this line's vehicles drive on.",
  pickPointsHint: 'Choose a start and an end point to save.',

  // point picker
  start: 'Start',
  end: 'End',
  tapForStart: 'Tap the map to set the start point.',
  tapForEnd: 'Tap the map to set the end point.',
  dragHint: 'You can drag the pins to adjust them.',
  useMyLocation: 'Start from my location',
  reset: 'Reset',
  locationFailed: "Couldn't get your location. Check the location permission.",
  locationFailedWeb: "Couldn't get your location. Check the browser's location permission.",
  webMapNote: 'The map isn\'t available on the web. Type the points as "latitude, longitude" (e.g. 52.22970, 21.01220).',

  // route detail
  computing: 'Checking road quality along the route…',
  badRoadAhead: 'Bad road ahead',
  inDistance: (dist: string, message: string) => `In ${dist}: ${message}`,
  onRouteClear: (dist: string) => `✓ You're on the route. No warnings in the next ${dist}.`,
  overall: (label: string) => `Overall: ${label}`,
  warnings: 'Warnings',
  offRoute: (dist: string) =>
    `You're not on the route (more than ${dist} away), so distances are measured from the start of the route.`,
  noWarnings: '✓ No known problems or bad road along this route.',
  warningAhead: (dist: string, message: string) => `${dist} ahead: ${message}`,
  warningPassed: (message: string) => `Behind you: ${message}`,
  warningAtStart: (message: string) => `At the start: ${message}`,
  mapMobileOnly: 'The route map is only shown in the mobile app.',

  // quality bar and map
  qualityBarA11y: 'Road quality along the route',
  noMeasurements: 'No measurements along this route yet.',
  reportedProblem: 'Reported problem',
  badRoad: 'Bad road',
  tapForDetails: (message: string) => `${message} · Tap for details`,
};

const pl: typeof en = {
  sessionExpired: 'Twoja sesja wygasła. Zaloguj się ponownie.',
  notFound: 'Nie znaleziono tej trasy. Mogła zostać usunięta.',
  tooManyRoutes: 'Masz już maksymalną liczbę zapisanych tras. Najpierw usuń jedną z nich.',
  invalidRoute: 'Nieprawidłowe dane trasy. Początek i koniec muszą się różnić.',
  loadFailed: (error: string) => `Nie udało się wczytać tras: ${error}`,
  deleteFailed: 'Nie udało się usunąć',
  refreshFailed: 'Nie udało się odświeżyć',

  deleteRoute: 'Usuń trasę',
  deleteConfirm: (name: string) => `Usunąć trasę „${name}”?`,
  deleteConfirmUnnamed: 'Usunąć tę trasę?',
  deleteA11y: (name: string) => `Usuń trasę ${name}`,

  addRoute: '+ Dodaj trasę',
  emptyTitle: 'Nie masz jeszcze zapisanych tras',
  emptyText:
    'Dodaj trasę, którą często jeździsz (np. Dom → Praca), albo linię autobusową lub tramwajową. ' +
    'Zobaczysz stan drogi na trasie w kolorach i dostaniesz ostrzeżenie, gdy przed tobą będzie zła ' +
    'nawierzchnia lub zgłoszony problem.',
  deleteHint: 'Aby usunąć trasę, przytrzymaj ją lub dotknij ikony kosza.',

  cardHint: 'Otwiera trasę. Przytrzymaj, aby usunąć.',
  computingShort: 'Sprawdzanie stanu drogi…',
  qualityFailed: 'Nie udało się pobrać stanu drogi',
  warningCount: (n: number) =>
    plural(n, {
      one: '{n} ostrzeżenie',
      few: '{n} ostrzeżenia',
      many: '{n} ostrzeżeń',
      other: '{n} ostrzeżenia',
    }),
  noWarningsShort: 'Brak ostrzeżeń',

  startToEnd: 'Początek → koniec',
  tramLine: (line: string) => `Tramwaj ${line}`,
  busLine: (line: string) => `Autobus ${line}`,
  tramLineGeneric: 'Linia tramwajowa',
  busLineGeneric: 'Linia autobusowa',
  lineGeneric: 'Linia',

  gateTitle: 'Twoje ulubione trasy',
  gateText:
    'Zapisz swoją drogę do pracy albo linię autobusową lub tramwajową, którą jeździsz. Pokażemy stan ' +
    'drogi na trasie w kolorach i ostrzeżemy cię, gdy przed tobą będzie zła nawierzchnia lub zgłoszony problem.',
  gateNeedSignIn: 'Trasy są zapisywane na twoim koncie, więc musisz się zalogować.',

  kindPoints: 'Początek → koniec',
  kindLine: 'Linia autobusowa lub tramwajowa',
  nameLabel: 'Nazwa trasy',
  defaultPointsName: 'Dom → Praca',
  startAndEnd: 'Początek i koniec',
  tooClose: 'Początek i koniec są zbyt blisko siebie.',
  vehicle: 'Pojazd',
  modeTram: 'Tramwaj',
  modeBus: 'Autobus',
  line: 'Linia',
  linesFailed: 'Nie udało się pobrać listy linii. Możesz wpisać numer linii poniżej.',
  noTramLines: 'Nie zmierzono jeszcze żadnej linii tramwajowej. Możesz wpisać numer linii poniżej.',
  noBusLines: 'Nie zmierzono jeszcze żadnej linii autobusowej. Możesz wpisać numer linii poniżej.',
  linePlaceholder: (example: string) => `Numer linii, np. ${example}`,
  lineHint: 'Stan drogi jest wyliczany z ulic, po których jeżdżą pojazdy tej linii.',
  pickPointsHint: 'Aby zapisać, wybierz punkt początkowy i końcowy.',

  start: 'Początek',
  end: 'Koniec',
  tapForStart: 'Dotknij mapy, aby ustawić punkt początkowy.',
  tapForEnd: 'Dotknij mapy, aby ustawić punkt końcowy.',
  dragHint: 'Możesz przeciągać pinezki, aby je poprawić.',
  useMyLocation: 'Zacznij od mojej lokalizacji',
  reset: 'Wyczyść',
  locationFailed: 'Nie udało się ustalić lokalizacji. Sprawdź uprawnienia do lokalizacji.',
  locationFailedWeb: 'Nie udało się ustalić lokalizacji. Sprawdź uprawnienia przeglądarki do lokalizacji.',
  webMapNote:
    'Mapa nie jest dostępna w przeglądarce. Wpisz punkty jako „szerokość, długość” (np. 52.22970, 21.01220).',

  computing: 'Sprawdzanie stanu drogi na trasie…',
  badRoadAhead: 'Zła droga przed tobą',
  inDistance: (dist: string, message: string) => `Za ${dist}: ${message}`,
  onRouteClear: (dist: string) => `✓ Jesteś na trasie. Na najbliższych ${dist} brak ostrzeżeń.`,
  overall: (label: string) => `Ogólna ocena: ${label}`,
  warnings: 'Ostrzeżenia',
  offRoute: (dist: string) =>
    `Nie jesteś na trasie (ponad ${dist} od niej), więc odległości są liczone od początku trasy.`,
  noWarnings: '✓ Na tej trasie nie ma znanych problemów ani złej nawierzchni.',
  warningAhead: (dist: string, message: string) => `Za ${dist}: ${message}`,
  warningPassed: (message: string) => `Już za tobą: ${message}`,
  warningAtStart: (message: string) => `Na początku trasy: ${message}`,
  mapMobileOnly: 'Mapa trasy jest dostępna tylko w aplikacji mobilnej.',

  qualityBarA11y: 'Stan drogi na trasie',
  noMeasurements: 'Na tej trasie nie ma jeszcze pomiarów.',
  reportedProblem: 'Zgłoszony problem',
  badRoad: 'Zła nawierzchnia',
  tapForDetails: (message: string) => `${message} · Dotknij, aby zobaczyć szczegóły`,
};

const uk: typeof en = {
  sessionExpired: 'Ваш сеанс завершився. Увійдіть ще раз.',
  notFound: 'Цей маршрут не знайдено. Можливо, його видалено.',
  tooManyRoutes: 'Ви вже зберегли максимальну кількість маршрутів. Спершу видаліть один із них.',
  invalidRoute: 'Неправильні дані маршруту. Початок і кінець мають відрізнятися.',
  loadFailed: (error: string) => `Не вдалося завантажити маршрути: ${error}`,
  deleteFailed: 'Не вдалося видалити',
  refreshFailed: 'Не вдалося оновити',

  deleteRoute: 'Видалити маршрут',
  deleteConfirm: (name: string) => `Видалити маршрут «${name}»?`,
  deleteConfirmUnnamed: 'Видалити цей маршрут?',
  deleteA11y: (name: string) => `Видалити маршрут ${name}`,

  addRoute: '+ Додати маршрут',
  emptyTitle: 'У вас ще немає збережених маршрутів',
  emptyText:
    'Додайте шлях, яким ви часто їздите (напр. Дім → Робота), або автобусну чи трамвайну лінію. ' +
    'Ви бачитимете стан дороги на маршруті кольорами й отримаєте попередження, якщо попереду ' +
    'погана дорога або повідомлена проблема.',
  deleteHint: 'Щоб видалити маршрут, утримуйте його або торкніться значка кошика.',

  cardHint: 'Відкриває маршрут. Утримуйте, щоб видалити.',
  computingShort: 'Перевіряємо стан дороги…',
  qualityFailed: 'Не вдалося отримати стан дороги',
  warningCount: (n: number) =>
    plural(n, {
      one: '{n} попередження',
      few: '{n} попередження',
      many: '{n} попереджень',
      other: '{n} попередження',
    }),
  noWarningsShort: 'Попереджень немає',

  startToEnd: 'Початок → кінець',
  tramLine: (line: string) => `Трамвай ${line}`,
  busLine: (line: string) => `Автобус ${line}`,
  tramLineGeneric: 'Трамвайна лінія',
  busLineGeneric: 'Автобусна лінія',
  lineGeneric: 'Лінія',

  gateTitle: 'Ваші улюблені маршрути',
  gateText:
    'Збережіть свій шлях на роботу або автобусну чи трамвайну лінію, якою ви їздите. Ми покажемо стан ' +
    'дороги на маршруті кольорами й попередимо вас, якщо попереду погана дорога або повідомлена проблема.',
  gateNeedSignIn: 'Маршрути зберігаються у вашому обліковому записі, тому потрібно увійти.',

  kindPoints: 'Початок → кінець',
  kindLine: 'Автобусна чи трамвайна лінія',
  nameLabel: 'Назва маршруту',
  defaultPointsName: 'Дім → Робота',
  startAndEnd: 'Початок і кінець',
  tooClose: 'Початок і кінець розташовані надто близько.',
  vehicle: 'Транспорт',
  modeTram: 'Трамвай',
  modeBus: 'Автобус',
  line: 'Лінія',
  linesFailed: 'Не вдалося отримати список ліній. Ви можете ввести номер лінії нижче.',
  noTramLines: 'Ще немає виміряних трамвайних ліній. Ви можете ввести номер лінії нижче.',
  noBusLines: 'Ще немає виміряних автобусних ліній. Ви можете ввести номер лінії нижче.',
  linePlaceholder: (example: string) => `Номер лінії, напр. ${example}`,
  lineHint: 'Стан дороги визначається за вулицями, якими їздять транспортні засоби цієї лінії.',
  pickPointsHint: 'Щоб зберегти, виберіть початкову й кінцеву точки.',

  start: 'Початок',
  end: 'Кінець',
  tapForStart: 'Торкніться мапи, щоб вибрати початкову точку.',
  tapForEnd: 'Торкніться мапи, щоб вибрати кінцеву точку.',
  dragHint: 'Мітки можна перетягувати, щоб уточнити їхнє розташування.',
  useMyLocation: 'Почати з мого місцезнаходження',
  reset: 'Скинути',
  locationFailed: 'Не вдалося визначити ваше місцезнаходження. Перевірте дозвіл на геолокацію.',
  locationFailedWeb: 'Не вдалося визначити ваше місцезнаходження. Перевірте дозвіл браузера на геолокацію.',
  webMapNote:
    'Мапа недоступна у вебверсії. Введіть точки у форматі «широта, довгота» (напр. 52.22970, 21.01220).',

  computing: 'Перевіряємо стан дороги на маршруті…',
  badRoadAhead: 'Попереду погана дорога',
  inDistance: (dist: string, message: string) => `Через ${dist}: ${message}`,
  onRouteClear: (dist: string) => `✓ Ви на маршруті. На найближчих ${dist} попереджень немає.`,
  overall: (label: string) => `Загальний стан: ${label}`,
  warnings: 'Попередження',
  offRoute: (dist: string) =>
    `Ви не на маршруті (далі ніж ${dist} від нього), тому відстані відраховуються від початку маршруту.`,
  noWarnings: '✓ На цьому маршруті немає відомих проблем чи поганої дороги.',
  warningAhead: (dist: string, message: string) => `Через ${dist}: ${message}`,
  warningPassed: (message: string) => `Уже позаду: ${message}`,
  warningAtStart: (message: string) => `На початку маршруту: ${message}`,
  mapMobileOnly: 'Мапа маршруту доступна лише в мобільному застосунку.',

  qualityBarA11y: 'Стан дороги на маршруті',
  noMeasurements: 'На цьому маршруті ще немає вимірювань.',
  reportedProblem: 'Повідомлена проблема',
  badRoad: 'Погана дорога',
  tapForDetails: (message: string) => `${message} · Торкніться, щоб побачити деталі`,
};

export const routesText = { en, pl, uk };
