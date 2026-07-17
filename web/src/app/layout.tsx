import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
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
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "https://digitalcanalst.up.railway.app"),
  title: { default: "Digital Canal St", template: "%s · Digital Canal St" },
  description: "Curated replica fashion catalog with one-click Superbuy links",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <div className="flex-1">{children}</div>
        <footer className="border-t border-zinc-200 mt-8">
          <div className="mx-auto max-w-6xl px-4 py-6 text-xs text-zinc-500">
            <p>
              As an affiliate, Digital Canal St may earn a commission from
              qualifying purchases made through links on this site, at no
              additional cost to you.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
