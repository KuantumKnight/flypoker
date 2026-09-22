import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Fly Poker — Six minds. One table.",
  description: "A cinematic live poker table powered by six batched MaleCNS or development-adapter fly brains.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
