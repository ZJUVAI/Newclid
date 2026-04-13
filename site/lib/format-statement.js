/**
 * Convert the legacy text-based math notation to Unicode-rich readable text.
 * The statements use words like "perpendicular", "parallel", "angle", etc.
 */
export function formatStatement(text) {
  if (!text) return '';
  return text
    .replace(/perpendicular/g, '⊥')
    .replace(/parallel/g, '∥')
    .replace(/\bnon-collinear\b/g, 'non-collinear')
    .replace(/\bcollinear\b/g, 'collinear')
    .replace(/\bmidpoint of\b/g, 'midpoint of')
    .replace(/\btimes\b/g, '×')
    .replace(/\bon a circle\b/g, 'on circle')
    .replace(/\bcenter of\b/g, 'center of')
    .replace(/=>/g, '⟹')
    .replace(/\bangle\b/g, '∠')
    .replace(/\bsimilar\b/g, '∼')
    .replace(/\bcongruent\b/g, '≅')
    .replace(/\^deg\b/g, '°')
    .replace(/\bsim\b/g, '∼');
}
