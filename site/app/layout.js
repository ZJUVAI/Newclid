import './globals.css';
import { SiteHeader } from '@/components/site-header';
import { siteMeta } from '@/lib/site-data';

export const metadata = {
  title: siteMeta.title,
  description: siteMeta.description,
  metadataBase: new URL('https://zjuvai.github.io'),
  openGraph: {
    title: siteMeta.title,
    description: siteMeta.description,
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: siteMeta.title,
    description: siteMeta.description,
  },
  icons: {
    icon: '/icon.svg',
  },
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#site-content">Skip to content</a>
        <div className="page-frame">
          <div className="paper-noise" />
          <SiteHeader />
          <span id="site-content" className="content-anchor" tabIndex="-1" />
          <main>{children}</main>
        </div>
      </body>
    </html>
  );
}
