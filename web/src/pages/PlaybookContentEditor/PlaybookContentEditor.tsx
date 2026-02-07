import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { playbooksApi } from '../../utils/api';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { ArrowLeft, Save, AlertCircle } from 'lucide-react';
import type { VersionCreate } from '../../types';
import styles from './PlaybookContentEditor.module.css';

export function PlaybookContentEditor() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [content, setContent] = useState('');
  const [diffSummary, setDiffSummary] = useState('');

  const { data: playbook, isLoading, error } = useQuery({
    queryKey: ['playbook', id],
    queryFn: () => playbooksApi.get(id!),
    enabled: !!id,
  });

  const savedContent = playbook?.current_version?.content ?? '';

  // Initialize content from playbook when loaded - this syncs external
  // (server) data into local state, which is a valid effect use case.
  useEffect(() => {
    if (savedContent) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setContent(savedContent);
    }
  }, [savedContent]);

  // Derive unsaved changes from current state (no effect needed)
  const hasUnsavedChanges = savedContent
    ? content !== savedContent
    : content.length > 0;

  // Warn user about unsaved changes
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (hasUnsavedChanges) {
        e.preventDefault();
        e.returnValue = '';
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [hasUnsavedChanges]);

  const saveMutation = useMutation({
    mutationFn: (data: VersionCreate) => playbooksApi.createVersion(id!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['playbook', id] });
      queryClient.invalidateQueries({ queryKey: ['playbook-versions', id] });
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
      navigate(`/playbooks/${id}`);
    },
  });

  const handleSave = () => {
    if (!content.trim()) {
      return;
    }

    saveMutation.mutate({
      content: content.trim(),
      diff_summary: diffSummary.trim() || undefined,
    });
  };

  const currentVersionNumber = playbook?.current_version?.version_number ?? 0;
  const nextVersionNumber = currentVersionNumber + 1;

  if (isLoading) {
    return (
      <div className={styles.container}>
        <div className={styles.loading}>
          <div className={styles.spinner} />
          <span>Loading playbook...</span>
        </div>
      </div>
    );
  }

  if (error || !playbook) {
    return (
      <div className={styles.container}>
        <div className={styles.error}>
          <AlertCircle size={24} />
          <span>Failed to load playbook</span>
          <Button variant="secondary" onClick={() => navigate('/dashboard')}>
            Back to Dashboard
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      {/* Header */}
      <div className={styles.header}>
        <Link to={`/playbooks/${id}`} className={styles.backLink}>
          <ArrowLeft size={20} />
          <span>Back to Playbook</span>
        </Link>

        <div className={styles.headerContent}>
          <h1>Edit Content</h1>
          <span className={styles.playbookName}>{playbook.name}</span>
        </div>

        <div className={styles.headerActions}>
          <Button
            variant="secondary"
            onClick={() => navigate(`/playbooks/${id}`)}
          >
            Cancel
          </Button>
          <Button
            icon={<Save size={16} />}
            onClick={handleSave}
            isLoading={saveMutation.isPending}
            disabled={!content.trim() || !hasUnsavedChanges}
          >
            Save Version
          </Button>
        </div>
      </div>

      {/* Version Info */}
      <div className={styles.versionInfo}>
        {currentVersionNumber > 0 ? (
          <span>
            Editing from Version {currentVersionNumber}. Saving will create{' '}
            <strong>Version {nextVersionNumber}</strong>.
          </span>
        ) : (
          <span>
            No content yet. Saving will create <strong>Version 1</strong>.
          </span>
        )}
      </div>

      {/* Editor */}
      <div className={styles.editorContainer}>
        <textarea
          className={styles.editor}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="# My Playbook&#10;&#10;Write your playbook content here..."
          spellCheck={false}
        />
      </div>

      {/* Change Summary */}
      <div className={styles.changeSummary}>
        <Input
          label="Change Summary (optional)"
          value={diffSummary}
          onChange={(e) => setDiffSummary(e.target.value)}
          placeholder="Brief description of changes (max 500 characters)"
          maxLength={500}
        />
        <p className={styles.hint}>
          This helps track what changed between versions.
        </p>
      </div>

      {/* Error display */}
      {saveMutation.isError && (
        <div className={styles.saveError}>
          <AlertCircle size={16} />
          <span>Failed to save. Please try again.</span>
        </div>
      )}
    </div>
  );
}
