import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono } from "next/font/google";
import { Nav } from "@/components/nav";
import { MobileNav } from "@/components/mobile-nav";
import { PageArrowNav } from "@/components/page-arrow-nav";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "UNIS 2014 Fantasy",
  description: "UNIS Fantasy Basketball League",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <header className="border-b border-border">
          <div className="mx-auto flex w-full max-w-5xl flex-col gap-3 px-4 py-4 sm:px-6">
            <div className="flex items-center justify-between gap-3">
              <Link
                href="/"
                className="text-xl font-black tracking-tight italic transition-opacity hover:opacity-80"
              >
                UNIS 2014 <span className="text-primary">FANTASY</span>
              </Link>
              <div className="flex items-center gap-3">
                <div className="sm:hidden">
                  <MobileNav />
                </div>
              </div>
            </div>
            <div className="hidden sm:block">
              <Nav />
            </div>
            <PageArrowNav />
          </div>
        </header>
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6 sm:px-6">
          {children}
        </main>
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
