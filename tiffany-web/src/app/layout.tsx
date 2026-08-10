import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: {
    default: "Tiffany Bot | One bot. Your entire server.",
    template: "%s | Tiffany Bot"
  },
  description: "Music, AI, moderation, games, giveaways, news, deals and more — built directly into Discord.",
  openGraph: {
    title: "Tiffany Bot",
    description: "One bot. Your entire Discord. Replace multiple separate bots with one cohesive system.",
    url: "https://tiffanybot.com",
    siteName: "Tiffany Bot",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Tiffany Bot",
    description: "One bot. Your entire Discord. Music, AI, moderation, games, giveaways, news, deals and more.",
  },
  keywords: [
    "Discord bot", 
    "Discord moderation bot", 
    "Discord music bot", 
    "Discord AI bot", 
    "Discord giveaway bot", 
    "Discord automation bot", 
    "Discord news bot", 
    "Discord deals bot"
  ],
};

import { ToastProvider } from "@/components/ToastProvider";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <ToastProvider>
          {children}
        </ToastProvider>
      </body>
    </html>
  );
}
