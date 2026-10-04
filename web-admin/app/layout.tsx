import type { Metadata, Viewport } from "next";
import { JetBrains_Mono, Public_Sans } from "next/font/google";
import AuthGate from "@/components/auth/AuthGate";
import Header from "@/components/Header";
import { THEME_SCRIPT } from "@/lib/themeScript";
import "./globals.css";

// Stitch design system: Public Sans for the interface, JetBrains Mono for ids, numbers and labels.
// latin-ext covers Polish street names (ł, ś, ż …).
const sans = Public_Sans({ subsets: ["latin", "latin-ext"], variable: "--font-public-sans", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin", "latin-ext"], variable: "--font-jetbrains-mono", display: "swap" });

export const metadata: Metadata = {
  title: { default: "CityEcho admin · Warsaw city health", template: "%s · CityEcho admin" },
  description: "Warsaw's buses verify its citizens — and its citizens verify its buses. Sensor rides and 19115 reports fused into verified incidents.",
  applicationName: "CityEcho",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#ffffff",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="flex min-h-dvh flex-col">
        <Header />
        <AuthGate>{children}</AuthGate>
      </body>
    </html>
  );
}
