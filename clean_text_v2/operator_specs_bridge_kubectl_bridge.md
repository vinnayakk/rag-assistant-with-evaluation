# kubectl bridge plugin

/

---

# kubectl bridge plugin

Status: Implemented
Issue: none
Parent: none

## Goal

A developer or administrator uses the Bridge UI without deploying a Bridge image, and with any
kubeconfig, including one that cannot be reduced to a bearer token.

## Requirements

* `kubectl bridge` serves the same API and SPA as Bridge in the cluster, on the local machine.
* The plugin acts as the current kubeconfig context, or the one `--context` and `--kubeconfig`
  select. Certificate, exec, OIDC, and token credentials all work.
* The plugin asks for no token. The SPA shows that it acts as the kubeconfig instead of a token
  field, and the terminal prints the identity and the URL.
* The plugin binds `127.0.0.1:8090` by default, and a random free port when that port is busy.
* Binding a non-loopback address with `--address` works, and prints a warning.
* An `/api` request whose `Host` is neither a loopback name, the bind address, nor a name passed to
  `--accept-hosts` receives `403`.
* An `/api` request that `Sec-Fetch-Site`, `Origin`, or `Referer` marks as coming from another
  origin receives `403`.
* A request with none of those browser headers, such as one from `curl`, is served.
* The plugin opens the URL in a browser, unless `--no-open` is set.

## Out of scope

* Authentication by the plugin itself.
* Running the reconcilers. The plugin serves the API only.

## FAQ

* **Why guard requests to loopback at all?** With no token to guess, any page open in the browser
  could send requests to the plugin with the permissions of the kubeconfig. For more information,
  see [ADR 34](../../developer/adr/0034-bridge-authentication.md).
* **Why does `curl` still work?** The guard rejects what a browser marks as cross-site. A client
  that sends no such header is not a page in the browser of the user.
