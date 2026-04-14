import createMDX from '@next/mdx';

const repoName = process.env.GITHUB_REPOSITORY?.split('/')[1] || 'GenesisGeo';
const isGithubPages = process.env.GITHUB_ACTIONS === 'true';
const basePath = isGithubPages ? `/${repoName}` : '';

const nextConfig = {
  output: 'export',
  reactStrictMode: true,
  images: {
    unoptimized: true,
  },
  pageExtensions: ['js', 'jsx', 'mdx'],
  basePath,
  assetPrefix: isGithubPages ? `/${repoName}/` : '',
  env: {
    NEXT_PUBLIC_BASE_PATH: basePath,
  },
};

const withMDX = createMDX({
  extension: /\.(md|mdx)$/,
});

export default withMDX(nextConfig);
