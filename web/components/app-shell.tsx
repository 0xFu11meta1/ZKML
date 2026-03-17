"use client";

import { useState, useCallback } from "react";
import { Sidebar } from "@/components/sidebar";
import { Header } from "@/components/header";
import { MobileNav } from "@/components/mobile-nav";
import { ErrorBoundary } from "@/components/error-boundary";

export function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const openMobileNav = useCallback(() => setMobileNavOpen(true), []);
  const closeMobileNav = useCallback(() => setMobileNavOpen(false), []);

  return (
    <>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:rounded-md focus:bg-brand-600 focus:px-4 focus:py-2 focus:text-white"
      >
        Skip to content
      </a>
      <div className="flex h-screen overflow-hidden bg-white dark:bg-gray-950">
        <Sidebar />
        <MobileNav open={mobileNavOpen} onClose={closeMobileNav} />
        <div className="flex flex-1 flex-col overflow-hidden">
          <Header onMenuToggle={openMobileNav} />
          <main
            id="main-content"
            className="flex-1 overflow-y-auto p-6 dark:text-gray-100"
          >
            <ErrorBoundary>{children}</ErrorBoundary>
          </main>
        </div>
      </div>
    </>
  );
}
