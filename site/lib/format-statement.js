/**
 * Convert the legacy text-based math notation to Unicode-rich readable text.
 * The statements use words like "perpendicular", "parallel", "angle", etc.
 */
export function formatStatement(text) {
  if (!text) return '';
  return text
    .replace(/perpendicular/g, '\u22A5')
    .replace(/parallel/g, '\u2225')
    .replace(/=>/g, '\u27F9')
    .replace(/\bangle\b/g, '\u2220')
    .replace(/\bsimilar\b/g, '\u223C')
    .replace(/\bcongruent\b/g, '\u2245')
    .replace(/\^deg\b/g, '\u00B0');
}
