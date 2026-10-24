// Light/dark theme. By default the app follows the viewer's own OS/browser
// setting (prefers-color-scheme, handled entirely in globals.css). Flipping
// the mobile menu's theme switch stores an explicit choice per device and
// stamps it on <html data-theme="...">, which globals.css's theme-dark
// variant honors over the device setting.

export type Theme = "light" | "dark";

export const THEME_STORAGE_KEY = "theme";

// Header-strip color (--card) per mode, for the mobile browser's own UI --
// must match layout.tsx's viewport.themeColor.
export const THEME_COLORS: Record<Theme, string> = {
  light: "#ffffff",
  dark: "#141e2b",
};

export function systemTheme(): Theme {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function storedTheme(): Theme | null {
  try {
    const value = localStorage.getItem(THEME_STORAGE_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null;
  }
}

// The theme currently on screen: the stored choice if any, else the device's.
export function currentTheme(): Theme {
  return storedTheme() ?? systemTheme();
}

export function setTheme(theme: Theme) {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {}
  document.documentElement.dataset.theme = theme;
  // Both media-scoped theme-color tags get the chosen color, so the browser
  // bar matches the override regardless of the device setting.
  document
    .querySelectorAll('meta[name="theme-color"]')
    .forEach((meta) => meta.setAttribute("content", THEME_COLORS[theme]));
}

// Inlined at the top of <body> (layout.tsx) so a stored choice is applied
// before first paint -- no flash of the device-default theme. Kept as a
// plain string: it runs before React or any bundle loads.
export const themeInitScript = `(function(){try{var t=localStorage.getItem(${JSON.stringify(THEME_STORAGE_KEY)});if(t==="light"||t==="dark"){document.documentElement.dataset.theme=t;var c=${JSON.stringify(THEME_COLORS)}[t];document.querySelectorAll('meta[name="theme-color"]').forEach(function(m){m.setAttribute("content",c)})}}catch(e){}})();`;
