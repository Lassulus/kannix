{
  "id": "a1ec24cb",
  "title": "Git integration — repos, worktrees, diff view",
  "status": "draft",
  "created_at": "2026-03-13T12:37:16.680Z",
  "assigned_to_session": "3c9966dc-9e30-4a7d-90a5-b1a5ce8cccd0",
  "steps": [
    {
      "id": 1,
      "text": "M7.1: Vendor diff2html — add fetchurl flake inputs for diff2html JS+CSS, copy into static/vendor/ at build time, serve at /static/vendor/. Test: files served with correct content-type.",
      "done": false
    },
    {
      "id": 2,
      "text": "M7.2: Git repo model + config — add repos_dir/worktree_dir to KannixConfig, add RepoState to state model (id, name, url, path, default_branch). TDD: config validation, state round-trip.",
      "done": false
    },
    {
      "id": 3,
      "text": "M7.3: Git manager — GitManager class: clone_repo(url), register_repo(path), list_repos(), delete_repo(), create_worktree(repo_id, ticket_id, title), delete_worktree(), get_diff(repo_id, ticket_id). TDD: clone, worktree create/delete, diff generation.",
      "done": false
    },
    {
      "id": 4,
      "text": "M7.4: Repo API endpoints — CRUD /api/repos (list, create via clone URL, delete), GET /api/repos/{id}. Auth required. TDD.",
      "done": false
    },
    {
      "id": 5,
      "text": "M7.5: Repo management UI — /repos page: list registered repos, form to clone new repo by URL, delete button. HTMX partials. TDD: page renders, form works.",
      "done": false
    },
    {
      "id": 6,
      "text": "M7.6: Ticket-repo assignment — API + UI to assign/unassign repos to tickets. On assign: create worktree + branch. On unassign: optionally delete worktree. Update ticket model with repos list. TDD.",
      "done": false
    },
    {
      "id": 7,
      "text": "M7.7: Diff view on ticket page — tabbed diff view per assigned repo on ticket detail page. Uses diff2html.js for rendering. Tab per repo, shows branch diff vs merge-base. TDD: diff endpoint returns unified diff, page includes diff2html, tabs render.",
      "done": false
    },
    {
      "id": 8,
      "text": "M7.8: Worktree paths in terminal — set KANNIX_WORKTREE_<REPO> env vars in tmux session so terminal has easy access to worktree paths. Update kannix-ctl with repo/worktree subcommands.",
      "done": false
    },
    {
      "id": 9,
      "text": "M7.9: NixOS module updates — add repos_dir, worktree_dir options. Ensure git is on PATH in systemd service. Update package.nix to include vendored diff2html.",
      "done": false
    }
  ]
}

# Git Integration

Add git repo management, per-ticket worktrees, and diff views to Kannix.

## Architecture

- **Repos**: Configured repos directory. Clone via URL or register existing bare repos.
- **Repo state**: Stored in `state.json` alongside tickets/users.
- **Worktrees**: Configurable base path. Created when repos are assigned to a ticket.
- **Branch naming**: `ticket/<id-short>-<slugified-title>` (e.g. `ticket/a3f8b2c1-fix-auth-bug`)
- **Diff**: Branch diff against merge-base (main/master). Rendered with diff2html.js.
- **diff2html.js**: Vendored via flake fetchurl inputs, served as static files.

## Config additions
```json
{
  \"repos_dir\": \"/var/lib/kannix/repos\",
  \"worktree_dir\": \"/var/lib/kannix/worktrees\"
}
```

## State additions
```json
{
  \"repos\": {
    \"repo-id\": {\"name\": \"kannix\", \"url\": \"...\", \"path\": \"...\", \"default_branch\": \"main\"}
  },
  \"tickets\": {
    \"ticket-id\": {\"repos\": [\"repo-id\", ...], ...}
  }
}
```

## Key decisions
- Bare clones in repos_dir, worktrees in worktree_dir/<ticket-id>/<repo-name>/
- Worktree branch created from default_branch HEAD at assignment time
- Diff = `git diff $(git merge-base HEAD main)..HEAD` in worktree
- diff2html.js vendored as flake input (fetchurl), served at /static/vendor/
