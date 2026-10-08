import type { Metadata, Viewport } from "next";
import { Archivo, Martian_Mono } from "next/font/google";
import { Suspense, ViewTransition } from "react";

import { SiteFooter } from "@/components/site/site-footer";
import { SiteHeader, SiteHeaderShell } from "@/components/site/site-header";

import "./globals.css";

const archivo = Archivo({
  subsets: ["latin"],
  axes: ["wdth"],
  variable: "--font-archivo",
  display: "swap",
});

const martian = Martian_Mono({
  subsets: ["latin"],
  axes: ["wdth"],
  variable: "--font-martian",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "ChangeGuard — evidence-grounded code-change risk analysis",
    template: "%s · ChangeGuard",
  },
  description:
    "ChangeGuard reads a diff the way a careful reviewer does: it reconstructs both revisions, follows every caller, runs differential static analysis, measures coverage of the changed lines, and lets a language model explain only where the evidence holds.",
  applicationName: "ChangeGuard",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0b0b0b" },
  ],
};

// Applies a stored theme choice before first paint (no flash). Without a stored
// choice the CSS follows the operating-system preference.
const THEME_SCRIPT = `try{var t=localStorage.getItem("cg-theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${archivo.variable} ${martian.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-dvh bg-bg text-ink antialiased">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[70] focus:rounded-md focus:bg-ink focus:px-3 focus:py-2 focus:text-bg"
        >
          Skip to content
        </a>
        <Suspense fallback={<SiteHeaderShell />}>
          <SiteHeader />
        </Suspense>
        <ViewTransition>
          <main id="main" className="relative">
            {children}
          </main>
        </ViewTransition>
        <SiteFooter />
      </body>
    </html>
  );
}
