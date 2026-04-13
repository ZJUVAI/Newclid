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
        The docs now carry the conceptual and formal material from the old documentation set: system framing,
        multimodal geometry motivation, problem language, default knowledge, detailed definitions, detailed rules,
        and benchmark collection context. Performance reporting now lives in the top-level Results area.
      </p>
      <DocsIndex />
    </div>
  );
}
