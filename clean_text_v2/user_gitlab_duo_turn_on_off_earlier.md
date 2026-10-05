# Control GitLab Duo availability for earlier GitLab versions

/

---

# Control GitLab Duo availability for earlier GitLab versions

* Tier: Premium, Ultimate
* Add-on: GitLab Duo Pro or Enterprise
* Offering: GitLab.com, GitLab Self-Managed

For GitLab Duo Pro or Enterprise, you can turn GitLab Duo on or off for a group, project, or instance.

This information applies to GitLab 18.1 and earlier. For GitLab 18.2 and later, view [the latest documentation](/user/gitlab_duo/turn_on_off/).

When GitLab Duo is turned off for a group, project, or instance:

* GitLab Duo features that access resources, like code, issues, and vulnerabilities, are not available.
* Code Suggestions is not available.
* GitLab Duo Chat is not available.

## For a group or subgroup

In 17.8 to 18.1

In GitLab 17.8 to 18.1, follow these instructions to turn GitLab Duo on or off
for a group, including its subgroups and projects.

Prerequisites:

* You must have the Owner role for the group.

To turn GitLab Duo on or off for a group or subgroup:

1. In the top bar, select **Search or go to** and find your group or subgroup.
2. Go to the settings, based on your deployment type and group level:
   * For GitLab.com top-level groups: Select **Settings** > **GitLab Duo** and select **Change configuration**.
   * For GitLab.com subgroups: Select **Settings** > **General** and expand **GitLab Duo features**.
   * For GitLab Self-Managed (all groups and subgroups): Select **Settings** > **General** and expand **GitLab Duo features**.
3. Choose an option.
4. Select **Save changes**.

In 17.7

In GitLab 17.7, follow these instructions to turn GitLab Duo on or off
for a group, including its subgroups and projects.

In GitLab 17.7:

* For GitLab.com, the GitLab Duo settings page is only available for top-level groups, not for subgroups.
* For GitLab Self-Managed, the GitLab Duo settings page is not available for groups or subgroups.

Prerequisites:

* You must have the Owner role for the group.

To turn GitLab Duo on or off for a top-level group:

1. In the top bar, select **Search or go to** and find your top-level group.
2. Select **Settings** > **GitLab Duo**.
3. Select **Change configuration**.
4. Choose an option.
5. Select **Save changes**.

In 17.4 to 17.6

In GitLab 17.4 to 17.6, follow these instructions to turn GitLab Duo on or off
for a group and its subgroups and projects.

In GitLab 17.4 to 17.6:

* For GitLab.com, the GitLab Duo settings page is only available for top-level groups, not for subgroups.
* For GitLab Self-Managed, the GitLab Duo settings page is not available for groups or subgroups.

Prerequisites:

* You must have the Owner role for the group.

To turn GitLab Duo on or off for a top-level group:

1. In the top bar, select **Search or go to** and find your top-level group.
2. Select **Settings** > **GitLab Duo**.
3. Select **Change configuration**.
4. Choose an option.
5. Select **Save changes**.

In 17.3 and earlier

In GitLab 17.3 and earlier, follow these instructions to turn GitLab Duo on or off for a group
and its subgroups and projects.

Prerequisites:

* You must have the Owner role for the group.

To turn GitLab Duo on or off for a group or subgroup:

1. In the top bar, select **Search or go to** and find your group or subgroup.
2. Select **Settings** > **General**.
3. Expand **Permissions and group features**.
4. Select or clear the **Use GitLab Duo features** checkbox.
5. Optional. Select the **Enforce for all subgroups** checkbox to cascade the setting to
   all subgroups.

   [![Cascading setting](/user/gitlab_duo/img/disable_duo_features_v17_1.png)](/user/gitlab_duo/img/disable_duo_features_v17_1.png)

## For a project

In 17.4 to 18.1

In GitLab 17.4 to 18.1, follow these instructions to turn GitLab Duo on or off for a project.

Prerequisites:

* You must have the Maintainer or Owner role for the project.

To turn GitLab Duo on or off for a project:

1. In the top bar, select **Search or go to** and find your project.
2. In the left sidebar, select **Settings** > **General**.
3. Expand **Visibility, project features, permissions**.
4. Under **GitLab Duo**, turn the toggle on or off.
5. Select **Save changes**.

In 17.3 and earlier

In GitLab 17.3 and earlier, follow these instructions to turn GitLab Duo on or off for a project.

1. Use the GitLab GraphQL API
   [`projectSettingsUpdate`](/api/graphql/reference/#mutationprojectsettingsupdate)
   mutation.
2. Set the
   [`duo_features_enabled`](/api/graphql/getting_started/#update-project-settings)
   setting to `true` or `false`.

## For an instance

* Offering: GitLab Self-Managed

In 17.7 to 18.1

In GitLab 17.7 to 18.1, follow these instructions to turn GitLab Duo on or off for an instance.

Prerequisites:

* You must be an administrator.

To turn GitLab Duo on or off for an instance:

1. In the upper-right corner, select **Admin**.
2. In the left sidebar, select **GitLab Duo**.
3. Select **Change configuration**.
4. Choose an option.
5. Select **Save changes**.

In 17.4 to 17.6

In GitLab 17.4 to 17.6, follow these instructions to turn GitLab Duo on or off for the instance.

Prerequisites:

* You must be an administrator.

To turn GitLab Duo on or off for an instance:

1. In the upper-right corner, select **Admin**.
2. In the left sidebar, select **Settings** > **General**.
3. Expand **GitLab Duo features**.
4. Choose an option.
5. Select **Save changes**.

In 17.3 and earlier

In GitLab 17.3 and earlier, follow these instructions to turn GitLab Duo on or off for an instance.

Prerequisites:

* You must be an administrator.

To turn GitLab Duo on or off for an instance:

1. In the left sidebar, at the bottom, select **Admin area**.
2. Select **Settings** > **General**.
3. Expand **AI-powered features**.
4. Select or clear the **Use Duo features** checkbox.
5. Optional. Select the **Enforce for all subgroups** checkbox to cascade
   the setting to all groups in the instance.
