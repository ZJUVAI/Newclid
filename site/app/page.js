import Link from 'next/link';
import { homeCards, siteMeta, benchmarkResults } from '@/lib/site-data';

export default function HomePage() {
  return (
    <div className="home-shell">
      <section className="landing-hero">
        <p className="eyebrow">Neuro-symbolic geometry theorem proving</p>
        <h1>GenesisGeo</h1>
        <p className="landing-copy">
          A project on olympiad-level geometry that brings together symbolic deduction, synthetic data, multimodal
          reasoning, and proof-oriented formal language.
        </p>
        <div className="hero-actions">
          <Link href="/docs" className="button button-primary">
            Explore Docs
          </Link>
          <Link href="/results" className="button">
            View Results
          </Link>
          <a className="button" href={siteMeta.paperUrl} target="_blank" rel="noreferrer">
            Read Paper
          </a>
        </div>
      </section>

      <section className="benchmark-strip">
        {benchmarkResults.map((b) => (
          <div key={b.label} className="benchmark-item">
            <span>{b.label}</span>
            <strong>{b.value}</strong>
            <p>{b.note}</p>
          </div>
        ))}
      </section>

      <section className="card-grid-section card-grid-spaced">
        {homeCards.map((card) => (
          <Link href={card.href} key={card.href} className="home-card">
            <span>{card.eyebrow}</span>
            <strong>{card.title}</strong>
            <p>{card.text}</p>
          </Link>
        ))}
      </section>
    </div>
  );
}
