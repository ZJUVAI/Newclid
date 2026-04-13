import Link from 'next/link';
import { docsNavigation } from '@/lib/site-data';

export function DocsIndex() {
  return (
    <div className="docs-index-grid">
      {docsNavigation.flatMap((section) =>
        section.items.map((item) => (
          <Link key={item.href} href={item.href} className="index-card">
            <span>{section.title}</span>
            <strong>{item.title}</strong>
            <p>{item.description}</p>
          </Link>
        ))
      )}
    </div>
  );
}
