import type { Metadata } from "next";
import Script from "next/script";
import { Analytics } from "@vercel/analytics/next";
import { TooltipProvider } from "@/components/ui/tooltip";
import { absoluteUrl, siteConfig } from "@/lib/site";
import "./globals.css";

// A new name for a new picture: the platforms that unfurl links cache a preview by its URL.
const socialPreview = {
  url: "/social-preview-products.png",
  width: 1200,
  height: 630,
  alt: "text-to-cad: Design physical products with AI. Colorful planetary gears rendered from editable CAD geometry.",
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
  authors: [{ name: siteConfig.author.name, url: siteConfig.author.url }],
  creator: siteConfig.author.name,
  alternates: {
    canonical: "/",
  },
  openGraph: {
    title: siteConfig.title,
    description: siteConfig.description,
    url: "/",
    siteName: siteConfig.name,
    images: [socialPreview],
    videos: [{
      url: absoluteUrl("/social-preview-products.mp4"),
      type: "video/mp4",
      width: 1200,
      height: 630,
    }],
    type: "website",
    locale: "en_US",
  },
  twitter: {
    card: "summary_large_image",
    title: siteConfig.title,
    description: siteConfig.description,
    creator: siteConfig.author.handle,
    images: [socialPreview],
  },
  icons: {
    icon: [
      { url: "/favicon.ico?v=soft-relief-c", type: "image/x-icon" },
    ],
    shortcut: [
      { url: "/favicon.ico?v=soft-relief-c", type: "image/x-icon" },
    ],
    apple: [
      { url: "/favicon.png?v=soft-relief-c", type: "image/png" },
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
