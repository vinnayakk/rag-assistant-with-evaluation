# GitLab Patch Release: 17.0.1, 16.11.3, 16.10.6

/

---

# GitLab Patch Release: 17.0.1, 16.11.3, 16.10.6

On May 22, 2024, we released versions 17.0.1, 16.11.3, and 16.10.6 for GitLab Community Edition (CE) and Enterprise Edition (EE).

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

## Security fixes

### Table of security fixes

| Title | Severity |
| --- | --- |
| [1-click account takeover via XSS leveraging the VS code editor (Web IDE)](/releases/patches/patch-release-gitlab-17-0-1-released/#1-click-account-takeover-via-xss-leveraging-the-vs-code-editor-web-ide) | High |
| [A DOS vulnerability in the ‘description’ field of the runner](/releases/patches/patch-release-gitlab-17-0-1-released/#a-dos-vulnerability-in-the-description-field-of-the-runner) | Medium |
| [CSRF via K8s cluster-integration](/releases/patches/patch-release-gitlab-17-0-1-released/#csrf-via-k8s-cluster-integration) | Medium |
| [Using Set Pipeline Status of a Commit API incorrectly create a new pipeline when SHA and pipeline\_id did not match](/releases/patches/patch-release-gitlab-17-0-1-released/#using-set-pipeline-status-of-a-commit-api-incorrectly-create-a-new-pipeline-when-sha-and-pipeline_id-did-not-match) | Medium |
| [Redos on wiki render API/Page](/releases/patches/patch-release-gitlab-17-0-1-released/#redos-on-wiki-render-apipage) | Medium |
| [Resource exhaustion and denial of service with test\_report API calls](/releases/patches/patch-release-gitlab-17-0-1-released/#resource-exhaustion-and-denial-of-service-with-test_report-api-calls) | Medium |
| [Guest user can view dependency lists of private projects through job artifacts](/releases/patches/patch-release-gitlab-17-0-1-released/#guest-user-can-view-dependency-lists-of-private-projects-through-job-artifacts) | Medium |

### 1-click account takeover via XSS leveraging the VS code editor (Web IDE)

A XSS condition exists within GitLab in versions 15.11 before 16.10.6, 16.11 before 16.11.3, and 17.0 before 17.0.1. By leveraging this condition, an attacker can craft a malicious page to exfiltrate sensitive user information.
This is a high severity issue (`CVSS:3.1/AV:N/AC:H/PR:N/UI:R/S:C/C:H/I:H/A:N`, 8.0)
It is now mitigated in the latest release and is assigned [CVE-2024-4835](https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2024-4835).

Thanks [matanber](https://hackerone.com/matanber) for reporting this vulnerability through our HackerOne bug bounty program.

### A DOS vulnerability in the ‘description’ field of the runner

An issue has been discovered in GitLab CE/EE affecting all versions up to 16.10.6, versions 16.11 up to 16.11.3, and 17.0 up to 17.0.1. A runner registered with a crafted description has the potential to disrupt the loading of targeted GitLab web resources.
This is a medium severity issue (`CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:H`, 6.5).
It is now mitigated in the latest release and is assigned [CVE-2024-2874](https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2024-2874).

Thanks [ac7n0w](https://hackerone.com/ac7n0w) for reporting this vulnerability through our HackerOne bug bounty program

### CSRF via K8s cluster-integration

A CSRF vulnerability exists within GitLab CE/EE from versions 16.3 up to 16.10.6, from 16.11 up to 16.11.3, from 17.0 up to 17.0.1. By leveraging this vulnerability, an attacker could exfiltrate anti-CSRF tokens via the Kubernetes Agent Server (KAS).
This is a medium severity issue (`AV:N/AC:L/PR:L/UI:R/S:C/C:L/I:L/A:N`, 5.4).
It is now mitigated in the latest release and is assigned [CVE-2023-7045](https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2023-7045).

Thanks [imrerad](https://hackerone.com/imrerad) for reporting this vulnerability through our HackerOne bug bounty program

### Using Set Pipeline Status of a Commit API incorrectly create a new pipeline when SHA and pipeline\_id did not match

An authorization vulnerability exists within GitLab from versions 16.10 up to 16.10.6, 16.11 up to 16.11.3, and 17.0 up to 17.0.1 where an authenticated attacker could utilize a crafted naming convention to bypass pipeline authorization logic.
This is a medium severity issue (`CVSS:3.1/AV:N/AC:H/PR:L/UI:R/S:C/C:L/I:L/A:N`, 4.4).
It is now mitigated in the latest release and is assigned [CVE-2024-5258](https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2024-5258).

Thanks to GitLab Team Member, Andrew Winata for reporting this issue.

### Redos on wiki render API/Page

A Denial of Service (DoS) condition has been discovered in GitLab CE/EE affecting all versions before 16.10.6, version 16.11 before 16.11.3, and 17.0 before 17.0.1. It is possible for an attacker to cause a denial of service using a crafted wiki page.
This is a medium severity issue (`CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:L`, 4.3).
It is now mitigated in the latest release and is assigned [CVE-2023-6502](https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2023-6502).

Thanks `Anonymizer` for reporting this vulnerability through our HackerOne bug bounty program.

### Resource exhaustion and denial of service with test\_report API calls

A denial of service (DoS) condition was discovered in GitLab CE/EE affecting all versions from 13.2.4 up to 16.10.6, 16.11 up to 16.11.3, and 17.0 up to 17.0.1. By leveraging this vulnerability an attacker could create a DoS condition by sending crafted API calls.
This is a medium severity issue (`CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:N/A:L`, 4.3).
It is now mitigated in the latest release and is assigned [CVE-2024-1947](https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2024-1947).

Thanks [luryus](https://hackerone.com/luryus) for reporting this vulnerability through our HackerOne bug bounty program.

### Guest user can view dependency lists of private projects through job artifacts

An issue has been discovered in GitLab CE/EE affecting all versions starting from 11.11 prior to 16.10.6, starting from 16.11 prior to 16.11.3, and starting from 17.0 prior to 17.0.1. A Guest user can view dependency lists of private projects through job artifacts.
This is a medium severity issue (`CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:L/I:N/A:N`, 4.3).
It is now mitigated in the latest release and is assigned [CVE-2024-5318](https://cve.mitre.org/cgi-bin/cvename.cgi?name=CVE-2024-5318).

Thanks [ricardobrito](https://hackerone.com/ricardobrito) for reporting this vulnerability through our HackerOne bug bounty program.

### Stored XSS via PDFjs

Mitigations were made to take care of vulnerability in PDF.js [CVE-2024-4367](https://nvd.nist.gov/vuln/detail/CVE-2024-4367).

Thanks [h4x0r\_dz](https://hackerone.com/h4x0r_dz) for reporting this vulnerability through our HackerOne bug bounty program.

### Mattermost Security Updates April 25th, 2024

Mattermost has been updated to versions 9.7.2, which contains several patches and security fixes.

## Bug fixes

### 17.0.1

* [Makefile: update Git versions (v17.0 backport)](https://gitlab.com/gitlab-org/gitaly/-/merge_requests/6922)
* [Merge branch ‘rymai-master-patch-5345’ into ‘master’](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/153144)
* [Don’t fail so loudly if default work item type is invalid](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/153330)
* [[17.0 backport] Project transfer fix for ES indexing](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/152962)
* [Ensure BLPOP/BRPOP returns nil instead of raising ReadTimeoutError](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/153304)
* [[17-0] Fix Sidekiq migration timeout](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/153574)

### 16.11.3

* [Makefile: update Git versions (v16.11 backport)](https://gitlab.com/gitlab-org/gitaly/-/merge_requests/6919)
* [Revert removal of bitbucket\_server\_convert\_mentions\_to\_users FF](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/152328)
* [Cherry pick print-out-release-environment-variables to 16.11](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/152915)
* [[16-11] Fix Sidekiq migration timeout](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/152891)
* [Merge branch ‘rymai-master-patch-5345’ into ‘master’](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/153146)
* [Ensure BLPOP/BRPOP returns nil instead of raising ReadTimeoutError](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/153302)
* [Draft: Update changelog for 16.11.0](https://gitlab.com/gitlab-org/omnibus-gitlab/-/merge_requests/7602)
* [BACKPORT-16-11-stable: Use bundler to install Omnibus gems](https://gitlab.com/gitlab-org/omnibus-gitlab/-/merge_requests/7586)

### 16.10.6

* [Makefile: update Git versions (v16.10 backport)](https://gitlab.com/gitlab-org/gitaly/-/merge_requests/6920)
* [Revert “Remove bitbucket\_server\_convert\_mentions\_to\_users feature flag”](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/152248)
* [Cherry pick print-out-release-environment-variables to 16.10](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/152916)
* [Merge branch ‘rymai-master-patch-5345’ into ‘master’](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/153147)
* [Ensure BLPOP/BRPOP returns nil instead of raising ReadTimeoutError](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/153301)
* [BACKPORT-16-10-stable: Use bundler to install Omnibus gems](https://gitlab.com/gitlab-org/omnibus-gitlab/-/merge_requests/7585)

## Updating

To update GitLab, see the [update page](https://about.gitlab.com/update/).
To update Gitlab Runner, see the [Updating the Runner page](https://docs.gitlab.com/runner/install/linux-repository.html#updating-the-runner).

## Receive Patch Notifications

To receive patch blog notifications delivered to your inbox, visit our [contact us](https://about.gitlab.com/company/contact/) page.
To receive release notifications via RSS, subscribe to our [patch release RSS feed](https://docs.gitlab.com/releases/security-releases.xml) or our [RSS feed for all releases](https://docs.gitlab.com/releases/all-releases.xml).

## We’re combining patch and security releases

This improvement in our release process matches the industry standard and will help GitLab users get information about security and
bug fixes sooner, [read the blog post here](https://about.gitlab.com/blog/were-combining-patch-and-security-releases/).
