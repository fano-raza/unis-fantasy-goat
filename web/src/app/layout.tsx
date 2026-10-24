import type { Metadata } from "next";
import Link from "next/link";
import { Archivo, Big_Shoulders } from "next/font/google";
import { Nav } from "@/components/nav";
import { MobileNav } from "@/components/mobile-nav";
import { PageArrowNav } from "@/components/page-arrow-nav";
import { FloatingMenuButton } from "@/components/floating-menu-button";
import { GlobalLastUpdated } from "@/components/global-last-updated";
import { MobileMenuProvider } from "@/components/mobile-menu-context";
import { API_BASE_URL } from "@/lib/api";
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

export const metadata: Metadata = {
  title: "UNIS 2014 Fantasy",
  description: "UNIS Fantasy Basketball League",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${archivo.variable} ${bigShoulders.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
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
        <MobileMenuProvider>
          {/* Sticky on mobile only (feature request, 2026-10-06) -- the home
              link + PageArrowNav are the only header content that renders
              there (desktop's Nav row is sm:hidden-gated out), so freezing
              the whole header is exactly "freeze the page toggle buttons
              and home button". z-40 keeps it under MobileNav's drawer
              (z-50 backdrop/popup) so the drawer still overlays it. */}
          <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur sm:static">
            <div className="mx-auto flex w-full max-w-5xl flex-col gap-3 px-4 pt-4 pb-3 sm:px-6 sm:pb-0">
              <div className="flex items-center justify-between gap-3">
                <Link href="/" className="wordmark transition-opacity hover:opacity-80">
                  UNIS 2014 Fantasy
                </Link>
                {/* The one freshness indicator in the whole app now (feature
                    request, 2026-10-06) -- see global-last-updated.tsx. */}
                <GlobalLastUpdated />
              </div>
              <div className="hidden sm:block">
                <Nav />
              </div>
              <PageArrowNav />
            </div>
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
