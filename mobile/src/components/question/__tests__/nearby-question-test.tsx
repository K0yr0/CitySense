/**
 * "I walk up to a problem and the app asks me about it."
 *
 * Runs the real NearbyQuestion card and the real useNearbyQuestion hook. Only the edges are faked:
 * the phone's GPS (expo-location), the server (getQuestion / answerIncident), the sign-in state,
 * device storage and the vibration.
 */
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import * as Haptics from 'expo-haptics';

import { NearbyQuestion } from '@/components/question/nearby-question';
import { answerIncident, getQuestion, type PublicIncident } from '@/lib/api';

// A pothole on Marszałkowska and two places to stand: 8 m away and 300 m away.
const POTHOLE: PublicIncident = {
  id: 42,
  type: 'road_damage',
  lon: 21.0122,
  lat: 52.2297,
  address: 'Marszałkowska',
  department: 'ZDM',
  status: 'likely',
  confidence: 0.72,
  work_status: 'todo',
  report_count: 5,
  first_seen: null,
  last_seen: null,
};
const NEAR = { latitude: 52.22977, longitude: 21.0122 }; // ~8 m north
const FAR = { latitude: 52.2324, longitude: 21.0122 }; // ~300 m north

// ---- the phone's GPS: tests choose where "I" am and how accurate the fix is ----
let here = NEAR;
let accuracy = 5;
const position = () => ({ coords: { ...here, accuracy, altitude: 0, altitudeAccuracy: 0, heading: 0, speed: 0 }, timestamp: Date.now() });

jest.mock('expo-location', () => ({
  Accuracy: { High: 4 },
  getForegroundPermissionsAsync: jest.fn(async () => ({ granted: true, status: 'granted' })),
  requestForegroundPermissionsAsync: jest.fn(async () => ({ granted: true, status: 'granted' })),
  getLastKnownPositionAsync: jest.fn(async () => position()),
  getCurrentPositionAsync: jest.fn(async () => position()),
  watchPositionAsync: jest.fn(async (_opts: unknown, onUpdate: (p: unknown) => void) => {
    onUpdate(position());
    return { remove: jest.fn() };
  }),
}));

jest.mock('@/lib/api', () => ({
  ...jest.requireActual('@/lib/api'),
  getQuestion: jest.fn(),
  answerIncident: jest.fn(),
}));
jest.mock('@/lib/session', () => ({ useSession: () => ({ status: 'signedIn', user: { id: 1 } }) }));
jest.mock('@/lib/storage', () => ({
  getItem: jest.fn(async () => null),
  setItem: jest.fn(async () => {}),
  removeItem: jest.fn(async () => {}),
}));
jest.mock('expo-haptics', () => ({
  notificationAsync: jest.fn(async () => {}),
  NotificationFeedbackType: { Warning: 'warning' },
}));
jest.mock('expo-localization', () => ({ getLocales: () => [{ languageCode: 'en', languageTag: 'en-US' }] }));
// jest.mock factories run before imports, so the library's own test double is loaded with require().
// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('react-native-safe-area-context', () => require('react-native-safe-area-context/jest/mock').default);

const mockGetQuestion = getQuestion as jest.MockedFunction<typeof getQuestion>;
const mockAnswer = answerIncident as jest.MockedFunction<typeof answerIncident>;

/** The server's rule (25 m, accuracy <= 25 m), so the fake behaves like /mobile/question. */
function serverFindsPotholeWithin25m() {
  mockGetQuestion.mockImplementation(async (lon, lat, acc) => {
    const dLat = (lat - POTHOLE.lat) * 111_320;
    const dLon = (lon - POTHOLE.lon) * 111_320 * Math.cos((lat * Math.PI) / 180);
    const meters = Math.hypot(dLat, dLon);
    return meters <= 25 && acc <= 25 ? { incident: POTHOLE, distance_m: meters } : { incident: null, distance_m: null };
  });
}

/**
 * Mount and stand still until the app has checked with the server (it checks on the first fix once
 * its memory is loaded, then every 5 s), at most 20 s. Low-accuracy cases never check, so they
 * simply wait the full 20 s and show nothing.
 */
async function walkUp() {
  render(<NearbyQuestion />);
  for (let s = 0; s < 20 && mockGetQuestion.mock.calls.length === 0; s++) {
    await act(async () => {
      await jest.advanceTimersByTimeAsync(1_000);
    });
  }
  await act(async () => {
    await jest.advanceTimersByTimeAsync(100); // let the answer render
  });
}

beforeEach(() => {
  jest.useFakeTimers();
  jest.clearAllMocks();
  here = NEAR;
  accuracy = 5;
  serverFindsPotholeWithin25m();
});

afterEach(() => {
  jest.useRealTimers();
});

test('pops up "Is there a pothole here?" when I am 8 m from it', async () => {
  await walkUp();

  expect(await screen.findByText('Is there a pothole here?')).toBeTruthy();
  expect(screen.getByText('Marszałkowska')).toBeTruthy();
  expect(screen.getByLabelText('Yes, I see it')).toBeTruthy();
  expect(screen.getByLabelText("No, I don't see it")).toBeTruthy();
  // Asked the server with my position and GPS accuracy, and buzzed the phone.
  expect(mockGetQuestion).toHaveBeenCalledWith(NEAR.longitude, NEAR.latitude, 5, []);
  expect(Haptics.notificationAsync).toHaveBeenCalled();
});

test('stays quiet when I am 300 m away', async () => {
  here = FAR;
  await walkUp();

  expect(mockGetQuestion).toHaveBeenCalled();
  expect(screen.queryByText('Is there a pothole here?')).toBeNull();
});

test('does not even ask the server when my GPS is worse than 25 m', async () => {
  accuracy = 40;
  await walkUp();

  expect(mockGetQuestion).not.toHaveBeenCalled();
  expect(screen.queryByText('Is there a pothole here?')).toBeNull();
});

test('never asks about a problem the city already fixed', async () => {
  mockGetQuestion.mockResolvedValue({ incident: { ...POTHOLE, work_status: 'done' }, distance_m: 8 });
  await walkUp();

  expect(mockGetQuestion).toHaveBeenCalled(); // the server offered it...
  expect(screen.queryByText('Is there a pothole here?')).toBeNull(); // ...but the app still stays quiet
});

test('tapping Yes sends my answer with my position and thanks me', async () => {
  mockAnswer.mockResolvedValue({ incident_id: 42, status: 'likely', confidence: 0.8, work_status: 'todo', contributor_trust: 0.64 });
  await walkUp();
  await screen.findByText('Is there a pothole here?');

  fireEvent.press(screen.getByLabelText('Yes, I see it'));
  await act(async () => {
    await jest.advanceTimersByTimeAsync(100);
  });

  expect(mockAnswer).toHaveBeenCalledWith(42, 'yes', { lon: NEAR.longitude, lat: NEAR.latitude, accuracy_m: 5 });
  expect(screen.getByText('Thanks! Your trust score: 64%')).toBeTruthy();
});

test('closes by itself after 15 s if I do not answer', async () => {
  await walkUp();
  await screen.findByText('Is there a pothole here?');

  await act(async () => {
    await jest.advanceTimersByTimeAsync(10_000);
  });
  expect(screen.getByText('Is there a pothole here?')).toBeTruthy(); // still up after 10 s
  await act(async () => {
    await jest.advanceTimersByTimeAsync(6_000);
  });

  expect(screen.queryByText('Is there a pothole here?')).toBeNull();
  expect(mockAnswer).not.toHaveBeenCalled();
});
