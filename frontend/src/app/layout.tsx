import type { Metadata } from "next";
import "@/styles/globals.css";
import { Sidebar } from "@/components/layout/Sidebar";

export const metadata: Metadata = {
  title: "Gotham4Justice — Digital Forensic Intelligence",
  description: "Law enforcement digital evidence investigation platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="flex h-screen overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-auto bg-forensic-bg">
          <div className="p-6">{children}</div>
        </main>
      </body>
    </html>
  );
}
