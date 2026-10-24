// Light/dark theme. Dark is the default for everyone (the device's own
// light/dark setting is deliberately ignored); Light mode is an opt-in
// setting -- the mobile menu's switch and the desktop settings shelf --
// stored per device and stamped on <html data-theme="light">, which
// globals.css's light token block keys off.

export type Theme = "light" | "dark";

export const THEME_STORAGE_KEY = "theme";

// Header-strip color (--card) per mode, for the mobile browser's own UI --
// the dark value must match layout.tsx's viewport.themeColor.
export const THEME_COLORS: Record<Theme, string> = {
  light: "#ffffff",
  dark: "#141e2b",
};

export function currentTheme(): Theme {
  try {
    return localStorage.getItem(THEME_STORAGE_KEY) === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

export function setTheme(theme: Theme) {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {}
  document.documentElement.dataset.theme = theme;
  document
    .querySelectorAll('meta[name="theme-color"]')
    .forEach((meta) => meta.setAttribute("content", THEME_COLORS[theme]));
}

// Inlined at the top of <body> (layout.tsx) so a stored Light mode choice is
// applied before first paint -- no flash of dark. Kept as a plain string:
// it runs before React or any bundle loads.
export const themeInitScript = `(function(){try{if(localStorage.getItem(${JSON.stringify(THEME_STORAGE_KEY)})==="light"){document.documentElement.dataset.theme="light";document.querySelectorAll('meta[name="theme-color"]').forEach(function(m){m.setAttribute("content",${JSON.stringify(THEME_COLORS.light)})})}}catch(e){}})();`;
