# System notes

/

---

# System notes

* Tier: Free, Premium, Ultimate
* Offering: GitLab.com, GitLab Self-Managed, GitLab Dedicated

System notes are short descriptions that help you understand the history of events
that occur during the lifecycle of a GitLab object, such as:

* [Alerts](/operations/incident_management/alerts/).
* [Designs](/user/project/issues/design_management/).
* [Issues](/user/project/issues/).
* [Merge requests](/user/project/merge_requests/).
* [Objectives and key results](/user/okrs/) (OKRs).
* [Tasks](/user/tasks/).

GitLab logs information about events triggered by Git or the GitLab application
in system notes. System notes use the format `<Author> <action> <time ago>`.

## Show or filter system notes

By default, system notes do not display. When displayed, they are shown oldest first.
If you change the filter or sort options, your selection is remembered across sections.
For all item types except merge requests, the filtering options are:

* **Show all activity** displays both comments and history.
* **Show comments only** hides system notes.
* **Show history only** hides user comments.

Merge requests provide more granular filtering options.

### On an epic

1. In the top bar, select **Search or go to** and find your project.
2. In the left sidebar, select **Plan** > **Work items**.
3. In the filter bar, select the filter **Type**, operator **is**, and value **Epic**.
4. Identify your desired epic, and select its title.
5. Go to the **Activity** section.
6. For **Sort or filter**, select **Show all activity**.

### On an issue

1. In the top bar, select **Search or go to** and find your project.
2. In the left sidebar, select **Plan** > **Work items**, then filter by **Type** = **Issue** and select your issue.
3. Go to **Activity**.
4. For **Sort or filter**, select **Show all activity**.

### On a merge request

1. In the top bar, select **Search or go to** and find your project.
2. In the left sidebar, select **Code** > **Merge requests** and find your merge request.
3. Go to **Activity**.
4. For **Sort or filter**, select **Show all activity** to see all system notes.
   To narrow the types of system notes returned, select one or more of:

   * **Approvals**
   * **Assignees & Reviewers**
   * **Comments**
   * **Commits & branches**
   * **Edits**
   * **Labels**
   * **Lock status**
   * **Mentions**
   * **Merge request status**
   * **Tracking**

## Privacy considerations

You can see only the system notes linked to objects you can access.

For example, if someone mentions your issue 111 in an issue in their private project:

* The project members see the following note in issue 111: `Alex Garcia mentioned in agarcia/private-project#222`.
* Non-members of the project can’t see the note at all.

## Related topics

* [Notes API](/api/notes/)
