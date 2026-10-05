# Runner fleet dashboard for groups

/

---

# Runner fleet dashboard for groups

* Tier: Ultimate
* Offering: GitLab.com, GitLab Self-Managed
* Status: Beta

History

* [Introduced](https://gitlab.com/gitlab-org/gitlab/-/merge_requests/151640) as a [beta](/policy/development_stages_support/#beta) in GitLab 17.0 [with a feature flag](/administration/feature_flags/) named `runners_dashboard_for_groups`. Disabled by default.
* Feature flag `runners_dashboard_for_groups` [removed](https://gitlab.com/gitlab-org/gitlab/-/issues/459052) in GitLab 17.2.

Users with the Maintainer or Owner role for a group can use the runner fleet dashboard to assess the health of group runners.

[![Runner fleet dashboard for groups](/ci/runners/img/runner_fleet_dashboard_groups_v17_1.png)](/ci/runners/img/runner_fleet_dashboard_groups_v17_1.png)

## Dashboard metrics

The following metrics are available in the runner fleet dashboard:

| Metric | Description |
| --- | --- |
| Online | Number of online runners. In the **Admin** area, this metric displays the number of runners for the entire instance. In a group, this metric displays the number of runners for the group and its subgroups. |
| Offline | Number of offline runners. |
| Active runners | Number of active runners. |
| Runner usage (previous month)[1](#fn:1) | Number of compute minutes used by each project on group runners. Includes the option to export as CSV for cost analysis. |
| Wait time to pick a job[1](#fn:1) | Displays the mean wait time for runners. This metric provides insights into whether the runners are capable of servicing the CI/CD job queue in your organization’s target service-level objectives. The data that creates this metric widget is updated every 24 hours. |

## View the runner fleet dashboard for groups

Prerequisites:

* You must have the Maintainer role for the group.
* For GitLab Self-Managed, to view the **Runner usage** and **Wait time to pick a job** metrics,
  configure the [ClickHouse integration](/integration/clickhouse/).

To view the runner fleet dashboard for groups:

1. In the top bar, select **Search or go to** and find your group.
2. In the left sidebar, select **Build** > **Runners**.
3. Select **Fleet dashboard**.

---

1. For GitLab Self-Managed, to view the **Runner usage** and **Wait time to pick a job** metrics,
   you must configure the [ClickHouse integration](/integration/clickhouse/). [↩︎](#fnref:1) [↩︎](#fnref1:1)
