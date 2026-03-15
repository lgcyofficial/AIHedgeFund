import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TradeAgent Command Deck",
  description: "Scenario-driven autonomous hedge fund simulator with committee voting and benchmark tracking.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
