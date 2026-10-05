# Selective synchronization

/

---

# Selective synchronization

* Tier: Premium, Ultimate
* Offering: GitLab Self-Managed

Geo supports selective synchronization, which allows administrators to choose
which projects should be synchronized by secondary sites.
A subset of projects can be chosen, either by group or by storage shard. The
former is ideal for reducing transfer and storage costs by replicating data
belonging to only a subset of users. The latter is more suited to progressively
rolling out Geo to a large GitLab instance.

Geo’s synchronization logic is outlined in the [documentation](/administration/geo/). Both the solution and the documentation are subject to change from time to time. You must independently determine your legal obligations in regard to privacy and cybersecurity laws, and applicable trade control law on an ongoing basis.

Selective synchronization:

1. Does not restrict permissions from secondary sites.
2. Does not prevent users from viewing, interacting with, cloning, and pushing to project repositories that are not included in the selective sync.
   * For more details, see [Geo proxying for secondary sites](/administration/geo/secondary_proxy/).
3. Does not hide project metadata from secondary sites.
   * Because Geo relies on PostgreSQL replication, all project metadata
     gets replicated to secondary sites, but repositories that have not been
     selected will not exist on the secondary site.
4. Does not reduce the number of events generated for the Geo event log.
   * The primary site generates events as long as any secondary sites are present.
     Selective synchronization restrictions are implemented on the secondary sites,
     not the primary site.

## Enable selective synchronization

By default, selective synchronization is disabled. To enable it:

1. In the upper-right corner, select **Admin**.
2. In the left sidebar, select **Geo** > **Sites**.
3. Next to the secondary site you want to edit, select the pencil icon.
4. From the **Selective synchronization** dropdown list, select **Projects in certain groups** or **Projects in certain storage shards**.
5. Depending on your selection, configure **Groups to synchronize** or **Shards to synchronize**.
6. Select **Save changes**.

## Promoting a secondary site with selective synchronization enabled

Promoting a secondary site with selective synchronization enabled to become the primary site
results in permanent data loss for all data that was not replicated to that secondary site.

When selective synchronization is configured on a secondary site, only a subset of data is replicated:

* If synchronizing by **groups**: Only projects in the selected groups are replicated.
* If synchronizing by **storage shards**: Only projects on the selected shards are replicated.
* If synchronizing by **organizations**: Only projects in the selected organizations are replicated.

All other data remains only on the original primary site. If you promote a secondary site with
selective synchronization to become the new primary:

* Data that was not selected for replication becomes permanently inaccessible.
* Users lose access to projects, repositories, and associated data that were excluded from selective sync.
* This data cannot be recovered unless you still have access to the original primary site.

There is no validation or warning in the promotion process to prevent this scenario.

### Recommendations

Before promoting a secondary site with selective synchronization:

1. **Disable selective synchronization** on the secondary site you plan to promote.
2. **Wait for full replication** to complete. Monitor the Geo dashboard to ensure all data types
   show 100% synchronization.
3. **Verify replication** is complete before proceeding with the promotion.
4. Only then proceed with the [planned failover](/administration/geo/disaster_recovery/planned_failover/) process.

If you must promote a secondary with selective sync enabled (for example, in an emergency):

* Document which data will be lost.
* Ensure stakeholders understand and accept the data loss.
* Plan to restore missing data from backups or the original primary site if it becomes available.

## Git operations on unreplicated repositories

Git clone, pull, and push operations over HTTP(S) and SSH are supported for repositories that
exist on the primary site but not on secondary sites. This situation can occur
when:

* Selective synchronization does not include the project attached to the repository.
* The repository is actively being replicated but has not completed yet.
