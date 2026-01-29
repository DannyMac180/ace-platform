import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'ACE',
  tagline: 'Playbooks as a Service - Self-improving AI instructions',
  favicon: 'img/favicon.ico',

  // Production URL
  url: 'https://docs.aceagent.io',
  baseUrl: '/',

  // GitHub pages deployment config (not used, but required)
  organizationName: 'DannyMac180',
  projectName: 'ace-platform',

  onBrokenLinks: 'throw',

  markdown: {
    hooks: {
      onBrokenMarkdownLinks: () => 'warn',
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
        },
        blog: false, // Disable blog
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    image: 'img/og-image.png',
    navbar: {
      title: 'ACE',
      logo: {
        alt: 'ACE Logo',
        src: 'img/logo.svg',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'docsSidebar',
          position: 'left',
          label: 'Documentation',
        },
        {
          href: 'https://app.aceagent.io',
          label: 'Dashboard',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'light',
      links: [
        {
          title: 'Documentation',
          items: [
            {
              label: 'Getting Started',
              to: '/docs/getting-started/quick-start',
            },
            {
              label: 'User Guides',
              to: '/docs/user-guides/creating-playbooks',
            },
            {
              label: 'API Reference',
              to: '/docs/api-reference/overview',
            },
          ],
        },
        {
          title: 'Product',
          items: [
            {
              label: 'Dashboard',
              href: 'https://app.aceagent.io',
            },
            {
              label: 'Pricing',
              href: 'https://aceagent.io/pricing',
            },
          ],
        },
              ],
      copyright: `Copyright © ${new Date().getFullYear()} ACE. Built with Docusaurus.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['bash', 'json', 'python', 'yaml', 'toml'],
    },
    colorMode: {
      defaultMode: 'light',
      disableSwitch: true, // Keep light mode only for playing card aesthetic
      respectPrefersColorScheme: false,
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
