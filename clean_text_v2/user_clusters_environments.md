# Cluster Environments (deprecated)

/

---

# Cluster Environments (deprecated)

* Tier: Premium, Ultimate
* Offering: GitLab.com, GitLab Self-Managed, GitLab Dedicated

This feature is not available by default on GitLab Self-Managed. To make it available, an administrator can [enable the feature flag](/administration/feature_flags/) named `certificate_based_clusters`.

Cluster environments provide a consolidated view of which CI [environments](/ci/environments/) are
deployed to the Kubernetes cluster. This view:

* Shows the project and the relevant environment related to the deployment.
* Displays the status of the pods for that environment.

With cluster environments, you can gain insight into:

* Which projects are deployed to the cluster.
* How many pods are in use for each project’s environment.
* The CI job that was used to deploy to that environment.

[![The cluster environments page showing a list of projects, their environments, and pod status.](/user/clusters/img/cluster_environments_table_v12_3.png)](/user/clusters/img/cluster_environments_table_v12_3.png)

Access to cluster environments is restricted to
[group maintainers and owners](/user/permissions/#group-permissions).

## Usage

To:

* Track environments for the cluster, you must
  [deploy to a Kubernetes cluster](/user/project/clusters/deploy_to_cluster/)
  successfully.
* Show pod usage correctly, you must
  [enable deploy boards](/user/project/deploy_boards/#enabling-deploy-boards).

After you have successful deployments to your group-level or instance-level cluster:

1. Go to your group’s **Kubernetes** page.
2. Select the **Environments** tab.

Only successful deployments to the cluster are included in this page.
Non-cluster environments aren’t included.
