import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "SDI — System Design Interview Practice",
  description:
    "Practice system design interviews with an AI interviewer. Real-time canvas, voice interaction, and detailed scorecards.",
  keywords: ["system design", "interview prep", "software engineering", "FAANG"],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`dark ${inter.variable} ${jetbrainsMono.variable}`}>
      <body className="min-h-screen bg-[#0a0a0b] text-[#e8e8e8] antialiased">
        {children}
      </body>
    </html>
  );
}
