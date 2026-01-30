import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

// Environment-specific URLs (set via build args)
const APP_URL = process.env.APP_URL || 'https://app.aceagent.io';
const API_URL = process.env.API_URL || 'https://aceagent.io';

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

  customFields: {
    appUrl: APP_URL,
    apiUrl: API_URL,
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
          href: APP_URL,
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
              label: 'MCP Integration',
              to: '/docs/developer-guides/mcp-integration/overview',
            },
          ],
        },
        {
          title: 'Product',
          items: [
            {
              label: 'Dashboard',
              href: APP_URL,
            },
            {
              label: 'Pricing',
              href: `${APP_URL}/pricing`,
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
