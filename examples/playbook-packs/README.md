# Example Playbook Packs

These packs are simple Markdown playbooks that can be copied into another local
ACE project. They are intentionally file-based so they work in the OSS runtime
without any ACE-operated cloud service.

## Included pack

- `repo-maintainer/`: guidance for maintaining an open-source repository with a
  repeatable release and triage workflow

## Suggested usage

Copy the files you want into a local project's playbook directory:

```bash
mkdir -p my-project/playbooks
cp examples/playbook-packs/repo-maintainer/*.md my-project/playbooks/
```

Then adapt the project-specific commands, paths, and validation rules.
