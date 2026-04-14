'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { siteMeta } from '@/lib/site-data';

const navLinks = [
  { href: '/docs', label: 'Docs' },
  { href: '/results', label: 'Results' },
];

export function SiteHeader() {
  const pathname = usePathname();

  return (
    <header className="site-header">
      <div className="brand-lockup">
        <Link className="brand-mark" href="/">
          GenesisGeo
        </Link>
        <span className="brand-tag">neuro-symbolic geometry theorem proving</span>
      </div>
      <nav className="top-nav" aria-label="Primary">
        {navLinks.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className={pathname.startsWith(link.href) ? 'is-active' : ''}
          >
            {link.label}
          </Link>
        ))}
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
