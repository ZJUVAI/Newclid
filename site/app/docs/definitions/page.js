import fs from 'fs';
import path from 'path';
import definitionEntries from '@/lib/legacy-definitions.json';
import { formatStatement } from '@/lib/format-statement';

function toTitle(slug) {
  return slug.replace(/_/g, ' ');
}

function loadCatalog(dir) {
  return fs
    .readdirSync(dir)
    .filter((file) => file.endsWith('.png'))
    .map((file) => ({
      slug: file.replace(/\.png$/, ''),
      image: `${process.env.NEXT_PUBLIC_BASE_PATH}/images/defs/${file}`,
      fallbackTitle: toTitle(file.replace(/\.png$/, '')),
    }))
    .sort((a, b) => a.fallbackTitle.localeCompare(b.fallbackTitle));
}

function mergeCatalog(catalog, details) {
  const detailMap = new Map(details.map((item) => [item.slug, item]));

  return catalog.map((item) => {
    const detail = detailMap.get(item.slug) ?? {};
    return {
      ...item,
      ...detail,
      title: detail.title ?? item.fallbackTitle,
    };
  });
}

export const metadata = {
  title: 'Definitions',
};

export default function DefinitionsPage() {
  const catalog = mergeCatalog(loadCatalog(path.join(process.cwd(), 'public/images/defs')), definitionEntries);

  return (
    <div>
      <p className="eyebrow">Reference</p>
      <h1>Definitions</h1>
      <p className="lede">
        Construction primitives available in the formal language. Each definition specifies how new geometric objects are
        introduced and what symbolic predicates they entail.
      </p>

      <section className="reference-section">
        <div className="reference-grid reference-grid-dense">
          {catalog.map((item) => (
            <section key={item.slug} className="reference-card">
              <img src={item.image} alt={item.title} />
              <p className="catalog-meta">{item.section ?? 'Definitions'}</p>
              <h3>{item.title}</h3>
              {item.description ? <p>{item.description}</p> : null}
              {item.statement ? (
                <p className="statement-line">
                  <strong>Statement:</strong> <code>{formatStatement(item.statement)}</code>
                </p>
              ) : null}
              {item.construction ? (
                <p className="construction-tag">
                  <strong>Type:</strong> {item.construction}
                </p>
              ) : null}
            </section>
          ))}
        </div>
      </section>
    </div>
  );
}
