# GitLab Patch Release: 16.10.3, 16.9.5, 16.8.7

/

---

# GitLab Patch Release: 16.10.3, 16.9.5, 16.8.7

On April 15, 2024, we released versions 16.10.3, 16.9.5, 16.8.7 for GitLab Community Edition and Enterprise Edition.

These versions resolve a number of regressions and bugs. This patch release does not include any security fixes.

## GitLab Community Edition and Enterprise Edition

### 16.10.3

* [Fix patroni no longer working with update to ydiff 1.3](https://gitlab.com/gitlab-org/omnibus-gitlab/-/merge_requests/7538)

### 16.9.5

* [Update Go packages to address vulnerabilities in 16-9-stable](https://gitlab.com/gitlab-org/gitaly/-/merge_requests/6811)
* [Make Gitaly no downtime upgrades work again in 16.9](https://gitlab.com/gitlab-org/gitaly/-/merge_requests/6807)
* [Fix patroni no longer working with update to ydiff 1.3](https://gitlab.com/gitlab-org/omnibus-gitlab/-/merge_requests/7537)

### 16.8.7

* [Fix patroni no longer working with update to ydiff 1.3](https://gitlab.com/gitlab-org/omnibus-gitlab/-/merge_requests/7536)

## Important notes on upgrading

This version does not include any new migrations, and for multi-node deployments, [should not require any downtime](https://docs.gitlab.com/ee/update/#upgrading-without-downtime).

Please be aware that by default the Omnibus packages will stop, run migrations,
and start again, no matter how “big” or “small” the upgrade is. This behavior
can be changed by adding a [`/etc/gitlab/skip-auto-reconfigure`](https://docs.gitlab.com/ee/update/zero_downtime.html) file,
which is only used for [updates](https://docs.gitlab.com/omnibus/update/README.html).

## Updating

To update, check out our [update page](https://about.gitlab.com/update/).

## GitLab subscriptions

Access to GitLab Premium and Ultimate features is granted by a paid [subscription](https://about.gitlab.com/pricing/).

Alternatively, [sign up for GitLab.com](https://gitlab.com/users/sign_in)
to use GitLab’s own infrastructure.

## We’re combining patch and security releases

This improvement in our release process matches the industry standard and will help GitLab users get information about security and
bug fixes sooner, [read the blog post here](https://about.gitlab.com/blog/were-combining-patch-and-security-releases/).
