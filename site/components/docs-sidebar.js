'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { docsNavigation } from '@/lib/site-data';

export function DocsSidebar() {
  const pathname = usePathname();

  return (
    <aside className="docs-sidebar">
      <p className="sidebar-kicker">Documentation</p>
      {docsNavigation.map((section) => (
        <div key={section.title} className="sidebar-section">
          <h2>{section.title}</h2>
          <ul>
            {section.items.map((item) => (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={pathname === item.href ? 'is-active' : ''}
                >
                  {item.title}
                </Link>
                <p>{item.description}</p>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </aside>
  );
}
