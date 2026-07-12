import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'Shelf-School Docs',
  tagline: 'Open-source circulation and cataloging for small school libraries',
  url: 'https://mrueda.github.io',
  baseUrl: '/shelf-school/',
  organizationName: 'mrueda',
  projectName: 'shelf-school',
  onBrokenLinks: 'warn',
  markdown: {
    hooks: {
      onBrokenMarkdownLinks: 'warn',
    },
  },
  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },
  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          routeBasePath: 'docs',
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],
  themes: [
    [
      '@easyops-cn/docusaurus-search-local',
      {
        hashed: true,
        language: ['en'],
        indexDocs: true,
        indexBlog: false,
        docsRouteBasePath: '/docs',
      },
    ],
  ],
  themeConfig: {
    image: 'img/circulation-desk.png',
    colorMode: {
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'Shelf-School',
      logo: {
        alt: 'Shelf-School logo',
        src: 'img/shelf-school-logo.svg',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'userGuide',
          position: 'left',
          label: 'User Guide',
        },
        {
          type: 'docSidebar',
          sidebarId: 'developerGuide',
          position: 'left',
          label: 'Developer Guide',
        },
        {
          href: 'https://github.com/mrueda/shelf-school',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'User Guide',
          items: [
            {label: 'Overview', to: '/docs/overview'},
            {label: 'Quick Start', to: '/docs/getting-started/quickstart'},
            {label: 'Self-Service', to: '/docs/usage/self-service'},
            {label: 'Photo Intake', to: '/docs/usage/photo-intake'},
            {label: 'Troubleshooting', to: '/docs/operations/troubleshooting'},
          ],
        },
        {
          title: 'Developer Guide',
          items: [
            {label: 'Architecture', to: '/docs/technical-details/architecture'},
            {label: 'Photo Identification', to: '/docs/technical-details/photo-identification'},
            {label: 'Testing', to: '/docs/technical-details/testing'},
          ],
        },
        {
          title: 'Project',
          items: [
            {label: 'Repository', href: 'https://github.com/mrueda/shelf-school'},
            {label: 'Roadmap', to: '/docs/about/roadmap'},
            {label: 'License', href: 'https://github.com/mrueda/shelf-school/blob/main/LICENSE'},
          ],
        },
      ],
      copyright: 'Copyright (C) 2026 Manuel Rueda.',
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
