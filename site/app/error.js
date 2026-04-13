'use client';

export default function Error({ error, reset }) {
  return (
    <section className="reference-card">
      <p className="eyebrow">Error</p>
      <h1>Something went wrong</h1>
      <p className="lede">{error?.message || 'Unexpected rendering error.'}</p>
      <button className="button" type="button" onClick={() => reset()}>
        Retry
      </button>
    </section>
  );
}
