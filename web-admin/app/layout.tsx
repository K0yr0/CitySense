import type { Metadata, Viewport } from "next";
import AuthGate from "@/components/auth/AuthGate";
import Header from "@/components/Header";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "CityEcho admin · Warsaw city health", template: "%s · CityEcho admin" },
  description: "Warsaw's buses verify its citizens — and its citizens verify its buses. Sensor rides and 19115 reports fused into verified incidents.",
  applicationName: "CityEcho",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#1a1a19" },
  ],
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en">
      <body className="flex min-h-dvh flex-col">
        <Header />
        <AuthGate>{children}</AuthGate>
      </body>
    </html>
  );
}
