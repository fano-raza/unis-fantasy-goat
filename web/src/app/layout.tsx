import type { Metadata, Viewport } from "next";
import Link from "next/link";
import { Archivo, Big_Shoulders } from "next/font/google";
import { Nav } from "@/components/nav";
import { MobileNav } from "@/components/mobile-nav";
import { SettingsMenu } from "@/components/settings-menu";
import { PageArrowNav } from "@/components/page-arrow-nav";
import { FloatingMenuButton } from "@/components/floating-menu-button";
import { GlobalLastUpdated } from "@/components/global-last-updated";
import { MobileMenuProvider } from "@/components/mobile-menu-context";
import { PremiumProvider } from "@/components/premium";
import { LiveDataProvider } from "@/lib/live-data";
import { API_BASE_URL } from "@/lib/api";
import { themeInitScript } from "@/lib/theme";
import "./globals.css";

// Archivo: UI text and every stat figure (tabular numerals via the global
// "tnum" feature in globals.css). Big Shoulders: condensed Chicago-signage
// face for the wordmark, page/section titles and jersey-style team names.
const archivo = Archivo({
  variable: "--font-archivo",
  subsets: ["latin"],
  axes: ["wdth"],
});

const bigShoulders = Big_Shoulders({
  variable: "--font-big-shoulders",
  subsets: ["latin"],
  axes: ["opsz"],
});

// Tints the mobile browser's own UI to match the header strip (--card) of
// the default dark theme; lib/theme.ts swaps it when Light mode is on.
export const viewport: Viewport = {
  themeColor: "#141e2b",
};

export const metadata: Metadata = {
  title: "UNIS 2014 Fantasy",
  description: "UNIS Fantasy Basketball League",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${archivo.variable} ${bigShoulders.variable} h-full antialiased`}
      // themeInitScript below may set data-theme on <html> before React
      // hydrates (a stored Light mode choice) -- expected, not a mismatch.
      suppressHydrationWarning
    >
      <body className="min-h-full flex flex-col">
        {/* Applies a stored Light mode choice before first paint. */}
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        {/* Opens the DNS+TCP+TLS connection to the backend while the page's
            JS is still downloading/parsing, instead of only starting once
            hydration triggers the first fetch -- that handshake measured
            ~550ms alone against the droplet, previously fully serial with
            bundle load. React/Next auto-hoist <link> tags rendered anywhere
            in the tree into the real document <head> -- no manual <head>
            element needed (and a literal one here was the likely cause of a
            hydration mismatch specifically on "/", the one route whose
            Suspense fallback forces a static/dynamic split at this level). */}
        <link rel="preconnect" href={API_BASE_URL} crossOrigin="anonymous" />
        <link rel="dns-prefetch" href={API_BASE_URL} />
        <LiveDataProvider>
        <PremiumProvider>
        <MobileMenuProvider>
          {/* Sticky on mobile only (feature request, 2026-10-06) -- the home
              link + PageArrowNav are the only header content that renders
              there (desktop's Nav row is sm:hidden-gated out), so freezing
              the whole header is exactly "freeze the page toggle buttons
              and home button". z-40 keeps it under MobileNav's drawer
              (z-50 backdrop/popup) so the drawer still overlays it. */}
          <header className="sticky top-0 z-40 bg-card sm:static">
            <div className="mx-auto flex w-full max-w-5xl flex-col gap-3 px-4 pt-4 pb-0 sm:px-6">
              <div className="flex items-center justify-between gap-3">
                <Link href="/" className="wordmark transition-opacity hover:opacity-80">
                  UNIS 2014 Fantasy
                </Link>
                {/* The one freshness indicator in the whole app now (feature
                    request, 2026-10-06) -- see global-last-updated.tsx. */}
                <GlobalLastUpdated />
              </div>
              {/* Tabs + the settings gear at the right end of the same row. */}
              <div className="hidden items-end gap-2 sm:flex">
                <div className="min-w-0 flex-1">
                  <Nav />
                </div>
                <SettingsMenu />
              </div>
              <PageArrowNav />
            </div>
            {/* Mobile-only full-width fade hanging just below the frozen
                header (user request, 2026-10-29): page background color
                (same fill as the current-page tab) fully opaque at the top,
                fading to transparent at the bottom, so scrolled content
                fades out as it passes under the tab. Positioned below the
                header (top-full) rather than inside it, so the transparent
                end reveals the page content, not the header's own card
                fill. h-6 = 1.5x main's mobile px-4 side padding. */}
            <div
              aria-hidden="true"
              className="pointer-events-none absolute inset-x-0 top-full h-6 bg-linear-to-b from-background to-transparent sm:hidden"
            />
          </header>
          {/* No visible trigger left in the header -- FloatingMenuButton
              (feature request, 2026-10-06) and PageArrowNav's page-name tab
              are the only ways to open MobileNav's drawer now. */}
          <MobileNav />
          <FloatingMenuButton />
          <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6 sm:px-6 sm:py-8">
            {children}
          </main>
        </MobileMenuProvider>
        </PremiumProvider>
        </LiveDataProvider>
        <footer className="border-t border-border">
          <div className="mx-auto w-full max-w-5xl px-4 py-4 text-center text-xs text-muted-foreground sm:px-6">
            <a
              href="https://www.fanoraza.com/"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-foreground hover:underline"
            >
              fanoraza.com
            </a>
          </div>
        </footer>
      </body>
    </html>
  );
}
