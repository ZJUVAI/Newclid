import { DocsSidebar } from '@/components/docs-sidebar';

export default function DocsLayout({ children }) {
  return (
    <div className="docs-shell">
      <DocsSidebar />
      <article className="docs-content">{children}</article>
    </div>
  );
}
