import fs from 'fs';
import path from 'path';
import ruleEntries from '@/lib/legacy-rules.json';
import { formatStatement } from '@/lib/format-statement';

function loadCatalog(dir) {
  return fs
    .readdirSync(dir)
    .filter((file) => file.endsWith('.png'))
    .map((file) => {
      const slug = file.replace(/\.png$/, '');
      return {
        slug,
        image: `${process.env.NEXT_PUBLIC_BASE_PATH}/images/rules/${file}`,
        fallbackTitle: slug.toUpperCase(),
      };
    })
    .sort((a, b) => a.slug.localeCompare(b.slug));
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
  title: 'Rules',
};

export default function RulesPage() {
  const catalog = mergeCatalog(loadCatalog(path.join(process.cwd(), 'public/images/rules')), ruleEntries);

  return (
    <div>
      <p className="eyebrow">Reference</p>
      <h1>Rules</h1>
      <p className="lede">
        Inference rules available to the symbolic deduction engine. Each rule specifies the geometric conditions under
        which new facts can be derived.
      </p>

      <section className="reference-section">
        <div className="reference-grid reference-grid-dense">
          {catalog.map((rule) => (
            <section key={rule.slug} className="reference-card">
              <img src={rule.image} alt={rule.title} />
              <p className="catalog-meta">{rule.section ?? 'Rules'}</p>
              <h3>{rule.title}</h3>
              {rule.statement ? (
                <p className="statement-line">
                  <strong>Statement:</strong> <code>{formatStatement(rule.statement)}</code>
                </p>
              ) : null}
              {rule.description ? <p>{rule.description}</p> : null}
            </section>
          ))}
        </div>
      </section>
    </div>
  );
}
