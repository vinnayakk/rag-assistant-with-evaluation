# Code Owners

/

---

# Code Owners

* Tier: Premium, Ultimate
* Offering: GitLab.com, GitLab Self-Managed, GitLab Dedicated

Use the Code Owners feature to define who has expertise for specific parts of your project’s codebase.

Define the owners of files and directories in a repository to:

* Require owners to approve changes. Combine protected branches with Code Owners to require
  experts to approve merge requests before they merge into a protected branch. For more information,
  see [Code Owners and protected branches](/user/project/codeowners/#code-owners-and-protected-branches).
* Identify owners. Code Owner names are displayed on the files and directories they own:

  [![File view showing the Code Owners listed below a description of the most recent change.](/user/project/codeowners/img/codeowners_in_UI_v15_10.png)](/user/project/codeowners/img/codeowners_in_UI_v15_10.png)

## Code Owners and approval rules

Combine Code Owners with merge request
[approval rules](/user/project/merge_requests/approvals/rules/) (either optional or required)
to build a flexible approval workflow:

* Use Code Owners to ensure quality. Define the users who have domain expertise
  for specific paths in your repository.
* Use approval rules to define areas of expertise that don’t correspond to specific
  file paths in your repository. Approval rules help guide merge request creators to
  the correct set of reviewers, such as frontend developers or a security team.

For example:

| Type | Name | Scope | Comment |
| --- | --- | --- | --- |
| Approval rule | UX | All files | A user experience (UX) team member reviews the user experience of all changes made in your project. |
| Approval rule | Security | All files | A security team member reviews all changes for vulnerabilities. |
| Code Owner approval rule | Frontend: Code Style | `*.css` files | A frontend engineer reviews CSS file changes for adherence to project style standards. |
| Code Owner approval rule | Backend: Code Review | `*.rb` files | A backend engineer reviews the logic and code style of Ruby files. |

Video introduction: [Code Owners](https://www.youtube.com/watch?v=RoyBySTUSB0).

For information about who is eligible to approve merge requests as either an approver or Code Owner, see [approver by membership type](/user/project/merge_requests/approvals/rules/#approver-by-membership-type).

## Code Owners and protected branches

To ensure merge request changes are reviewed and approved by Code Owners, specified in the
[`CODEOWNERS` file](/user/project/codeowners/#codeowners-file), the merge request’s target branch must be
[protected](/user/project/repository/branches/protected/)
and [Code Owner approval](/user/project/repository/branches/protected/#require-code-owner-approval) must be enabled.

The following features are available when you enable Code Owner approvals on protected branches:

* [Require approvals from Code Owners](/user/project/repository/branches/protected/#require-code-owner-approval).
* [Require multiple approvals from Code Owners](/user/project/codeowners/advanced/#require-multiple-approvals-from-code-owners).
* [Optional approvals from Code Owners](/user/project/codeowners/reference/#optional-sections).

### Practical example

Your project contains sensitive and important information in a `config/` directory. You can:

1. Assign ownership of the directory. To do this, set up a `CODEOWNERS` file.
2. Create a protected branch for your default branch. For example, `main`.
3. Enable **Required approval from code owners** on the protected branch.
4. Optional. Edit the `CODEOWNERS` file to add a rule for multiple approvals.

With this configuration, merge requests that change files in the `config/` directory and target the `main` branch
require approval from the designated Code Owners before merging.

### Files without a Code Owner

GitLab compares the files changed in a merge request with the `CODEOWNERS` file in the target branch.
A file that does not match any `CODEOWNERS` rules does not need Code Owner approval. This includes new files, and files
that were moved or renamed in the target branch while a merge request was open.

To require approval for every file, add a default owner with a `*` entry at the top of the file.

If you add more specific entries later, they override the `*` entry because the last matching entry is used.

For more information, see [`CODEOWNERS` syntax](/user/project/codeowners/reference/) and [advanced `CODEOWNERS` configuration](/user/project/codeowners/advanced/).

### Allowed to push and merge to a protected branch

Users who are **Allowed to push and merge** can choose to create a merge request
for their changes, or push the changes directly to a branch. If the user
skips the merge request process, the protected branch features
and Code Owner approvals built into merge requests are also skipped.

This permission is often granted to accounts associated with
automation ([internal users](/administration/internal_users/))
and release tooling.

All changes from users without the **Allowed to push** permission must be routed through a merge request.

## View Code Owners of a file or directory

To view the Code Owners of a file or directory:

1. In the top bar, select **Search or go to** and find your project.
2. In the left sidebar, select **Code** > **Repository**.
3. Go to the file or directory you want to see the Code Owners for.
4. Optional. Select a branch or tag.

GitLab shows the Code Owners at the top of the page.

## Set up Code Owners

Prerequisites:

* You must have permissions to push to the default branch or to create a merge request.

1. Create a `CODEOWNERS` file in your [preferred location](/user/project/codeowners/#codeowners-file).
2. Define some rules in the file following the [`CODEOWNERS` syntax](/user/project/codeowners/reference/).
   Some suggestions:
   * Configure the [**All eligible users**](/user/project/merge_requests/approvals/rules/#code-owners-as-approvers) approval rule.
   * [Require code owner approval](/user/project/repository/branches/protected/#require-code-owner-approval) on a protected branch.
3. Commit your changes, and push them up to GitLab.

## `CODEOWNERS` file

The `CODEOWNERS` file defines who is responsible for code in a GitLab project.
Its purpose is to:

* Define Code Owners for specific files and directories.
* Enforce approval requirements for protected branches.
* Communicate code ownership in a project.

This file determines who should review and approve changes and ensures the right
experts are involved in code changes.

Each repository uses a single `CODEOWNERS` file. GitLab checks these locations
in your repository in this order. The first `CODEOWNERS` file found is used, and
all others are ignored:

1. In the root directory: `./CODEOWNERS`.
2. In the `docs` directory: `./docs/CODEOWNERS`.
3. In the `.gitlab` directory: `./.gitlab/CODEOWNERS`.

For more information, see [`CODEOWNERS` syntax](/user/project/codeowners/reference/) and [advanced `CODEOWNERS` configuration](/user/project/codeowners/advanced/).

## Related topics

* [`CODEOWNERS` syntax](/user/project/codeowners/reference/)
* [Advanced `CODEOWNERS` configuration](/user/project/codeowners/advanced/)
* [Troubleshooting Code Owners](/user/project/codeowners/troubleshooting/)
* [Protect your repository](/user/project/repository/protect/)
* [Protected branches](/user/project/repository/branches/protected/)
