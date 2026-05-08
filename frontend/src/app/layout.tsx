import type { Metadata } from "next";

import { Footer } from "@/components/Footer";
import { TopNav } from "@/components/TopNav";

import "./globals.css";

export const metadata: Metadata = {
  title: "VJU Hardware Lab Portal",
  description:
    "Cổng truy cập từ xa thiết bị FPGA/Jetson/RPi cho sinh viên BCSE — Đại học Việt Nhật.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi" suppressHydrationWarning>
      <head>
        <script
          // Avoid theme flash — read localStorage before paint
          dangerouslySetInnerHTML={{
            __html: `
try {
  var s = localStorage.getItem('theme');
  var d = s === 'dark' || (s == null && window.matchMedia('(prefers-color-scheme: dark)').matches);
  if (d) document.documentElement.classList.add('dark');
} catch (e) {}
            `,
          }}
        />
      </head>
      <body className="flex min-h-screen flex-col antialiased">
        <TopNav />
        <main className="flex-1">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
