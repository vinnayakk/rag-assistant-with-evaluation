# glab issue delete

/

---

# `glab issue delete`

Delete an issue.

## Synopsis

Permanently deletes the issue. You can pass an issue ID or a full
issue URL.

```
glab issue delete <id> [flags]
```

## Aliases

```
del
```

## Examples

console

```
glab issue delete 123
glab issue del 123
glab issue delete https://gitlab.com/profclems/glab/-/issues/123
```

## Options inherited from parent commands

```
  -h, --help          Show help for this command.
  -R, --repo string   Select another repository. You can use either OWNER/REPO or GROUP/NAMESPACE/REPO. The full URL or Git URL is also accepted.
```
