# Contribute to the GitLab documentation

/

---

# Contribute to the GitLab documentation

The GitLab documentation is the single source of truth (SSoT)
for information about how to configure, use, and troubleshoot GitLab.
Everyone is welcome to contribute to the GitLab documentation.

The following instructions are for community contributors.

## Update the documentation

Prerequisites:

* [Start your contributor onboarding](https://contributors.gitlab.com/start) to get access
  to the community forks.
  The community fork is a shared copy of the main GitLab repository.
  When you make the request, you’ll be asked to answer a few questions. Let them know
  that you’re interested in contributing to the GitLab documentation.

To update the documentation:

1. In the GitLab community fork, go to the [`/doc` directory](https://gitlab.com/gitlab-community/gitlab-org/gitlab/-/tree/master/doc).
2. Find the documentation page you want to update. If you’re not sure where the page is,
   look at the URL of the page on <https://docs.gitlab.com>.
   The path is listed there.

   Alternatively, if you are already on the documentation page you would like to update, scroll to the bottom and on the footer, select **View page source**. This link takes you directly to the source file.
3. In the upper right, select **Edit** > **Edit single file**.
4. Make your updates.
5. When you’re done, in the **Commit message** text box, enter a commit message.
   Use 3-5 words, start the first word with a capital letter, and do not end the phrase with a period.
6. Select **Commit changes**.
7. A new merge request opens.
8. On the **New merge request** page, select the **Documentation** template and select **Apply template**.
9. In the description, write a brief summary of the changes and link to the related issue, if there is one.
10. Select **Create merge request**.

After your merge request is created, look for a message from **GitLab Bot**. This message has instructions for what to do when you’re ready for review.

## What to work on

You don’t need an issue to update the documentation, but if you’re looking for open issues to work on,
[review the list of documentation issues curated specifically for new contributors](https://gitlab.com/gitlab-org/gitlab/-/issues/?sort=created_date&state=opened&label_name%5B%5D=documentation&label_name%5B%5D=docs-only&label_name%5B%5D=quick%20win&first_page_size=20).

When you find an issue you’d like to work on:

* If the issue is already assigned to someone, pick a different one.
* If the issue is unassigned, review the issue description for instructions on how to contribute. Some issues can be worked on by multiple contributors, and you don’t need to be assigned to the issue to work on it.
  Otherwise, add a comment (mention the author) and ask to work on the issue.

You can try installing and running the [Vale linting tool](/development/documentation/testing/vale/)
and fixing the resulting issues.

### Translated documentation

To make GitLab documentation easier to use around the world, we plan to have product documentation
translated and published in other languages.

The [file structure](/development/documentation/site_architecture/#documentation-in-other-languages)
and initial translations have been created, but this project is not complete.

After the official public release of the translated documentation, we will share details
on how to help us improve our translations. But while this work is in progress,
we cannot accept contributions to any translations of product documentation.

Additionally, only localization team members can change localization-related files.

## Ask for help

Ask for help from the Technical Writing team if you:

* Need help to choose the correct place for documentation.
* Want to discuss a documentation idea or outline.
* Want to request any other help.

To identify someone who can help you:

1. Locate the Technical Writer for the relevant
   [DevOps stage group](https://handbook.gitlab.com/handbook/product/ux/technical-writing/#assignments).
2. Either:
   * If urgent help is required, directly assign the Technical Writer in the issue or in the merge request.
   * If non-urgent help is required, ping the Technical Writer in the issue or merge request.

If you are a member of the GitLab Slack workspace, you can request help in the `#docs` channel.

## Edit a document from your own fork

If you already have your own fork of the GitLab repository, you can use it,
rather than using the GitLab community fork.

1. On <https://docs.gitlab.com>, scroll to the bottom of the page you want to edit.
2. Select **View page source**.
3. In the upper-right corner, select **Edit** > **Edit single file**.
4. Make your updates.
5. When you’re done, in the **Commit message** text box, enter a commit message.
   Use 3-5 words, start the first word with a capital letter, and do not end the phrase with a period.
6. Select **Commit changes**.
7. Note the name of your branch and then select **Commit changes**.

The changes were added to GitLab in your forked repository, in a branch with the name noted in the last step.

Now, create a merge request. This merge request is how the changes from your branch
are merged into the GitLab `master` branch.

1. In the left sidebar, select **Code** > **Merge requests**.
2. Select **New merge request**.
3. For the source branch, select your fork and branch.
4. For the target branch, select the [GitLab repository](https://gitlab.com/gitlab-org/gitlab) `master` branch.
5. Select **Compare branches and continue**. A new merge request opens.
6. On the **New merge request** page, select the **Documentation** template and select **Apply template**.
7. In the description, write a brief summary of the changes and link to the related issue, if there is one.
8. Select **Create merge request**.

After your merge request is created, look for a message from **GitLab Bot**. This message has instructions for what to do when you’re ready for review.
