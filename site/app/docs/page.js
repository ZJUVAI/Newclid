import { DocsIndex } from '@/components/docs-index';

export const metadata = {
  title: 'GenesisGeo Docs',
};

export default function DocsPage() {
  return (
    <div>
      <p className="eyebrow">Documentation index</p>
      <h1>Docs</h1>
      <p className="lede">
        Conceptual foundations, formal language specification, and reference material for the GenesisGeo system.
        Performance reporting lives in the top-level Results area.
      </p>
      <DocsIndex />
    </div>
  );
}
