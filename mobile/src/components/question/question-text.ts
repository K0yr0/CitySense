/** Wording of the 25 m question, adapted to the incident type (ROADMAP M4). Texts: i18n/question.ts. */
import { questionText } from '@/i18n/question';
import type { IssueType } from '@/lib/api';
import { text } from '@/lib/i18n';
import { typeLabel } from '@/lib/labels';

type QuestionTexts = (typeof questionText)['en'];

/** The question for an incident type; pass `s` from useText(questionText) inside components. */
export function questionFor(type: IssueType, s: QuestionTexts = text(questionText)): string {
  switch (type) {
    case 'road_damage':
    case 'tram_track':
    case 'streetlight':
      return s.ask[type];
    default:
      return s.ask.other(typeLabel(type));
  }
}
