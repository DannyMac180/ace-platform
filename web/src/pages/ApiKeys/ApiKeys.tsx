import { useState, useEffect } from 'react';
import { AxiosError } from 'axios';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { apiKeysApi } from '../../utils/api';
import { useAuth } from '../../contexts/AuthContext';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Input } from '../../components/ui/Input';
import { SubscriptionGate } from '../../components/SubscriptionGate';
import {
  Plus,
  Key,
  Trash2,
  Copy,
  Check,
  Clock,
  AlertCircle,
  Shield,
  Terminal,
  Info,
  Mail,
  BookOpen,
  FileText,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import type { ApiKey, ApiKeyCreate, ApiKeyCreateResponse } from '../../types';
import styles from './ApiKeys.module.css';

const AVAILABLE_SCOPES = [
  { id: 'playbooks:read', label: 'Read Playbooks', description: 'View playbook content' },
  { id: 'playbooks:write', label: 'Write Playbooks', description: 'Create and update playbooks' },
  { id: 'outcomes:write', label: 'Record Outcomes', description: 'Submit task outcomes' },
  { id: 'evolution:read', label: 'Read Evolution', description: 'View evolution status' },
  { id: 'evolution:write', label: 'Trigger Evolution', description: 'Manually trigger evolution' },
];

const RECOMMENDED_INSTRUCTIONS_TEMPLATE = `## ACE Playbooks

This project uses ACE for self-improving AI instructions.
The ACE MCP server is configured and available.

### Workflow

For each new task (or when task intent changes materially):

1. **Discover relevant playbooks first (semantic search)**
   - Summarize the request as a concise task description
   - Prefer \`find_playbook(task_description="<task description>")\` to get the best match
   - If needed, use \`list_playbooks(task="<task description>")\` to review ranked alternatives
   - If no relevant playbook is found, continue normally and do not force playbook usage

2. **Load playbook instructions before doing the task (Generator step)**
   - Use \`get_playbook(playbook_id="<selected id>")\` for the selected playbook
   - Read the playbook content before starting execution
   - Apply those instructions during planning and implementation

3. **Execute the task using the playbook guidance**
   - Use one **primary** playbook for execution and outcome attribution
   - If multiple playbooks are relevant, keep additional playbooks as supporting context only

4. **Record outcomes automatically after task completion**
   - Call \`record_outcome\` exactly once per completed, playbook-guided task
   - Include all relevant fields:
     - \`playbook_id\`: ID of the primary playbook used
     - \`task_description\`: What was attempted, including scope and deliverable summary
     - \`outcome\`: \`success\`, \`partial\`, or \`failure\`
     - \`notes\`: What worked, what failed, key decisions, and blockers
     - \`reasoning_trace\`: Concise summary of reasoning and tradeoffs
   - If recording fails (permissions, validation, rate limit), report the error and continue helping the user

5. **Check for evolution when applicable**
   - If you manually call \`trigger_evolution\` and receive a Job ID, call \`get_evolution_status(job_id=...)\`
   - Do not call \`get_evolution_status\` without a known Job ID`;

export function ApiKeys() {
  const { user, refreshUser } = useAuth();
  const navigate = useNavigate();
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showVerificationModal, setShowVerificationModal] = useState(false);
  const [showSetupDocsModal, setShowSetupDocsModal] = useState(false);
  const [newKey, setNewKey] = useState<ApiKeyCreateResponse | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);

  const queryClient = useQueryClient();
  const isEmailVerified = user?.email_verified ?? false;
  const hasPaidAccess =
    user?.subscription_status === 'active' &&
    !!user.subscription_tier &&
    user.subscription_tier !== 'free';
  const hasUsedTrial = user?.has_used_trial ?? false;

  // Refresh user data on mount to get latest verification status
  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const handleCreateClick = () => {
    if (!isEmailVerified) {
      setShowVerificationModal(true);
    } else {
      setShowCreateModal(true);
    }
  };

  const { data: apiKeys, isLoading, error } = useQuery({
    queryKey: ['api-keys', isEmailVerified, hasPaidAccess],
    queryFn: apiKeysApi.list,
    enabled: isEmailVerified && hasPaidAccess,
  });

  const apiKeyList = apiKeys ?? [];
  const errorStatus = error instanceof AxiosError ? error.response?.status : undefined;
  const shouldShowSubscriptionState = !hasPaidAccess || errorStatus === 402;

  const createMutation = useMutation({
    mutationFn: (data: ApiKeyCreate) => apiKeysApi.create(data),
    onSuccess: (key) => {
      queryClient.invalidateQueries({ queryKey: ['api-keys'] });
      setNewKey(key);
      setShowCreateModal(false);
      setMutationError(null);
    },
    onError: (err: unknown) => {
      // Extract error message from API response
      let message = 'Failed to create API key. Please try again.';
      if (err && typeof err === 'object' && 'response' in err) {
        const response = (err as { response?: { data?: { detail?: string; error?: { message?: string } } } }).response;
        message = response?.data?.error?.message || response?.data?.detail || message;
      }
      setMutationError(message);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (keyId: string) => apiKeysApi.delete(keyId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api-keys'] });
      setMutationError(null);
    },
    onError: () => {
      setMutationError('Failed to delete API key. Please try again.');
    },
  });

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.headerContent}>
          <h1>API Keys</h1>
          <p>Manage API keys for MCP integration and programmatic access</p>
        </div>
        <SubscriptionGate featureName="API Keys">
          <Button icon={<Plus size={18} />} onClick={handleCreateClick}>
            Create API Key
          </Button>
        </SubscriptionGate>
      </div>

      {/* Warning Banner */}
      <div className={styles.warning}>
        <Shield size={20} />
        <div>
          <strong>Keep your API keys secure</strong>
          <p>API keys provide access to your account. Never share them or commit them to version control.</p>
        </div>
      </div>

      {/* Email Verification Required Banner */}
      {!isEmailVerified && (
        <div className={styles.verificationBanner}>
          <Mail size={20} />
          <div>
            <strong>Email verification required</strong>
            <p>You must verify your email before creating API keys. <Link to="/settings">Go to Settings</Link> to resend the verification email.</p>
          </div>
        </div>
      )}

      {/* Mutation Error */}
      {mutationError && (
        <div className={styles.error}>
          <AlertCircle size={20} />
          <span>{mutationError}</span>
          <button
            className={styles.dismissError}
            onClick={() => setMutationError(null)}
            aria-label="Dismiss error"
          >
            &times;
          </button>
        </div>
      )}

      {/* API Keys List */}
      {isLoading ? (
        <div className={styles.loading}>
          <div className={styles.spinner} />
          <span>Loading API keys...</span>
        </div>
      ) : shouldShowSubscriptionState ? (
        <SubscriptionRequiredState
          hasUsedTrial={hasUsedTrial}
          onUpgradeClick={() => navigate('/pricing')}
        />
      ) : error ? (
        <div className={styles.error}>
          <AlertCircle size={24} />
          <span>Failed to load API keys</span>
        </div>
      ) : apiKeyList.length === 0 ? (
        <EmptyState onCreateClick={handleCreateClick} />
      ) : (
        <div className={styles.keysList}>
          {apiKeyList.map((key) => (
            <ApiKeyCard
              key={key.id}
              apiKey={key}
              onDelete={() => deleteMutation.mutate(key.id)}
              onShowSetupDocs={() => setShowSetupDocsModal(true)}
              isDeleting={deleteMutation.isPending}
            />
          ))}
        </div>
      )}

      {/* Create Modal */}
      {showCreateModal && (
        <CreateKeyModal
          onClose={() => setShowCreateModal(false)}
          onCreate={(data) => createMutation.mutate(data)}
          isLoading={createMutation.isPending}
        />
      )}

      {/* New Key Display Modal */}
      {newKey && (
        <NewKeyModal apiKey={newKey} onClose={() => setNewKey(null)} />
      )}

      {/* Verification Required Modal */}
      {showVerificationModal && (
        <VerificationRequiredModal onClose={() => setShowVerificationModal(false)} />
      )}

      {/* Setup Documentation Modal */}
      {showSetupDocsModal && (
        <SetupDocsModal onClose={() => setShowSetupDocsModal(false)} />
      )}
    </div>
  );
}

