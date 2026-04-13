import './globals.css';
import { SiteHeader } from '@/components/site-header';
import { siteMeta } from '@/lib/site-data';

export const metadata = {
  title: siteMeta.title,
  description: siteMeta.description,
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <div className="page-frame">
          <div className="paper-noise" />
          <SiteHeader />
          <main>{children}</main>
        </div>
      </body>
    </html>
  );
}
