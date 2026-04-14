export const siteMeta = {
  title: 'GenesisGeo',
  description:
    'GenesisGeo is a neuro-symbolic geometry theorem proving project that combines symbolic deduction, synthetic data, and multimodal reasoning.',
  paperUrl: 'https://arxiv.org/abs/2509.21896',
  repoUrl: 'https://github.com/ZJUVAI/GenesisGeo',
  datasetUrl: 'https://huggingface.co/datasets/ZJUVAI/GenesisGeo',
  modelUrl: 'https://huggingface.co/ZJUVAI/GenesisGeo',
};

export const benchmarkResults = [
  { label: 'IMO-AG-30', value: '29/30', note: 'Olympiad benchmark' },
  { label: 'IMO-95', value: '63/95', note: 'Extended IMO set' },
  { label: 'HAGeo-409', value: '278/409', note: 'Large-scale evaluation' },
];

export const docsNavigation = [
  {
    title: 'Core Concepts',
    items: [
      { href: '/docs/overview', title: 'Overview', description: 'Project framing and motivation.' },
      { href: '/docs/visual-geometry-reasoning', title: 'Visual Geometry Reasoning', description: 'Why multimodal geometry is difficult and useful.' },
      { href: '/docs/system', title: 'System', description: 'How neural guidance and symbolic verification fit together.' },
      { href: '/docs/data-generation', title: 'Data Generation', description: 'Synthetic supervision, proof traces, and scale.' },
    ],
  },
  {
    title: 'Formal Language',
    items: [
      { href: '/docs/problem-language', title: 'Problem Language', description: 'How problems are written and solved formally.' },
      { href: '/docs/default-knowledge', title: 'Default Knowledge', description: 'What lives in definitions and rules files.' },
      { href: '/docs/definitions', title: 'Definitions', description: 'Detailed construction vocabulary with legacy diagrams.' },
      { href: '/docs/rules', title: 'Rules', description: 'Detailed rule gallery with formal statements and figures.' },
    ],
  },
  {
    title: 'Collections',
    items: [
      { href: '/docs/problem-collections', title: 'Problem Collections', description: 'Benchmark sets and evaluation coverage.' },
    ],
  },
];

export const homeCards = [
  {
    href: '/docs/definitions',
    eyebrow: 'Vocabulary',
    title: 'Definitions',
    text: 'Construction primitives, attached predicates, and diagrams that form the formal problem language.',
  },
  {
    href: '/docs/rules',
    eyebrow: 'Deduction',
    title: 'Rules',
    text: 'Geometry rules that drive proof-state expansion, with formal statements and figures.',
  },
  {
    href: '/docs/system',
    eyebrow: 'Architecture',
    title: 'System',
    text: 'How neural auxiliary construction proposals feed into symbolic deduction and proof writing.',
  },
  {
    href: '/results',
    eyebrow: 'Benchmarks',
    title: 'Results',
    text: 'Per-benchmark problem listings with solve status and solution traces.',
  },
];
