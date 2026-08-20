import type { Metadata } from "next";
import Script from "next/script";
import { Analytics } from "@vercel/analytics/next";
import { TooltipProvider } from "@/components/ui/tooltip";
import { siteConfig } from "@/lib/site";
import "./globals.css";

const socialPreview = {
  url: "/social-preview-gear.png",
  width: 1200,
  height: 630,
  alt: "text-to-cad homepage showing a planetary gear CAD model",
};

const themeScript = `
(() => {
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  const storageKey = "cad-skills-theme-v2";
  const applyTheme = (theme) => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.style.colorScheme = theme;
  };
  const getStoredTheme = () => {
    try {
      const storedTheme = window.localStorage.getItem(storageKey);
      return storedTheme === "dark" || storedTheme === "light"
        ? storedTheme
        : null;
    } catch {
      return null;
    }
  };

  applyTheme(getStoredTheme() ?? "dark");

  const handleSystemThemeChange = () => {
    if (!getStoredTheme()) {
      applyTheme("dark");
    }
  };

  try {
    media.addEventListener("change", handleSystemThemeChange);
  } catch {
    media.addListener(handleSystemThemeChange);
  }
})();
`;

export const metadata: Metadata = {
  metadataBase: new URL(siteConfig.origin),
  applicationName: siteConfig.name,
  title: {
    default: siteConfig.title,
    template: `%s | ${siteConfig.name}`,
  },
  description: siteConfig.description,
  keywords: siteConfig.keywords,
  alternates: {
    canonical: "/",
  },
  openGraph: {
    title: siteConfig.title,
    description: siteConfig.description,
    url: "/",
    siteName: siteConfig.name,
    images: [socialPreview],
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: siteConfig.title,
    description: siteConfig.description,
    images: [socialPreview],
  },
  icons: {
    icon: [
      { url: "/favicon.ico?v=star-tile", type: "image/x-icon" },
    ],
    shortcut: [
      { url: "/favicon.ico?v=star-tile", type: "image/x-icon" },
    ],
    apple: [
      { url: "/favicon.png?v=star-tile", type: "image/png" },
    ],
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-image-preview": "large",
      "max-snippet": -1,
      "max-video-preview": -1,
    },
  },
  category: "engineering",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <Script
          id="theme-script"
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{ __html: themeScript }}
        />
        <TooltipProvider>{children}</TooltipProvider>
        <Analytics />
      </body>
    </html>
  );
}
