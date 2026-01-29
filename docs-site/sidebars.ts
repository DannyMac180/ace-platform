import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docsSidebar: [
    'intro',
    {
      type: 'category',
      label: 'Getting Started',
      items: [
        'getting-started/quick-start',
        'getting-started/core-concepts',
        'getting-started/creating-account',
      ],
    },
    {
      type: 'category',
      label: 'User Guides',
      items: [
        'user-guides/creating-playbooks',
        'user-guides/understanding-evolution',
        'user-guides/managing-api-keys',
        'user-guides/billing-subscriptions',
      ],
    },
    {
      type: 'category',
      label: 'Developer Guides',
      items: [
        {
          type: 'category',
          label: 'MCP Integration',
          items: [
            'developer-guides/mcp-integration/overview',
            'developer-guides/mcp-integration/claude-desktop',
            'developer-guides/mcp-integration/claude-code',
            'developer-guides/mcp-integration/custom-agents',
          ],
        },
        'developer-guides/authentication',
        'developer-guides/recording-outcomes',
      ],
    },
    {
      type: 'category',
      label: 'API Reference',
      items: [
        'api-reference/overview',
        'api-reference/authentication',
        'api-reference/playbooks',
        'api-reference/outcomes',
        'api-reference/evolution',
        'api-reference/usage-billing',
      ],
    },
  ],
};

export default sidebars;
