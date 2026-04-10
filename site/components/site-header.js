import Link from 'next/link';
import { siteMeta } from '@/lib/site-data';

export function SiteHeader() {
  return (
    <header className="site-header">
      <div className="brand-lockup">
        <Link className="brand-mark" href="/">
          GenesisGeo
        </Link>
        <span className="brand-tag">neuro-symbolic geometry theorem proving</span>
      </div>
      <nav className="top-nav" aria-label="Primary">
        <Link href="/docs">Docs</Link>
        <Link href="/results">Results</Link>
        <a href={siteMeta.paperUrl} target="_blank" rel="noreferrer">
          Paper
        </a>
        <a href={siteMeta.repoUrl} target="_blank" rel="noreferrer">
          Code
        </a>
      </nav>
    </header>
  );
}
