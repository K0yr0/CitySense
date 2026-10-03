/**
 * Turkish UI labels and colours for incidents and road health.
 * Two separate states, never mixed: `status` (confidence engine) and `work_status` (the city's work).
 */
import type { HealthClass, IncidentStatus, IssueType, WorkStatus } from '@/lib/api';

export const TYPE_LABELS: Record<IssueType, string> = {
  road_damage: 'Yol çukuru',
  tram_track: 'Ray kusuru',
  streetlight: 'Sokak lambası',
  flooding: 'Su baskını',
  waste: 'Çöp',
  other: 'Diğer',
};

export const TYPE_ICONS: Record<IssueType, string> = {
  road_damage: '🕳️',
  tram_track: '🚋',
  streetlight: '💡',
  flooding: '🌊',
  waste: '🗑️',
  other: '❔',
};

export function typeLabel(type: IssueType | null | undefined): string {
  return type ? (TYPE_LABELS[type] ?? TYPE_LABELS.other) : TYPE_LABELS.other;
}

/** Confidence label (candidate → likely → verified). */
export const STATUS_LABELS: Record<IncidentStatus, string> = {
  candidate: 'Aday',
  likely: 'Muhtemel',
  verified: 'Doğrulandı',
  dismissed: 'Bulunamadı',
  closed: 'Kapandı',
};

export const STATUS_COLORS: Record<IncidentStatus, string> = {
  candidate: '#9AA0A6',
  likely: '#F29900',
  verified: '#D93025',
  dismissed: '#5F6368',
  closed: '#5F6368',
};

export function statusLabel(status: IncidentStatus): string {
  return STATUS_LABELS[status] ?? status;
}

/** The city's work on it (todo → in_progress → done). */
export const WORK_STATUS_LABELS: Record<WorkStatus, string> = {
  todo: 'Yapılmadı',
  in_progress: 'Belediye ilgileniyor',
  done: 'Yapıldı',
};

export const WORK_STATUS_COLORS: Record<WorkStatus, string> = {
  todo: '#9AA0A6',
  in_progress: '#1A73E8',
  done: '#1F9D55',
};

export function workStatusLabel(work: WorkStatus): string {
  return WORK_STATUS_LABELS[work] ?? work;
}

/** Road health is shown to citizens only as one of these colour classes. */
export const HEALTH_CLASSES: HealthClass[] = ['good', 'fair', 'poor', 'unknown'];

export const HEALTH_LABELS: Record<HealthClass, string> = {
  good: 'İyi',
  fair: 'Orta',
  poor: 'Kötü',
  unknown: 'Ölçülmedi',
};

export const HEALTH_COLORS: Record<HealthClass, string> = {
  good: '#1F9D55',
  fair: '#F2B300',
  poor: '#D93025',
  unknown: '#9AA0A6',
};

export function healthColor(health: HealthClass): string {
  return HEALTH_COLORS[health] ?? HEALTH_COLORS.unknown;
}

/** Colour of an incident marker: done = green, otherwise by confidence status. */
export function incidentColor(incident: { status: IncidentStatus; work_status: WorkStatus }): string {
  return incident.work_status === 'done' ? WORK_STATUS_COLORS.done : STATUS_COLORS[incident.status];
}

/** "%80" style percentage; confidence is never shown as certain. */
export function confidencePct(confidence: number): string {
  const x = Math.min(1, Math.max(0, confidence || 0));
  return `%${Math.min(99, Math.round(100 * x))}`;
}

/** "3 dk önce" / "2 sa önce" / "5 gün önce" for an ISO timestamp. */
export function timeAgo(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return '';
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return '';
  const min = Math.max(0, Math.round((now - t) / 60000));
  if (min < 1) return 'az önce';
  if (min < 60) return `${min} dk önce`;
  const h = Math.round(min / 60);
  if (h < 24) return `${h} sa önce`;
  return `${Math.round(h / 24)} gün önce`;
}
