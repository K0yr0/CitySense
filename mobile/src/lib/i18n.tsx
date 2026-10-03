/**
 * App languages: English (default), Polish, Ukrainian.
 *
 * Texts live in src/i18n/<area>.ts as `{ en, pl, uk }` objects; `pl` and `uk` are typed as
 * `typeof en`, so a missing or extra key is a type error. Values are strings or functions
 * (for numbers / names), e.g.:
 *
 *     const s = useText(mapText);           // in a component
 *     <Text>{s.title}</Text>  <Text>{s.reportedBy(3)}</Text>
 *
 *     text(mapText).title                    // outside React (hooks' callbacks, helpers)
 *
 * The chosen language is stored on the device; the first launch follows the phone's
 * language when it is Polish or Ukrainian, otherwise English. Changing the language
 * remounts the app below <I18nProvider>, so every screen re-renders in the new language.
 */
import { getLocales } from 'expo-localization';
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { getItem, setItem } from '@/lib/storage';

export type Locale = 'en' | 'pl' | 'uk';

export const LOCALES: { code: Locale; name: string }[] = [
  { code: 'en', name: 'English' },
  { code: 'pl', name: 'Polski' },
  { code: 'uk', name: 'Українська' },
];

export type Translations<T> = { en: T; pl: T; uk: T };

const LOCALE_KEY = 'cityecho.locale';

let current: Locale = deviceLocale();

function isLocale(value: unknown): value is Locale {
  return value === 'en' || value === 'pl' || value === 'uk';
}

/** The phone's preferred language if we support it, else English. */
export function deviceLocale(): Locale {
  try {
    for (const l of getLocales()) {
      if (isLocale(l.languageCode)) return l.languageCode;
    }
  } catch {
    // no native module (tests / unusual platforms)
  }
  return 'en';
}

/** Current language (also sent to the backend as Accept-Language). */
export function getLocale(): Locale {
  return current;
}

/** The current language's texts of one area, for code outside components. */
export function text<T>(translations: Translations<T>): T {
  return translations[current];
}

// ---- plurals ----------------------------------------------------------------

export type PluralForms = { one: string; few?: string; many?: string; other: string };

/** CLDR plural category for whole numbers. pl/uk: one / few / many; en: one / other. */
function pluralCategory(n: number, locale: Locale): 'one' | 'few' | 'many' | 'other' {
  const abs = Math.abs(n);
  if (!Number.isInteger(abs)) return 'other';
  const mod10 = abs % 10;
  const mod100 = abs % 100;
  if (locale === 'en') return abs === 1 ? 'one' : 'other';
  if (locale === 'pl') {
    if (abs === 1) return 'one';
    if (mod10 >= 2 && mod10 <= 4 && !(mod100 >= 12 && mod100 <= 14)) return 'few';
    return 'many';
  }
  // uk
  if (mod10 === 1 && mod100 !== 11) return 'one';
  if (mod10 >= 2 && mod10 <= 4 && !(mod100 >= 12 && mod100 <= 14)) return 'few';
  return 'many';
}

/**
 * Pick the plural form for `n` in the current language and replace `{n}`.
 *   plural(5, { one: '{n} osoba', few: '{n} osoby', many: '{n} osób', other: '{n} osoby' })
 */
export function plural(n: number, forms: PluralForms, locale: Locale = current): string {
  const cat = pluralCategory(n, locale);
  const form = forms[cat] ?? forms.other;
  return form.replace(/\{n\}/g, formatNumber(n, locale));
}

/** Whole numbers as-is; decimals with the language's separator (1.5 / 1,5). */
export function formatNumber(n: number, locale: Locale = current, digits = 1): string {
  const s = Number.isInteger(n) ? String(n) : n.toFixed(digits);
  return locale === 'en' ? s : s.replace('.', ',');
}

// ---- provider -----------------------------------------------------------------

type I18nValue = { locale: Locale; setLocale: (locale: Locale) => void };

const I18nContext = createContext<I18nValue>({ locale: current, setLocale: () => {} });

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(current);

  useEffect(() => {
    let cancelled = false;
    getItem(LOCALE_KEY).then((stored) => {
      if (!cancelled && isLocale(stored) && stored !== current) {
        current = stored;
        setLocaleState(stored);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const setLocale = useCallback((next: Locale) => {
    current = next;
    setLocaleState(next);
    void setItem(LOCALE_KEY, next);
  }, []);

  const value = useMemo(() => ({ locale, setLocale }), [locale, setLocale]);

  // key: a language change remounts the tree, so module-level text() callers update too.
  return (
    <I18nContext.Provider value={value} key={locale}>
      {children}
    </I18nContext.Provider>
  );
}

/** { locale, setLocale } for the language picker. */
export function useLocale(): I18nValue {
  return useContext(I18nContext);
}

/** The current language's texts of one area (re-renders on language change). */
export function useText<T>(translations: Translations<T>): T {
  return translations[useContext(I18nContext).locale];
}
