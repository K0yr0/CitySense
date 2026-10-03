/**
 * Glossary for incidents and road health. Every screen uses these words (via lib/labels.ts),
 * so the same thing is always called the same.
 * Two separate states, never mixed: `status` (confidence engine) and `work` (the city's work).
 */
import type { HealthClass, IncidentStatus, IssueType, WorkStatus } from '@/lib/api';

type Labels = {
  type: Record<IssueType, string>;
  status: Record<IncidentStatus, string>;
  /** One line explaining the confidence status to a citizen. */
  statusHint: Record<IncidentStatus, string>;
  work: Record<WorkStatus, string>;
  health: Record<HealthClass, string>;
};

const en: Labels = {
  type: {
    road_damage: 'Road damage',
    tram_track: 'Tram track defect',
    streetlight: 'Streetlight out',
    flooding: 'Flooding',
    waste: 'Litter',
    other: 'Other',
  },
  status: {
    candidate: 'Unconfirmed',
    likely: 'Likely',
    verified: 'Verified',
    dismissed: 'Not found',
    closed: 'Closed',
  },
  statusHint: {
    candidate: 'Not confirmed yet',
    likely: 'Most likely a real problem',
    verified: 'Confirmed',
    dismissed: 'Checks found no problem here',
    closed: 'Closed',
  },
  work: { todo: 'Not started', in_progress: 'City is working on it', done: 'Fixed' },
  health: { good: 'Good', fair: 'Fair', poor: 'Poor', unknown: 'Not measured' },
};

const pl: Labels = {
  type: {
    road_damage: 'Uszkodzona jezdnia',
    tram_track: 'Usterka torowiska',
    streetlight: 'Niedziałająca latarnia',
    flooding: 'Podtopienie',
    waste: 'Śmieci',
    other: 'Inne',
  },
  status: {
    candidate: 'Niepotwierdzone',
    likely: 'Prawdopodobne',
    verified: 'Potwierdzone',
    dismissed: 'Nie znaleziono',
    closed: 'Zamknięte',
  },
  statusHint: {
    candidate: 'Jeszcze niepotwierdzone',
    likely: 'Najprawdopodobniej prawdziwy problem',
    verified: 'Potwierdzone',
    dismissed: 'Kontrole nie wykazały tu problemu',
    closed: 'Zamknięte',
  },
  work: { todo: 'Nierozpoczęte', in_progress: 'Miasto się tym zajmuje', done: 'Naprawione' },
  health: { good: 'Dobra', fair: 'Średnia', poor: 'Zła', unknown: 'Nie zmierzono' },
};

const uk: Labels = {
  type: {
    road_damage: 'Пошкоджена дорога',
    tram_track: 'Дефект трамвайної колії',
    streetlight: 'Не працює ліхтар',
    flooding: 'Підтоплення',
    waste: 'Сміття',
    other: 'Інше',
  },
  status: {
    candidate: 'Не підтверджено',
    likely: 'Ймовірно',
    verified: 'Підтверджено',
    dismissed: 'Не виявлено',
    closed: 'Закрито',
  },
  statusHint: {
    candidate: 'Ще не підтверджено',
    likely: 'Найімовірніше, справжня проблема',
    verified: 'Підтверджено',
    dismissed: 'Перевірки не виявили тут проблеми',
    closed: 'Закрито',
  },
  work: { todo: 'Не розпочато', in_progress: 'Місто працює над цим', done: 'Виправлено' },
  health: { good: 'Добрий', fair: 'Середній', poor: 'Поганий', unknown: 'Не виміряно' },
};

export const labelsText = { en, pl, uk };
