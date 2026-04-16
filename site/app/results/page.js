'use client';

import { useState } from 'react';
import { benchmarkGroups } from '@/lib/catalog-data';

export default function ResultsPage() {
  const [selected, setSelected] = useState(benchmarkGroups[0].key);
  const benchmark = benchmarkGroups.find((item) => item.key === selected) || benchmarkGroups[0];

  return (
    <div className="results-shell">
      <aside className="results-sidebar">
        <p className="sidebar-kicker">Benchmarks</p>
        {benchmarkGroups.map((item) => (
          <button
            key={item.key}
            type="button"
            className={`results-nav-button ${item.key === selected ? 'is-active' : ''}`}
            onClick={() => setSelected(item.key)}
          >
            {item.name}
          </button>
        ))}
      </aside>

      <section className="results-main">
        <p className="eyebrow">Benchmark</p>
        <h1>{benchmark.name}</h1>
        <p className="lede">{benchmark.description}</p>

        <div className="results-table-wrap">
          <table className="results-table">
            <thead>
              <tr>
                <th>Problem</th>
                <th>Formal language</th>
                <th>Symbolic engine</th>
              </tr>
            </thead>
            <tbody>
              {benchmark.rows.map((row) => (
                <tr key={row.id}>
                  <td className="results-problem-id">{row.id}</td>
                  <td><code className="results-fl">{row.fl}</code></td>
                  <td className="results-check">{row.symbolic ? '✓' : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
