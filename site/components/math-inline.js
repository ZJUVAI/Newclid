'use client';

import { useEffect, useRef } from 'react';

export function MathInline({ tex }) {
  const ref = useRef(null);

  useEffect(() => {
    if (!ref.current || !tex) return;
    import('katex').then((katex) => {
      katex.default.render(tex, ref.current, {
        throwOnError: false,
        displayMode: false,
      });
    });
  }, [tex]);

  return <span ref={ref} className="math-inline" />;
}

export function MathBlock({ tex }) {
  const ref = useRef(null);

  useEffect(() => {
    if (!ref.current || !tex) return;
    import('katex').then((katex) => {
      katex.default.render(tex, ref.current, {
        throwOnError: false,
        displayMode: true,
      });
    });
  }, [tex]);

  return <span ref={ref} className="math-block" />;
}
