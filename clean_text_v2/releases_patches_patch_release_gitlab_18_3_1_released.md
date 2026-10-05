# GitLab Patch Release: 18.3.1, 18.2.5, 18.1.5

/

---

# GitLab Patch Release: 18.3.1, 18.2.5, 18.1.5

On August 27, 2025, we released versions 18.3.1, 18.2.5, 18.1.5 for GitLab Community Edition (CE) and Enterprise Edition (EE).

These versions contain important bug and security fixes, and we strongly recommend that all self-managed GitLab installations be upgraded to
one of these versions immediately. GitLab.com is already running the patched version. GitLab Dedicated customers do not need to take action.

GitLab releases fixes for vulnerabilities in patch releases. There are two types of patch releases:
scheduled releases and ad-hoc critical patches for high-severity vulnerabilities. Scheduled releases are released twice a month on the second and fourth Wednesdays.
For more information, please visit our [releases handbook](https://handbook.gitlab.com/handbook/engineering/releases/) and [security FAQ](https://about.gitlab.com/security/faq/).
You can see all of GitLab release blog posts [here](https://about.gitlab.com/releases/categories/releases/).

For security fixes, the issues detailing each vulnerability are made public on our
[issue tracker](https://gitlab.com/gitlab-org/gitlab/-/issues/?sort=created_date&state=closed&label_name%5B%5D=bug%3A%3Avulnerability&confidential=no&first_page_size=100)
30 days after the release in which they were patched.

We are committed to ensuring that all aspects of GitLab that are exposed to customers or that host customer data are held to
the highest security standards. To maintain good security hygiene, it is highly recommended that all customers
upgrade to the latest patch release for their supported version. You can read more
[best practices in securing your GitLab instance](https://about.gitlab.com/blog/gitlab-instance-security-best-practices/) in our blog post.

### Recommended Action

We **strongly recommend** that all installations running a version affected by the issues described below are **upgraded to the latest version as soon as possible**.

When no specific deployment type (omnibus, source code, helm chart, etc.) of a product is mentioned, it means all types are affected.

## Security fixes

### Table of security fixes

| Title | Severity |
| --- | --- |
| [Allocation of Resources Without Limits issue in import function impacts GitLab CE/EE](/releases/patches/patch-release-gitlab-18-3-1-released/#cve-2025-3601---allocation-of-resources-without-limits-issue-in-import-function-impacts-gitlab-ceee) | Medium |
| [Missing authentication issue in GraphQL endpoint impacts GitLab CE/EE](/releases/patches/patch-release-gitlab-18-3-1-released/#cve-2025-2246---missing-authentication-issue-in-graphql-endpoint-impacts-gitlab-ceee) | Medium |
| [Allocation of Resources Without Limits issue in GraphQL impacts GitLab CE/EE](/releases/patches/patch-release-gitlab-18-3-1-released/#cve-2025-4225---allocation-of-resources-without-limits-issue-in-graphql-impacts-gitlab-ceee) | Medium |
| [Code injection issue in GitLab repositories impacts GitLab CE/EE](/releases/patches/patch-release-gitlab-18-3-1-released/#cve-2025-5101---code-injection-issue-in-gitlab-repositories-impacts-gitlab-ceee) | Medium |

### [CVE-2025-3601](https://www.cve.org/CVERecord?id=CVE-2025-3601) - Allocation of Resources Without Limits issue in import function impacts GitLab CE/EE

GitLab has remediated an issue that could have allowed an authenticated user to cause a Denial of Service (DoS) condition by submitting URLs that generate excessively large responses.

**Impacted Versions**: GitLab CE/EE: all versions from 8.15 before 18.1.5, 18.2 before 18.2.5, and 18.3 before 18.3.1  
**CVSS**: 6.5 ([`CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:H`](https://gitlab-com.gitlab.io/gl-security/product-security/appsec/cvss-calculator/explain#explain=CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:H))

Thanks [nermalt](https://hackerone.com/nermalt) for reporting this vulnerability through our HackerOne bug bounty program.

### [CVE-2025-2246](https://www.cve.org/CVERecord?id=CVE-2025-2246) - Missing authentication issue in GraphQL endpoint impacts GitLab CE/EE

GitLab has remediated an issue that could have allowed unauthenticated users to access sensitive manual CI/CD variables by querying the GraphQL API.

**Impacted Versions**: GitLab CE/EE: all versions before 18.1.5, 18.2 before 18.2.5, and 18.3 before 18.3.1  
**CVSS**: 5.8 ([`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:L/I:N/A:N`](https://gitlab-com.gitlab.io/gl-security/product-security/appsec/cvss-calculator/explain#explain=CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:L/I:N/A:N))

Thanks [pwnie](https://hackerone.com/pwnie) for reporting this vulnerability through our HackerOne bug bounty program.

### [CVE-2025-4225](https://www.cve.org/CVERecord?id=CVE-2025-4225) - Allocation of Resources Without Limits issue in GraphQL impacts GitLab CE/EE

GitLab has remediated an issue that under certain conditions could have allowed an unauthenticated attacker to cause a denial-of-service condition affecting all users by sending specially crafted GraphQL requests.

**Impacted Versions**: GitLab CE/EE: all versions from 14.1 before 18.1.5, 18.2 before 18.2.5, and 18.3 before 18.3.1  
**CVSS**: 5.3 ([`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:L`](https://gitlab-com.gitlab.io/gl-security/product-security/appsec/cvss-calculator/explain#explain=CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:L))

Thanks [pwnie](https://hackerone.com/pwnie) for reporting this vulnerability through our HackerOne bug bounty program.

### [CVE-2025-5101](https://www.cve.org/CVERecord?id=CVE-2025-5101) - Code injection issue in GitLab repositories impacts GitLab CE/EE

GitLab has remediated an issue that under certain conditions could have allowed an authenticated attacker to distribute malicious code that appears harmless in the web interface by taking advantage of ambiguity between branches and tags during repository imports.

**Impacted Versions**: GitLab CE/EE: all versions before 18.1.5, 18.2 before 18.2.5, and 18.3 before 18.3.1  
**CVSS**: 5.0 ([`CVSS:3.1/AV:L/AC:H/PR:H/UI:R/S:C/C:N/I:H/A:N`](https://gitlab-com.gitlab.io/gl-security/product-security/appsec/cvss-calculator/explain#explain=CVSS:3.1/AV:L/AC:H/PR:H/UI:R/S:C/C:N/I:H/A:N)).

Thanks [st4nly0n](https://hackerone.com/st4nly0n) for reporting this vulnerability through our HackerOne bug bounty program.

## Bug fixes

### 18.3.1

* [[Backport 18.3] Making changes for container scanning for SBOMs](https://gitlab.com/gitlab-org/build/CNG/-/merge_requests/2626)
* [Backport of ‘Fix cannot load such file – gitlab’](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/202294)
* [Backport: Fix namespace issue preventing Ci::Build filtering optimization](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/202065)
* [Backport of “Dependency Path creation with path caching”](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/202363)
* [Fix trusted proxies regression when hostname is specified](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/202656)
* [Backport of E2E test: use correct checkbox method](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/202706)
* [Update Mattermost to v10.10.2](https://gitlab.com/gitlab-org/omnibus-gitlab/-/merge_requests/8677)

### 18.2.5

* [[Backport 18.2] Making changes for container scanning for SBOMs](https://gitlab.com/gitlab-org/build/CNG/-/merge_requests/2627)
* [[18.2] Fix flaky specs due to label ordering](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/201853)
* [Backport ‘Danger to fail backport MRs without descriptive title’](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/201990)
* [Backport bug - Fix mutations of frozen object in feature\_setting.rb](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/201270)
* [Add stage check for agentic chat](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/201937)
* [Backport of ‘update the active\_add\_on\_purchase check to include self-managed check’](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/202418)
* [Backport of “Create noop pipeline template compatible with test-on-omnibus”](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/202564)
* [Backport of ‘Fix cannot load such file – gitlab’](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/202673)
* [Backport of E2E test: use correct checkbox method](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/202705)
* [Backport of ‘Ignore silent\_mode in clickhouse http calls’](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/202570)

### 18.1.5

* [Backport “Danger to not error when e2e:test-on-omnibus-ee job not present for only QA changes” to 18.1](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/201046)
* [Backport Set :throttled urgency for GlobalAdvisoryScanWorker](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/196606)
* [Backport ‘Add job and script to update backport MR label after deployment’](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/201245)
* [Backport ‘Update gitlab-chart digest to 9d9e150’](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/201425)
* [Backport of ‘fix missing ref attribute’](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/201655)
* [[18.1] Fix flaky specs due to label ordering](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/201854)
* [Backport ‘Danger to fail backport MRs without descriptive title’](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/201992)
* [Backport of ‘update the active\_add\_on\_purchase check to include self-managed check’](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/202419)
* [Backport of E2E test: use correct checkbox method](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/202540)
* [Backport of “Create noop pipeline template compatible with test-on-omnibus”](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/202565)

## Important notes on upgrading

These versions do not include any new migrations, and for multi-node deployments, [should not require any downtime](https://docs.gitlab.com/ee/update/#upgrading-without-downtime).

Please be aware that by default the Omnibus packages will stop, run migrations,
and start again, no matter how “big” or “small” the upgrade is. This behavior
can be changed by adding a [`/etc/gitlab/skip-auto-reconfigure`](https://docs.gitlab.com/ee/update/zero_downtime.html) file,
which is only used for [updates](https://docs.gitlab.com/omnibus/update/README.html).

## Updating

To update GitLab, see the [Update page](https://about.gitlab.com/update/).
To update Gitlab Runner, see the [Updating the Runner page](https://docs.gitlab.com/runner/install/linux-repository.html#updating-the-runner).

## Receive Patch Notifications

To receive patch blog notifications delivered to your inbox, visit our [contact us](https://about.gitlab.com/company/contact/) page.
To receive release notifications via RSS, subscribe to our [patch release RSS feed](https://docs.gitlab.com/releases/security-releases.xml) or our [RSS feed for all releases](https://docs.gitlab.com/releases/all-releases.xml).
