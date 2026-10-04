"use client";

import { useSyncExternalStore } from "react";
import { THEME_KEY } from "./themeScript";

function subscribe(cb: () => void) {
  const mo = new MutationObserver(cb);
  mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => mo.disconnect();
}

/** True while the dark theme is on (used for the basemap, deck.gl and Google button colours). */
export function useDarkTheme(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => document.documentElement.dataset.theme === "dark",
    () => false,
  );
}

export function setDarkTheme(dark: boolean) {
  if (dark) document.documentElement.dataset.theme = "dark";
  else delete document.documentElement.dataset.theme;
  try {
    localStorage.setItem(THEME_KEY, dark ? "dark" : "light");
  } catch {
    // storage blocked: the choice lasts for this page only
  }
}
