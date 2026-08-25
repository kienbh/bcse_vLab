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
        <script defer src="https://sv05.bcse-vju.com/script.js" data-website-id="443c38f1-0b6c-430d-80f2-eba6ee772fa1" />

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
        <script defer src="https://sv05.bcse-vju.com/script.js" data-website-id="443c38f1-0b6c-430d-80f2-eba6ee772fa1" />
      </head>
      <body className="flex min-h-screen flex-col antialiased">
        <TopNav />
        <main className="flex-1">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
