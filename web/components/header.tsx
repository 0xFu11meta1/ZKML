"use client";

import { useSession, signIn, signOut } from "next-auth/react";
import { Search, Moon, Sun, Menu } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, useEffect, useCallback } from "react";

function useDarkMode() {
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("theme");
    if (stored === "dark" || (!stored && window.matchMedia("(prefers-color-scheme: dark)").matches)) {
      setIsDark(true);
      document.documentElement.classList.add("dark");
    }
  }, []);

  const toggle = useCallback(() => {
    setIsDark((prev) => {
      const next = !prev;
      if (next) {
        document.documentElement.classList.add("dark");
        localStorage.setItem("theme", "dark");
      } else {
        document.documentElement.classList.remove("dark");
        localStorage.setItem("theme", "light");
      }
      return next;
    });
  }, []);

  return { isDark, toggle };
}

export function Header({ onMenuToggle }: { onMenuToggle?: () => void }) {
  const { data: session } = useSession();
  const router = useRouter();
  const [query, setQuery] = useState("");
  const { isDark, toggle: toggleDark } = useDarkMode();

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      router.push(`/search?q=${encodeURIComponent(query.trim())}`);
    }
  };

  return (
    <header className="flex h-16 items-center justify-between border-b border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-900 px-6">
      <div className="flex items-center gap-3">
        {/* Mobile hamburger */}
        <button
          onClick={onMenuToggle}
          className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 md:hidden"
          aria-label="Open navigation menu"
        >
          <Menu className="h-5 w-5" />
        </button>

        {/* Search bar */}
        <form
          onSubmit={handleSearch}
          className="flex w-full max-w-md items-center"
          role="search"
          aria-label="Search proofs and circuits"
        >
          <div className="relative w-full">
            <Search
              className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400"
              aria-hidden="true"
            />
            <input
              type="search"
              placeholder="Search circuits, proofs, provers..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Search circuits, proofs, and provers"
              className="w-full rounded-lg border border-gray-200 bg-surface-1 py-2 pl-10 pr-4 text-sm text-gray-700 placeholder-gray-400 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 transition-colors dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200 dark:placeholder-gray-500"
            />
          </div>
        </form>
      </div>

      {/* Right section: dark mode toggle + auth */}
      <div className="ml-4 flex items-center gap-3">
        <button
          onClick={toggleDark}
          className="rounded-lg p-2 text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800 transition-colors"
          aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
        >
          {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </button>

        {session ? (
          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-600 dark:text-gray-300 font-medium">
              {session.user?.name || "Wallet Connected"}
            </span>
            <button
              onClick={() => signOut()}
              className="rounded-lg border border-gray-200 dark:border-gray-600 px-3 py-1.5 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
            >
              Sign Out
            </button>
          </div>
        ) : (
          <button
            onClick={() => signIn()}
            className="rounded-lg bg-brand-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-brand-700 transition-colors"
          >
            Connect Wallet
          </button>
        )}
      </div>
    </header>
  );
}
