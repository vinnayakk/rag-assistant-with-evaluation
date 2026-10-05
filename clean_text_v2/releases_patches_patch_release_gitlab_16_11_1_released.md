# GitLab Patch Release: 16.11.1, 16.10.4, 16.9.6

/

---

# GitLab Patch Release: 16.11.1, 16.10.4, 16.9.6

On April 24, 2024, we released versions 16.11.1, 16.10.4, 16.9.6 for GitLab Community Edition (CE) and Enterprise Edition (EE).

These versions contain important bug and security fixes, and we strongly recommend that all GitLab installations be upgraded to
one of these versions immediately. GitLab.com is already running the patched version.

GitLab releases fixes for vulnerabilities in dedicated patch releases. There are two types of patch releases:
scheduled releases, and ad-hoc critical patches for high-severity vulnerabilities. Scheduled releases are released twice a month on the second and fourth Wednesdays.
For more information, you can visit our [releases handbook](https://handbook.gitlab.com/handbook/engineering/releases/) and [security FAQ](https://about.gitlab.com/security/faq/).
You can see all of GitLab release blog posts [here](https://about.gitlab.com/releases/categories/releases/).

For security fixes, the issues detailing each vulnerability are made public on our
[issue tracker](https://gitlab.com/gitlab-org/gitlab/-/issues/?sort=created_date&state=closed&label_name%5B%5D=bug%3A%3Avulnerability&confidential=no&first_page_size=100)
30 days after the release in which they were patched.

We are dedicated to ensuring all aspects of GitLab that are exposed to customers or that host customer data are held to
the highest security standards. As part of maintaining good security hygiene, it is highly recommended that all customers
upgrade to the latest patch release for their supported version. You can read more
[best practices in securing your GitLab instance](https://about.gitlab.com/blog/gitlab-instance-security-best-practices/) in our blog post.

### Recommended Action

We **strongly recommend** that all installations running a version affected by the issues described below are **upgraded to the latest version as soon as possible**.

When no specific deployment type (omnibus, source code, helm chart, etc.) of a product is mentioned, this means all types are affected.

#### Accidental breaking changes in KAS configuration

The following KAS patch releases contain breaking changes from the %17.0 revision, because they were tagged from the wrong source (master instead of stable branches):

* v16.11.1
* v16.10.4
* v16.9.6

The next GitLab patch release will fix those changes. [Issue 458462](https://gitlab.com/gitlab-org/gitlab/-/issues/458462) provides more information.

As a workaround KAS can be downgraded to the last release. Working KAS versions are:

* v16.11.0
* v16.10.1
* v16.9.3

## Security fixes

### Table of security fixes

| Title | Severity |
| --- | --- |
| [GitLab account takeover, under certain conditions, when using Bitbucket as an OAuth provider](/releases/patches/patch-release-gitlab-16-11-1-released/#gitlab-account-takeover-under-certain-conditions-when-using-bitbucket-as-an-oauth-provider) | High |
| [Path Traversal leads to DoS and Restricted File Read](/releases/patches/patch-release-gitlab-16-11-1-released/#path-traversal-leads-to-dos-and-restricted-file-read) | High |
| [Unauthenticated ReDoS in FileFinder when using wildcard filters in project file search](/releases/patches/patch-release-gitlab-16-11-1-released/#unauthenticated-redos-in-filefinder-when-using-wildcard-filters-in-project-file-search) | High |
| [Personal Access Token scopes not honoured by GraphQL subscriptions](/releases/patches/patch-release-gitlab-16-11-1-released/#personal-access-token-scopes-not-honoured-by-graphql-subscriptions) | Medium |
| [Domain based restrictions bypass using a crafted email address](/releases/patches/patch-release-gitlab-16-11-1-released/#domain-based-restrictions-bypass-using-a-crafted-email-address) | Medium |

### GitLab account takeover, under certain conditions, when using Bitbucket as an OAuth provider

An issue has been discovered in GitLab CE/EE affecting all versions starting from 7.8 before 16.9.6, all versions starting from 16.10 before 16.10.4, all versions starting from 16.11 before 16.11.1. Under certain conditions, an attacker with their Bitbucket account credentials may be able to take over a GitLab account linked to another user’s Bitbucket account, if Bitbucket is used as an OAuth 2.0 provider on GitLab.
This is a high severity issue (`CVSS:3.1/AV:N/AC:L/PR:L/UI:R/S:U/C:H/I:H/A:N`, 7.3).
It is now mitigated in the latest release and is assigned [CVE-2024-4024](https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2024-4024).

This vulnerability has been discovered internally by GitLab team members [Sam Word](https://gitlab.com/SamWord) and [Rodrigo Tomonari](https://gitlab.com/rodrigo.tomonari).

On 2024-04-24, GitLab changed the way Bitbucket authentication works with GitLab. To continue using Bitbucket Authentication, please sign in to GitLab with your Bitbucket account credentials, before 2024-05-16.

If you do not sign into GitLab using your Bitbucket account until after 2024-05-16, you will need to [re-link your Bitbucket account](https://docs.gitlab.com/ee/user/profile/#sign-in-services) to your GitLab account manually. For some users, signing in to GitLab using their Bitbucket account may not work after this fix is applied. If this happens to you, your Bitbucket and GitLab accounts have different email addresses. To resolve this, you must log in to your GitLab account with your GitLab username and password and [re-link your Bitbucket account](https://docs.gitlab.com/ee/user/profile/#sign-in-services).

### Path Traversal leads to DoS and Restricted File Read

An issue has been discovered in GitLab affecting all versions of GitLab CE/EE 16.9 prior to 16.9.6, 16.10 prior to 16.10.4, and 16.11 prior to 16.11.1 where path traversal could lead to DoS and restricted file read. This is a high severity issue (`CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:C/C:L/I:N/A:H`, 8.5). It is now mitigated in the latest release and is assigned [CVE-2024-2434](https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2024-2434).

Thanks [pwnie](https://hackerone.com/pwnie) for reporting this vulnerability through our HackerOne bug bounty program.

### Unauthenticated ReDoS in FileFinder when using wildcard filters in project file search

An issue has been discovered in GitLab CE/EE affecting all versions starting from 12.5 before 16.9.6, all versions starting from 16.10 before 16.10.4, all versions starting from 16.11 before 16.11.1. A crafted wildcard filter in FileFinder may lead to a denial of service.
This is a high severity issue (`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H`, 7.5).
It is now mitigated in the latest release and is assigned [CVE-2024-2829](https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2024-2829).

Thanks [joaxcar](https://hackerone.com/joaxcar) for reporting this vulnerability through our HackerOne bug bounty program.

### Personal Access Token scopes not honoured by GraphQL subscriptions

An issue has been discovered in GitLab CE/EE affecting all versions starting from 16.7 before 16.9.6, all versions starting from 16.10 before 16.10.4, all versions starting from 16.11 before 16.11.1 where personal access scopes were not honored by GraphQL subscriptions.
This is a medium severity issue (`CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:L/I:N/A:N`, 4.3).
It is now mitigated in the latest release and is assigned [CVE-2024-4006](https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2024-4006).

This vulnerability was internally discovered and reported by a GitLab team member, [Dylan Griffith](https://gitlab.com/DylanGriffith).

### Domain based restrictions bypass using a crafted email address

An issue has been discovered in GitLab CE/EE affecting all versions before 16.9.6, all versions starting from 16.10 before 16.10.4, all versions starting from 16.11 before 16.11.1. Under certain conditions, an attacker through a crafted email address may be able to bypass domain based restrictions on an instance or a group.
This is a medium severity issue (`CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:L/A:N`, 4.3).
It is now mitigated in the latest release and is assigned [CVE-2024-1347](https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2024-1347).

Thanks [garethheyes](https://hackerone.com/garethheyes) for reporting this vulnerability through our HackerOne bug bounty program.

## Bug fixes

### 16.11.1

* [Backport fixing release environment pipeline triggering rule to 16.11](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/150027)
* [Fix for missing branch\_build\_package\_download\_url](https://gitlab.com/gitlab-org/omnibus-gitlab/-/merge_requests/7556)
* [Fix missing arguments when PostgreSQL upgrade times out](https://gitlab.com/gitlab-org/omnibus-gitlab/-/merge_requests/7559)

### 16.10.4

* [go.mod: Update `golang.org/x/net` dependency](https://gitlab.com/gitlab-org/gitaly/-/merge_requests/6825)
* [Update vulnerability\_reads scanner in the ingestion pipeline](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/149253)
* [Fix migration error when updating from GitLab 16.x to 16.10](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/149810)
* [Backport fixing release environment pipeline triggering rule to 16.10](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/150029)

### 16.9.6

* [Backport fixing release environment pipeline triggering rule to 16.9](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/150030)

## Updating

To update GitLab, see the [update page](https://about.gitlab.com/update/).
To update Gitlab Runner, see the [Updating the Runner page](https://docs.gitlab.com/runner/install/linux-repository.html#updating-the-runner).

## Receive Patch Notifications

To receive patch blog notifications delivered to your inbox, visit our [contact us](https://about.gitlab.com/company/contact/) page.
To receive release notifications via RSS, subscribe to our [patch release RSS feed](https://docs.gitlab.com/releases/security-releases.xml) or our [RSS feed for all releases](https://docs.gitlab.com/releases/all-releases.xml).

## We’re combining patch and security releases

This improvement in our release process matches the industry standard and will help GitLab users get information about security and
bug fixes sooner, [read the blog post here](https://about.gitlab.com/blog/were-combining-patch-and-security-releases/).
