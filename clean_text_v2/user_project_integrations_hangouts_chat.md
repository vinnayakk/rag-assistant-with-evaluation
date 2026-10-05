# Google Chat

/

---

# Google Chat

* Tier: Free, Premium, Ultimate
* Offering: GitLab.com, GitLab Self-Managed, GitLab Dedicated

You can configure your project in GitLab to send notifications to a
space of your choice in [Google Chat](https://chat.google.com/).

Threaded notifications are turned on by default
in Google Chat for the same GitLab object (for example, an issue or merge request).
For more information, see [issue 438452](https://gitlab.com/gitlab-org/gitlab/-/issues/438452).

## Configure the integration

### In Google Chat

To configure the integration in Google Chat:

1. Go to the space where you want to receive notifications from GitLab.
2. In the upper left, next to the space name, select the down arrow ( ) > **Apps & integrations**.
3. In the **Webhooks** section, select **Add webhooks**.
4. On the **Incoming webhooks** dialog:
   * In **Name**, enter a name for your webhook (for example, `GitLab integration`).
   * Optional. In **Avatar URL**, enter an avatar for your bot.
5. Select **Save**.
6. Next to the webhook URL, select the vertical ellipsis ( ) > **Copy link**.

For more information about webhooks, see the
[Google Chat documentation](https://developers.google.com/workspace/chat/quickstart/webhooks).

### In GitLab

To configure the integration in GitLab:

1. In the top bar, select **Search or go to** and find your project.
2. In the left sidebar, select **Settings** > **Integrations**.
3. Select **Google Chat**.
4. Under **Enable integration**, select the **Active** checkbox.
5. In **Webhook**, [paste the URL you copied from Google Chat](/user/project/integrations/hangouts_chat/#in-google-chat).
6. In the **Trigger** section, select the checkbox for each GitLab event
   you want to receive notifications for in your Google Chat space.
7. Optional. In the **Notification settings** section:
   * Select the **Notify only broken pipelines** checkbox
     to receive notifications for failed pipelines only.
   * Select the **Notify only when status changes** checkbox
     to receive notifications only when the pipeline status for the ref changes.
   * From the **Branches for which notifications are to be sent** dropdown list,
     select the branches you want to receive notifications for.
8. Optional. Select **Test settings**.
9. Select **Save changes**.
