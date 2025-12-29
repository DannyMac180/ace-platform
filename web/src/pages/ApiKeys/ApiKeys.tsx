import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiKeysApi } from '../../utils/api';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Input } from '../../components/ui/Input';
import {
  Plus,
  Key,
  Trash2,
  Copy,
  Check,
  Clock,
  AlertCircle,
  Shield,
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

export function ApiKeys() {
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newKey, setNewKey] = useState<ApiKeyCreateResponse | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);

  const queryClient = useQueryClient();

  const { data: apiKeys, isLoading, error } = useQuery({
    queryKey: ['api-keys'],
    queryFn: apiKeysApi.list,
  });

  const createMutation = useMutation({
    mutationFn: (data: ApiKeyCreate) => apiKeysApi.create(data),
    onSuccess: (key) => {
      queryClient.invalidateQueries({ queryKey: ['api-keys'] });
      setNewKey(key);
      setShowCreateModal(false);
      setMutationError(null);
    },
    onError: () => {
      setMutationError('Failed to create API key. Please try again.');
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
        <Button icon={<Plus size={18} />} onClick={() => setShowCreateModal(true)}>
          Create API Key
        </Button>
      </div>

      {/* Warning Banner */}
      <div className={styles.warning}>
        <Shield size={20} />
        <div>
          <strong>Keep your API keys secure</strong>
          <p>API keys provide access to your account. Never share them or commit them to version control.</p>
        </div>
      </div>

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
      ) : error ? (
        <div className={styles.error}>
          <AlertCircle size={24} />
          <span>Failed to load API keys</span>
        </div>
      ) : apiKeys?.length === 0 ? (
        <EmptyState onCreateClick={() => setShowCreateModal(true)} />
      ) : (
        <div className={styles.keysList}>
          {apiKeys?.map((key) => (
            <ApiKeyCard
              key={key.id}
              apiKey={key}
              onDelete={() => deleteMutation.mutate(key.id)}
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
    </div>
  );
}

interface ApiKeyCardProps {
  apiKey: ApiKey;
  onDelete: () => void;
  isDeleting: boolean;
}

function ApiKeyCard({ apiKey, onDelete, isDeleting }: ApiKeyCardProps) {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  return (
    <Card variant="default" className={styles.keyCard}>
      <div className={styles.keyHeader}>
        <div className={styles.keyIcon}>
          <Key size={20} />
        </div>
        <div className={styles.keyInfo}>
          <h3>{apiKey.name}</h3>
          <code className={styles.keyPreview}>{apiKey.key_preview}</code>
        </div>
        <button
          className={styles.deleteButton}
          onClick={() => setShowDeleteConfirm(true)}
          disabled={isDeleting}
        >
          <Trash2 size={18} />
        </button>
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
        {apiKey.expires_at && (
          <div className={styles.metaItem}>
            <AlertCircle size={14} />
            <span>Expires {new Date(apiKey.expires_at).toLocaleDateString()}</span>
          </div>
        )}
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
      <Button icon={<Plus size={18} />} onClick={onCreateClick}>
        Create your first API key
      </Button>
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
  const [expiresInDays, setExpiresInDays] = useState<string>('');

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

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onCreate({
      name,
      scopes: Array.from(selectedScopes),
      expires_in_days: expiresInDays ? parseInt(expiresInDays) : undefined,
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

          <div className={styles.expirySection}>
            <label className={styles.expiryLabel}>Expiration (optional)</label>
            <select
              value={expiresInDays}
              onChange={(e) => setExpiresInDays(e.target.value)}
              className={styles.expirySelect}
            >
              <option value="">Never expires</option>
              <option value="30">30 days</option>
              <option value="90">90 days</option>
              <option value="180">180 days</option>
              <option value="365">1 year</option>
            </select>
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

  const copyToClipboard = async () => {
    await navigator.clipboard.writeText(apiKey.key);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
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
          <p><strong>Scopes:</strong> {apiKey.scopes.join(', ')}</p>
          {apiKey.expires_at && (
            <p><strong>Expires:</strong> {new Date(apiKey.expires_at).toLocaleDateString()}</p>
          )}
        </div>

        <Button onClick={onClose} className={styles.doneButton}>
          Done
        </Button>
      </div>
    </div>
  );
}
