import type { Metadata } from "next";
import { Inter, Roboto_Mono } from "next/font/google";
import { Providers } from "./providers";
import "./globals.css";

const sans = Inter({ variable: "--font-inter", subsets: ["latin"], weight: ["300", "400", "500"] });
const mono = Roboto_Mono({ variable: "--font-roboto-mono", subsets: ["latin"], weight: ["400", "500"] });

export const metadata: Metadata = {
  title: "Transaction Validation",
  description: "An auditable agent that validates bank transactions",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    // Dark by default. Remove "dark" for the light theme (better on a projector).
    <html lang="en" className={`${sans.variable} ${mono.variable} dark h-full antialiased`}>
      <body className="min-h-full flex flex-col">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
