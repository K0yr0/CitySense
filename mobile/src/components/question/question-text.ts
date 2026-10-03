/** Turkish wording of the 25 m question, adapted to the incident type (ROADMAP M4). */
import type { IssueType } from '@/lib/api';
import { typeLabel } from '@/lib/labels';

export function questionText(type: IssueType): string {
  switch (type) {
    case 'road_damage':
      return '25 m çevrende çukur görüyor musun?';
    case 'tram_track':
      return '25 m çevrende rayda bir kusur görüyor musun?';
    case 'streetlight':
      return '25 m çevrende yanmayan bir lamba görüyor musun?';
    default:
      return `25 m çevrende bu sorunu görüyor musun? (${typeLabel(type)})`;
  }
}
