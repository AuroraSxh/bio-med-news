import type { Metadata, Viewport } from "next";
import "./globals.css";

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export const metadata: Metadata = {
  title: "Biomed / Cell Therapy Daily Intelligence",
  description: "Daily biomedicine and cell therapy news intelligence dashboard.",
  openGraph: {
    title: "Biomed / Cell Therapy Daily Intelligence",
    description:
      "AI-powered daily biomedicine and cell therapy news dashboard with automated classification and summarization.",
    type: "website",
    siteName: "Biomed Daily",
  },
  twitter: {
    card: "summary",
    title: "Biomed / Cell Therapy Daily Intelligence",
    description: "AI-powered daily biomedicine and cell therapy news dashboard.",
  },
  icons: {
    icon: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html className="font-text antialiased" lang="en" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var d=document.documentElement;var t=localStorage.getItem("theme");if(t==="dark"||(!t&&matchMedia("(prefers-color-scheme:dark)").matches)){d.classList.add("dark")}else{d.classList.remove("dark")}}catch(e){}})()`,
          }}
        />
      </head>
      <body className="font-text bg-apple-gray text-apple-text dark:bg-apple-black dark:text-white">
        {children}
      </body>
    </html>
  );
}
