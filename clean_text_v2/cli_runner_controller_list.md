# glab runner-controller list

/

---

# `glab runner-controller list`

List runner controllers. (EXPERIMENTAL)

## Synopsis

You must have administrator access.

This feature is an experiment and is not ready for production use.
It might be unstable or removed at any time.
For more information, see
<https://docs.gitlab.com/policy/development_stages_support/>.

```
glab runner-controller list [flags]
```

## Examples

console

```
# List all runner controllers
glab runner-controller list

# List runner controllers as JSON
glab runner-controller list --output json
```

## Options

```
      --jq string       Filter JSON output with a jq expression.
  -F, --output string   Format output as: text, json. (default "text")
  -p, --page int        Page number. (default 1)
  -P, --per-page int    Number of items per page. (default 30)
```

## Options inherited from parent commands

```
  -h, --help   Show help for this command.
```