function SubscriptionRequiredState({
  hasUsedTrial,
  onUpgradeClick,
}: {
  hasUsedTrial: boolean;
  onUpgradeClick: () => void;
}) {
  return (
    <div className={styles.emptyState}>
      <div className={styles.emptyIcon}>
        <Key size={48} />
      </div>
      <h2>{hasUsedTrial ? 'Upgrade to Access API Keys' : 'Start Your Free Trial'}</h2>
      <p>
        {hasUsedTrial
          ? 'Your trial has ended. Upgrade your plan to create and manage API keys.'
          : 'Start your free trial to create and manage API keys.'}
      </p>
      <Button onClick={onUpgradeClick}>{hasUsedTrial ? 'View Plans' : 'Start Free Trial'}</Button>
    </div>
  );
}

interface ApiKeyCardProps {
  apiKey: ApiKey;
  onDelete: () => void;
  onShowSetupDocs: () => void;
  isDeleting: boolean;
}

function ApiKeyCard({ apiKey, onDelete, onShowSetupDocs, isDeleting }: ApiKeyCardProps) {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  return (
    <Card variant="default" className={styles.keyCard}>
      <div className={styles.keyHeader}>
        <div className={styles.keyIcon}>
          <Key size={20} />
        </div>
        <div className={styles.keyInfo}>
          <h3>{apiKey.name}</h3>
          <code className={styles.keyPreview}>{apiKey.key_prefix}</code>
        </div>
        <div className={styles.keyActions}>
          <button
            className={styles.setupButton}
            onClick={onShowSetupDocs}
            title="View setup instructions"
            aria-label="View setup instructions"
          >
            <BookOpen size={18} />
          </button>
          <button
            className={styles.deleteButton}
            onClick={() => setShowDeleteConfirm(true)}
            disabled={isDeleting}
            aria-label={`Delete API key ${apiKey.name}`}
          >
            <Trash2 size={18} />
          </button>
        </div>
      </div>

      <div className={styles.keyScopes}>
        {apiKey.scopes.map((scope) => (
          <span key={scope} className={styles.scopeBadge}>
            {scope}
          </span>
        ))}
      </div>

      <div className={styles.keyMeta}>
        <div className={styles.metaItem}>
          <Clock size={14} />
          <span>Created {new Date(apiKey.created_at).toLocaleDateString()}</span>
        </div>
        {apiKey.last_used_at && (
          <div className={styles.metaItem}>
            <span>Last used {new Date(apiKey.last_used_at).toLocaleDateString()}</span>
          </div>
        )}
      </div>

      {/* Delete Confirmation */}
      {showDeleteConfirm && (
        <div className={styles.deleteConfirm}>
          <p>Delete this API key?</p>
          <div className={styles.confirmActions}>
            <Button variant="ghost" size="sm" onClick={() => setShowDeleteConfirm(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              size="sm"
              onClick={() => {
                onDelete();
                setShowDeleteConfirm(false);
              }}
              isLoading={isDeleting}
            >
              Delete
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}

function EmptyState({ onCreateClick }: { onCreateClick: () => void }) {
  return (
    <div className={styles.emptyState}>
      <div className={styles.emptyIcon}>
        <Key size={48} />
      </div>
      <h2>No API keys yet</h2>
      <p>Create an API key to connect your playbooks with Claude or other tools</p>
      <SubscriptionGate featureName="API Keys">
        <Button icon={<Plus size={18} />} onClick={onCreateClick}>
          Create your first API key
        </Button>
      </SubscriptionGate>
    </div>
  );
}

interface CreateModalProps {
  onClose: () => void;
  onCreate: (data: ApiKeyCreate) => void;
  isLoading: boolean;
}

function CreateKeyModal({ onClose, onCreate, isLoading }: CreateModalProps) {
  const [name, setName] = useState('');
  const [selectedScopes, setSelectedScopes] = useState<Set<string>>(new Set());

  const toggleScope = (scopeId: string) => {
    setSelectedScopes((prev) => {
      const next = new Set(prev);
      if (next.has(scopeId)) {
        next.delete(scopeId);
      } else {
        next.add(scopeId);
      }
      return next;
    });
  };

  const toggleAllScopes = () => {
    if (selectedScopes.size === AVAILABLE_SCOPES.length) {
      setSelectedScopes(new Set());
    } else {
      setSelectedScopes(new Set(AVAILABLE_SCOPES.map((s) => s.id)));
    }
  };

  const allSelected = selectedScopes.size === AVAILABLE_SCOPES.length;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onCreate({
      name,
      scopes: Array.from(selectedScopes),
    });
  };

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <h2>Create API Key</h2>
        <form onSubmit={handleSubmit} className={styles.modalForm}>
          <Input
            label="Key Name"
            placeholder="e.g., Claude Desktop, Development"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />

          <div className={styles.scopesSection}>
            <label className={styles.scopesLabel}>Permissions</label>
            <label className={styles.selectAllOption}>
              <input
                type="checkbox"
                checked={allSelected}
                onChange={toggleAllScopes}
                className={styles.scopeCheckbox}
              />
              <span className={styles.selectAllLabel}>Select All</span>
            </label>
            <div className={styles.scopesGrid}>
              {AVAILABLE_SCOPES.map((scope) => (
                <label key={scope.id} className={styles.scopeOption}>
                  <input
                    type="checkbox"
                    checked={selectedScopes.has(scope.id)}
                    onChange={() => toggleScope(scope.id)}
                    className={styles.scopeCheckbox}
                  />
                  <div className={styles.scopeContent}>
                    <span className={styles.scopeName}>{scope.label}</span>
                    <span className={styles.scopeDescription}>{scope.description}</span>
                  </div>
                </label>
              ))}
            </div>
          </div>

          <div className={styles.modalActions}>
            <Button variant="ghost" type="button" onClick={onClose}>
              Cancel
            </Button>
            <Button
              type="submit"
              isLoading={isLoading}
              disabled={!name || selectedScopes.size === 0}
            >
              Create Key
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function NewKeyModal({ apiKey, onClose }: { apiKey: ApiKeyCreateResponse; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const [setupTab, setSetupTab] = useState<'prompt' | 'claude' | 'headers'>('prompt');
  const [setupCopied, setSetupCopied] = useState(false);
  const [templateCopied, setTemplateCopied] = useState(false);
  const [templateExpanded, setTemplateExpanded] = useState(false);

  const copyToClipboard = async () => {
    await navigator.clipboard.writeText(apiKey.key);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const mcpServerUrl = 'https://aceagent.io/mcp';

  const promptInstructions = `Set up the ACE Platform MCP server with these settings:
- Server Name: ace
- Server URL: ${mcpServerUrl}
- API Key Header: X-API-Key: ${apiKey.key}

For Claude Code, add this to your ~/.claude.json under the "mcpServers" key for your project.`;

  const claudeCommand = `# Add to ~/.claude.json in your project's mcpServers config:
{
  "ace": {
    "type": "http",
    "url": "${mcpServerUrl}",
    "headers": {
      "X-API-Key": "${apiKey.key}"
    }
  }
}`;

  const headersConfig = JSON.stringify({
    "ace": {
      "type": "http",
      "url": mcpServerUrl,
      "headers": {
        "X-API-Key": apiKey.key
      }
    }
  }, null, 2);

  const getSetupContent = () => {
    switch (setupTab) {
      case 'prompt':
        return promptInstructions;
      case 'claude':
        return claudeCommand;
      case 'headers':
        return headersConfig;
    }
  };

  const copySetupContent = async () => {
    await navigator.clipboard.writeText(getSetupContent());
    setSetupCopied(true);
    setTimeout(() => setSetupCopied(false), 2000);
  };

  return (
    <div className={styles.modalOverlay}>
      <div className={styles.modal}>
        <div className={styles.successHeader}>
          <div className={styles.successIcon}>
            <Check size={24} />
          </div>
          <h2>API Key Created</h2>
        </div>
        <p className={styles.successMessage}>
          Copy your API key now. You won't be able to see it again!
        </p>

        <div className={styles.keyDisplay}>
          <code>{apiKey.key}</code>
          <button className={styles.copyButton} onClick={copyToClipboard}>
            {copied ? <Check size={18} /> : <Copy size={18} />}
          </button>
        </div>

        <div className={styles.keyDetails}>
          <p><strong>Name:</strong> {apiKey.name}</p>
          <p><strong>Key Prefix:</strong> {apiKey.key_prefix}</p>
          <p><strong>Scopes:</strong> {apiKey.scopes.join(', ')}</p>
        </div>

        {/* Setup Instructions */}
        <div className={styles.setupSection}>
          <h3>
            <Terminal size={18} />
            Set up your coding agent
          </h3>

          <div className={styles.setupTabs}>
            <button
              className={`${styles.setupTab} ${setupTab === 'prompt' ? styles.active : ''}`}
              onClick={() => setSetupTab('prompt')}
            >
              Any Agent
            </button>
            <button
              className={`${styles.setupTab} ${setupTab === 'claude' ? styles.active : ''}`}
              onClick={() => setSetupTab('claude')}
            >
              Claude Code
            </button>
            <button
              className={`${styles.setupTab} ${setupTab === 'headers' ? styles.active : ''}`}
              onClick={() => setSetupTab('headers')}
            >
              JSON Config
            </button>
          </div>

          <div className={styles.setupContent}>
            {setupTab === 'prompt' && (
              <p className={styles.setupInstructions}>
                Copy and paste this into your AI coding assistant:
              </p>
            )}
            {setupTab === 'claude' && (
              <p className={styles.setupInstructions}>
                Add this to your <code>~/.claude.json</code> in your project's config:
              </p>
            )}
            {setupTab === 'headers' && (
              <p className={styles.setupInstructions}>
                Add this to your MCP client configuration:
              </p>
            )}

            <div className={styles.setupCodeBlock}>
              <pre>{getSetupContent()}</pre>
              <button className={styles.copyButton} onClick={copySetupContent}>
                {setupCopied ? <Check size={18} /> : <Copy size={18} />}
              </button>
            </div>

            <div className={styles.setupNote}>
              <Info size={14} />
              <span>
                The MCP server lets your coding agent read playbooks, record outcomes, and trigger evolution automatically.
              </span>
            </div>
            <div className={styles.setupNote}>
              <Info size={14} />
              <span>
                Legacy SSE endpoint compatibility remains available at <code>https://aceagent.io/mcp/sse</code> through May 22, 2026.
              </span>
            </div>
          </div>
        </div>

        {/* Recommended Instructions Template */}
        <div className={styles.instructionsTemplateSection}>
          <button
            className={styles.instructionsTemplateToggle}
            onClick={() => setTemplateExpanded(!templateExpanded)}
          >
            <FileText size={18} />
            <div className={styles.instructionsTemplateToggleText}>
              <strong>Recommended: Add agent instructions</strong>
              <span>Copy the instructions template into your CLAUDE.md, AGENTS.md, or custom instructions</span>
            </div>
            {templateExpanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
          </button>

          {templateExpanded && (
            <div className={styles.instructionsTemplateContent}>
              <p className={styles.instructionsTemplateDescription}>
                This template tells your AI agent how to discover, use, and improve your playbooks automatically.
                Paste it into your project's instructions file:
              </p>
              <div className={styles.instructionsTemplateTargets}>
                <span className={styles.targetBadge}>CLAUDE.md</span>
                <span className={styles.targetBadge}>AGENTS.md</span>
                <span className={styles.targetBadge}>Custom Instructions</span>
                <span className={styles.targetBadge}>System Prompt</span>
              </div>
              <div className={styles.setupCodeBlock}>
                <pre>{RECOMMENDED_INSTRUCTIONS_TEMPLATE}</pre>
                <button
                  className={styles.copyButton}
                  onClick={async () => {
                    await navigator.clipboard.writeText(RECOMMENDED_INSTRUCTIONS_TEMPLATE);
                    setTemplateCopied(true);
                    setTimeout(() => setTemplateCopied(false), 2000);
                  }}
                >
                  {templateCopied ? <Check size={18} /> : <Copy size={18} />}
                </button>
              </div>
              <div className={styles.setupNote}>
                <Info size={14} />
                <span>
                  Without these instructions, your agent won't know to look up playbooks or record outcomes. This is what closes the feedback loop for self-improving playbooks.
                </span>
              </div>
            </div>
          )}
        </div>

        <Button onClick={onClose} className={styles.doneButton}>
          Done
        </Button>
      </div>
    </div>
  );
}

function VerificationRequiredModal({ onClose }: { onClose: () => void }) {
  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.verificationModalHeader}>
          <div className={styles.verificationModalIcon}>
            <Mail size={24} />
          </div>
          <h2>Email Verification Required</h2>
        </div>
        <p className={styles.verificationModalMessage}>
          You need to verify your email address before you can create API keys.
          This helps us keep your account secure.
        </p>
        <div className={styles.verificationModalActions}>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Link to="/settings">
            <Button>
              Go to Settings
            </Button>
          </Link>
        </div>
      </div>
    </div>
  );
}

function SetupDocsModal({ onClose }: { onClose: () => void }) {
  const [setupTab, setSetupTab] = useState<'prompt' | 'claude' | 'headers'>('prompt');
  const [setupCopied, setSetupCopied] = useState(false);
  const [templateCopied, setTemplateCopied] = useState(false);
  const [templateExpanded, setTemplateExpanded] = useState(false);

  const mcpServerUrl = 'https://aceagent.io/mcp';
  const keyPlaceholder = '<YOUR_API_KEY>';

  const promptInstructions = `Set up the ACE Platform MCP server with these settings:
- Server Name: ace
- Server URL: ${mcpServerUrl}
- API Key Header: X-API-Key: ${keyPlaceholder}

For Claude Code, add this to your ~/.claude.json under the "mcpServers" key for your project.`;

  const claudeCommand = `# Add to ~/.claude.json in your project's mcpServers config:
{
  "ace": {
    "type": "http",
    "url": "${mcpServerUrl}",
    "headers": {
      "X-API-Key": "${keyPlaceholder}"
    }
  }
}`;

  const headersConfig = JSON.stringify({
    "ace": {
      "type": "http",
      "url": mcpServerUrl,
      "headers": {
        "X-API-Key": keyPlaceholder
      }
    }
  }, null, 2);

  const getSetupContent = () => {
    switch (setupTab) {
      case 'prompt':
        return promptInstructions;
      case 'claude':
        return claudeCommand;
      case 'headers':
        return headersConfig;
    }
  };

  const copySetupContent = async () => {
    await navigator.clipboard.writeText(getSetupContent());
    setSetupCopied(true);
    setTimeout(() => setSetupCopied(false), 2000);
  };

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.setupDocsHeader}>
          <div className={styles.setupDocsIcon}>
            <BookOpen size={24} />
          </div>
          <h2>MCP Setup Guide</h2>
        </div>
        <p className={styles.setupDocsMessage}>
          Connect your AI coding assistant to ACE Platform using the Model Context Protocol (MCP).
        </p>

        {/* Setup Instructions */}
        <div className={styles.setupSectionStandalone}>
          <div className={styles.setupTabs}>
            <button
              className={`${styles.setupTab} ${setupTab === 'prompt' ? styles.active : ''}`}
              onClick={() => setSetupTab('prompt')}
            >
              Any Agent
            </button>
            <button
              className={`${styles.setupTab} ${setupTab === 'claude' ? styles.active : ''}`}
              onClick={() => setSetupTab('claude')}
            >
              Claude Code
            </button>
            <button
              className={`${styles.setupTab} ${setupTab === 'headers' ? styles.active : ''}`}
              onClick={() => setSetupTab('headers')}
            >
              JSON Config
            </button>
          </div>

          <div className={styles.setupContent}>
            {setupTab === 'prompt' && (
              <p className={styles.setupInstructions}>
                Copy and paste this into your AI coding assistant:
              </p>
            )}
            {setupTab === 'claude' && (
              <p className={styles.setupInstructions}>
                Add this to your <code>~/.claude.json</code> in your project's config:
              </p>
            )}
            {setupTab === 'headers' && (
              <p className={styles.setupInstructions}>
                Add this to your MCP client configuration:
              </p>
            )}

            <div className={styles.setupCodeBlock}>
              <pre>{getSetupContent()}</pre>
              <button className={styles.copyButton} onClick={copySetupContent}>
                {setupCopied ? <Check size={18} /> : <Copy size={18} />}
              </button>
            </div>

            <div className={styles.setupNote}>
              <Info size={14} />
              <span>
                Replace <code>&lt;YOUR_API_KEY&gt;</code> with your API key. If you've lost your key, create a new one.
              </span>
            </div>

            <div className={styles.setupNote}>
              <Terminal size={14} />
              <span>
                The MCP server lets your coding agent read playbooks, record outcomes, and trigger evolution automatically.
              </span>
            </div>
            <div className={styles.setupNote}>
              <Info size={14} />
              <span>
                Legacy SSE endpoint compatibility remains available at <code>https://aceagent.io/mcp/sse</code> through May 22, 2026.
              </span>
            </div>
          </div>
        </div>

        {/* Recommended Instructions Template */}
        <div className={styles.instructionsTemplateSection}>
          <button
            className={styles.instructionsTemplateToggle}
            onClick={() => setTemplateExpanded(!templateExpanded)}
          >
            <FileText size={18} />
            <div className={styles.instructionsTemplateToggleText}>
              <strong>Recommended: Add agent instructions</strong>
              <span>Copy the instructions template into your CLAUDE.md, AGENTS.md, or custom instructions</span>
            </div>
            {templateExpanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
          </button>

          {templateExpanded && (
            <div className={styles.instructionsTemplateContent}>
              <p className={styles.instructionsTemplateDescription}>
                This template tells your AI agent how to discover, use, and improve your playbooks automatically.
                Paste it into your project's instructions file:
              </p>
              <div className={styles.instructionsTemplateTargets}>
                <span className={styles.targetBadge}>CLAUDE.md</span>
                <span className={styles.targetBadge}>AGENTS.md</span>
                <span className={styles.targetBadge}>Custom Instructions</span>
                <span className={styles.targetBadge}>System Prompt</span>
              </div>
              <div className={styles.setupCodeBlock}>
                <pre>{RECOMMENDED_INSTRUCTIONS_TEMPLATE}</pre>
                <button
                  className={styles.copyButton}
                  onClick={async () => {
                    await navigator.clipboard.writeText(RECOMMENDED_INSTRUCTIONS_TEMPLATE);
                    setTemplateCopied(true);
                    setTimeout(() => setTemplateCopied(false), 2000);
                  }}
                >
                  {templateCopied ? <Check size={18} /> : <Copy size={18} />}
                </button>
              </div>
              <div className={styles.setupNote}>
                <Info size={14} />
                <span>
                  Without these instructions, your agent won't know to look up playbooks or record outcomes. This is what closes the feedback loop for self-improving playbooks.
                </span>
              </div>
            </div>
          )}
        </div>

        <Button onClick={onClose} className={styles.doneButton}>
          Done
        </Button>
      </div>
    </div>
  );
}
