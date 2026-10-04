// Light is the default (Stitch). Dark is opt-in from the header toggle and remembered per browser.
// Kept free of React so the root layout (a server component) can import it.
export const THEME_KEY = "citysense-theme";

/** Runs in <head> before the first paint so a saved dark choice doesn't flash light. */
export const THEME_SCRIPT = `try{if(localStorage.getItem("${THEME_KEY}")==="dark")document.documentElement.dataset.theme="dark"}catch(e){}`;
